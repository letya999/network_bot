import os
import logging
import time
import uuid
import tempfile
from pathlib import Path
from telegram import Update
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.gemini_service import GeminiService
from app.services.export_service import ExportService
from app.utils.text_parser import extract_contact_info
from app.bot.rate_limiter import rate_limit_middleware
from app.services.profile_service import ProfileService
from app.services.card_service import CardService

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        # Handle Deep Linking
        if context.args and context.args[0].startswith("c_"):
            try:
                target_id = int(context.args[0][2:])
                target_user = await user_service.get_user(target_id)
                
                if target_user:
                    profile_service = ProfileService(session)
                    # We reuse get_profile logic (it calls get_or_create but we know user exists)
                    profile = await profile_service.get_profile(target_id)
                    card_text = CardService.generate_text_card(profile)
                    
                    await update.message.reply_text(
                        f"👋 Привет! Вот визитка, которой с тобой поделились:\n\n{card_text}\n\n"
                        "_Нажми /save чтобы сохранить (WIP)_", 
                        parse_mode="Markdown"
                    )
                    # Optimization: Should we prompt to save this user as a Contact immediately?
                    # That would be a nice "reception" flow.
                else:
                    await update.message.reply_text("❌ Профиль не найден или удален.")
            except ValueError:
                pass
        
    await update.message.reply_text(
        f"Привет {user.first_name}! Я Networking Bot.\n"
        "Отправь мне голосовое сообщение или контакт, чтобы я сохранил его.\n"
        "Команды:\n"
        "/list - мои контакты\n"
        "/find <query> - поиск\n"
        "/export - скачать CSV"
    )

def format_card(contact):
    text = f"✅ {contact.name}\n\n"
    if contact.company:
        text += f"🏢 {contact.company}"
        if contact.role:
            text += f" · {contact.role}"
        text += "\n"
    if contact.phone:
        text += f"📱 {contact.phone}\n"
    if contact.telegram_username:
        text += f"💬 {contact.telegram_username}\n"
    if contact.email:
        text += f"📧 {contact.email}\n"
    
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
    
    # Show notes/errors (stored in attributes for "Неизвестно" contacts)
    notes = None
    if hasattr(contact, 'attributes') and contact.attributes:
        notes = contact.attributes.get('notes')
    
    if notes:
        text += f"\n📄 Заметки: {notes}\n"
        
    return text

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security: Check rate limit
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    voice = update.message.voice
    logger.info(f"Received voice from user {user.id}. Duration: {voice.duration}s")

    # Security: Validate voice file size (max 20MB)
    if voice.file_size and voice.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ Файл слишком большой. Максимум 20 МБ.")
        return

    # Security: Validate duration (max 10 minutes)
    if voice.duration > 600:
        await update.message.reply_text("❌ Слишком длинное сообщение. Максимум 10 минут.")
        return

    status_msg = await update.message.reply_text("🎤 Слушаю и обрабатываю...")
    status_msg_deleted = False  # Track if we deleted the status message

    # Security: Use secure temporary directory with random filename
    temp_dir = tempfile.mkdtemp(prefix="voice_")
    # Generate random filename to prevent path traversal
    random_filename = f"{uuid.uuid4()}.ogg"
    file_path = os.path.join(temp_dir, random_filename)

    try:
        new_file = await context.bot.get_file(voice.file_id)
        await new_file.download_to_drive(file_path)

        # Security: Validate file type by checking magic bytes
        with open(file_path, 'rb') as f:
            header = f.read(4)
            # OGG files start with "OggS"
            if header[:4] != b'OggS':
                await status_msg.edit_text("❌ Неверный формат файла.")
                return

        gemini = GeminiService()
        
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
            
            # Use custom prompt if set
            prompt_to_use = db_user.custom_prompt
            
            data = await gemini.extract_contact_data(audio_path=file_path, prompt_template=prompt_to_use)
            contact_service = ContactService(session)

            # Merge logic
            now = time.time()
            last_contact_time = context.user_data.get("last_contact_time", 0)
            last_contact_id = context.user_data.get("last_contact_id")

            contact = None
            if last_contact_id and (now - last_contact_time < 300):
                contact = await contact_service.update_contact(last_contact_id, data)
                await status_msg.edit_text("🔗 Объединено с недавним контактом!")
                context.user_data.pop("last_contact_id", None)
            else:
                contact = await contact_service.create_contact(db_user.id, data)
                context.user_data["last_voice_id"] = contact.id
                context.user_data["last_voice_time"] = now
                await status_msg.delete()
                status_msg_deleted = True  # Mark as deleted

            card = format_card(contact)
            await update.message.reply_text(card)

    except Exception as e:
        logger.exception("Error handling voice")
        # Security: Don't expose internal error details to user
        # Only try to edit if we haven't deleted the message
        if not status_msg_deleted:
            try:
                await status_msg.edit_text("❌ Произошла ошибка при обработке. Попробуйте еще раз.")
            except Exception:
                # Message might have been deleted or is no longer editable
                await update.message.reply_text("❌ Произошла ошибка при обработке. Попробуйте еще раз.")
    finally:
        # Security: Clean up temporary files and directory
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up temporary files: {cleanup_error}")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security: Check rate limit
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    logger.info(f"Received contact from user {user.id}.")
    contact_data = update.message.contact
    
    data = {
        "name": f"{contact_data.first_name} {contact_data.last_name or ''}".strip(),
        "phone": contact_data.phone_number,
        "notes": "Shared Telegram contact",
        "telegram_username": None # Contact object doesn't have username typically
    }
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        contact_service = ContactService(session)
        
        # Merge logic
        now = time.time()
        last_voice_time = context.user_data.get("last_voice_time", 0)
        last_voice_id = context.user_data.get("last_voice_id")
        
        contact = None
        if last_voice_id and (now - last_voice_time < 300):
            contact = await contact_service.update_contact(last_voice_id, data)
            await update.message.reply_text("🔗 Объединено с голосовой заметкой!")
            context.user_data.pop("last_voice_id", None)
        else:
            contact = await contact_service.create_contact(db_user.id, data)
            context.user_data["last_contact_id"] = contact.id
            context.user_data["last_contact_time"] = now
        
        card = format_card(contact)
        await update.message.reply_text(card)

