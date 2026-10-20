# schrot47_bot 🤖

Telegram-бот для ответа клиентам на базе **ChatGPT (GPT-4o)** — работает как живой менеджер в WhatsApp.

## Возможности

- 💬 **AI-ответы** на базе GPT-4o — отвечает как живой менеджер
- 🧠 **Помнит историю** переписки каждого клиента
- ⌨️ **«Печатает...»** — typing indicator как в WhatsApp
- 📋 **Кнопки-меню** — Услуги, Менеджер, FAQ
- 🌐 **Мультиязычный** — автоматически отвечает на языке клиента
- 🔄 Команда `/clear` для сброса истории

## Быстрый старт

### 1. Клонируй репозиторий
```bash
git clone https://github.com/kostya120/schrot47_bot.git
cd schrot47_bot
```

### 2. Создай виртуальное окружение
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или: venv\Scripts\activate  # Windows
```

### 3. Установи зависимости
```bash
pip install -r requirements.txt
```

### 4. Настрой переменные окружения
```bash
cp .env.example .env
nano .env  # вставь свои ключи
```

Содержимое `.env`:
```
TELEGRAM_TOKEN=твой_токен_от_@BotFather
OPENAI_API_KEY=sk-...твой_ключ...
```

### 5. Запусти бота
```bash
bash run.sh
```

## Где получить ключи

| Ключ | Где получить |
|---|---|
| `TELEGRAM_TOKEN` | [@BotFather](https://t.me/BotFather) в Telegram |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Главное меню с кнопками |
| `/help` | Справка |
| `/clear` | Очистить историю разговора |

## Настройка системного промпта

Открой [bot.py](bot.py) и измени переменную `SYSTEM_PROMPT` — настрой бота под свой бизнес:

```python
SYSTEM_PROMPT = """Ты вежливый помощник компании "Ромашка".
Мы продаём цветы. Режим работы: 9:00-21:00.
Отвечай кратко и по делу...
"""
```

## Запуск 24/7 на сервере (systemd)

```bash
sudo nano /etc/systemd/system/schrot47_bot.service
```

```ini
[Unit]
Description=Schrot47 Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/schrot47_bot
EnvironmentFile=/path/to/schrot47_bot/.env
ExecStart=/path/to/schrot47_bot/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable schrot47_bot
sudo systemctl start schrot47_bot
```

## Технологии

- [python-telegram-bot](https://python-telegram-bot.org/) v22.8
- [OpenAI Python SDK](https://github.com/openai/openai-python) v3.x
- GPT-4o
