import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, TypeHandler
from app.core.config import settings
from app.bot.handlers import start, handle_voice, handle_contact, list_contacts, find_contact, export_contacts

logger = logging.getLogger(__name__)

async def post_init(application):
    """
    Post initialization hook to set bot commands.
    """
    bot = application.bot
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("list", "Показать список контактов"),
        BotCommand("find", "Найти контакт"),
        BotCommand("export", "Экспорт контактов в CSV"),
    ]
    await bot.set_my_commands(commands)
    logger.info(f"Bot commands set: {commands}")

async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Log usage of the bot to console.
    """
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    log_text = f"\n--- NEW UPDATE ---\n"
    log_text += f"User: {user.first_name} (ID: {user.id}) @{user.username}\n"
    if chat:
        log_text += f"Chat: {chat.type} (ID: {chat.id})\n"
    
    if message:
        if message.text:
            log_text += f"Text: {message.text}\n"
        elif message.voice:
            log_text += f"Voice: {message.voice.file_id} ({message.voice.duration}s)\n"
        elif message.contact:
            log_text += f"Contact: {message.contact.phone_number} - {message.contact.first_name}\n"
        else:
            log_text += f"Message type: {message.chat.type}\n"
    else:
        log_text += f"Update type: {update}\n"
        
    logger.info(log_text)

def create_bot():
    if not settings.TELEGRAM_BOT_TOKEN:
       logger.error("No TELEGRAM_BOT_TOKEN found. Bot will not start.")
       return None
       
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Log all updates
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_contacts))
    app.add_handler(CommandHandler("find", find_contact))
    app.add_handler(CommandHandler("export", export_contacts))
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    return app
