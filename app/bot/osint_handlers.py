"""
OSINT & Enrichment Bot Handlers

Handlers for:
- /enrich command - manual enrichment trigger
- /import command - LinkedIn CSV import
- Enrichment callbacks
"""

import logging
import csv
import io
import uuid
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.osint_service import OSINTService, format_osint_data
from app.models.contact import Contact
from app.bot.rate_limiter import rate_limit_middleware

logger = logging.getLogger(__name__)

# Conversation states for import
WAITING_FOR_CSV = 1


async def enrich_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /enrich [contact_name] - Enrich a contact with OSINT data.
    If no name provided, enriches the last mentioned contact.
    """
    if not await rate_limit_middleware(update, context):
        return

    user = update.effective_user
    query = " ".join(context.args) if context.args else None

    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

        contact_service = ContactService(session)
        osint_service = OSINTService(session)

        contact = None

        if query:
            # Search for contact by name
            contacts = await contact_service.find_contacts(db_user.id, query)
            if not contacts:
                await update.message.reply_text(
                    f"❌ Контакт '{query}' не найден.\n"
                    "Используй /find для поиска контактов."
                )
                return

            if len(contacts) > 1:
                # Show selection buttons
                keyboard = []
                for c in contacts[:5]:
                    name_display = c.name
                    if c.company:
                        name_display += f" ({c.company})"
                    keyboard.append([
                        InlineKeyboardButton(
                            f"🔍 {name_display}",
                            callback_data=f"enrich_{c.id}"
                        )
                    ])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Найдено {len(contacts)} контактов. Выбери кого обогатить:",
                    reply_markup=reply_markup
                )
                return

            contact = contacts[0]
        else:
            # Try to get last contact from context
            last_contact_id = context.user_data.get("last_contact_id")
            last_voice_id = context.user_data.get("last_voice_id")

            contact_id = last_contact_id or last_voice_id
            if contact_id:
                contact = await session.get(Contact, contact_id)

            if not contact:
                await update.message.reply_text(
                    "❓ Укажи имя контакта для обогащения.\n"
                    "Пример: `/enrich Иван Петров`",
                    parse_mode="Markdown"
                )
                return

        # Perform enrichment
        status_msg = await update.message.reply_text(
            f"🔍 Ищу публичную информацию о *{contact.name}*...\n"
            "_Это может занять несколько секунд_",
            parse_mode="Markdown"
        )

        try:
            result = await osint_service.enrich_contact(contact.id)

            if result["status"] == "success":
                formatted = format_osint_data(result["data"])
                await status_msg.edit_text(
                    f"✅ *{contact.name}* — информация обновлена!\n\n"
                    f"{formatted}",
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            elif result["status"] == "cached":
                formatted = format_osint_data(result["data"])
                await status_msg.edit_text(
                    f"💾 *{contact.name}* — уже обогащён\n\n"
                    f"{formatted}\n\n"
                    "_Используй_ `/enrich {contact.name} --force` _для повторного поиска_",
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            elif result["status"] == "no_results":
                await status_msg.edit_text(
                    f"ℹ️ *{contact.name}*\n\n"
                    "Публичная информация не найдена.\n"
                    "Попробуй уточнить компанию или добавить LinkedIn вручную.",
                    parse_mode="Markdown"
                )
            else:
                await status_msg.edit_text(
                    f"❌ Ошибка: {result.get('message', 'Unknown error')}"
                )

        except Exception as e:
            logger.exception(f"Error enriching contact: {e}")
            await status_msg.edit_text(
                "❌ Произошла ошибка при обогащении. Попробуй позже."
            )


async def enrich_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle enrichment button callback."""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("enrich_"):
        return

    contact_id = query.data[7:]  # Strip "enrich_"
    user = update.effective_user

    await query.edit_message_text("🔍 Ищу публичную информацию...")

    try:
        async with AsyncSessionLocal() as session:
            # Verify user owns this contact
            contact = await session.get(Contact, contact_id)
            if not contact:
                await query.edit_message_text("❌ Контакт не найден.")
                return

            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id)

            if contact.user_id != db_user.id:
                await query.edit_message_text("❌ У тебя нет доступа к этому контакту.")
                return

            osint_service = OSINTService(session)
            result = await osint_service.enrich_contact(uuid.UUID(contact_id))

            if result["status"] == "success":
                formatted = format_osint_data(result["data"])
                await query.edit_message_text(
                    f"✅ *{contact.name}* — информация обновлена!\n\n"
                    f"{formatted}",
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            elif result["status"] == "no_results":
                await query.edit_message_text(
                    f"ℹ️ *{contact.name}*\n\n"
                    "Публичная информация не найдена.",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    f"❌ {result.get('message', 'Ошибка')}"
                )

    except Exception as e:
        logger.exception(f"Error in enrich callback: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")


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
    await update.message.reply_text(
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

    if document.file_size > 5 * 1024 * 1024:  # 5MB limit
        await update.message.reply_text("❌ Файл слишком большой. Максимум 5 МБ.")
        return WAITING_FOR_CSV

    file_name = document.file_name or ""
    if not file_name.endswith(".csv"):
        await update.message.reply_text("❌ Пожалуйста, отправь файл в формате CSV.")
        return WAITING_FOR_CSV

    status_msg = await update.message.reply_text("⏳ Обрабатываю файл...")

    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        content = file_bytes.decode("utf-8")

        # Parse CSV
        reader = csv.DictReader(io.StringIO(content))

        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(user.id, user.username, user.first_name)

            contact_service = ContactService(session)

            imported = 0
            skipped = 0
            errors = []

            for row in reader:
                try:
                    # LinkedIn export format varies, try common field names
                    first_name = row.get("First Name", row.get("first_name", ""))
                    last_name = row.get("Last Name", row.get("last_name", ""))
                    name = f"{first_name} {last_name}".strip()

                    if not name:
                        skipped += 1
                        continue

                    company = row.get("Company", row.get("company", ""))
                    position = row.get("Position", row.get("position", row.get("Title", "")))
                    email = row.get("Email Address", row.get("email", ""))
                    linkedin_url = row.get("URL", row.get("Profile URL", row.get("linkedin_url", "")))

                    # Check for duplicates
                    existing = await contact_service.find_contacts(db_user.id, name)
                    if existing:
                        # Check if it's the same person (same company)
                        for ex in existing:
                            if ex.company and company and ex.company.lower() == company.lower():
                                skipped += 1
                                break
                        else:
                            # Different company, might be different person - import anyway
                            pass

                    # Create contact data
                    contact_data = {
                        "name": name,
                        "company": company if company else None,
                        "role": position if position else None,
                        "email": email if email else None,
                        "linkedin_url": linkedin_url if linkedin_url else None,
                        "notes": "Imported from LinkedIn CSV",
                    }

                    # Connected On date if available
                    connected_on = row.get("Connected On", "")
                    if connected_on:
                        try:
                            event_date = datetime.strptime(connected_on, "%d %b %Y")
                            contact_data["event_date"] = event_date.date()
                            contact_data["event"] = "LinkedIn Connection"
                        except ValueError:
                            pass

                    await contact_service.create_contact(db_user.id, contact_data)
                    imported += 1

                except Exception as e:
                    logger.error(f"Error importing row: {e}")
                    errors.append(str(e))

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

            osint_service = OSINTService(session)
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
