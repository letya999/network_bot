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
from app.bot.match_handlers import notify_match_if_any
from app.bot.handlers.common import format_card, get_contact_keyboard
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
        await update.message.reply_text("❌ Файл слишком большой. Максимум 20 МБ.")
        return

    if voice.duration > 600:
        await update.message.reply_text("❌ Слишком длинное сообщение. Максимум 10 минут.")
        return

    status_msg = await update.message.reply_text("🎤 Слушаю и обрабатываю...")
    status_msg_deleted = False

    temp_dir = tempfile.mkdtemp(prefix="voice_")
    random_filename = f"{uuid.uuid4()}.ogg"
    file_path = os.path.join(temp_dir, random_filename)

    try:
        new_file = await context.bot.get_file(voice.file_id)
        await new_file.download_to_drive(file_path)

        with open(file_path, 'rb') as f:
            if f.read(4)[:4] != b'OggS':
                await status_msg.edit_text("❌ Неверный формат файла.")
                return

        gemini = GeminiService()
        
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
            
            data = await gemini.extract_contact_data(audio_path=file_path, prompt_template=db_user.custom_prompt)
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
                            title=rem.get("title", "Напоминание"),
                            due_at=due_date,
                            description=rem.get("description")
                        )
                        count += 1
                    except Exception:
                        logger.exception("Error creating reminder")
                
                await status_msg.delete()
                status_msg_deleted = True
                await update.message.reply_text(f"✅ Создано напоминаний: {count}")
                return

            # Process with Merge Service
            contact, was_merged = await merge_service.process_contact_data(db_user.id, data, context.user_data)
            
            if was_merged:
                await status_msg.edit_text("🔗 Объединено с недавним контактом!")
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
                    card, parse_mode="Markdown", reply_markup=keyboard,
                    disable_web_page_preview=True
                )

    except Exception:
        logger.exception("Error handling voice")
        if not status_msg_deleted:
            try:
                await status_msg.edit_text("❌ Произошла ошибка при обработке. Попробуйте еще раз.")
            except Exception:
                await update.message.reply_text("❌ Произошла ошибка при обработке. Попробуйте еще раз.")
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
            await update.message.reply_text("🔗 Объединено с недавней заметкой!")
        
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
            card, parse_mode="Markdown", reply_markup=keyboard,
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
        
        # Merge manual regex data if Gemini missed it
        for key in ['telegram_username', 'phone']:
            if regex_data.get(key) and not data.get(key):
                data[key] = regex_data[key]
        
        # EXPLICIT EDITING LOGIC
        editing_contact_id = context.user_data.get('editing_contact_id')
        if editing_contact_id:
            logger.info(f"User {user.id} is explicitly editing contact {editing_contact_id}")
            contact_service = ContactService(session)
            
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
                    
                    await update.message.reply_text("✅ Данные обновлены.")
                    # Show updated card
                    card = format_card(updated_contact)
                    keyboard = get_contact_keyboard(updated_contact)
                    await update.message.reply_text(
                        card, parse_mode="Markdown", reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
                    return
                else:
                    await update.message.reply_text("❌ Ошибка: Контакт не найден.")
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
            await update.message.reply_text("🔗 Информация добавлена!")
        else:
            await update.message.reply_text("💾 Контакт сохранен (жду описание...)")
            
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
            card, parse_mode="Markdown", reply_markup=keyboard,
            disable_web_page_preview=True
        )
