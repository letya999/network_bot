
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler
from app.bot.handlers.menu_handlers import MAIN_MENU

logger = logging.getLogger(__name__)

async def start_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the introductory message for the bot.
    Replaces the default /start behavior.
    Supports deep links: /start share_<token>
    """
    user = update.effective_user

    # Handle deep links
    if context.args:
        arg = context.args[0]
        if arg.startswith("share_"):
            token = arg[6:]  # Remove "share_" prefix
            from app.bot.handlers.sharing_handlers import handle_deep_link_share
            await handle_deep_link_share(update, context, token)
            return

    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🤖 <b>Network Bot</b> — твой персональный AI-ассистент для умного нетворкинга.\n\n"
        "<b>Что я умею:</b>\n"
        "• 📇 <b>Организация:</b> Создаю контакты из голосовых, визиток и текста.\n"
        "• 🧠 <b>Память:</b> Помню контекст встреч и договоренности.\n"
        "• 🔍 <b>Поиск:</b> Нахожу людей по смыслу (например, <i>\"кто занимается AI?\"</i>).\n"
        "• ⚡ <b>Синергия:</b> Подсказываю, чем вы можете быть полезны друг другу.\n"
        "• 📁 <b>Ассеты:</b> Храню твои питчи и materials для быстрой отправки.\n\n"
        "<b>Основные команды:</b>\n"
        "/main — Главное меню\n"
        "/faq — Инструкция и настройка ключей\n"
        "/profile — Твой профиль\n\n"
        "<b>Популярные кейсы:</b>\n"
        "1️⃣ <i>Запиши голосовое после встречи</i> — я всё структурирую.\n"
        "2️⃣ <i>Спроси \"кого я знаю из финтеха?\"</i> — я найду контакты.\n"
        "3️⃣ <i>Загрузи базу LinkedIn</i> — я создам профили.\n\n"
        "Жми кнопку ниже, чтобы перейти к работе! 👇"
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 Начать работу", callback_data=MAIN_MENU)],
        [InlineKeyboardButton("📚 FAQ & Инструкция", callback_data="cmd_faq")] # We'll need to route this
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the FAQ and credentials setup info.
    """
    text = (
        "📚 <b>FAQ & Настройка Network Bot</b>\n\n"
        "<b>Как это работает?</b>\n"
        "Бот использует современные LLM (Large Language Models) для понимания естественного языка. "
        "Твои данные (контакты, заметки) хранятся в защищенной базе данных PostgreSQL.\n\n"
        "🔐 <b>Настройка API ключей (.env)</b>\n"
        "Бот требует внешние сервисы для работы. По умолчанию используются системные настройки, "
        "но ты можешь добавить свои ключи в разделе <b>⚙️ Настройки -> 🔑 API Ключи</b>.\n\n"
        "<b>Список переменных и где их взять:</b>\n"
        "🔹 <code>TELEGRAM_BOT_TOKEN</code> — Токен от @BotFather.\n"
        "🔹 <code>GEMINI_API_KEY</code> — Основной мозг бота.\n"
        "   <i>Получить: aistudio.google.com</i>\n"
        "🔹 <code>TAVILY_API_KEY</code> — Для поиска в интернете (OSINT).\n"
        "   <i>Получить: tavily.com</i>\n\n"
        "<b>Интеграции (опционально):</b>\n"
        "🔸 <code>NOTION_API_KEY</code> + <code>NOTION_DATABASE_ID</code> — Синхронизация с Notion.\n"
        "🔸 <code>GOOGLE_...</code> — Синхронизация с Google Sheets.\n\n"
        "<i>Системные переменные (Postgres, Redis) настраиваются администратором при развертывании.</i>\n\n"
        "🔗 <b>Исходный код и документация:</b>\n"
        "https://github.com/letya999/network_bot\n\n"
        "<b>Важные нюансы:</b>\n"
        "• Голосовые сообщения распознаются автоматически.\n"
        "• Карточку контакта можно редактировать вручную.\n"
        "• Поиск работает лучше, если контакты заполнены подробно."
    )
    
    # Check if triggered by callback or command
    if update.callback_query:
        await update.callback_query.answer()
        # Ensure we don't edit a message into FAQ if it's the main menu, better send new one or edit?
        # Usually FAQ is long, maybe send new.
        # But if navigating, edit is smoother.
        # Let's send new if command, edit if callback? 
        # But FAQ is informational. Let's send new to keep history if command.
        # If callback (from start info), edit.
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]]))
    else:
        await update.message.reply_text(text, parse_mode="HTML")


def register_handlers(app: Application):
    """Register info handlers."""
    app.add_handler(CommandHandler("start", start_info))
    app.add_handler(CommandHandler("faq", faq_command))
