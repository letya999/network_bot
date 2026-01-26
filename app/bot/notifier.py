from telegram import Bot
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def send_telegram_message(telegram_id: int, text: str):
    """
    Send a message to a Telegram user independently of the main Bot loop.
    Useful for background tasks/workers.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        return

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=telegram_id, text=text)
        logger.info(f"Sent notification to {telegram_id}: {text[:20]}...")
    except Exception:
        logger.exception(f"Failed to send notification to {telegram_id}")
