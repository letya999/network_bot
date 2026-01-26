
import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.notion_service import NotionService
from app.services.sheets_service import SheetsService

logger = logging.getLogger(__name__)

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /sync command.
    Usage: /sync notion | /sync sheets
    """
    user = update.effective_user
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "⚠️ Использование: `/sync <service>`\n"
            "Доступные сервисы: `notion`, `sheets`",
            parse_mode="Markdown"
        )
        return

    service_name = args[0].lower()
    
    if service_name == "notion":
        await sync_notion(update, context)
    elif service_name == "sheets":
        await sync_sheets(update, context)
    else:
        await update.message.reply_text(f"❌ Неизвестный сервис: {service_name}")

async def sync_notion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status_msg = await update.message.reply_text("🔄 Начинаю синхронизацию с Notion...")
    
    try:
        async with AsyncSessionLocal() as session:
            # Check user permission/existence
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username)
            
            # Fetch all contacts
            contact_service = ContactService(session)
            contacts = await contact_service.get_all_contacts(db_user.id)
            
            if not contacts:
                await status_msg.edit_text("❌ У вас нет контактов для синхронизации.")
                return

            # Sync
            notion_service = NotionService()
            result = await notion_service.sync_contacts(contacts)
            
            if "error" in result:
                await status_msg.edit_text(f"❌ Ошибка: {result['error']}")
                return

        # Success report
        await status_msg.edit_text(
            f"✅ Синхронизация завершена (Notion)!\n\n"
            f"🆕 Создано: {result['created']}\n"
            f"🔄 Обновлено: {result['updated']}\n"
            f"⚠️ Ошибок: {result['failed']}"
        )

    except Exception as e:
        logger.error(f"Error executing sync notion: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при синхронизации.")

async def sync_sheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status_msg = await update.message.reply_text("🔄 Начинаю синхронизацию с Google Sheets...")
    
    try:
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            await user_service.get_or_create_user(user.id, user.username)
            
            contact_service = ContactService(session)
            contacts = await contact_service.get_all_contacts(user.id)
            
            if not contacts:
                await status_msg.edit_text("❌ Нет контактов.")
                return

            service = SheetsService()
            result = await service.sync_contacts(contacts)
            
            if "error" in result:
                await status_msg.edit_text(f"❌ Ошибка: {result['error']}")
                return

        await status_msg.edit_text(
            f"✅ Синхронизация завершена (Sheets)!\n\n"
            f"🆕 Добавлено: {result['created']}\n"
            f"🔄 Обновлено: {result['updated']} (частично)\n"
            f"⚠️ Ошибок: {result['failed']}"
        )

    except Exception as e:
        logger.error(f"Error executing sync sheets: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при синхронизации.")
