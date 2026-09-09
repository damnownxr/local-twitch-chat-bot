"""Local-only settings panel. No new dependencies; Python 3.10+."""
import argparse
import copy
import hashlib
import json
import os
import secrets
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import bot

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()


def read_document(name):
    raw = (ROOT / name).read_bytes()
    return json.loads(raw.decode('utf-8-sig')), hashlib.sha256(raw).hexdigest()


def atomic_json(name, data):
    fd, temp = tempfile.mkstemp(prefix='.panel-', suffix='.tmp', dir=ROOT)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, ROOT / name)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def terms_ok(items):
    if not isinstance(items, list) or len(items) > 2000:
        raise ValueError('Нужен список не более 2000 записей.')
    if not all(isinstance(x, str) and 1 <= len(x.strip()) <= 100 and '\n' not in x and '\r' not in x for x in items):
        raise ValueError('Каждая запись: 1–100 символов, одна строка.')
    return list(dict.fromkeys(x.strip() for x in items))


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError('Некорректные настройки.')
    c = copy.deepcopy(data)
    if not isinstance(c.get('channel'), str):
        raise ValueError('Логин канала должен быть строкой.')
    if not isinstance(c.get('moderation'), dict) or not isinstance(c.get('timer'), dict):
        raise ValueError('Не найдены настройки фильтра или таймера.')
    for key in ['blocked_words', 'blocked_phrases', 'blocked_substrings']:
        c['moderation'][key] = terms_ok(c['moderation'].get(key, []))
    # The placeholder is allowed while configuring; the bot itself rejects it.
    return bot.validate_config(c, allow_placeholder=True)


def validate_dictionary(data):
    if not isinstance(data, dict) or not isinstance(data.get('languages'), dict):
        raise ValueError('Некорректный словарь.')
    if len(data['languages']) > 40:
        raise ValueError('Не более 40 языковых разделов.')
    result = {'description': str(data.get('description', ''))[:1000], 'languages': {}}
    total = 0
    for lang, group in data['languages'].items():
        if not isinstance(lang, str) or not lang.isascii() or not lang.replace('-', '').isalnum() or len(lang) > 15 or not isinstance(group, dict):
            raise ValueError('Некорректный языковой раздел.')
        result['languages'][lang] = {k: terms_ok(group.get(k, [])) for k in ['words', 'phrases']}
        total += sum(len(v) for v in result['languages'][lang].values())
    if total > 5000:
        raise ValueError('В словаре допускается не более 5000 записей.')
    return result


def create_server(port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No request bodies, message contents or credentials in logs.

        def headers_safe(self):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'nonce-" + token + "'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

        def reply(self, code, obj):
            raw = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(code)
            self.headers_safe()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def allowed_host(self):
            actual_port = self.server.server_address[1]
            allowed = {f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'}
            if self.headers.get('Host') not in allowed:
                self.reply(403, {'error': 'Разрешён только локальный адрес панели.'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + h for h in allowed}:
                self.reply(403, {'error': 'Запрос с другого сайта запрещён.'})
                return False
            return True

        def authorized(self):
            if not secrets.compare_digest(self.headers.get('X-Panel-Token', ''), token):
                self.reply(403, {'error': 'Сессия устарела. Обновите страницу.'})
                return False
            return True

        def do_GET(self):
            if not self.allowed_host():
                return
            path = urlparse(self.path).path
            if path == '/':
                raw = (ROOT / 'panel.html').read_text(encoding='utf-8').replace('__PANEL_TOKEN__', token).encode('utf-8')
                self.send_response(200)
                self.headers_safe()
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path != '/api/state':
                self.reply(404, {'error': 'Не найдено.'})
                return
            if not self.authorized():
                return
            try:
                with LOCK:
                    config, cr = read_document('config.json')
                    dictionary, dr = read_document('blocklist.json')
                self.reply(200, {'config': config, 'dictionary': dictionary, 'config_revision': cr, 'dictionary_revision': dr})
            except (OSError, ValueError):
                self.reply(500, {'error': 'Не удалось прочитать JSON. Проверьте config.json и blocklist.json.'})

        def do_POST(self):
            if not self.allowed_host() or not self.authorized():
                return
            try:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    self.reply(415, {'error': 'Требуется JSON.'})
                    return
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 500_000:
                    self.reply(413, {'error': 'Запрос слишком большой или пустой.'})
                    return
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('Некорректный запрос.')
                path = urlparse(self.path).path
                if path == '/api/test':
                    text = data.get('message')
                    if not isinstance(text, str) or not 1 <= len(text) <= 500:
                        raise ValueError('Тестовое сообщение: 1–500 символов.')
                    with LOCK:
                        config, _ = read_document('config.json')
                        rules = bot.compile_rules(config)
                    matched = bot.is_blocked(text, rules)
                    self.reply(200, {'matched': matched, 'enabled': config['moderation']['enabled'],
                                     'blocked': matched and config['moderation']['enabled']})
                    return
                names = {'/api/config': ('config.json', validate_settings), '/api/dictionary': ('blocklist.json', validate_dictionary)}
                if path not in names:
                    self.reply(404, {'error': 'Не найдено.'})
                    return
                name, validator = names[path]
                validated = validator(data.get('value'))
                with LOCK:
                    _, revision = read_document(name)
                    if data.get('revision') != revision:
                        self.reply(409, {'error': 'Файл изменён в другой вкладке или редакторе. Обновите страницу; несохранённые правки будут потеряны.'})
                        return
                    atomic_json(name, validated)
                    saved, revision = read_document(name)
                self.reply(200, {'value': saved, 'revision': revision})
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                self.reply(400, {'error': str(exc) or 'Некорректные данные.'})
            except OSError:
                self.reply(500, {'error': 'Не удалось сохранить файл. Проверьте доступ к папке.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='Веб-панель Twitch-бота — только на этом компьютере')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = create_server(args.port)
    except OSError:
        raise SystemExit('Порт занят. Закройте другую панель или используйте --port 8766.')
    url = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'Панель настроек: {url}\nБот запускается отдельно: python bot.py\nОстановка панели: Ctrl+C')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
