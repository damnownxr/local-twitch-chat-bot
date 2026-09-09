"""Twitch moderation + timed messages. Python 3.10+."""
import argparse
import json
import logging
import os
import re
import secrets
import socket
import ssl
import time
import unicodedata
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / '.tokens.json'
SCOPES = ['chat:read', 'user:write:chat', 'moderator:manage:chat_messages']
LOG = logging.getLogger('twitch-bot')


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return ' '.join(text.split())


# Visual confusables and common leetspeak substitutions, not translation.
CONFUSABLES = str.maketrans({
    '0': 'o', '1': 'i', '!': 'i', '|': 'i', '3': 'e',
    '4': 'a', '@': 'a', '5': 's', '$': 's', '7': 't', '+': 't', '8': 'b',
    'а': 'a', 'е': 'e', 'ё': 'e', 'о': 'o', 'р': 'p', 'с': 'c',
    'у': 'y', 'х': 'x', 'і': 'i', 'ї': 'i', 'ј': 'j', 'ѕ': 's',
    'к': 'k', 'м': 'm', 'т': 't', 'в': 'b', 'н': 'h',
    'α': 'a', 'ο': 'o', 'ι': 'i', 'κ': 'k', 'τ': 't', 'χ': 'x',
})


def skeleton(text):
    text = normalize(text)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    # Treat !, | and + at word edges as punctuation, not extra letters.
    text = re.sub(r'(?<!\w)[!|+]|[!|+](?!\w)', ' ', text)
    return text.translate(CONFUSABLES)


class Rules:
    def __init__(self, exact, fuzzy):
        self.exact = exact
        self.fuzzy = fuzzy


def dictionary_terms(moderation):
    words, phrases = [], []
    if moderation.get('use_builtin_dictionary', False):
        data = json.loads((ROOT / 'blocklist.json').read_text(encoding='utf-8-sig'))
        groups = data['languages']
        if not isinstance(groups, dict):
            raise ValueError('blocklist.json: languages должен быть объектом')
        for group in groups.values():
            for key, target in [('words', words), ('phrases', phrases)]:
                items = group.get(key, [])
                if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                    raise ValueError('blocklist.json: words/phrases должны быть списками строк')
                target.extend(items)
    return words, phrases


def fuzzy_pattern(term):
    term = skeleton(term)
    chunks = []
    for word in term.split():
        if not word.isalnum():
            # User-entered punctuation remains literal in the exact filter.
            return None
        # Preserve required doubled letters; explicitly list shortened variants.
        # A repeat may itself contain separators, as in g.g.
        runs = []
        for match in re.finditer(r'(.)\1*', word):
            ch = re.escape(match.group(1))
            minimum = len(match.group(0)) - 1
            maximum = max(7, minimum)
            runs.append(ch + '(?:' + r'[\W_]{0,6}' + ch + '){' + str(minimum) + ',' + str(maximum) + '}')
        chunks.append(r'[\W_]{0,6}'.join(runs))
    if not chunks:
        return None
    # Keep a separator between words of a phrase to reduce false positives.
    pattern = r'[\W_]{1,8}'.join(chunks)
    return re.compile(r'(?<!\w)' + pattern + r'(?!\w)')


def compile_rules(config):
    exact, fuzzy = [], []
    moderation = config['moderation']
    words, phrases = dictionary_terms(moderation)
    words += moderation.get('blocked_words', [])
    phrases += moderation.get('blocked_phrases', [])
    for term in set(words + phrases):
        term = normalize(term)
        if term:
            exact.append(re.compile(r'(?<!\w)' + re.escape(term).replace(r'\ ', r'\s+') + r'(?!\w)'))
            if moderation.get('anti_obfuscation', False):
                rule = fuzzy_pattern(term)
                if rule:
                    fuzzy.append(rule)
    for term in moderation.get('blocked_substrings', []):
        term = normalize(term)
        if term:
            exact.append(re.compile(re.escape(term)))
    return Rules(exact, fuzzy)


def is_blocked(text, rules):
    text = normalize(text)
    if any(rule.search(text) for rule in rules.exact):
        return True
    if rules.fuzzy:
        text = skeleton(text)
        return any(rule.search(text) for rule in rules.fuzzy)
    return False


