from datetime import datetime, timedelta
import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.reminder_service import ReminderService
from app.models.reminder import ReminderStatus

logger = logging.getLogger(__name__)

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.callback_query:
        await update.callback_query.answer()

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id)
        
        reminder_service = ReminderService(session)
        reminders = await reminder_service.get_user_reminders(
            db_user.id, 
            status=ReminderStatus.PENDING
        )
        
        if not reminders:
            await update.effective_message.reply_text("Нет активных напоминаний.")
            return
            
        text = "🔔 *Активные напоминания:*\n\n"
        keyboard = []
        
        for r in reminders:
            due_str = r.due_at.strftime("%d.%m %H:%M")
            text += f"📅 *{due_str}* — {r.title}\n"
            
            # Action buttons
            keyboard.append([
                InlineKeyboardButton(f"✅ Готово: {r.title[:15]}...", callback_data=f"rem_done_{r.id}")
            ])
        
        # Add Back button
        from app.bot.handlers.menu_handlers import NETWORKING_MENU
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=NETWORKING_MENU)])

        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def reminder_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("rem_done_"):
        rem_id = data[9:]
        async with AsyncSessionLocal() as session:
            try:
                reminder_service = ReminderService(session)
                success = await reminder_service.complete_reminder(uuid.UUID(rem_id))
                
                if success:
                    await query.answer("Напоминание выполнено!")
                    # Optimistically update the message
                    # We can't easily edit just one line in a big list without fetching again
                    # So we just acknowledge.
                    # Or we edits the buttons to show "Completed"
                    await query.edit_message_reply_markup(reply_markup=None) # Remove buttons? Or refresh?
                    await query.message.reply_text("✅ Напоминание отмечено выполненным.")
                else:
                    await query.answer("Ошибка или уже выполнено.", show_alert=True)
            except Exception as e:
                logger.error(f"Error completing reminder: {e}")
                await query.answer("Ошибка", show_alert=True)
