
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.bot.handlers.common import format_card, get_contact_keyboard

logger = logging.getLogger(__name__)

# Callbacks
CONTACT_VIEW_PREFIX = "contact_view_"
CONTACT_EDIT_PREFIX = "contact_edit_"
CONTACT_DEL_ASK_PREFIX = "contact_del_ask_"
CONTACT_DEL_CONFIRM_PREFIX = "contact_del_confirm_"

async def view_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows full details of a contact.
    """
    query = update.callback_query
    await query.answer()
    
    contact_id = query.data.replace(CONTACT_VIEW_PREFIX, "")
    
    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(contact_id)
        
        if not contact:
            await query.edit_message_text("❌ Контакт не найден.")
            return

        # Format full card
        text = format_card(contact)
        keyboard = get_contact_keyboard(contact)
        
        # Determine if we edit or send new. 
        # Since we are "Viewing details" from "View Details" button which was on a card...
        # It's basically refreshing the card but maybe with more info if format_card hides things?
        # Actually format_card shows quite a bit.
        # But if the user was in a list view (which is text only usually), then they click "View".
        # If they are already viewing the card, this button might be redundant unless we have a "Short" vs "Full" view.
        # Assume "format_card" is the full view.
        
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown", disable_web_page_preview=True)

async def delete_contact_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Asks for confirmation to delete.
    """
    query = update.callback_query
    await query.answer()
    contact_id = query.data.replace(CONTACT_DEL_ASK_PREFIX, "")
    
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить", callback_data=f"{CONTACT_DEL_CONFIRM_PREFIX}{contact_id}"),
            InlineKeyboardButton("🔙 Отмена", callback_data=f"{CONTACT_VIEW_PREFIX}{contact_id}") 
            # Go back to view
        ]
    ]
    await query.edit_message_text("❓ Вы уверены, что хотите удалить этот контакт?", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_contact_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deletes the contact.
    """
    query = update.callback_query
    await query.answer()
    contact_id = query.data.replace(CONTACT_DEL_CONFIRM_PREFIX, "")
    
    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        success = await contact_service.delete_contact(contact_id)
        
        if success:
            await query.edit_message_text("✅ Контакт удален.")
        else:
            await query.edit_message_text("❌ Ошибка при удалении.")

async def edit_contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Starts editing a contact.
    """
    query = update.callback_query
    await query.answer()
    contact_id = query.data.replace(CONTACT_EDIT_PREFIX, "")
    
    # Store contact_id in user_data to know what we are editing
    context.user_data['editing_contact_id'] = contact_id
    
    text = (
        "✏️ **Редактирование контакта**\n\n"
        "Отправьте мне новую информацию текстом, и я обновлю этот контакт.\n"
        "Вы можете написать, например: 'Измени телефон на +123456789' или 'Добавь заметку: встретились на конференции'.\n\n"
        "Или нажмите /cancel для отмены."
    )
    
    # We might need to handle this in a ConversationHandler or checking 'editing_contact_id' in text handler.
    # For now, we'll rely on the global text handler checking 'editing_contact_id'.
    # Or cleaner: Enter a specific state if we had a ContactEdit Conversation.
    # Given the complexity, let's just use the "Smart Update" via text handler if possible, 
    # but the current text handler treats text as NEW contact or merge. 
    # To support explicit edit, we should probably set a state.
    
    await query.edit_message_text(text, parse_mode="Markdown")
    # Note: We need to ensure the main text handler respects this context.

async def cancel_contact_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels contact editing mode.
    """
    if context.user_data.get('editing_contact_id'):
        context.user_data.pop('editing_contact_id', None)
        await update.message.reply_text("✅ Редактирование отменено.")
    else:
        await update.message.reply_text("Нет активного редактирования.")
