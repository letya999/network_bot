import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.profile_service import ProfileService
from app.services.card_service import CardService
from app.services.osint_service import format_osint_data

logger = logging.getLogger(__name__)

def format_card(contact):
    """
    Format a contact object into a Markdown card for Telegram.
    """
    # Smart Name Display
    name_display = contact.name
    show_tg_line = True
    
    if contact.telegram_username and contact.name:
        # Check for redundancy (Name == Nickname)
        norm_name = re.sub(r'[\s_]', '', contact.name.lower())
        norm_tg = re.sub(r'[\s_]', '', contact.telegram_username.lower().lstrip('@'))
        
        # If very similar, hide the separate line and link the name
        if norm_name == norm_tg:
             tg = contact.telegram_username.lstrip("@")
             safe_name = contact.name.replace("_", "\\_")
             name_display = f"[{safe_name}](https://t.me/{tg})"
             show_tg_line = False

    text = f"✅ {name_display}\n\n"
    if contact.company:
        text += f"🏢 {contact.company}"
        if contact.role:
            text += f" · {contact.role}"
        text += "\n"
    if contact.phone:
        clean_phone = re.sub(r'[^\d+]', '', contact.phone)
        text += f"📱 [{contact.phone}](tel:{clean_phone})\n"
    if contact.telegram_username and show_tg_line:
        tg = contact.telegram_username.lstrip("@")
        safe_tg_url = f"https://t.me/{tg}".replace("_", "\\_")
        text += f"💬 {safe_tg_url}\n"
    if contact.email:
        text += f"📧 [{contact.email}](mailto:{contact.email})\n"
    
    text += "\n"
    if contact.event_name:
        text += f"📍 {contact.event_name}\n"
    
    if contact.agreements:
        text += "\n📝 Договорённости:\n"
        for item in contact.agreements:
            text += f"• {item}\n"
            
    if contact.follow_up_action:
        text += f"\n🎯 Следующий шаг: {contact.follow_up_action}\n"
        
    if contact.what_looking_for:
        text += f"\n💡 Ищет: {contact.what_looking_for}\n"
    
    if contact.can_help_with:
        text += f"🤝 Может помочь: {contact.can_help_with}\n"
    
    # Show notes/errors (stored in attributes for contacts)
    notes = None
    if hasattr(contact, 'attributes') and contact.attributes:
        notes = contact.attributes.get('notes')

    if notes:
        text += f"\n📄 Заметки: {notes}\n"

    # Show OSINT data if available
    if hasattr(contact, 'osint_data') and contact.osint_data:
        osint_text = format_osint_data(contact.osint_data)
        if osint_text:
            text += f"\n{'─' * 20}\n📊 *Публичная информация:*\n{osint_text}\n"

    return text

def get_contact_keyboard(contact):
    """Generate inline keyboard for contact card."""
    keyboard = []

    # Updated keyboard structure
    
    # Row 1: Main Actions
    row1 = [
        InlineKeyboardButton("👁 Подробнее", callback_data=f"contact_view_{contact.id}"),
        InlineKeyboardButton("✏️ Изменить", callback_data=f"contact_edit_{contact.id}")
    ]
    keyboard.append(row1)

    # Row 2: Enrichment & Tools
    row2 = []
    if not contact.osint_data or contact.osint_data.get("no_results"):
        row2.append(InlineKeyboardButton("🌍 OSINT", callback_data=f"enrich_start_{contact.id}"))
    else:
        row2.append(InlineKeyboardButton("🔄 Обновить OSINT", callback_data=f"enrich_start_{contact.id}"))
        
    row2.append(InlineKeyboardButton("✨ Визитка", callback_data=f"gen_card_{contact.id}"))
    keyboard.append(row2)
    
    # Row 3: Export & Delete
    row3 = [
        InlineKeyboardButton("📥 Notion", callback_data=f"export_notion_{contact.id}"),
        InlineKeyboardButton("📊 Sheets", callback_data=f"export_sheets_{contact.id}"),
        InlineKeyboardButton("🗑", callback_data=f"contact_del_ask_{contact.id}")
    ]
    keyboard.append(row3)

    return InlineKeyboardMarkup(keyboard) if keyboard else None
