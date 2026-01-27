
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # Added imports

# ... (omitted)

async def sync_notion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    status_msg = await message.reply_text("🔄 Начинаю синхронизацию с Notion...")
    
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
            user_settings = db_user.settings or {}
            notion_service = NotionService(
                api_key=user_settings.get("notion_api_key"),
                database_id=user_settings.get("notion_database_id")
            )
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
    message = update.effective_message
    status_msg = await message.reply_text("🔄 Начинаю синхронизацию с Google Sheets...")
    
    try:
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username)
            
            contact_service = ContactService(session)
            contacts = await contact_service.get_all_contacts(db_user.id)
            
            if not contacts:
                await status_msg.edit_text("❌ Нет контактов.")
                return

            user_settings = db_user.settings or {}
            google_creds = {
                 "project_id": user_settings.get("google_proj_id"),
                 "private_key_id": user_settings.get("google_private_key_id"),
                 "private_key": user_settings.get("google_private_key"),
                 "client_email": user_settings.get("google_client_email")
            }
            # Clean empty keys
            google_creds = {k: v for k, v in google_creds.items() if v}

            service = SheetsService(
                sheet_id=user_settings.get("google_sheet_id"),
                google_creds=google_creds if google_creds else None
            )
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

async def export_contact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    # export_notion_{id} or export_sheets_{id}
    if data.startswith("export_notion_"):
        service_type = "notion"
        contact_id = data[14:]
    elif data.startswith("export_sheets_"):
        service_type = "sheets"
        contact_id = data[14:]
    else:
        return

    # User feedback
    # await query.message.reply_text(f"⏳ Экспорт контакта в {service_type}...")

    try:
        async with AsyncSessionLocal() as session:
            # Get Contact
            contact_service = ContactService(session)
            # contact_id is UUID string
            from app.models.contact import Contact
            contact = await session.get(Contact, contact_id)
            
            if not contact:
                await query.message.reply_text("❌ Контакт не найден.")
                return

            # Get User to fetch settings
            from app.models.user import User
            db_user = await session.get(User, contact.user_id)
            user_settings = db_user.settings if db_user else {}
            
            if service_type == "notion":
                service = NotionService(
                    api_key=user_settings.get("notion_api_key"),
                    database_id=user_settings.get("notion_database_id")
                )
                # We reuse sync_contacts but just for one
                result = await service.sync_contacts([contact])
            else:
                google_creds = {
                     "project_id": user_settings.get("google_proj_id"),
                     "private_key_id": user_settings.get("google_private_key_id"),
                     "private_key": user_settings.get("google_private_key"),
                     "client_email": user_settings.get("google_client_email")
                }
                google_creds = {k: v for k, v in google_creds.items() if v}
                
                service = SheetsService(
                    sheet_id=user_settings.get("google_sheet_id"),
                    google_creds=google_creds if google_creds else None
                )
                result = await service.sync_contacts([contact])

            if "error" in result:
                await query.message.reply_text(f"❌ Ошибка экспорта в {service_type}: {result['error']}")
            elif result['created'] > 0:
                await query.message.reply_text(f"✅ Контакт {contact.name} добавлен в {service_type}!")
            elif result['updated'] > 0:
                await query.message.reply_text(f"✅ Данные контакта {contact.name} обновлены в {service_type}!")
            else:
                 await query.message.reply_text(f"⚠️ Изменений в {service_type} не потребовалось.")

    except Exception as e:
        logger.error(f"Error single export to {service_type}: {e}")
        await query.message.reply_text(f"❌ Произошла ошибка: {e}")
