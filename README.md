# Damnowner chat bot v1

---

## RU

### Что это за бот?

**Damnowner chat bot** — это локальный Twitch chat bot с веб-панелью.

Он умеет:
- удалять сообщения с запрещёнными словами;
- удалять сообщения с запрещёнными фразами;
- учитывать свои списки слов и фраз;
- использовать встроенный словарь на нескольких языках;
- распознавать часть обходов написания вроде `n1g@`, `n.i.g.g.a` и похожих вариантов;
- отправлять свою фразу в чат по таймеру;
- настраиваться через **веб-панель**.

### Если не хочешь настраивать сам

Если тебе лень запускать всё локально, есть готовый сайт:

**https://damnownbot-twitch-damnownxr.amvera.io/**

Там можно подключить облачную версию через сайт.

**Важно:** сайт пока только **на русском языке**.

---

## Как работает эта версия?

Это **локальная версия**.

Это значит:
- бот работает у тебя на компьютере или сервере;
- для работы бот должен быть **запущен**;
- если бот выключен — он ничего не модерирует и не пишет в чат;
- веб-панель тоже запускается локально.

---

## Что такое веб-панель?

Веб-панель нужна для удобной настройки бота через браузер.

Через неё можно:
- указать Twitch-канал;
- включить или выключить таймер;
- написать фразу для таймера;
- указать интервал;
- включить или выключить фильтр;
- добавить свои слова, фразы и подстроки;
- редактировать встроенный словарь;
- проверить тестовое сообщение без отправки в Twitch.

### Важно

**Веб-панель и бот — это не одно и то же.**

Нужно запускать:
- `panel.py` — это веб-панель;
- `bot.py` — это сам бот.

**Если открыть `panel.html` двойным кликом, ничего нормально не заработает.**
Нужно запускать именно `panel.py`.

---

## Быстрый запуск

### Windows

Открой PowerShell в папке проекта и выполни:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux / macOS

Открой терминал в папке проекта и выполни:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

---

## Как открыть веб-панель?

### Windows

```powershell
.venv\Scripts\python.exe panel.py
```

### Linux / macOS

```bash
.venv/bin/python panel.py
```

После этого открой в браузере:

```text
http://127.0.0.1:8765
```

Если браузер не открылся сам — просто вставь этот адрес вручную.

### Что делать дальше в панели?

1. Укажи логин своего Twitch-канала
2. Напиши фразу для таймера
3. Укажи интервал
4. Включи или выключи фильтр
5. Добавь свои слова или фразы
6. Нажми **Save settings / Сохранить настройки**
7. Если менял встроенный словарь — нажми **Save dictionary / Сохранить словарь**

---

## Что нужно для работы самого бота?

Перед запуском бота нужен Twitch application и авторизация Twitch-аккаунта бота.

### Нужно подготовить

1. **Отдельный Twitch-аккаунт для бота**
2. Выдать ему модератора в своём канале:

```text
/mod логин_бота
```

3. Создать Twitch application:

https://dev.twitch.tv/console/apps

### Как создать Twitch application?

При создании укажи:
- **Name** — любое название;
- **OAuth Redirect URL** — строго:
  ```text
  http://localhost:3000
  ```
- **Category** — `Chat Bot`;
- если спрашивает тип клиента — выбирай **Confidential**.

Потом получишь:
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

---

## Как заполнить `.env`?

Открой файл `.env` и вставь туда:

```dotenv
TWITCH_CLIENT_ID=твой_client_id
TWITCH_CLIENT_SECRET=твой_client_secret
```

---

## Как настроить `config.json`?

Открой `config.json`.

Пример:

```json
{
  "channel": "your_channel",
  "moderation": {
    "enabled": true,
    "ignore_moderators": false,
    "use_builtin_dictionary": true,
    "anti_obfuscation": true,
    "blocked_words": ["word1", "word2"],
    "blocked_phrases": ["bad phrase", "another phrase"],
    "blocked_substrings": []
  },
  "timer": {
    "enabled": true,
    "interval_minutes": 60,
    "message": "Здесь напиши свою фразу!"
  }
}
```

### Главное

- `channel` — логин твоего Twitch-канала, **не ссылка**;
- `blocked_words` — отдельные слова;
- `blocked_phrases` — фразы;
- `blocked_substrings` — совпадения внутри слов;
- `timer.enabled` — включён ли таймер;
- `timer.interval_minutes` — интервал;
- `timer.message` — сообщение по таймеру.

---

## Как авторизовать аккаунт бота?

### Windows

```powershell
.venv\Scripts\python.exe bot.py --auth
```

### Linux / macOS

```bash
.venv/bin/python bot.py --auth
```

После этого:
- откроется браузер;
- войди **именно в Twitch-аккаунт бота**;
- разреши доступ.

**Не входи тут под своим основным аккаунтом стримера**, если бот должен работать с отдельного аккаунта.

После авторизации появится файл:

```text
.tokens.json
```

---

## Как включить самого бота?

### Windows

```powershell
.venv\Scripts\python.exe bot.py
```

### Linux / macOS

```bash
.venv/bin/python bot.py
```