def settings_stamp():
    paths = [ROOT / 'config.json', ROOT / 'blocklist.json']
    return tuple(path.stat().st_mtime_ns if path.exists() else None for path in paths)


def read_config():
    c = json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig'))
    return validate_config(c)


def validate_config(c, allow_placeholder=False):
    channel = c['channel'].strip().lower().lstrip('#')
    if not re.fullmatch(r'[a-z0-9_]{1,25}', channel) or (channel == 'your_channel' and not allow_placeholder):
        raise ValueError('Укажите настоящий логин канала в config.json → channel')
    c['channel'] = channel
    m = c['moderation']
    if not isinstance(m.get('enabled'), bool):
        raise ValueError('moderation.enabled должен быть true/false')
    for key in ['blocked_words', 'blocked_phrases', 'blocked_substrings']:
        if not isinstance(m.get(key, []), list) or not all(isinstance(s, str) for s in m.get(key, [])):
            raise ValueError(f'{key}: нужен список строк')
    if not isinstance(m.get('ignore_moderators', False), bool):
        raise ValueError('ignore_moderators должен быть true/false')
    for key in ['use_builtin_dictionary', 'anti_obfuscation']:
        if not isinstance(m.get(key, False), bool):
            raise ValueError(f'{key} должен быть true/false')
    t = c['timer']
    if not isinstance(t['enabled'], bool):
        raise ValueError('timer.enabled должен быть true/false')
    if isinstance(t['interval_minutes'], bool) or not isinstance(t['interval_minutes'], (int, float)) or not 1 <= t['interval_minutes'] <= 525600:
        raise ValueError('Интервал должен быть от 1 до 525600 минут')
    if not isinstance(t['message'], str) or '\n' in t['message'] or '\r' in t['message'] or (not t['message'].strip() or len(t['message']) > 500):
        raise ValueError('Сообщение таймера: одна непустая строка, до 500 символов')
    return c


def save_tokens(tokens):
    temp = TOKEN_FILE.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(tokens, f)
    os.replace(temp, TOKEN_FILE)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


class Twitch:
    def __init__(self):
        self.client_id = os.environ.get('TWITCH_CLIENT_ID', '').strip()
        self.secret = os.environ.get('TWITCH_CLIENT_SECRET', '').strip()
        if not self.client_id or not self.secret:
            raise ValueError('Заполните TWITCH_CLIENT_ID и TWITCH_CLIENT_SECRET в .env')
        self.tokens = {}
        self.expires_at = 0

    def exchange(self, data):
        data.update(client_id=self.client_id, client_secret=self.secret)
        try:
            r = requests.post('https://id.twitch.tv/oauth2/token', data=data, timeout=20)
        except requests.RequestException:
            raise RuntimeError('Не удалось подключиться к OAuth Twitch') from None
        if r.status_code != 200:
            raise RuntimeError(f'OAuth Twitch: HTTP {r.status_code}. Проверьте .env или выполните --auth заново')
        result = r.json()
        if 'refresh_token' not in result and 'refresh_token' in self.tokens:
            result['refresh_token'] = self.tokens['refresh_token']
        self.tokens = result
        self.expires_at = time.monotonic() + result.get('expires_in', 3600)
        save_tokens(result)

    def refresh(self):
        if not self.tokens.get('refresh_token'):
            raise RuntimeError('Нет refresh token. Выполните python bot.py --auth')
        self.exchange({'grant_type': 'refresh_token', 'refresh_token': self.tokens['refresh_token']})

    def token(self):
        if time.monotonic() >= self.expires_at - 120:
            self.refresh()
        return self.tokens['access_token']

    def load(self):
        if not TOKEN_FILE.exists():
            raise RuntimeError('Сначала выполните python bot.py --auth')
        self.tokens = json.loads(TOKEN_FILE.read_text(encoding='utf-8'))
        self.refresh()
        return self.validate()

    def validate(self):
        try:
            r = requests.get('https://id.twitch.tv/oauth2/validate', headers={'Authorization': 'OAuth ' + self.token()}, timeout=15)
        except requests.RequestException:
            raise RuntimeError('Проверка токена Twitch: ошибка сети') from None
        if r.status_code != 200:
            raise RuntimeError(f'Проверка токена: HTTP {r.status_code}; выполните --auth заново')
        data = r.json()
        if data.get('client_id') != self.client_id or not set(SCOPES).issubset(data.get('scopes', [])):
            raise RuntimeError('Неверное приложение или недостаточно прав. Выполните --auth заново')
        return data

    def api(self, method, endpoint, *, params=None, body=None):
        for attempt in range(2):
            try:
                r = requests.request(method, 'https://api.twitch.tv/helix/' + endpoint,
                    headers={'Client-Id': self.client_id, 'Authorization': 'Bearer ' + self.token()},
                    params=params, json=body, timeout=15)
            except requests.RequestException:
                raise RuntimeError('Twitch API: ошибка сети') from None
            if r.status_code == 401 and attempt == 0:
                self.refresh()
                continue
            if not r.ok:
                # Do not print tokens, request URLs, or user message contents.
                raise RuntimeError(f'Twitch API {endpoint}: HTTP {r.status_code}')
            return r.json() if r.content else {}
        raise RuntimeError('Авторизация Twitch не удалась')


