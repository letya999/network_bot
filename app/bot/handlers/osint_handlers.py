"""
OSINT & Enrichment Bot Handlers

Handlers for:
- /enrich command - manual enrichment trigger
- /import command - LinkedIn CSV import
- Enrichment callbacks
"""

import logging
import uuid
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.osint_service import OSINTService
from app.services.csv_service import CSVImportService
from app.bot.views import format_osint_data
from app.models.contact import Contact
from app.bot.rate_limiter import rate_limit_middleware

logger = logging.getLogger(__name__)

# Conversation states for import
WAITING_FOR_CSV = 1


async def enrich_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /enrich [contact_name] - Step 1: Search for potential profiles.
    """
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    query = " ".join(context.args) if context.args else None

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        contact_service = ContactService(session)
        user_settings = db_user.settings or {}
        osint_service = OSINTService(
            session,
            tavily_api_key=user_settings.get("tavily_api_key"),
            gemini_api_key=user_settings.get("gemini_api_key")
        )

        contact = None

        if query:
            contacts = await contact_service.find_contacts(db_user.id, query)
            if not contacts:
                await update.message.reply_text(f"❌ Контакт '{query}' не найден.")
                return
            
            if len(contacts) > 1:
                # Ambiguous contact name
                keyboard = []
                for c in contacts[:5]:
                    keyboard.append([InlineKeyboardButton(f"🔍 {c.name} ({c.company or 'No Company'})", callback_data=f"enrich_start_{c.id}")])
                await update.message.reply_text("Уточни контакт:", reply_markup=InlineKeyboardMarkup(keyboard))
                return
                
            contact = contacts[0]
        else:
            # Last mentioned
            last_contact_id = context.user_data.get("last_contact_id") or context.user_data.get("last_voice_id")
            if last_contact_id:
                contact = await session.get(Contact, last_contact_id)

            if not contact:
                await update.message.reply_text("❓ Кого обогатить? Напиши `/enrich Имя`")
                return

        # Start Search
        msg = await update.message.reply_text(f"🕵️‍♂️ Ищу профили *{contact.name}*...", parse_mode="Markdown")
        
        candidates = await osint_service.search_potential_profiles(contact.id)
        
        if not candidates:
            await msg.edit_text(f"🤷‍♂️ Не нашел профилей LinkedIn для *{contact.name}*.\nПопробуй добавить ссылку вручную через редактирование профиля.", parse_mode="Markdown")
            return

        # Store candidates in user_data to retrieve URL later
        # key: enrich_candidates_{contact_id}
        context.user_data[f"enrich_candidates_{contact.id}"] = candidates
        
        keyboard = []
        for idx, cand in enumerate(candidates[:5]):
            # Button: "Name - Role"
            btn_text = cand['name'][:40] 
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"enrich_select_{contact.id}_{idx}")])
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_enrich")])

        await msg.edit_text(
            f"🔎 Нашел {len(candidates)} профилей для *{contact.name}*.\nВыберите правильный:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )


async def enrich_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle selection of a profile."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_enrich":
        await query.edit_message_text("❌ Обогащение отменено.")
        return

    if data.startswith("enrich_start_"):
        # Selected contact from ambiguous list, restart search flow
        contact_id = data.split("_")[2]
        # Recursively call search logic (simulating command)
        # But we need fresh session. Easier to just tell user to click again or refactor.
        # Let's just trigger the search here.
        async with AsyncSessionLocal() as session:
             contact = await session.get(Contact, contact_id)
             if contact:
                 # Clean way: redirect to search logic, but we need to Duplicate code slightly or split func
                 # For brevity, let's just edit message "Searching..." and call search_potential_profiles
                 # Re-init service with creds
                 user_service = UserService(session)
                 db_user = await user_service.get_or_create_user(update.effective_user.id)
                 user_settings = db_user.settings or {}
                 
                 osint_service = OSINTService(
                    session,
                    tavily_api_key=user_settings.get("tavily_api_key"),
                    gemini_api_key=user_settings.get("gemini_api_key")
                 )
                 await query.edit_message_text(f"🕵️‍♂️ Ищу профили *{contact.name}*...", parse_mode="Markdown")
                 candidates = await osint_service.search_potential_profiles(contact.id)
                 if not candidates:
                     await query.edit_message_text("🤷‍♂️ Профили не найдены.")
                     return
                 
                 context.user_data[f"enrich_candidates_{contact.id}"] = candidates
                 keyboard = [[InlineKeyboardButton(c['name'][:40], callback_data=f"enrich_select_{contact.id}_{i}")] for i, c in enumerate(candidates[:5])]
                 keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_enrich")])
                 await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
                 await query.edit_message_text(f"🔎 Нашел профили для *{contact.name}*. Выбери:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data.startswith("enrich_select_"):
        # User selected a specific profile index
        parts = data.split("_")
        contact_id = parts[2]
        index = int(parts[3])
        
        candidates = context.user_data.get(f"enrich_candidates_{contact_id}")
        if not candidates or index >= len(candidates):
            await query.edit_message_text("⚠️ Данные устарели. Повторите поиск через /enrich.")
            return

        selected_candidate = candidates[index]
        linkedin_url = selected_candidate["url"]
        
        await query.edit_message_text(f"⏳ Анализирую профиль: {linkedin_url}\n_Это займет 10-20 секунд..._", parse_mode="Markdown")
        
        async with AsyncSessionLocal() as session:
            # Need user settings
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(update.effective_user.id)
            user_settings = db_user.settings or {}
            
            osint_service = OSINTService(
                session,
                tavily_api_key=user_settings.get("tavily_api_key"),
                gemini_api_key=user_settings.get("gemini_api_key")
            )
            try:
                result = await osint_service.enrich_contact_final(uuid.UUID(contact_id), linkedin_url)
                
                if result["status"] == "success":
                    formatted = format_osint_data(result["data"])
                    await query.edit_message_text(
                        f"✅ Информация обновлена!\n\n{formatted}",
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                else:
                    await query.edit_message_text(f"❌ Ошибка: {result.get('message')}")
                    
            except Exception as e:
                try:
                    await session.rollback()
                except Exception:
                    pass
                logger.exception(f"Deep enrich error: {e}")
                await query.edit_message_text("❌ Произошла ошибка при анализе профиля.")


async def show_osint_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /osint [contact_name] - Show OSINT data for a contact.
    """
    user = update.effective_user
    query = " ".join(context.args) if context.args else None

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        contact_service = ContactService(session)
        contact = None

        if query:
            contacts = await contact_service.find_contacts(db_user.id, query)
            if not contacts:
                await update.message.reply_text(f"❌ Контакт '{query}' не найден.")
                return
            contact = contacts[0]
        else:
            last_contact_id = context.user_data.get("last_contact_id")
            if last_contact_id:
                contact = await session.get(Contact, last_contact_id)

        if not contact:
            await update.message.reply_text(
                "❓ Укажи имя контакта.\n"
                "Пример: `/osint Иван`",
                parse_mode="Markdown"
            )
            return

        if not contact.osint_data or contact.osint_data.get("no_results"):
            # Offer to enrich
            keyboard = [[
                InlineKeyboardButton("🔍 Найти информацию", callback_data=f"enrich_{contact.id}")
            ]]
            await update.message.reply_text(
                f"ℹ️ *{contact.name}*\n\n"
                "Публичная информация ещё не собрана.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        formatted = format_osint_data(contact.osint_data)
        keyboard = [[
            InlineKeyboardButton("🔄 Обновить", callback_data=f"enrich_{contact.id}")
        ]]
        await update.message.reply_text(
            f"📊 *{contact.name}* — публичная информация:\n\n"
            f"{formatted}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )


# LinkedIn CSV Import

async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /import - Start LinkedIn CSV import process.
    """
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message

    await message.reply_text(
        "📥 *Импорт контактов из LinkedIn*\n\n"
        "Чтобы экспортировать контакты из LinkedIn:\n"
        "1. Перейди в Settings & Privacy → Data Privacy\n"
        "2. Get a copy of your data → Connections\n"
        "3. Скачай CSV файл\n\n"
        "Отправь мне CSV файл с контактами.\n"
        "Отправь /cancel для отмены.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_CSV


async def handle_csv_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded CSV file."""
    if not await rate_limit_middleware(update, context):
        return ConversationHandler.END

    user = update.effective_user
    document = update.message.document

    # Validate file
    if not document:
        await update.message.reply_text("❌ Пожалуйста, отправь CSV файл.")
        return WAITING_FOR_CSV

    file_name = document.file_name or ""
    error = CSVImportService.validate_csv_file(file_name, document.file_size)
    if error:
        await update.message.reply_text(f"❌ {error}")
        return WAITING_FOR_CSV

    status_msg = await update.message.reply_text("⏳ Обрабатываю файл...")

    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        content = file_bytes.decode("utf-8")

        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

            csv_service = CSVImportService(session)
            imported, skipped, errors = await csv_service.import_linkedin_csv(db_user.id, content)

            # Summary
            summary = f"✅ *Импорт завершён!*\n\n"
            summary += f"📥 Импортировано: {imported}\n"
            if skipped:
                summary += f"⏭️ Пропущено (дубликаты): {skipped}\n"
            if errors:
                summary += f"❌ Ошибок: {len(errors)}\n"

            await status_msg.edit_text(summary, parse_mode="Markdown")

    except UnicodeDecodeError:
        await status_msg.edit_text(
            "❌ Не могу прочитать файл. Убедись, что это CSV в кодировке UTF-8."
        )
    except Exception as e:
        logger.exception(f"Error importing CSV: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при импорте.")

    return ConversationHandler.END


async def cancel_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel import process."""
    await update.message.reply_text("🚫 Импорт отменён.")
    return ConversationHandler.END


async def enrichment_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /enrich_stats - Show enrichment statistics.
    """
    user = update.effective_user

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id)

        osint_service = OSINTService(session)
        stats = await osint_service.get_enrichment_stats(db_user.id)

        total = stats["total_contacts"]
        enriched = stats["enriched_contacts"]
        pending = stats["pending_enrichment"]

        # Progress bar
        if total > 0:
            progress = enriched / total
            bar_length = 10
            filled = int(progress * bar_length)
            bar = "█" * filled + "░" * (bar_length - filled)
            percent = int(progress * 100)
        else:
            bar = "░" * 10
            percent = 0

        text = (
            f"📊 *Статистика обогащения*\n\n"
            f"Всего контактов: {total}\n"
            f"Обогащено: {enriched}\n"
            f"Ожидают: {pending}\n\n"
            f"[{bar}] {percent}%"
        )

        if pending > 0:
            keyboard = [[
                InlineKeyboardButton(
                    f"🔍 Обогатить {min(pending, 5)} контактов",
                    callback_data="batch_enrich"
                )
            ]]
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(text, parse_mode="Markdown")


async def batch_enrich_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle batch enrichment button."""
    query = update.callback_query
    await query.answer("Запускаю обогащение...")

    user = update.effective_user
    await query.edit_message_text("🔍 Обогащаю контакты... (это может занять минуту)")

    try:
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id)

            user_settings = db_user.settings or {}
            osint_service = OSINTService(
                session,
                tavily_api_key=user_settings.get("tavily_api_key"),
                gemini_api_key=user_settings.get("gemini_api_key")
            )
            result = await osint_service.batch_enrich(db_user.id, limit=5)

            if result["status"] == "complete":
                await query.edit_message_text("✅ Все контакты уже обогащены!")
            else:
                text = f"✅ Обогащено контактов: {result['enriched']}"
                if result.get("errors"):
                    text += f"\n❌ Ошибок: {len(result['errors'])}"
                await query.edit_message_text(text)

    except Exception as e:
        logger.exception(f"Error in batch enrich: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")
