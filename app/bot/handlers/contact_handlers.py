import os
import re
import uuid
import logging
import tempfile
import time
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.contact_service import ContactService
from app.services.user_service import UserService
from app.services.gemini_service import GeminiService
from app.services.reminder_service import ReminderService
from app.services.merge_service import ContactMergeService
from app.services.pulse_service import PulseService
from app.utils.text_parser import extract_contact_info
from app.bot.rate_limiter import rate_limit_middleware
from app.bot.handlers.match_handlers import notify_match_if_any
from app.bot.views import format_card, get_contact_keyboard
import dateparser
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def _apply_event_context(data: dict, context: ContextTypes.DEFAULT_TYPE):
    """Helper to inject current event mode into contact data."""
    current_event = context.user_data.get("current_event")
    if current_event:
        existing = data.get("event_name")
        if existing:
            if current_event.lower() not in existing.lower():
                data["event_name"] = f"{current_event} · {existing}"
        else:
            data["event_name"] = current_event

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for voice messages. Transcribes audio and extracts contact information.
    """
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    voice = update.message.voice
    logger.info(f"Received voice from user {user.id}. Duration: {voice.duration}s")

    if voice.file_size and voice.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File too large. Maximum 20 MB.")
        return

    if voice.duration > 600:
        await update.message.reply_text("❌ Message too long. Maximum 10 minutes.")
        return

    status_msg = await update.message.reply_text("🎤 Listening and processing...")
    status_msg_deleted = False

    temp_dir = tempfile.mkdtemp(prefix="voice_")
    random_filename = f"{uuid.uuid4()}.ogg"
    file_path = os.path.join(temp_dir, random_filename)

    try:
        new_file = await context.bot.get_file(voice.file_id)
        await new_file.download_to_drive(file_path)

        with open(file_path, 'rb') as f:
            if f.read(4)[:4] != b'OggS':
                await status_msg.edit_text("❌ Invalid file format.")
                return

        gemini = GeminiService()
        
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
            
            data = await gemini.extract_contact_data(audio_path=file_path, prompt_template=db_user.custom_prompt)
            
            if data.get("error"):
                 await status_msg.edit_text(f"❌ Processing error (possible AI limit): {data.get('error')}")
                 return

            _apply_event_context(data, context)
            
            merge_service = ContactMergeService(session)

            if merge_service.is_reminder_only(data):
                # Standalone Reminder logic
                reminder_service = ReminderService(session)
                count = 0
                for rem in data.get("reminders", []):
                    try:
                        due_date = dateparser.parse(rem.get("due_date", ""), settings={'PREFER_DATES_FROM': 'future'})
                        if not due_date or due_date < datetime.now():
                             due_date = datetime.now() + timedelta(days=1)
                             
                        await reminder_service.create_reminder(
                            user_id=db_user.id,
                            title=rem.get("title", "Reminder"),
                            due_at=due_date,
                            description=rem.get("description")
                        )
                        count += 1
                    except Exception:
                        logger.exception("Error creating reminder")
                
                await status_msg.delete()
                status_msg_deleted = True
                await update.message.reply_text(f"✅ Reminders created: {count}")
                return

            # Process with Merge Service
            contact, was_merged = await merge_service.process_contact_data(db_user.id, data, context.user_data)
            
            if was_merged:
                await status_msg.edit_text("🔗 Merged with recent contact!")
            else:
                await status_msg.delete()
                status_msg_deleted = True
            
            # Update last context
            context.user_data["last_contact_id"] = contact.id
            context.user_data["last_contact_time"] = time.time()
            
            # Match notification
            await notify_match_if_any(update, contact, db_user, session)
            
            # Triangulation detection (Relationship Pulse)
            if contact and not was_merged:
                pulse_service = PulseService(session)
                triangulation_contacts = await pulse_service.detect_company_triangulation(db_user.id, contact)
                if triangulation_contacts:
                    triangulation_msg = pulse_service.generate_triangulation_message(contact, triangulation_contacts)
                    await update.message.reply_text(triangulation_msg, parse_mode="Markdown")

            if contact:
                card = format_card(contact)
                keyboard = get_contact_keyboard(contact)
                await update.message.reply_text(
                    card, parse_mode="HTML", reply_markup=keyboard,
                    disable_web_page_preview=True
                )

    except Exception:
        logger.exception("Error handling voice")
        if not status_msg_deleted:
            try:
                await status_msg.edit_text("❌ An error occurred during processing. Please try again.")
            except Exception:
                await update.message.reply_text("❌ An error occurred during processing. Please try again.")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except Exception:
            logger.exception("Error cleaning up temporary files")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for shared Telegram contacts.
    """
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    contact_data = update.message.contact
    logger.info(f"Received contact {contact_data.first_name} from user {user.id}.")
    
    data = {
        "name": f"{contact_data.first_name} {contact_data.last_name or ''}".strip(),
        "phone": contact_data.phone_number,
        "notes": "Shared Telegram contact"
    }
    _apply_event_context(data, context)

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        merge_service = ContactMergeService(session)
        contact, was_merged = await merge_service.process_contact_data(db_user.id, data, context.user_data)
        
        if was_merged:
            await update.message.reply_text("🔗 Merged with recent note!")
        
        # Update last context
        context.user_data["last_contact_id"] = contact.id
        context.user_data["last_contact_time"] = time.time()
        
        await notify_match_if_any(update, contact, db_user, session)
        
        # Triangulation detection (Relationship Pulse)
        if contact and not was_merged:
            pulse_service = PulseService(session)
            triangulation_contacts = await pulse_service.detect_company_triangulation(db_user.id, contact)
            if triangulation_contacts:
                triangulation_msg = pulse_service.generate_triangulation_message(contact, triangulation_contacts)
                await update.message.reply_text(triangulation_msg, parse_mode="Markdown")

        card = format_card(contact)
        keyboard = get_contact_keyboard(contact)
        await update.message.reply_text(
            card, parse_mode="HTML", reply_markup=keyboard,
            disable_web_page_preview=True
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for text messages that might contain contact info.
    """
    user = update.effective_user
    text = update.message.text
    
    # 1. Fast regex extraction
    regex_data = extract_contact_info(text) or {}
    
    # Check for nick
    if not regex_data and re.match(r'^@?[a-zA-Z0-9_]{3,32}$', text.strip()):
        regex_data = {"telegram_username": text.strip().lstrip('@')}

    # Optional: Verify nickname existence via Bot API
    if regex_data.get('telegram_username'):
        tg_user = regex_data['telegram_username']
        try:
            chat = await context.bot.get_chat(chat_id=f"@{tg_user}")
            if chat.username:
                regex_data['telegram_username'] = chat.username
            extracted_name = f"{chat.first_name} {chat.last_name or ''}".strip()
            if extracted_name:
                regex_data['name'] = extracted_name
        except Exception:
            logger.debug(f"Could not verify username {tg_user}")

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        gemini = GeminiService()
        data = await gemini.extract_contact_data(text=text, prompt_template=db_user.custom_prompt)
        
        # Check for Critical API Errors (e.g. Quota Exceeded)
        if data.get("error"):
            error_msg = data.get("error")
            if regex_data:
                data = regex_data
                # Ensure minimal fields
                if "name" not in data:
                    data["name"] = "New Contact"
                data["notes"] = f"⚠️ Retrieved during AI failure: {text[:50]}..."
                
                await update.message.reply_text(
                    f"⚠️ <b>AI limit exceeded or error.</b>\n"
                    f"Saving what could be extracted via templates (Regex).\n"
                    f"Error: {error_msg}",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"⏳ <b>AI limit exceeded (20 req/min)</b> or error occurred.\n"
                    f"Please wait a minute and try again.\n"
                    f"No contacts found in text via templates.\n\n"
                    f"Error: {error_msg}",
                    parse_mode="HTML"
                )
                return
        
        # Merge manual regex data if Gemini missed it
        for key in ['telegram_username', 'phone']:
            if regex_data.get(key) and not data.get(key):
                data[key] = regex_data[key]
        
        # EXPLICIT EDITING LOGIC
        editing_contact_id = context.user_data.get('editing_contact_id')
        edit_contact_field = context.user_data.get('edit_contact_field')

        if editing_contact_id:
            logger.info(f"User {user.id} is explicitly editing contact {editing_contact_id}")
            contact_service = ContactService(session)
            
            # 1. SPECIFIC FIELD EDITING (Menu driven)
            if edit_contact_field:
                # Need to handle Add Contact Wizard
                if edit_contact_field == 'add_contact_label':
                    context.user_data['add_contact_label_temp'] = text
                    context.user_data['edit_contact_field'] = 'add_contact_value'
                    await update.message.reply_text(
                        f"Great. Now enter the **value** for '{text}' (link, phone, or text):",
                        parse_mode="Markdown"
                    )
                    return
                
                elif edit_contact_field == 'add_contact_value':
                    label = context.user_data.get('add_contact_label_temp', 'Contact')
                    value = text
                    context.user_data.pop('add_contact_label_temp', None)
                    
                    # Logic to map to standard fields or custom
                    update_data = {}
                    label_lower = label.lower().strip()
                    
                    GENERIC_PHONES = {'phone', 'telephone', 'mobile', 'телефон', 'мобильный', 'тел', 'сот', 'сотовый'}
                    GENERIC_TG = {'telegram', 'телеграм', 'тг', 'tg', 'telegram username'}
                    GENERIC_EMAIL = {'email', 'mail', 'почта', 'емейл', 'электронная почта'}
                    GENERIC_LINKEDIN = {'linkedin', 'линкедин', 'in', 'линк'}
                    
                    # Strict check for standard fields to avoid stealing custom labels
                    if label_lower in GENERIC_PHONES:
                        update_data = {'phone': value}
                    elif label_lower in GENERIC_TG:
                        # Clean username if it's a URL
                        clean_tg = value.replace("https://t.me/", "").replace("http://t.me/", "").strip().lstrip("@")
                        update_data = {'telegram_username': clean_tg}
                    elif label_lower in GENERIC_EMAIL:
                         update_data = {'email': value}
                    elif label_lower in GENERIC_LINKEDIN:
                         update_data = {'linkedin_url': value}
                    else:
                         # It's a custom contact
                         # We need to fetch existing attributes to append
                         contact = await contact_service.get_contact_by_id(editing_contact_id)
                         if contact:
                             custom = contact.attributes.get('custom_contacts', []) if contact.attributes else []
                             custom.append({'label': label, 'value': value})
                             update_data = {'custom_contacts': custom}
                    
                    if update_data:
                        try:
                            cid = uuid.UUID(str(editing_contact_id))
                            updated_contact = await contact_service.update_contact(cid, update_data)
                            
                            if updated_contact:
                                 context.user_data.pop('edit_contact_field', None)
                                 await update.message.reply_text("✅ Contact added.")
                                 
                                 # Return to Manage Contacts Menu
                                 from app.bot.handlers.contact_detail_handlers import manage_contact_contacts_menu
                                 # Fake update
                                 # We need to construct a fake callback query update to reuse the handler?
                                 # No, the handler expects update.callback_query usually. 
                                 # If we call it with a Message update, it might check callback_query.
                                 # Let's check logic of `manage_contact_contacts_menu`...
                                 # It does `query = update.callback_query` and `await query.answer()`. This will FAIL on message update.
                                 # So we must recreate the UI manually here or Refactor the handler to accept message.
                                 
                                 # OPTION: duplicate logic (easiest now)
                                 # Or better: make a common function `show_manage_contacts(update, context, contact_id)`
                                 
                                 # Let's duplicate "Show Menu" logic briefly but using send_message
                                 from app.bot.handlers.contact_detail_handlers import (
                                     CONTACT_DEL_FIELD_PREFIX, CONTACT_ADD_FIELD_PREFIX, CONTACT_EDIT_PREFIX
                                 )
                                 from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                                 
                                 menu_text = "🔗 **Contacts**\n\nManage contacts:"
                                 keyboard = []
                                 contact = updated_contact
                                 # Standard Fields
                                 if contact.phone:
                                      keyboard.append([InlineKeyboardButton(f"❌ Телефон: {contact.phone}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}phone")])
                                 if contact.telegram_username:
                                      keyboard.append([InlineKeyboardButton(f"❌ Telegram: {contact.telegram_username}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}telegram_username")])
                                 if contact.email:
                                      keyboard.append([InlineKeyboardButton(f"❌ Email: {contact.email}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}email")])
                                 if contact.linkedin_url:
                                      short_li = contact.linkedin_url[:20] + "..." if len(contact.linkedin_url) > 20 else contact.linkedin_url
                                      keyboard.append([InlineKeyboardButton(f"❌ LinkedIn: {short_li}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}linkedin_url")])
                                 # Custom
                                 if contact.attributes and 'custom_contacts' in contact.attributes:
                                      for idx, cc in enumerate(contact.attributes['custom_contacts']):
                                           lbl = cc.get('label', 'Contact')
                                           val = cc.get('value', '')
                                           short_val = val[:20] + "..." if len(val) > 20 else val
                                           keyboard.append([InlineKeyboardButton(f"❌ {lbl}: {short_val}", callback_data=f"{CONTACT_DEL_FIELD_PREFIX}custom_{idx}")])

                                 keyboard.append([InlineKeyboardButton("➕ Add Contact", callback_data=f"{CONTACT_ADD_FIELD_PREFIX}")])
                                 keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"{CONTACT_EDIT_PREFIX}{contact.id}")])
                                 
                                 await update.message.reply_text(menu_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                                 return
                        except Exception:
                             logger.exception("Error adding contact")
                             context.user_data.pop('edit_contact_field', None)
                             await update.message.reply_text("❌ Error.")
                             return

                # Normal single field edit
                # Use raw text for the field value
                update_data = {edit_contact_field: text}
                
                try:
                    cid = uuid.UUID(str(editing_contact_id))
                    updated_contact = await contact_service.update_contact(cid, update_data)
                    
                    if updated_contact:
                        context.user_data.pop('edit_contact_field', None)
                        await update.message.reply_text(f"✅ Field updated.")
                        
                        # Show Edit Menu again to continue editing
                        # Re-import to avoid circular dependency at top level
                        from app.bot.handlers.contact_detail_handlers import CONTACT_EDIT_FIELD_PREFIX, CONTACT_VIEW_PREFIX, CONTACT_ADD_FIELD_PREFIX
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                        menu_text = f"✏️ **Editing Contact: {updated_contact.name}**\n\nSelect a field to change:"
                        keyboard = [
                            [
                                 InlineKeyboardButton("👤 Name", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}name"),
                                 InlineKeyboardButton("🏢 Company", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}company"),
                                 InlineKeyboardButton("💼 Role", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}role")
                            ],
                            [
                                InlineKeyboardButton("🔗 Contacts (+)", callback_data=f"contact_manage_contacts")
                            ],
                            [
                                InlineKeyboardButton("📄 Notes", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}notes"),
                                InlineKeyboardButton("📍 Event", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}event_name")
                            ],
                            [
                                InlineKeyboardButton("🎯 Next Step", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}follow_up_action"),
                                InlineKeyboardButton("📝 Agreements", callback_data=f"{CONTACT_EDIT_FIELD_PREFIX}agreements")
                            ],
                            [
                                InlineKeyboardButton("🔙 Back to view", callback_data=f"{CONTACT_VIEW_PREFIX}{updated_contact.id}")
                            ]
                        ]
                        await update.message.reply_text(menu_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                        return
                    else:
                        await update.message.reply_text("❌ Error: Contact not found.")
                        context.user_data.pop('editing_contact_id', None)
                        return
                except ValueError:
                     context.user_data.pop('editing_contact_id', None)
                     return

            # 2. FULL TEXT EDITING (Legacy/Smart Update)
            # Handle reminders if present
            if data.get("reminders"):
                 reminder_service = ReminderService(session)
                 for rem in data.get("reminders", []):
                    try:
                        due_date = dateparser.parse(rem.get("due_date", ""), settings={'PREFER_DATES_FROM': 'future'})
                        if not due_date or due_date < datetime.now():
                             due_date = datetime.now() + timedelta(days=1)
                        # We pass the contact_id being edited
                        await reminder_service.create_reminder(db_user.id, rem.get("title"), due_date, rem.get("description"), contact_id=editing_contact_id)
                    except Exception:
                        logger.exception("Error creating reminder during edit")

            # Update contact fields
            try:
                # Ensure it's UUID
                cid = uuid.UUID(str(editing_contact_id))
                updated_contact = await contact_service.update_contact(cid, data)
                
                if updated_contact:
                    # Clear edit state
                    context.user_data.pop('editing_contact_id', None)
                    
                    await update.message.reply_text("✅ Data updated.")
                    # Show updated card
                    card = format_card(updated_contact)
                    keyboard = get_contact_keyboard(updated_contact)
                    await update.message.reply_text(
                        card, parse_mode="HTML", reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
                    return
                else:
                    await update.message.reply_text("❌ Error: Contact not found.")
                    context.user_data.pop('editing_contact_id', None)
                    return
            except ValueError:
                 context.user_data.pop('editing_contact_id', None)

        _apply_event_context(data, context)
        
        merge_service = ContactMergeService(session)
        
        if merge_service.is_reminder_only(data) and not regex_data:
            # Standalone Reminder logic
            reminder_service = ReminderService(session)
            count = 0
            for rem in data.get("reminders", []):
                try:
                    due_date = dateparser.parse(rem.get("due_date", ""), settings={'PREFER_DATES_FROM': 'future'})
                    if not due_date or due_date < datetime.now():
                         due_date = datetime.now() + timedelta(days=1)
                    await reminder_service.create_reminder(db_user.id, rem.get("title"), due_date, rem.get("description"))
                    count += 1
                except Exception:
                    logger.exception("Error creating reminder from text")
            await update.message.reply_text(f"✅ Создано напоминаний: {count}")
            return

        if 'notes' not in data and len(text) > 20: 
             data['notes'] = text

        contact, was_merged = await merge_service.process_contact_data(db_user.id, data, context.user_data)
        
        if was_merged:
            await update.message.reply_text("🔗 Information added!")
        else:
            await update.message.reply_text("💾 Contact saved (waiting for description...)")
            
        context.user_data["last_contact_id"] = contact.id
        context.user_data["last_contact_time"] = time.time()
        
        await notify_match_if_any(update, contact, db_user, session)
        
        # Triangulation detection (Relationship Pulse)
        if contact and not was_merged:
            pulse_service = PulseService(session)
            triangulation_contacts = await pulse_service.detect_company_triangulation(db_user.id, contact)
            if triangulation_contacts:
                triangulation_msg = pulse_service.generate_triangulation_message(contact, triangulation_contacts)
                await update.message.reply_text(triangulation_msg, parse_mode="Markdown")

        card = format_card(contact)
        keyboard = get_contact_keyboard(contact)
        await update.message.reply_text(
            card, parse_mode="HTML", reply_markup=keyboard,
            disable_web_page_preview=True
        )
