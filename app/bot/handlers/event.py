import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def set_event_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /event command. Sets the current event name for context.
    Usage: /event Web Summit 2024
    """
    user = update.effective_user
    args = context.args
    
    if not args:
        # Toggle off if no args
        if context.user_data.get("current_event"):
            old_event = context.user_data.pop("current_event")
            await update.message.reply_text(f"🛑 Режим мероприятия '{old_event}' выключен.")
        else:
            await update.message.reply_text(
                "📍 Режим мероприятия позволяет автоматически добавлять событие ко всем новым контактам.\n\n"
                "Использование: /event Название события\n"
                "Пример: `/event TechCrunch 2024`"
            )
        return

    event_name = " ".join(args)
    context.user_data["current_event"] = event_name
    
    await update.message.reply_text(
        f"📍 Режим мероприятия включен: *{event_name}*\n\n"
        "Теперь это событие будет автоматически привязываться к новым контактам.\n"
        "Отправь /event без параметров, чтобы выключить.",
        parse_mode="Markdown"
    )
