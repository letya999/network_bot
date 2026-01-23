import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, TypeHandler, ConversationHandler, CallbackQueryHandler
from app.core.config import settings
from app.bot.handlers import (
    start, handle_voice, handle_contact, list_contacts, find_contact, export_contacts, handle_text_message,
    show_prompt, start_edit_prompt, save_prompt, cancel_prompt_edit, reset_prompt, WAITING_FOR_PROMPT,
    generate_card_callback
)
from app.bot.profile_handlers import (
    show_profile, handle_edit_callback, save_profile_value, cancel_edit, 
    SELECT_FIELD, INPUT_VALUE, send_card, share_card
)

logger = logging.getLogger(__name__)

async def post_init(application):
    """
    Post initialization hook to set bot commands.
    """
    bot = application.bot
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("profile", "Мой профиль"),
        BotCommand("card", "Моя визитка"),
        BotCommand("share", "Поделиться профилем"),
        BotCommand("list", "Показать список контактов"),
        BotCommand("find", "Найти контакт"),
        BotCommand("export", "Экспорт контактов в CSV"),
        BotCommand("prompt", "Показать текущий промпт"),
        BotCommand("edit_prompt", "Изменить промпт"),
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
    app.add_handler(CommandHandler("prompt", show_prompt))
    app.add_handler(CommandHandler("reset_prompt", reset_prompt))
    
    prompt_conv = ConversationHandler(
        entry_points=[CommandHandler("edit_prompt", start_edit_prompt)],
        states={
            WAITING_FOR_PROMPT: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_prompt)],
        },
        fallbacks=[CommandHandler("cancel", cancel_prompt_edit)]
    )
    app.add_handler(prompt_conv)

    profile_conv = ConversationHandler(
        entry_points=[CommandHandler("profile", show_profile)],
        states={
            SELECT_FIELD: [CallbackQueryHandler(handle_edit_callback)],
            INPUT_VALUE: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_profile_value)]
        },
        fallbacks=[CommandHandler("cancel", cancel_edit)]
    )
    app.add_handler(profile_conv)
    
    app.add_handler(CommandHandler("card", send_card))
    app.add_handler(CommandHandler("share", share_card))
    
    # Callback for finding contacts card generation
    app.add_handler(CallbackQueryHandler(generate_card_callback, pattern="^gen_card_"))
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))
    
    return app
