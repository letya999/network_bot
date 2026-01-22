import os
import logging
import time
from telegram import Update
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.gemini_service import GeminiService
from app.services.export_service import ExportService
from app.utils.text_parser import extract_contact_info

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
    user = update.effective_user
    voice = update.message.voice
    logger.info(f"Received voice from user {user.id} ({user.username}). Duration: {voice.duration}s")
    
    status_msg = await update.message.reply_text("🎤 Слушаю и обрабатываю...")
    
    os.makedirs("downloads", exist_ok=True)
    file_path = f"downloads/{voice.file_id}.ogg"
    
    try:
        new_file = await context.bot.get_file(voice.file_id)
        await new_file.download_to_drive(file_path)
        
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

            card = format_card(contact)
            await update.message.reply_text(card)
            
    except Exception as e:
        logger.exception("Error handling voice")
        await status_msg.edit_text(f"Произошла ошибка: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Received contact from user {user.id} ({user.username}).")
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
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /find <имя или компания>")
        return
    
    query = " ".join(context.args)
    logger.info(f"User {user.id} searching for: {query}")
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

