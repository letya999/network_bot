from telegram.ext import ApplicationBuilder, CommandHandler
from app.core.config import settings
from app.bot.handlers import start

def create_bot():
    if not settings.TELEGRAM_BOT_TOKEN:
       print("No TELEGRAM_BOT_TOKEN found. Bot will not start.")
       return None
       
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    return app
