#!/bin/bash
# Запуск бота @schrot47_bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Загружаем переменные из .env если есть
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Активируем виртуальное окружение
source venv/bin/activate

echo "🤖 Запускаем @schrot47_bot..."
python3 bot.py
