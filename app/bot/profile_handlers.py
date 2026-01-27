from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import AsyncSessionLocal
from app.services.profile_service import ProfileService
from app.services.card_service import CardService

from app.bot.handlers.assets_handler import (
    show_asset_list, ASSET_MENU, ASSET_CONFIG, 
    ASSET_INPUT_NAME, ASSET_INPUT_CONTENT
)

# States
SELECT_FIELD, INPUT_VALUE = range(2)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show profile and return state for conversation"""
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        
    # Build text representation
    text = f"👤 *Ваш Профиль*\n\n"
    name = profile.full_name or user.first_name or "Без имени"
    text += f"*{name}*\n"
    
    if profile.job_title:
        text += f"💼 {profile.job_title}"
        if profile.company:
            text += f" @ {profile.company}"
        text += "\n"
    elif profile.company:
        text += f"🏢 {profile.company}\n"
        
    if profile.location:
        text += f"📍 {profile.location}\n"
    
    if profile.bio:
        text += f"\n📝 {profile.bio}\n"
        
    if profile.interests:
        text += f"\n⭐ *Интересы*: {', '.join(profile.interests)}\n"
        
    phone = profile.phone or "—"
    email = profile.email or "—"
    text += f"\n📞 *Контакты*:\n📱 {phone}\n📧 {email}\n"

    # Assets summary
    if profile.pitches:
        text += f"🚀 *Питчи*: {len(profile.pitches)}\n"
    if profile.one_pagers:
        text += f"📄 *Ванпейджеры*: {len(profile.one_pagers)}\n"
    if profile.welcome_messages:
        text += f"👋 *Приветствия*: {len(profile.welcome_messages)}\n"

    # Social links could be added here
        
    keyboard = [
        [InlineKeyboardButton("✏️ Имя", callback_data="edit_full_name"), InlineKeyboardButton("📝 Био", callback_data="edit_bio")],
        [InlineKeyboardButton("💼 Работа", callback_data="edit_job"), InlineKeyboardButton("📍 Город", callback_data="edit_location")],
        [InlineKeyboardButton("⭐ Интересы", callback_data="edit_interests"), InlineKeyboardButton("📞 Телефон", callback_data="edit_phone")],
        [InlineKeyboardButton("📧 Email", callback_data="edit_email"), InlineKeyboardButton("🚀 Питчи", callback_data="manage_pitches")],
        [InlineKeyboardButton("📄 Ванпейджеры", callback_data="manage_one_pagers"), InlineKeyboardButton("👋 Приветствия", callback_data="manage_welcome")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # If this comes from a callback (button click), edit the message
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        # Command /profile
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        
    return SELECT_FIELD

async def handle_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "close_profile":
        await query.delete_message()
        return ConversationHandler.END
        
    # Handle asset management transition
    if data == "manage_pitches":
        context.user_data["current_asset_type"] = "pitch"
        return await show_asset_list(update, context)
    if data == "manage_one_pagers":
        context.user_data["current_asset_type"] = "one_pager"
        return await show_asset_list(update, context)
    if data == "manage_welcome":
        context.user_data["current_asset_type"] = "greeting"
        return await show_asset_list(update, context)
        
    # Map callback data to field names defined in UserProfile schema (mostly)
    # or custom logic keys
    field_map = {
        "edit_full_name": "full_name",
        "edit_bio": "bio",
        "edit_job": "job_title", # Handling job & company together specific logic
        "edit_location": "location",
        "edit_interests": "interests",
        "edit_phone": "phone",
        "edit_email": "email",
    }
    
    field = field_map.get(data)
    if not field:
        # If it's one of the old keys but somehow passed through, ignore or handle
        return SELECT_FIELD
        
    context.user_data["edit_field"] = field
    
    prompts = {
        "full_name": "Введите ваше полное имя:",
        "bio": "Напишите кратко о себе (био):",
        "job_title": "Введите Должность и Компанию (например: CTO, NetworkBot):",
        "location": "Введите ваш Город/Локацию:",
        "interests": "Перечислите ваши интересы через запятую:",
        "phone": "Введите номер телефона:",
        "email": "Введите email:",
    }
    
    prompt_text = prompts.get(field, "Введите значение:")
    
    await query.edit_message_text(
        f"{prompt_text}\n\n_Нажмите /cancel чтобы отменить_",
        parse_mode="Markdown"
    )
    return INPUT_VALUE

async def save_profile_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    value = update.message.text
    field = context.user_data.get("edit_field")
    
    if not field:
        await update.message.reply_text("Ошибка контекста. Попробуйте /profile снова.")
        return ConversationHandler.END
    
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        
        # Special handling
        if field == "job_title":
            parts = [p.strip() for p in value.split(",", 1)]
            job = parts[0]
            company = parts[1] if len(parts) > 1 else None
            
            await service.update_profile_field(user.id, "job_title", job)
            if company:
                await service.update_profile_field(user.id, "company", company)
            elif len(parts) == 1 and "," not in value:
                pass
        elif field == "interests":
            # Split by comma
            items = [i.strip() for i in value.split(",")]
            items = [i for i in items if i] # Filter empty
            await service.update_profile_field(user.id, field, items)
        else:
            await service.update_profile_field(user.id, field, value)
            
    await update.message.reply_text("✅ Сохранено!")
    
    # We want to return to the profile view.
    # Since we are in a Message handler (user sent text), we can't edit the bot's previous message easily 
    # unless we saved its ID. But replying with new profile is standard.
    # But to keep state, we call show_profile which usually takes 'update'.
    # We can fake the update or just copy logic. 
    # Calling show_profile(update, context) works if it handles message updates (it does).
    return await show_profile(update, context)

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Редактирование отменено.")
    return ConversationHandler.END

async def send_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the user's business card info"""
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        
    card_text = CardService.generate_text_card(profile)
    await update.message.reply_text(card_text, parse_mode="Markdown")
    
async def share_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a deep link to share the card"""
    user = update.effective_user
    bot_username = context.bot.username
    
    # We use telegram_id for now. UUID might be safer but ID is public anyway if they message you.
    # Format: start=c_<id> (c for card)
    link = f"https://t.me/{bot_username}?start=c_{user.id}"
    
    await update.message.reply_text(
        f"🔗 *Твоя ссылка-визитка:*\n`{link}`\n\n"
        "Отправь её кому угодно, и они увидят твой профиль!",
        parse_mode="Markdown"
    )
