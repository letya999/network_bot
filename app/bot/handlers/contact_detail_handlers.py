
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
CONTACT_VIEW_PREFIX = "contact_view_"
CONTACT_EDIT_PREFIX = "contact_edit_"
CONTACT_EDIT_FIELD_PREFIX = "contact_field_"
CONTACT_DEL_FIELD_PREFIX = "contact_del_field_"
CONTACT_ADD_FIELD_PREFIX = "contact_add_field"
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
    Starts editing a contact. Shows a menu of fields to edit.
    """
    query = update.callback_query
    await query.answer()
    
    # Check if we are coming from the main edit button or "Back" from a field edit
    if query.data.startswith(CONTACT_EDIT_PREFIX):
        contact_id = query.data.replace(CONTACT_EDIT_PREFIX, "")
    else:
        # Fallback if we lost context, though unlikely
        contact_id = context.user_data.get('editing_contact_id')
        
    if not contact_id:
        await update.effective_message.reply_text("❌ Ошибка контекста.")
        return
    
    # Store contact_id in user_data
    context.user_data['editing_contact_id'] = contact_id
    # Clear specific field if any
    context.user_data.pop('edit_contact_field', None)

    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(contact_id)
        
        if not contact:
            await update.effective_message.reply_text("❌ Контакт не найден.")
            return

        text = f"✏️ **Редактирование контакта: {contact.name}**\n\nВыберите поле для изменения:"
        
        keyboard = [
            [
                InlineKeyboardButton("👤 Имя", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}name"),
                InlineKeyboardButton("🏢 Компания", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}company"),
                InlineKeyboardButton("💼 Роль", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}role")
            ],
            [
                InlineKeyboardButton("🔗 Контакты (+)", callback_data=f"contact_manage_contacts")
            ],
            [
                InlineKeyboardButton("📄 Заметки", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}notes"),
                 InlineKeyboardButton("📍 Событие", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}event_name")
            ],
             [
                InlineKeyboardButton("🎯 След. шаг", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}follow_up_action"),
                InlineKeyboardButton("📝 Договорённости", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}agreements")
            ],
            [
                InlineKeyboardButton("🔙 Назад к просмотру", callback_data=f"{CONTACT_VIEW_PREFIX}{contact.id}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send as NEW message to keep contact card visible
        await update.effective_message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def manage_contact_contacts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows list of contacts to add/delete.
    """
    query = update.callback_query
    await query.answer()
    
    contact_id = context.user_data.get('editing_contact_id')
    if not contact_id:
         await update.effective_message.reply_text("❌ Ошибка контекста.")
         return

    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(contact_id)
        
        text = f"🔗 **Контакты ({contact.name})**\n\nУправление контактами:"
        keyboard = []
        
        # Standard Fields
        if contact.phone:
             keyboard.append([InlineKeyboardButton(f"❌ Телефон: {contact.phone}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}phone")])
        if contact.telegram_username:
             keyboard.append([InlineKeyboardButton(f"❌ Telegram: {contact.telegram_username}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}telegram_username")])
        if contact.email:
             keyboard.append([InlineKeyboardButton(f"❌ Email: {contact.email}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}email")])
        if contact.linkedin_url:
             # Truncate
             short_li = contact.linkedin_url[:20] + "..." if len(contact.linkedin_url) > 20 else contact.linkedin_url
             keyboard.append([InlineKeyboardButton(f"❌ LinkedIn: {short_li}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}linkedin_url")])
             
        # Custom Fields
        if contact.attributes and 'custom_contacts' in contact.attributes:
             for idx, cc in enumerate(contact.attributes['custom_contacts']):
                  label = cc.get('label', 'Contact')
                  val = cc.get('value', '')
                  short_val = val[:20] + "..." if len(val) > 20 else val
                  # We use index to delete custom contacts
                  keyboard.append([InlineKeyboardButton(f"❌ {label}: {short_val}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}custom_{idx}")])

        keyboard.append([InlineKeyboardButton("➕ Добавить контакт", callback_data=f"{CONTACT_ADD_FIELD_PREFIX}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"{CONTACT_EDIT_PREFIX}{contact_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send as NEW message to keep edit menu visible
        await update.effective_message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def delete_contact_field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deletes a specific contact field.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace(CONTACT_DEL_FIELD_PREFIX, "")
    contact_id = context.user_data.get('editing_contact_id')
    
    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(contact_id)
        
        update_data = {}
        
        if data.startswith("custom_"):
            idx = int(data.replace("custom_", ""))
            if contact.attributes and 'custom_contacts' in contact.attributes:
                 custom = contact.attributes['custom_contacts']
                 if 0 <= idx < len(custom):
                      custom.pop(idx)
                      # Update attributes
                      current_attrs = dict(contact.attributes)
                      current_attrs['custom_contacts'] = custom
                      # We need to explicitly update attributes via service
                      # ContactServices smart update merges, so passing dict with same key replaces it? 
                      # Check service logic. Service: current_attrs.update(data). 
                      # Wait, if I pass {'custom_contacts': new_list}, it updates that key. Correct.
                      update_data = {'custom_contacts': custom}
        else:
             # Standard field
             update_data = {data: None}
             
        if update_data:
            # We need to use update_contact but handle 'custom_contacts' correctly.
            # ContactService.update_contact merges `attributes`.
            # If we pass `custom_contacts` inside `data` (which is flattened), it goes to attributes.
            # Wait, `update_contact` logic: 
            # 1. iter items. if hasattr(contact, field) -> setattr.
            # 2. attributes.update(data).
            # So if I pass 'phone': None, it sets phone=None.
            # If I pass 'custom_contacts': [...], it goes to attributes['custom_contacts'].
            # Perfect.
            await contact_service.update_contact(contact.id, update_data)
            
    await manage_contact_contacts_menu(update, context)

async def add_contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Starts add contact wizard.
    """
    query = update.callback_query
    await query.answer()
    
    context.user_data['edit_contact_field'] = 'add_contact_label'
    
    # Remove buttons from contacts menu, send prompt separately
    await query.edit_message_reply_markup(reply_markup=None)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Введите **название** для нового контакта (например: 'Мой сайт', 'LinkedIn', 'Секретный телефон'):\n\n_Нажмите /cancel для отмены_",
        parse_mode="Markdown"
    )

async def handle_contact_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler when a specific field is selected for editing.
    """
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace(CONTACT_EDIT_FIELD_PREFIX, "")
    context.user_data['edit_contact_field'] = field
    contact_id = context.user_data.get('editing_contact_id')
    
    field_names = {
        "name": "Имя",
        "company": "Компания",
        "role": "Роль",
        "phone": "Телефон",
        "telegram_username": "Telegram username/ссылку",
        "email": "Email",
        "linkedin_url": "LinkedIn профиль",
        "notes": "Заметки",
        "event_name": "Событие/Откуда контакт",
        "follow_up_action": "Следующий шаг",
        "agreements": "Договорённости",
    }
    
    label = field_names.get(field, field)
    
    text = (
        f"Введите новое значение для **{label}**:\n\n"
        "_Нажмите /cancel для отмены_"
    )
    
    # Remove buttons from edit menu to keep it as reference
    await query.edit_message_reply_markup(reply_markup=None)
    
    # Send prompt as NEW message
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode="Markdown"
    )

async def cancel_contact_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels contact editing mode.
    """
    if context.user_data.get('editing_contact_id'):
        context.user_data.pop('editing_contact_id', None)
        await update.message.reply_text("✅ Редактирование отменено.")
    else:
        await update.message.reply_text("Нет активного редактирования.")
