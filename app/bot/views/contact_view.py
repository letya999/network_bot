"""Contact view layer - presentation logic for contact cards and UI elements."""
import re
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def format_card(contact):
    """
    Format a contact object into a HTML card for Telegram.

    Args:
        contact: Contact model instance

    Returns:
        Formatted HTML string for Telegram message
    """
    # Smart Name Display
    name_display = escape(contact.name or "Без имени")
    show_tg_line = True

    if contact.telegram_username and contact.name:
        # Check for redundancy (Name == Nickname)
        norm_name = re.sub(r'[\s_]', '', contact.name.lower())
        norm_tg = re.sub(r'[\s_]', '', contact.telegram_username.lower().lstrip('@'))

        # If very similar, hide the separate line and link the name
        if norm_name == norm_tg:
             tg = contact.telegram_username.lstrip("@")
             # Use HTML link
             name_display = f'<a href="https://t.me/{tg}">{name_display}</a>'
             show_tg_line = False

    text = f"✅ <b>{name_display}</b>\n\n"
    if contact.company:
        text += f"🏢 {escape(contact.company)}"
        if contact.role:
            text += f" · {escape(contact.role)}"
        text += "\n"

    text += "\n"
    if contact.event_name:
        text += f"📍 {escape(contact.event_name)}\n"

    if contact.agreements:
        text += "\n📝 Договорённости:\n"
        for item in contact.agreements:
            text += f"• {escape(item)}\n"

    if contact.follow_up_action:
        text += f"\n🎯 Следующий шаг: {escape(contact.follow_up_action)}\n"

    if contact.what_looking_for:
        text += f"\n💡 Ищет: {escape(contact.what_looking_for)}\n"

    # Show notes/errors (stored in attributes for contacts)
    notes = None
    if hasattr(contact, 'attributes') and contact.attributes:
        notes = contact.attributes.get('notes')

    if notes:
        text += f"\n📄 Заметки: {escape(notes)}\n"

    # CONTACT DETAILS SECTION (Moved to bottom)
    text += "\n📞 <b>Контакты:</b>\n"
    has_contacts = False

    if contact.phone:
        clean_phone = re.sub(r'[^\d+]', '', contact.phone)
        text += f"• Телефон: <a href=\"tel:{clean_phone}\">{escape(contact.phone)}</a>\n"
        has_contacts = True

    if contact.telegram_username:
        # Normalize: strip URL prefixes and @ symbol
        tg = contact.telegram_username
        tg = re.sub(r'^https?://t\.me/', '', tg)
        tg = tg.lstrip("@")

        if show_tg_line:
             text += f"• Telegram: <a href=\"https://t.me/{tg}\">@{escape(tg)}</a>\n"
             has_contacts = True
        else:
             # Already linked in name, but show in contacts section for consistency
             text += f"• Telegram: <a href=\"https://t.me/{tg}\">@{escape(tg)}</a>\n"
             has_contacts = True

    if contact.email:
        text += f"• Почта: <a href=\"mailto:{escape(contact.email)}\">{escape(contact.email)}</a>\n"
        has_contacts = True

    if contact.linkedin_url:
        # Extract display name from URL if possible
        li_display = contact.linkedin_url
        if "linkedin.com/in/" in li_display:
            li_display = li_display.split("linkedin.com/in/")[-1].strip("/")

        target_url = contact.linkedin_url.replace('https://', '').replace('http://', '').replace('www.', '')
        text += f"• LinkedIn: <a href=\"https://www.{target_url}\">{escape(li_display)}</a>\n"
        has_contacts = True

    # Custom Contacts from Attributes
    if hasattr(contact, 'attributes') and contact.attributes:
        custom_contacts = contact.attributes.get('custom_contacts', [])
        if custom_contacts:
             for cc in custom_contacts:
                label = cc.get('label', 'Ссылка')
                val = cc.get('value', '')
                if val:
                    if val.startswith('http') or val.startswith('t.me'):
                         link = val
                         if val.startswith('t.me'):
                             link = f"https://{val}"
                         text += f"• <a href=\"{escape(link)}\">{escape(label)}</a>\n"
                    else:
                         text += f"• {escape(label)}: {escape(val)}\n"
                    has_contacts = True

    if not has_contacts:
        text += "<i>(пусто)</i>\n"

    # Show OSINT data if available
    if hasattr(contact, 'osint_data') and contact.osint_data:
        from app.bot.views.osint_view import format_osint_data
        osint_text = format_osint_data(contact.osint_data)
        if osint_text:
            text += f"\n{'─' * 20}\n📊 <b>Публичная информация:</b>\n{osint_text}\n"

    return text


def get_contact_keyboard(contact):
    """
    Generate inline keyboard for contact card.

    Args:
        contact: Contact model instance

    Returns:
        InlineKeyboardMarkup with action buttons
    """
    keyboard = []

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

    # Row 4: Back
    row4 = [
        InlineKeyboardButton("🔙 Главное меню", callback_data="menu_main")
    ]
    keyboard.append(row4)

    return InlineKeyboardMarkup(keyboard) if keyboard else None
