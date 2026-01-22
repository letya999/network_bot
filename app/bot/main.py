from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from app.core.config import settings
from app.bot.handlers import start, handle_voice, handle_contact, list_contacts, find_contact, export_contacts

def create_bot():
    if not settings.TELEGRAM_BOT_TOKEN:
       print("No TELEGRAM_BOT_TOKEN found. Bot will not start.")
       return None
       
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_contacts))
    app.add_handler(CommandHandler("find", find_contact))
    app.add_handler(CommandHandler("export", export_contacts))
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    return app
