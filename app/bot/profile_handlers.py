from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import AsyncSessionLocal
from app.services.profile_service import ProfileService
from app.services.card_service import CardService
from app.schemas.profile import CustomContact

from app.bot.handlers.assets_handler import (
    show_asset_list, ASSET_MENU, ASSET_CONFIG, 
    ASSET_INPUT_NAME, ASSET_INPUT_CONTENT
)

# States
SELECT_FIELD, INPUT_VALUE, INPUT_CONTACT_LABEL, INPUT_CONTACT_VALUE = range(4)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show profile and return state for conversation"""
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        
    # Build text representation (HTML)
    text = f"👤 <b>Ваш Профиль</b>\n\n"
    name = profile.full_name or user.first_name or "Без имени"
    text += f"<b>{name}</b>\n"
    
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
        text += f"\n<i>{profile.bio}</i>\n"
        
    if profile.interests:
        text += f"\n⭐ <b>Интересы</b>: {', '.join(profile.interests)}\n"
        
    # Combined Contacts section
    text += "\n📞 <b>Контакты</b>:\n"
    
    has_contacts = False
    
    # Custom Contacts
    if profile.custom_contacts:
        for cc in profile.custom_contacts:
            if cc.value.startswith("http") or cc.value.startswith("t.me"):
                 text += f"• <a href=\"{cc.value}\">{cc.label}</a>\n"
            else:
                 text += f"• {cc.label}: {cc.value}\n"
        has_contacts = True
                 
    if not has_contacts:
        text += "_(пусто)_\n"

    # Social links could be added here
        
    keyboard = [
        [InlineKeyboardButton("✏️ Имя", callback_data="edit_full_name"), InlineKeyboardButton("📝 Био", callback_data="edit_bio")],
        [InlineKeyboardButton("💼 Работа", callback_data="edit_job"), InlineKeyboardButton("📍 Город", callback_data="edit_location")],
        [InlineKeyboardButton("⭐ Интересы", callback_data="edit_interests"), InlineKeyboardButton("🔗 Контакты (+)", callback_data="manage_custom_contacts")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # If this comes from a callback (button click), edit the message
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        # Command /profile
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        
    return SELECT_FIELD

async def handle_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "close_profile":
        await query.delete_message()
        return ConversationHandler.END
        
    # Handle asset management transition
    # Handle custom contacts
    if data == "manage_custom_contacts":
        return await show_custom_contacts_menu(update, context)
    
    if data == "add_contact":
        await query.edit_message_text(
            "Введите <b>название</b> для нового контакта (например: 'Мой сайт', 'LinkedIn', 'Портфолио'):\n\n<i>Нажмите /cancel для отмены</i>", 
            parse_mode="HTML"
        )
        return INPUT_CONTACT_LABEL
        
    if data.startswith("del_contact_"):
        cid = data.replace("del_contact_", "")
        return await delete_custom_contact(update, context, cid)
        
    if data == "back_to_profile":
        return await show_profile(update, context)
        
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
    
    # helper to reply whether it's a message or callback
    if update.callback_query:
        await update.callback_query.answer()
        # If called from button, we might want to send a NEW message, not edit
        await update.effective_message.reply_text(card_text, parse_mode="HTML")
    else:
        await update.message.reply_text(card_text, parse_mode="HTML")
    
async def share_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a deep link to share the card"""
    user = update.effective_user
    bot_username = context.bot.username
    
    # We use telegram_id for now.
    link = f"https://t.me/{bot_username}?start=c_{user.id}"
    
    text = (
        f"🔗 <b>Твоя ссылка-визитка:</b>\n<code>{link}</code>\n\n"
        "Отправь её кому угодно, и они увидят твой профиль!"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.effective_message.reply_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")

async def show_custom_contacts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
    
    text = "🔗 <b>Ссылки и контакты</b>\n\nСписок ваших дополнительных контактов:"
    keyboard = []
    
    if profile.custom_contacts:
        for cc in profile.custom_contacts:
            val = cc.value[:30] + "..." if len(cc.value) > 30 else cc.value
            text += f"\n• {cc.label}: {val}"
            keyboard.append([InlineKeyboardButton(f"❌ {cc.label}", callback_data=f"del_contact_{cc.id}")])
    else:
        text += "\n_(пусто)_"
        
    keyboard.append([InlineKeyboardButton("➕ Добавить контакт", callback_data="add_contact")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_profile")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Can be called from callback or message, usually callback from profile edit
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        
    return SELECT_FIELD

async def save_contact_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = update.message.text
    context.user_data["new_contact_label"] = label
    
    await update.message.reply_text(
        f"Отлично. Теперь пришлите <b>значение</b> (ссылку или текст) для \"{label}\":\n\n<i>Например: https://linkedin.com/in/username</i>", 
        parse_mode="HTML"
    )
    return INPUT_CONTACT_VALUE

async def save_contact_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text
    label = context.user_data.get("new_contact_label", "Контакт")
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        
        current = profile.custom_contacts or []
        new_contact = CustomContact(label=label, value=value)
        current.append(new_contact)
        
        # Serialize (ProfileService accepts dict update for custom field or we update UserProfile directly)
        # ProfileService.update_profile_field handles serialization if we pass list of dicts.
        # But here we have objects.
        # Let's adjust manually.
        serialized = [c.model_dump() for c in current]
        await service.update_profile_field(user.id, "custom_contacts", serialized)
        
    await update.message.reply_text("✅ Контакт добавлен!")
    return await show_custom_contacts_menu(update, context)

async def delete_custom_contact(update: Update, context: ContextTypes.DEFAULT_TYPE, contact_id: str):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        
        current = profile.custom_contacts or []
        # Filter
        new_list = [c for c in current if c.id != contact_id]
        
        if len(current) != len(new_list):
            serialized = [c.model_dump() for c in new_list]
            await service.update_profile_field(user.id, "custom_contacts", serialized)
            try: 
                 await update.callback_query.answer("🗑 Удалено") 
            except: pass
        else:
             try:
                 await update.callback_query.answer("❌ Не найдено")
             except: pass
             
    # Try to return to menu (might edit message)
    return await show_custom_contacts_menu(update, context)
