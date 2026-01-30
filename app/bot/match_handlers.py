import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.match_service import MatchService
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.models.contact import Contact
import uuid

logger = logging.getLogger(__name__)

async def find_matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manual trigger to find matches for the last active contact or general matches.
    """
    if update.callback_query:
        await update.callback_query.answer()

    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, username=user.username, first_name=user.full_name)
        
        # Determine context: specific contact or global
        # If called from "Matches" button in Networking menu, user might not have a "last_contact_id" set RECENTLY, 
        # or we explicitly want global.
        # Check if we have arguments or if we are just in "Networking" flow.
        # But `find_matches_command` is triggered by `cmd_matches` callback.
        
        # If we are coming from a specific contact view, we usually have `last_contact_id`.
        # However, if the user clicked "Networking" -> "Matches", they want GLOBAL matches.
        # If they clicked "Matches" INSIDE a contact card (if such button exists), they want specific.
        # Currently, the button on Contact Card is "✨ Визитка" or "Найти информацию". 
        # Wait, `get_contact_keyboard` has NO "Matches" button?
        # It has "✨ Визитка" (generate card) and "Enrich".
        # So "Matches" is ONLY in the Networking Menu.
        # BUT `notify_match_if_any` suggests matches.
        
        # The user says: "при переходе к конкретный контакт считались только между мной и им" -> this implies there IS a way to trigger matches for a contact.
        # Maybe I should ADD a button "Matches" to the Contact Card to support the second part of the request?
        # Or maybe the user means `notify_match_if_any` logic or the automatic check.
        
        # ACTUALLY, checking `match_handlers.py`:
        # `find_matches_command` uses `last_contact_id`.
        # `start_menu` -> `Networking` -> `cmd_matches`.
        # Taking "last_contact_id" from context might be stale (from a contact viewed 10 mins ago).
        
        # FIX:
        # 1. If triggered via `cmd_matches` (Networking Menu), do GLOBAL matches (User vs Network).
        # 2. To support "Specific Contact Matches", I should add a button `matches_<id>` to the Contact Card (in `common.py`).
        # 3. And handle `matches_<id>` in `match_handlers.py`.
        
        # Let's adjust `find_matches_command` to handle both `cmd_matches` (Global) and `matches_<uuid>` (Specific).
        
        target_contact_id = None
        is_global = True
        
        if update.callback_query and update.callback_query.data.startswith("matches_"):
             # Specific contact match requested
             target_contact_id = update.callback_query.data.replace("matches_", "")
             is_global = False
        elif context.user_data.get("last_contact_id") and not update.callback_query.data == "cmd_matches":
             # Fallback if triggered by command /matches while viewing a contact? 
             # But /matches command is usually global.
             # User said: "In Networking menu -> count for all. In specific contact -> count me vs him".
             # So default /matches or cmd_matches should be GLOBAL.
             # Only if explicit ID provided, do specific.
             pass

        from html import escape
        from app.bot.handlers.menu_handlers import NETWORKING_MENU
        from app.bot.handlers.contact_detail_handlers import CONTACT_VIEW_PREFIX

        match_service = MatchService(session)
        response = ""
        back_button = []

        if is_global:
            # Global Matches: User vs All Active Contacts
            status_msg = await update.effective_message.reply_text("🔍 Анализирую всю базу контактов на синергию с вами...")
            
            # Use a new method or iterate
            # We need to find matches where User <-> Contact is high.
            # Reuse find_peer_matches logic but for User?
            # match_service.get_user_matches takes (contact, user).
            
            contact_service = ContactService(session)
            all_contacts = await contact_service.get_recent_contacts(user.id, limit=20) # Limit 20 for now
            
            matches_found = []
            for c in all_contacts:
                # Basic check before heavy AI
                if not c.what_looking_for and not c.can_help_with:
                    continue
                    
                m = await match_service.get_user_matches(c, db_user)
                if m.get("is_match") and m.get("match_score", 0) > 65:
                    m['contact_name'] = c.name
                    m['contact_id'] = c.id
                    matches_found.append(m)
            
            await status_msg.delete()
            
            if matches_found:
                response = "✨ <b>Твои лучшие синергии:</b>\n\n"
                matches_found.sort(key=lambda x: x.get("match_score", 0), reverse=True)
                for m in matches_found[:5]:
                    response += f"👤 <b>{escape(m['contact_name'])}</b>: {escape(m.get('synergy_summary', ''))}\n"
                    response += f"💡 Питч: <i>{escape(m.get('suggested_pitch', ''))}</i>\n\n"
            else:
                response = "Пока не найдено сильных совпадений по всей базе. Попробуй дополнить профили контактов."
            
            back_button = [InlineKeyboardButton("⬅️ Назад", callback_data=NETWORKING_MENU)]

        else:
            # Specific Contact
            start_time = update.effective_message.date
            contact = await session.get(Contact, target_contact_id)
            if not contact:
                await update.effective_message.reply_text("Контакт не найден.")
                return

            status_msg = await update.effective_message.reply_text(f"🔍 Ищу синергии с {contact.name}...")
            
            # 1. Match with User Profile
            user_match = await match_service.get_user_matches(contact, db_user)
            
            await status_msg.delete()
            
            if user_match.get("is_match"):
                response += f"🎯 <b>С тобой:</b> {escape(user_match.get('synergy_summary', ''))}\n"
                response += f"💡 <b>Питч:</b> <i>{escape(user_match.get('suggested_pitch', ''))}</i>\n\n"
            else:
                response = f"🤷‍♂️ Явных синергий с <b>{escape(contact.name)}</b> не найдено.\n"
            
            back_button = [InlineKeyboardButton("⬅️ Назад к контакту", callback_data=f"{CONTACT_VIEW_PREFIX}{contact.id}")]

        keyboard = [back_button]
        await update.effective_message.reply_text(response, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

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
        
    from html import escape
    text = "🧠 <b>Результаты AI поиска:</b>\n\n"
    from app.models.contact import Contact
    for m in matches:
        contact_id = m.get("contact_id")
        reason = m.get("reason")
        
        contact = await session.get(Contact, contact_id)
        if contact:
            text += f"👤 <b>{escape(contact.name)}</b>\n"
            text += f"💡 {escape(reason)}\n\n"
            
    await message.reply_text(text, parse_mode="HTML")

async def notify_match_if_any(update: Update, contact, user, session):
    """
    Helper to notify user about a match immediately after adding a contact.
    """
    match_service = MatchService(session)
    match_data = await match_service.get_user_matches(contact, user)
    
    if match_data.get("is_match") and match_data.get("match_score", 0) > 70:
        from html import escape
        # Prepare contact display name
        contact_display = escape(contact.name)
        if contact.telegram_username:
            contact_display += f" (@{escape(contact.telegram_username.replace('@', ''))})"

        text = f"🎯 <b>Найден матч!</b>\n\n"
        text += f"Вы с {contact_display} можете быть полезны друг другу:\n"
        text += f"<i>{escape(match_data.get('synergy_summary', ''))}</i>\n\n"
        text += f"Предлагаемый питч: {escape(match_data.get('suggested_pitch', ''))}\n\n"

        # Add contact info block
        info_lines = []
        if contact.telegram_username:
            tg_clean = contact.telegram_username.replace('@', '')
            info_lines.append(f"✈️ @{escape(tg_clean)}")
        if contact.email:
            info_lines.append(f"📧 {escape(contact.email)}")
        if contact.linkedin_url:
            info_lines.append(f"🔗 {escape(contact.linkedin_url)}")
        
        if info_lines:
            text += "<b>Контакты:</b>\n" + "\n".join(info_lines)
        
        # Use a button to set a reminder
        keyboard = [[InlineKeyboardButton("⏰ Напомнить написать", callback_data=f"remind_{contact.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
