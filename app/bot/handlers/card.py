import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.profile_service import ProfileService
from app.services.card_service import CardService
from app.services.gemini_service import GeminiService
from app.models.contact import Contact

logger = logging.getLogger(__name__)

async def generate_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback for generating a personalized digital card for a specific contact.
    If user has multiple pitches, offers to select one first.
    """
    query = update.callback_query
    await query.answer("Генерирую визитку...")
    
    data = query.data
    if not data.startswith("gen_card_"):
        return
        
    target_id = data[9:] # strip "gen_card_"
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.get_or_create_user(user.id)
        
        target_contact = await session.get(Contact, target_id)
        if not target_contact:
            await query.message.reply_text("❌ Контакт не найден.")
            return

        profile_service = ProfileService(session)
        my_profile = await profile_service.get_profile(user.id)
        
        # Check if user has multiple pitches
        if my_profile.pitches and len(my_profile.pitches) > 1:
            # Offer pitch selection
            keyboard = []
            for idx, pitch in enumerate(my_profile.pitches[:5]):  # Max 5 pitches
                preview = pitch[:30] + "..." if len(pitch) > 30 else pitch
                keyboard.append([
                    InlineKeyboardButton(
                        f"🎯 {preview}", 
                        callback_data=f"card_pitch_{target_id}_{idx}"
                    )
                ])
            keyboard.append([
                InlineKeyboardButton("❌ Без питча", callback_data=f"card_pitch_{target_id}_none")
            ])
            
            await query.message.reply_text(
                "🚀 *Выберите питч для визитки:*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        # Generate card without pitch selection (no pitches or only one)
        selected_pitch = my_profile.pitches[0] if my_profile.pitches else None
        await _generate_and_send_card(query.message, user.id, target_contact, my_profile, selected_pitch)


async def card_pitch_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback for pitch selection when generating a card.
    Format: card_pitch_{contact_id}_{pitch_index|none}
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("card_pitch_"):
        return
    
    parts = data.split("_")
    if len(parts) < 4:
        return
    
    target_id = parts[2]
    pitch_selection = parts[3]
    
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        target_contact = await session.get(Contact, target_id)
        if not target_contact:
            await query.edit_message_text("❌ Контакт не найден.")
            return
        
        profile_service = ProfileService(session)
        my_profile = await profile_service.get_profile(user.id)
        
        # Get selected pitch
        selected_pitch = None
        if pitch_selection != "none":
            try:
                pitch_idx = int(pitch_selection)
                if 0 <= pitch_idx < len(my_profile.pitches):
                    selected_pitch = my_profile.pitches[pitch_idx]
            except ValueError:
                pass
        
        await query.delete_message()
        await _generate_and_send_card(query.message, user.id, target_contact, my_profile, selected_pitch)


async def _generate_and_send_card(
    message,
    user_telegram_id: int,
    target_contact: Contact,
    my_profile,
    selected_pitch: str = None
):
    """
    Internal helper to generate and send the card.
    """
    status_msg = await message.reply_text("⏳ Читаю профили и придумываю интро...")
    
    try:
        gemini = GeminiService()
        
        # Prepare contextual information
        target_info = [f"Name: {target_contact.name}"]
        if target_contact.company: target_info.append(f"Company: {target_contact.company}")
        if target_contact.role: target_info.append(f"Role: {target_contact.role}")
        if target_contact.what_looking_for: target_info.append(f"Looking for: {target_contact.what_looking_for}")
        if target_contact.can_help_with: target_info.append(f"Can help with: {target_contact.can_help_with}")
        if target_contact.topics: target_info.append(f"Topics: {', '.join(target_contact.topics)}")

        my_info = [
            f"Name: {my_profile.full_name}",
            f"Bio: {my_profile.bio}",
            f"Job: {my_profile.job_title} at {my_profile.company}",
            f"Interests: {', '.join(my_profile.interests or [])}"
        ]
        
        if selected_pitch:
            my_info.append(f"Pitch: {selected_pitch}")
        
        intro = await gemini.customize_card_intro("\n".join(my_info), "\n".join(target_info))
        card_text = CardService.generate_text_card(my_profile, intro_text=intro, pitch=selected_pitch)
        
        await status_msg.delete()
        await message.reply_text(
            f"📨 *Персонализированная визитка для {target_contact.name}*:\n\n{card_text}",
            parse_mode="Markdown"
        )
    except Exception:
        logger.exception("Error generating card")
        await status_msg.edit_text("❌ Произошла ошибка при генерации.")