После этого бот начнёт:
- подключаться к чату;
- удалять запрещённые сообщения;
- отправлять таймерную фразу.

Остановка:

```text
Ctrl + C
```

---

## Как проверить, что всё работает?

### Проверка фильтра

1. Добавь безопасное тестовое слово, например:
   ```text
   тестудаления
   ```
2. Напиши его с обычного аккаунта зрителя.
3. Сообщение должно удалиться.

### Проверка таймера

1. Временно поставь:
   ```text
   1 минуту
   ```
2. Сохрани настройки.
3. Подожди полный интервал.
4. Бот должен отправить сообщение.

---

## Важные замечания

- Панель **не запускает** бота автоматически.
- Нужно отдельно держать открытыми `panel.py` и `bot.py`, если хочешь и панель, и работающего бота.
- Закрытие браузера **не останавливает** уже отдельно запущенный `bot.py`.
- Если поменял канал — лучше перезапустить `bot.py`.
- Пока бот выключен, он ничего не модерирует.
- Таймер работает независимо от того, идёт стрим или нет.
- Первое сообщение таймера приходит **через полный интервал**, а не сразу.

---

---

## EN

### What kind of bot is this?

**Damnowner chat bot** is a local Twitch chat bot with a web panel.

It can:
- delete messages with blocked words;
- delete messages with blocked phrases;
- use your own custom word lists;
- use the built-in dictionary in multiple languages;
- detect some obfuscated spellings like `n1g@` or `n.i.g.g.a`;
- send a timed message to chat;
- be configured from a **web panel**.

### If you do not want to set it up yourself

There is also a ready website:

**https://damnownbot-twitch-damnownxr.amvera.io/**

You can use the cloud version there.

**Important:** the website is currently available in **Russian only**.

---

## How this version works?

This is a **local version**.

That means:
- the bot runs on your computer or server;
- the bot must stay **running**;
- if the bot is turned off, it will not moderate chat or send messages;
- the web panel also runs locally.

---

## What the web panel is?

The web panel is used to configure the bot in a browser.

You can use it to:
- set the Twitch channel login;
- enable or disable the timer;
- set the timer message;
- set the interval;
- enable or disable filtering;
- add custom words, phrases, and substrings;
- edit the built-in dictionary;
- test a message without sending anything to Twitch.

### Important

**The web panel and the bot are separate processes.**

You need to run:
- `panel.py` — the web panel;
- `bot.py` — the actual bot.

**Do not open `panel.html` directly by double-clicking it.**
You must run `panel.py`.

---

## Quick start

### Windows

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

---

## How to open the web panel?

### Windows

```powershell
.venv\Scripts\python.exe panel.py
```

### Linux / macOS

```bash
.venv/bin/python panel.py
```

Then open this address in your browser:

```text
http://127.0.0.1:8765
```

If it does not open automatically, paste the address manually.

---

## What to do in the panel?

1. Enter your Twitch channel login
2. Add your timer message
3. Set the interval
4. Enable or disable the filter
5. Add your own blocked words or phrases
6. Click **Save settings**
7. If you changed the built-in dictionary, click **Save dictionary**

---

## What you need for the bot itself?

Before starting the bot, you need a Twitch application and authorization for the Twitch bot account.

### You need

1. A **separate Twitch account for the bot**
2. Moderator permissions in your channel:

```text
/mod bot_login
```

3. A Twitch application:

https://dev.twitch.tv/console/apps

### Twitch application settings

Use:
- **Name** — anything you want
- **OAuth Redirect URL** — exactly:
  ```text
  http://localhost:3000
  ```
- **Category** — `Chat Bot`
- if asked for client type, choose **Confidential**

Then copy:
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`

---

## How to fill `.env`?

Open `.env` and add:

```dotenv
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
```

---

## How to configure `config.json`?

Example:

```json
{
  "channel": "your_channel",
  "moderation": {
    "enabled": true,
    "ignore_moderators": false,
    "use_builtin_dictionary": true,
    "anti_obfuscation": true,
    "blocked_words": ["word1", "word2"],
    "blocked_phrases": ["bad phrase", "another phrase"],
    "blocked_substrings": []
  },
  "timer": {
    "enabled": true,
    "interval_minutes": 60,
    "message": "Type your message here"
  }
}
```

---

## How to authorize the bot account?

### Windows

```powershell
.venv\Scripts\python.exe bot.py --auth
```

### Linux / macOS

```bash
.venv/bin/python bot.py --auth
```

Then:
- the browser opens;
- log in with the **bot Twitch account**;
- allow access.

After that, the project creates:

```text
.tokens.json
```

---

## How to start the bot?

### Windows

```powershell
.venv\Scripts\python.exe bot.py
```

### Linux / macOS

```bash
.venv/bin/python bot.py
```

Stop it with:

```text
Ctrl + C
```

---

## How to test it?

### Filter test

1. Add a safe test word
2. Send it from a normal viewer account
3. The message should be deleted

### Timer test

1. Set the timer to 1 minute
2. Save settings
3. Wait one full interval
4. The bot should send the message

---
