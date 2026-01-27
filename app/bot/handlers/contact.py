import os
import re
import uuid
import logging
import tempfile
import time
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.contact_service import ContactService  # Added import

# ... (omitted existing imports)

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