def authorize(client):
    redirect = 'http://localhost:3000'
    state = secrets.token_urlsafe(32)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if not secrets.compare_digest(q.get('state', [''])[0], state):
                self.send_error(400, 'Invalid OAuth state')
                return
            result['code'] = q.get('code', [''])[0]
            result['error'] = q.get('error', [''])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Можно закрыть вкладку и вернуться в терминал.'.encode('utf-8'))

    url = 'https://id.twitch.tv/oauth2/authorize?' + urlencode({
        'client_id': client.client_id, 'redirect_uri': redirect, 'response_type': 'code',
        'scope': ' '.join(SCOPES), 'state': state, 'force_verify': 'true'})
    with HTTPServer(('127.0.0.1', 3000), Callback) as server:
        server.timeout = 1
        print('Войдите в Twitch под аккаунтом БОТА, затем откройте:\n' + url)
        webbrowser.open(url)
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result.get('code'):
        raise RuntimeError('Авторизация отменена или истекли 5 минут')
    client.exchange({'grant_type': 'authorization_code', 'code': result['code'], 'redirect_uri': redirect})
    account = client.validate()
    print(f"Авторизован аккаунт: {account['login']}. Токены сохранены локально.")


def parse_irc(line):
    tags = {}
    if line.startswith('@'):
        raw, line = line[1:].split(' ', 1)
        tags = dict(part.split('=', 1) if '=' in part else (part, '') for part in raw.split(';'))
    prefix = ''
    if line.startswith(':'):
        prefix, line = line[1:].split(' ', 1)
    main, sep, text = line.partition(' :')
    parts = main.split()
    return tags, prefix, parts[0] if parts else '', parts[1:], text if sep else ''


