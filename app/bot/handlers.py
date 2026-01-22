import os
import logging
import time
import uuid
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.gemini_service import GeminiService
from app.services.export_service import ExportService
from app.bot.rate_limiter import rate_limit_middleware

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
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
        data = await gemini.extract_contact_data(audio_path=file_path)

        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

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

            card = format_card(contact)
            await update.message.reply_text(card)

    except Exception as e:
        logger.exception("Error handling voice")
        # Security: Don't expose internal error details to user
        await status_msg.edit_text("❌ Произошла ошибка при обработке. Попробуйте еще раз.")
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
