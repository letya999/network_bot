import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.export_service import ExportService
from app.bot.rate_limiter import rate_limit_middleware
from app.config.constants import MAX_SEARCH_QUERY_LENGTH

logger = logging.getLogger(__name__)

async def list_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /list command. Shows recent contacts.
    """
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
        for i, contact in enumerate(contacts, 1):
            text += f"{i}. {contact.name}"
            if contact.company:
                text += f" — {contact.company}"
            text += "\n"
        
        await update.message.reply_text(text)

async def find_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /find command. Searches contacts by name or company.
    """
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /find <имя или компания>")
        return

    query = " ".join(context.args)

    if len(query) > MAX_SEARCH_QUERY_LENGTH:
        await update.message.reply_text(f"❌ Поисковый запрос слишком длинный. Максимум {MAX_SEARCH_QUERY_LENGTH} символов.")
        return

    if not query.strip():
        await update.message.reply_text("❌ Пустой поисковый запрос.")
        return

    logger.info(f"User {user.id} searching contacts for query: {query}")
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        contact_service = ContactService(session)
        contacts = await contact_service.find_contacts(db_user.id, query)

        if not contacts:
            await update.message.reply_text("Ничего не найдено.")
            return

        text = f"🔍 Найдено {len(contacts)} контактов:\n\n"
        for i, contact in enumerate(contacts, 1):
            text += f"{i}. {contact.name}"
            if contact.company:
                text += f" — {contact.company}"
            text += "\n"

        await update.message.reply_text(text)

        # Show buttons if few results for quick access
        if len(contacts) <= 5:
            keyboard = []
            for contact in contacts:
                keyboard.append([InlineKeyboardButton(f"✨ Визитка для {contact.name}", callback_data=f"gen_card_{contact.id}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите контакт для генерации персонализированной визитки:", reply_markup=reply_markup)

async def export_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /export command. Generates and sends a CSV file.
    """
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
