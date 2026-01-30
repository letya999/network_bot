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
    
    text += "\n"
    if contact.event_name:
        text += f"📍 {contact.event_name}\n"
    
    if contact.agreements:
        text += "\n📝 Договорённости:\n"
        for item in contact.agreements:
            text += f"• {item}\n"
            
    if contact.follow_up_action:
        text += f"\n🎯 Следующий шаг: {contact.follow_up_action}\n"
    
    # Removed "can_help_with" and "what_looking_for" as per update,
    # OR we can keep looking_for but remove help_with if specifically requested.
    # User said: "Может помочь убери" (Remove Can Help With).
    # He didn't explicitly say remove "looking for", but focused on layout.
    # Let's keep looking_for if it exists, as it's useful context but less cluttered.
    if contact.what_looking_for:
        text += f"\n💡 Ищет: {contact.what_looking_for}\n"

    # Show notes/errors (stored in attributes for contacts)
    notes = None
    if hasattr(contact, 'attributes') and contact.attributes:
        notes = contact.attributes.get('notes')

    if notes:
        text += f"\n📄 Заметки: {notes}\n"

    # CONTACT DETAILS SECTION (Moved to bottom)
    text += "\n📞 *Контакты:*\n"
    has_contacts = False
    
    if contact.phone:
        clean_phone = re.sub(r'[^\d+]', '', contact.phone)
        text += f"• Телефон: [{contact.phone}](tel:{clean_phone})\n"
        has_contacts = True
        
    if contact.telegram_username:
        # Normalize: strip URL prefixes and @ symbol
        tg = contact.telegram_username
        tg = re.sub(r'^https?://t\.me/', '', tg)
        tg = tg.lstrip("@")
        safe_display = tg.replace("_", "\\_")
        text += f"• Telegram: [@{safe_display}](https://t.me/{tg})\n"
        has_contacts = True
        
    if contact.email:
        text += f"• Почта: [{contact.email}](mailto:{contact.email})\n"
        has_contacts = True
        
    if contact.linkedin_url:
        # Extract display name from URL if possible
        li_display = contact.linkedin_url
        if "linkedin.com/in/" in li_display:
            li_display = li_display.split("linkedin.com/in/")[-1].strip("/")
        text += f"• LinkedIn: [{li_display}](https://www.{contact.linkedin_url.replace('https://', '').replace('http://', '').replace('www.', '')})\n"
        has_contacts = True
        
    # Custom Contacts from Attributes
    if hasattr(contact, 'attributes') and contact.attributes:
        custom_contacts = contact.attributes.get('custom_contacts', [])
        if custom_contacts:
             for cc in custom_contacts:
                # Expecting dict like {'label': '...', 'value': '...'}
                label = cc.get('label', 'Ссылка')
                val = cc.get('value', '')
                if val:
                    # Check if val is a URL
                    if val.startswith('http') or val.startswith('t.me'):
                         # If it's t.me but no protocol, add it
                         link = val
                         if val.startswith('t.me'):
                             link = f"https://{val}"
                         text += f"• [{label}]({link})\n"
                    else:
                         text += f"• {label}: {val}\n"
                    has_contacts = True
        
    if not has_contacts:
        text += "_(пусто)_\n"

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
        row2.append(InlineKeyboardButton("Найти информацию (OSINT)", callback_data=f"enrich_start_{contact.id}"))
    else:
        row2.append(InlineKeyboardButton("🔄 Обновить OSINT", callback_data=f"enrich_start_{contact.id}"))
        
    row2.append(InlineKeyboardButton("✨ Визитка", callback_data=f"gen_card_{contact.id}"))
    keyboard.append(row2)
    
    # Row 3: Delete
    row3 = [
        InlineKeyboardButton("Удалить", callback_data=f"contact_del_ask_{contact.id}")
    ]
    keyboard.append(row3)

    return InlineKeyboardMarkup(keyboard) if keyboard else None
