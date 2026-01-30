import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.export_service import ExportService
from app.bot.rate_limiter import rate_limit_middleware
from app.config.constants import MAX_SEARCH_QUERY_LENGTH
from app.bot.handlers.menu_handlers import NETWORKING_MENU

PAGE_SIZE = 10

logger = logging.getLogger(__name__)

async def list_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /list command. Shows recent contacts with pagination.
    """
    user = update.effective_user
    logger.info(f"User {user.id} requested contact list.")
    
    page = 0
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        data = update.callback_query.data
        if data.startswith("cmd_list_page_"):
            try:
                page = int(data.replace("cmd_list_page_", ""))
            except ValueError:
                page = 0
    else:
        message = update.message

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        contact_service = ContactService(session)
        # Fetch one extra to determine if there is a next page
        contacts = await contact_service.get_recent_contacts(db_user.id, limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE)
        
        has_next = len(contacts) > PAGE_SIZE
        current_contacts = contacts[:PAGE_SIZE]
        
        if not current_contacts and page == 0:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=NETWORKING_MENU)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            text = "У тебя пока нет контактов."
            # Edit if callback, reply if message
            if update.callback_query:
                await message.edit_text(text, reply_markup=reply_markup)
            else:
                await message.reply_text(text, reply_markup=reply_markup)
            return

        text = f"📋 *Твои последние контакты (стр. {page + 1}):*\nВыберите контакт, чтобы посмотреть подробности:"
        
        keyboard = []
        for contact in current_contacts:
            btn_text = f"{contact.name}"
            if contact.company:
                btn_text += f" — {contact.company}"
            # Limit button text length to avoid telegram errors
            if len(btn_text) > 40:
                btn_text = btn_text[:37] + "..."
                
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"contact_view_{contact.id}")])
            
        # Pagination controls
        pagination_row = []
        if page > 0:
            pagination_row.append(InlineKeyboardButton("⬅️ Стр. назад", callback_data=f"cmd_list_page_{page - 1}"))
        
        # Helper text button purely for info (optional, or just skip)
        # pagination_row.append(InlineKeyboardButton(f"📄 {page + 1}", callback_data="noop")) 
        
        if has_next:
            pagination_row.append(InlineKeyboardButton("Стр. вперед ➡️", callback_data=f"cmd_list_page_{page + 1}"))
            
        if pagination_row:
            keyboard.append(pagination_row)
            
        # Back button
        keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data=NETWORKING_MENU)])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def find_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /find command. Searches contacts by name or company.
    """
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("🔍 Чтобы найти контакт, отправьте команду:\n`/find Имя` или `/find Компания`", parse_mode="Markdown")
        return

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
    
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message

    status_msg = await message.reply_text("⏳ Генерирую экспорт...")
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        contact_service = ContactService(session)
        contacts = await contact_service.get_all_contacts(db_user.id)
        
        if not contacts:
            await status_msg.edit_text("Нет контактов для экспорта.")
            return

        csv_file = ExportService.to_csv(contacts)
        await message.reply_document(
            document=csv_file,
            filename="my_contacts.csv",
            caption=f"Экспорт {len(contacts)} контактов."
        )
        await status_msg.delete()