async def list_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} requested contact list.")
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        contact_service = ContactService(session)
        contacts = await contact_service.get_recent_contacts(db_user.id)
        
        if not contacts:
            await update.message.reply_text("У тебя пока нет контактов.")
            return

        text = "📋 Твои последние контакты:\n\n"
        for i, c in enumerate(contacts, 1):
            text += f"{i}. {c.name}"
            if c.company:
                text += f" — {c.company}"
            text += "\n"
        
        await update.message.reply_text(text)

async def find_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security: Check rate limit
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /find <имя или компания>")
        return

    query = " ".join(context.args)

    # Security: Validate query length
    if len(query) > 100:
        await update.message.reply_text("❌ Поисковый запрос слишком длинный. Максимум 100 символов.")
        return

    if len(query.strip()) == 0:
        await update.message.reply_text("❌ Пустой поисковый запрос.")
        return

    logger.info(f"User {user.id} searching contacts")
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        contact_service = ContactService(session)
        contacts = await contact_service.find_contacts(db_user.id, query)

        if not contacts:
            await update.message.reply_text("Ничего не найдено.")
            return

        text = f"🔍 Найдено {len(contacts)} контактов:\n\n"
        for i, c in enumerate(contacts, 1):
            text += f"{i}. {c.name}"
            if c.company:
                text += f" — {c.company}"
            text += "\n"

        await update.message.reply_text(text)

        # Personalization: Show buttons if few results
        if len(contacts) <= 5:
            keyboard = []
            for c in contacts:
                # Callback data: gen_card_<uuid>
                keyboard.append([InlineKeyboardButton(f"✨ Визитка для {c.name}", callback_data=f"gen_card_{c.id}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите контакт для генерации персонализированной визитки:", reply_markup=reply_markup)

async def generate_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Генерирую визитку... (это может занять пару секунд)", show_alert=True)
    
    data = query.data
    if not data.startswith("gen_card_"):
        return
        
    target_id = data[9:] # strip "gen_card_"
    user = update.effective_user
    
    # Send temporary status
    status_msg = await query.message.reply_text("⏳ Читаю профили и придумываю интро...", quote=True)

    try:
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            # Ensure user exists (should be)
            await user_service.get_or_create_user(user.id)
            
            # Get Target
            from app.models.contact import Contact
            target_contact = await session.get(Contact, target_id)
            
            if not target_contact:
                await status_msg.edit_text("❌ Контакт не найден.")
                return

            # Get My Profile
            profile_service = ProfileService(session)
            my_profile = await profile_service.get_profile(user.id)
            
            # Prepare Gemini inputs
            gemini = GeminiService()
            
            target_info_str = f"Name: {target_contact.name}\n"
            if target_contact.company: target_info_str += f"Company: {target_contact.company}\n"
            if target_contact.role: target_info_str += f"Role: {target_contact.role}\n"
            if target_contact.what_looking_for: target_info_str += f"Looking for: {target_contact.what_looking_for}\n"
            if target_contact.can_help_with: target_info_str += f"Can help with: {target_contact.can_help_with}\n"
            if target_contact.topics: target_info_str += f"Topics: {', '.join(target_contact.topics)}\n"

            my_info_str = f"Name: {my_profile.full_name}\nBio: {my_profile.bio}\nJob: {my_profile.job_title} at {my_profile.company}\nInterests: {', '.join(my_profile.interests)}"
            
            intro = await gemini.customize_card_intro(my_info_str, target_info_str)
            
            card_text = CardService.generate_text_card(my_profile, intro_text=intro)
            
            await status_msg.delete()
            await query.message.reply_text(
                f"📨 *Персонализированная визитка для {target_contact.name}*:\n\n"
                f"{card_text}",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error generating card: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при генерации.")

async def export_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security: Check rate limit
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    logger.info(f"User {user.id} requested export.")
    status_msg = await update.message.reply_text("⏳ Генерирую экспорт...")
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        contact_service = ContactService(session)
        contacts = await contact_service.get_all_contacts(db_user.id)
        
        if not contacts:
            await status_msg.edit_text("Нет контактов для экспорта.")
            return

        csv_file = ExportService.to_csv(contacts)
        await update.message.reply_document(
            document=csv_file,
            filename="my_contacts.csv",
            caption=f"Экспорт {len(contacts)} контактов."
        )
        await status_msg.delete()

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    # Regex Filter: Only process if looks like contact info
    regex_data = extract_contact_info(text)
    if not regex_data:
        return

    logger.info(f"Received text with contact info from user {user.id}. Processing with Gemini...")
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        # Use Gemini for full extraction
        gemini = GeminiService()
        data = await gemini.extract_contact_data(text=text, prompt_template=db_user.custom_prompt)
        
        contact_service = ContactService(session)
        
        # Merge logic
        now = time.time()
        last_voice_time = context.user_data.get("last_voice_time", 0)
        last_voice_id = context.user_data.get("last_voice_id")
        
        contact = None
        # Scenario: Voice -> Text (Link)
        if last_voice_id and (now - last_voice_time < 300):
            contact = await contact_service.update_contact(last_voice_id, data)
            await update.message.reply_text("🔗 Информация добавлена к последнему контакту!")
            # We don't clear last_voice_id immediately? Or we do? 
            # Usually strict pairs, but maybe multiple links?
            # Let's keep the context open for a bit?
            # Existing logic in handle_contact pops it. lets follow that for consistency.
            context.user_data.pop("last_voice_id", None)
        else:
            # Scenario: Text (Link) -> pending Voice
            # Or just a standalone text contact
            
            # We might want to add existing notes if any?
            # data parsing only extracts specific fields.
            # If the user wrote "Here is his email: bob@example.com and he is a nice guy",
            # our parser extracts email. The interaction notes could be the full text.
            data["notes"] = text 
            
            contact = await contact_service.create_contact(db_user.id, data)
            
            # Set context so next voice can pick this up
            context.user_data["last_contact_id"] = contact.id
            context.user_data["last_contact_time"] = now
            
            await update.message.reply_text("💾 Контакт сохранен (жду голосовое описание если есть...)")

        card = format_card(contact)
        await update.message.reply_text(card)

# Prompt Conversation States
WAITING_FOR_PROMPT = 1

async def show_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id)
        
        prompt = db_user.custom_prompt
        source = "Custom (Saved in DB)"
        
        if not prompt:
            gemini = GeminiService()
            prompt = gemini.get_prompt("extract_contact")
            source = "Default (System)"
            
        # Escape markdown chars if needed, or use block code.
        await update.message.reply_text(
            f"📜 *Текущий Промпт* ({source}):\n\n"
            f"```\n{prompt}\n```\n\n"
            "Используй /edit_prompt чтобы изменить его.\n"
            "Используй /reset_prompt чтобы сбросить.",
            parse_mode="Markdown"
        )

async def start_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли мне новый текст промпта.\n"
        "Ты можешь скопировать текущий (/prompt) и отредактировать его.\n"
        "Отправь /cancel чтобы отменить."
    )
    return WAITING_FOR_PROMPT

async def save_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    new_prompt = update.message.text
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.update_custom_prompt(user.id, new_prompt)
        
    await update.message.reply_text("✅ Новый промпт сохранен!")
    return ConversationHandler.END

async def cancel_prompt_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Редактирование отменено.")
    return ConversationHandler.END

async def reset_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.update_custom_prompt(user.id, None) # Set to None
        
    await update.message.reply_text("🔄 Промпт сброшен на стандартный.")

