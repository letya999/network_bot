import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.match_service import MatchService
from app.services.user_service import UserService
from app.services.contact_service import ContactService
import uuid

logger = logging.getLogger(__name__)

async def find_matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manual trigger to find matches for the last active contact or general matches.
    """
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, username=user.username, first_name=user.full_name)
        
        last_contact_id = context.user_data.get("last_contact_id")
        if not last_contact_id:
            await update.message.reply_text("Сначала выбери или добавь контакт, чтобы найти для него матчи.")
            return

        contact_service = ContactService(session)
        from app.models.contact import Contact
        contact = await session.get(Contact, last_contact_id)
        
        if not contact:
            await update.message.reply_text("Контакт не найден.")
            return

        status_msg = await update.message.reply_text(f"🔍 Ищу синергии для {contact.name}...")
        
        match_service = MatchService(session)
        # 1. Match with User Profile
        user_match = await match_service.get_user_matches(contact, db_user)
        
        # 2. Match with other contacts
        peer_matches = await match_service.find_peer_matches(contact)
        
        await status_msg.delete()
        
        response = ""
        if user_match.get("is_match"):
            response += f"🎯 *С тобой:* {user_match.get('synergy_summary')}\n"
            response += f"💡 *Питч:* _{user_match.get('suggested_pitch')}_\n\n"
        
        if peer_matches:
            response += "🤝 *С другими контактами:*\n"
            for m in peer_matches:
                response += f"• *{m['peer_name']}*: {m['synergy_summary']}\n"
        
        if not response:
            response = "Явных синергий пока не найдено. Попробуй добавить больше информации о том, что человек ищет или чем может помочь."
            
        await update.message.reply_text(response, parse_mode="Markdown")

async def semantic_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Upgraded /find with semantic search capabilities.
    """
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Использование: /find <запрос>")
        return
        
    query = " ".join(context.args)
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, username=user.username, first_name=user.full_name)
        
        contact_service = ContactService(session)
        # First try basic search
        contacts = await contact_service.find_contacts(db_user.id, query)
        
        if contacts:
            # Show basic results
            text = f"🔍 Найдено {len(contacts)} контактов:\n\n"
            for i, c in enumerate(contacts, 1):
                text += f"{i}. {c.name} ({c.company or '?'})\n"
            
            keyboard = [[InlineKeyboardButton("🤖 Спросить AI (семантический поиск)", callback_data=f"semantic_{query[:30]}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup)
        else:
            # Fallback to semantic search immediately
            await perform_semantic_search(update.message, query, db_user.id, session)

async def semantic_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_data = update.callback_query.data
    query_text = query_data[9:] # strip "semantic_"
    user_id = update.effective_user.id
    
    await update.callback_query.answer("Запускаю AI поиск...")
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = update.effective_user
        db_user = await user_service.get_or_create_user(user.id, username=user.username, first_name=user.full_name)
        await perform_semantic_search(update.callback_query.message, query_text, db_user.id, session)

async def perform_semantic_search(message, query, user_id, session):
    placeholder = await message.reply_text("🧠 AI анализирует твои контакты...")
    
    match_service = MatchService(session)
    matches = await match_service.semantic_search(user_id, query)
    
    await placeholder.delete()
    
    if not matches:
        await message.reply_text("AI не нашёл ничего подходящего по смыслу.")
        return
        
    text = "🧠 *Результаты AI поиска:*\n\n"
    from app.models.contact import Contact
    for m in matches:
        contact_id = m.get("contact_id")
        reason = m.get("reason")
        
        contact = await session.get(Contact, contact_id)
        if contact:
            text += f"👤 *{contact.name}*\n"
            text += f"💡 {reason}\n\n"
            
    await message.reply_text(text, parse_mode="Markdown")

async def notify_match_if_any(update: Update, contact, user, session):
    """
    Helper to notify user about a match immediately after adding a contact.
    """
    match_service = MatchService(session)
    match_data = await match_service.get_user_matches(contact, user)
    
    if match_data.get("is_match") and match_data.get("match_score", 0) > 70:
        # Prepare contact display name
        contact_display = contact.name
        if contact.telegram_username:
            contact_display += f" (@{contact.telegram_username.replace('@', '')})"

        text = f"🎯 *Найден матч!*\n\n"
        text += f"Вы с {contact_display} можете быть полезны друг другу:\n"
        text += f"_{match_data.get('synergy_summary')}_\n\n"
        text += f"Предлагаемый питч: {match_data.get('suggested_pitch')}\n\n"

        # Add contact info block
        info_lines = []
        if contact.telegram_username:
            info_lines.append(f"✈️ @{contact.telegram_username.replace('@', '')}")
        if contact.email:
            info_lines.append(f"📧 {contact.email}")
        if contact.linkedin_url:
            info_lines.append(f"🔗 {contact.linkedin_url}")
        
        if info_lines:
            text += "*Контакты:*\n" + "\n".join(info_lines)
        
        # Use a button to set a reminder
        keyboard = [[InlineKeyboardButton("⏰ Напомнить написать", callback_data=f"remind_{contact.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
