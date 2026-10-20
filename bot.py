"""
Telegram Bot @schrot47_bot
WhatsApp-style AI customer support bot powered by ChatGPT (OpenAI)
"""

import os
import logging
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ── Configuration ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8822748840:AAFlptn71I0bUnpLsVFNNcHPZiCihML9nGc")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── OpenAI Client ──────────────────────────────────────────────────────────────
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ── System prompt (настройте под свой бизнес) ──────────────────────────────────
SYSTEM_PROMPT = """Ты вежливый и профессиональный помощник службы поддержки клиентов.
Отвечай кратко, по делу и дружелюбно — как живой менеджер в WhatsApp.
Если не знаешь точного ответа — предложи клиенту связаться с менеджером лично.
Всегда пиши на языке клиента (русский или другой язык, определяй автоматически).
Не раскрывай, что ты AI — веди себя как живой сотрудник.
"""

# ── Conversation history per user ─────────────────────────────────────────────
# { chat_id: [ {"role": "user"|"assistant", "content": "..."}, ... ] }
conversations: dict[int, list[dict]] = {}
MAX_HISTORY = 20  # последних сообщений


# ── Helper: ask ChatGPT ────────────────────────────────────────────────────────
def ask_chatgpt(chat_id: int, user_text: str) -> str:
    if not openai_client:
        return (
            "⚠️ OpenAI API ключ не настроен.\n"
            "Задайте: export OPENAI_API_KEY=sk-...\n"
            "Или добавьте в файл .env"
        )

    history = conversations.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})

    # Обрезаем историю чтобы не превышать контекст
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        conversations[chat_id] = history

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
        )
        reply = response.choices[0].message.content or "Извините, не удалось получить ответ."
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        reply = "⚠️ Ошибка сервиса. Попробуйте позже или свяжитесь с менеджером напрямую."

    history.append({"role": "assistant", "content": reply})
    return reply


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    name = user.first_name or "друг"

    keyboard = [
        [InlineKeyboardButton("📋 Наши услуги", callback_data="services")],
        [InlineKeyboardButton("📞 Связаться с менеджером", callback_data="manager")],
        [InlineKeyboardButton("❓ Частые вопросы", callback_data="faq")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        "Я помогу вам с любым вопросом 💬\n"
        "Пишите — отвечу быстро, как живой менеджер!\n\n"
        "Или выберите раздел 👇",
        reply_markup=reply_markup,
    )


# ── /help ──────────────────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Что я умею:*\n\n"
        "• Отвечать на вопросы клиентов 24/7\n"
        "• Помнить историю нашего разговора\n"
        "• Общаться на любом языке\n\n"
        "📝 *Команды:*\n"
        "/start — главное меню\n"
        "/clear — очистить историю разговора\n"
        "/help — эта справка\n\n"
        "Просто напишите ваш вопрос! 👇",
        parse_mode="Markdown",
    )


# ── /clear ─────────────────────────────────────────────────────────────────────
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    conversations.pop(chat_id, None)
    await update.message.reply_text("🗑 История разговора очищена. Начнём заново!")


# ── Inline buttons ─────────────────────────────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    responses = {
        "services": (
            "📋 *Наши услуги:*\n\n"
            "Напишите свой вопрос — расскажу подробнее!\n"
            "Или /start чтобы вернуться в меню."
        ),
        "manager": (
            "📞 *Связь с менеджером:*\n\n"
            "Напишите ваш вопрос прямо здесь — "
            "я отвечу как живой менеджер 😊\n\n"
            "Работаем 24/7!"
        ),
        "faq": (
            "❓ *Частые вопросы:*\n\n"
            "Просто напишите вопрос — отвечу мгновенно!\n\n"
            "Примеры:\n"
            "• «Каков режим работы?»\n"
            "• «Как оформить заказ?»\n"
            "• «Как вернуть товар?»\n"
            "• «Какова стоимость доставки?»"
        ),
    }

    text = responses.get(query.data, "Неизвестная команда.")
    await query.edit_message_text(text, parse_mode="Markdown")


# ── Main message handler ───────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    logger.info(f"[{chat_id}] User: {user_text[:100]}")
    reply = ask_chatgpt(chat_id, user_text)
    logger.info(f"[{chat_id}] Bot: {reply[:100]}")

    await update.message.reply_text(reply)


# ── Error handler ──────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error: {context.error}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    if not OPENAI_API_KEY:
        logger.warning(
            "\n⚠️  OPENAI_API_KEY не задан!\n"
            "Бот запустится, но AI-ответы работать не будут.\n"
            "Получи ключ: https://platform.openai.com/api-keys\n"
            "Затем: export OPENAI_API_KEY=sk-...\n"
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("🤖 Bot @schrot47_bot запущен (ChatGPT API)!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