def run(client):
    config = read_config()
    identity = client.load()
    bot_id, login = identity['user_id'], identity['login']
    users = client.api('GET', 'users', params={'login': config['channel']})['data']
    if not users:
        raise ValueError('Канал не найден')
    channel_id = users[0]['id']
    channel = config['channel']
    rules = compile_rules(config)
    stamp = settings_stamp()
    due = time.monotonic() + config['timer']['interval_minutes'] * 60
    validate_due = time.monotonic() + 3500
    retry = 2
    LOG.info('Бот %s → канал %s. Аккаунт бота должен быть модератором.', login, channel)

    while True:
        sock = None
        joined = False
        try:
            token = client.token()
            raw = socket.create_connection(('irc.chat.twitch.tv', 6697), timeout=15)
            try:
                sock = ssl.create_default_context().wrap_socket(raw, server_hostname='irc.chat.twitch.tv')
            except Exception:
                raw.close()
                raise
            sock.settimeout(1)

            def send(line):
                sock.sendall((line + '\r\n').encode('utf-8'))

            send('CAP REQ :twitch.tv/tags twitch.tv/commands')
            send('PASS oauth:' + token)
            send('NICK ' + login)
            send('JOIN #' + channel)
            buffer = b''
            last_rx = time.monotonic()
            while True:
                now = time.monotonic()
                if now >= validate_due:
                    client.validate()  # Twitch requires periodic validation.
                    validate_due = now + 3500
                try:
                    current_stamp = settings_stamp()
                    if current_stamp != stamp:
                        stamp = current_stamp
                        candidate = read_config()
                        if candidate['channel'] != channel:
                            LOG.warning('Для смены канала перезапустите бота. Остальные настройки применены.')
                            candidate['channel'] = channel
                        candidate_rules = compile_rules(candidate)
                        config = candidate
                        rules = candidate_rules
                        due = now + config['timer']['interval_minutes'] * 60
                        LOG.info('Настройки перечитаны; таймер отсчитывает интервал заново.')
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    LOG.warning('Новые настройки не применены: %s', exc)

                if joined and config['timer']['enabled'] and now >= due:
                    try:
                        response = client.api('POST', 'chat/messages', body={
                            'broadcaster_id': channel_id, 'sender_id': bot_id,
                            'message': config['timer']['message']})
                        info = response.get('data', [{}])[0]
                        if not info.get('is_sent'):
                            reason = (info.get('drop_reason') or {}).get('code', 'unknown')
                            raise RuntimeError('Twitch отклонил сообщение: ' + reason)
                        LOG.info('Сообщение по таймеру отправлено.')
                        due = time.monotonic() + config['timer']['interval_minutes'] * 60
                    except RuntimeError as exc:
                        LOG.warning('%s; повтор отправки не раньше чем через 60 секунд.', exc)
                        due = time.monotonic() + 60

                try:
                    chunk = sock.recv(16384)
                except socket.timeout:
                    if time.monotonic() - last_rx > 360:
                        raise ConnectionError('Нет ответа IRC более 6 минут')
                    continue
                if not chunk:
                    raise ConnectionError('IRC закрыл соединение')
                last_rx = time.monotonic()
                buffer += chunk
                if len(buffer) > 1_000_000:
                    raise ConnectionError('Слишком большой IRC буфер')
                while b'\r\n' in buffer:
                    raw_line, buffer = buffer.split(b'\r\n', 1)
                    line = raw_line.decode('utf-8', errors='replace')
                    if line.startswith('PING'):
                        send('PONG' + line[4:])
                        continue
                    tags, prefix, command, args, text = parse_irc(line)
                    if command == 'RECONNECT':
                        raise ConnectionError('Twitch запросил переподключение')
                    if command == 'ROOMSTATE' and args and args[0].lower() == '#' + channel:
                        joined = True
                        retry = 2
                        LOG.info('Подключён к чату.')
                    if command == 'NOTICE':
                        if 'authentication failed' in text.lower() or 'improperly formatted auth' in text.lower():
                            client.refresh()
                            raise ConnectionError('IRC отклонил авторизацию; токен обновлён')
                        LOG.warning('Уведомление Twitch: %s', tags.get('msg-id', 'notice'))
                    if command != 'PRIVMSG' or not config['moderation']['enabled']:
                        continue
                    if not args or args[0].lower() != '#' + channel:
                        continue
                    if tags.get('user-id') in {bot_id, channel_id}:
                        continue
                    if config['moderation'].get('ignore_moderators', False) and tags.get('mod') == '1':
                        continue
                    if is_blocked(text, rules) and tags.get('id'):
                        try:
                            client.api('DELETE', 'moderation/chat', params={
                                'broadcaster_id': channel_id, 'moderator_id': bot_id,
                                'message_id': tags['id']})
                            LOG.info('Удалено сообщение по правилу фильтра.')
                        except RuntimeError as exc:
                            LOG.warning('Не удалось удалить сообщение: %s. Проверьте права модератора.', exc)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            LOG.warning('Соединение прервано: %s. Повтор через %s сек.', exc, retry)
        finally:
            if sock:
                sock.close()
        time.sleep(retry)
        retry = min(retry * 2, 120)


def main():
    load_dotenv(ROOT / '.env')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description='Twitch: фильтр сообщений и таймер')
    parser.add_argument('--auth', action='store_true', help='Авторизация аккаунта бота')
    args = parser.parse_args()
    try:
        client = Twitch()
        authorize(client) if args.auth else run(client)
    except KeyboardInterrupt:
        print('\nБот остановлен.')
    except Exception as exc:
        LOG.error('%s', exc)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
