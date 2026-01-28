import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from app.db.session import AsyncSessionLocal
from app.services.profile_service import ProfileService
from app.schemas.profile import ContentItem

# States for conversation
ASSET_MENU = "ASSET_MENU"
ASSET_INPUT_NAME = "ASSET_INPUT_NAME"
ASSET_INPUT_CONTENT = "ASSET_INPUT_CONTENT"

# Configuration for different asset types
ASSET_CONFIG = {
    "pitch": {
        "field": "pitches",
        "label": "Питч",
        "plural": "Питчи",
        "emoji": "🚀",
        "command": "pitches"
    },
    "one_pager": {
        "field": "one_pagers",
        "label": "Ванпейджер",
        "plural": "Ванпейджеры",
        "emoji": "📄",
        "command": "onepagers"
    },
    "greeting": {
        "field": "welcome_messages",
        "label": "Приветствие",
        "plural": "Приветствия",
        "emoji": "👋",
        "command": "greetings"
    }
}

async def start_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for asset commands"""
    # Try to determine type from command if it's a message
    if update.message and update.message.text:
        command = update.message.text.replace("/", "").split("@")[0]
        
        # Determine type based on command
        asset_type = None
        for k, v in ASSET_CONFIG.items():
            if v["command"] == command:
                asset_type = k
                break
        
        if asset_type:
            context.user_data["current_asset_type"] = asset_type
            
    # If no type determined (and not set previously by wrapper), error
    if not context.user_data.get("current_asset_type"):
        if update.message:
            await update.message.reply_text("❌ Неизвестная команда.")
        return ConversationHandler.END
        
    return await show_asset_list(update, context)

async def show_asset_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset_type = context.user_data.get("current_asset_type")
    if not asset_type:
        return ConversationHandler.END
        
    config = ASSET_CONFIG[asset_type]
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        
    items = getattr(profile, config["field"], [])
    
    text = f"{config['emoji']} *Ваши {config['plural']}*\n\n"
    if not items:
        text += "Список пуст. Добавьте первый!"
    else:
        text += "Выберите элемент для просмотра или редактирования:"
        
    keyboard = []
    for item in items:
        # Compatibility with strings if migration failed or legacy data
        name = item.name if hasattr(item, "name") else (item[:20] + "...")
        item_id = item.id if hasattr(item, "id") else "legacy"
        
        keyboard.append([InlineKeyboardButton(f"{name}", callback_data=f"asset_view_{item_id}")])
        
    keyboard.append([InlineKeyboardButton(f"➕ Добавить {config['label']}", callback_data="asset_add")])
    keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data="asset_exit")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        
    return ASSET_MENU

async def asset_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "asset_exit":
        await query.delete_message()
        return ConversationHandler.END
        
    if data == "asset_add":
        # Clear any previous edit state
        context.user_data.pop("edit_mode", None)
        context.user_data.pop("current_asset_id", None)
        
        config = ASSET_CONFIG[context.user_data["current_asset_type"]]
        await query.edit_message_text(
            f"Введите *название* для нового {config['label']} (для кнопок):\n\n_Нажмите /cancel для отмены_",
            parse_mode="Markdown"
        )
        return ASSET_INPUT_NAME
        
    if data.startswith("asset_view_"):
        item_id = data.replace("asset_view_", "")
        context.user_data["current_asset_id"] = item_id
        return await show_asset_detail(update, context)
        
    return ASSET_MENU

async def show_asset_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset_type = context.user_data.get("current_asset_type")
    item_id = context.user_data.get("current_asset_id")
    config = ASSET_CONFIG[asset_type]
    
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
    
    items = getattr(profile, config["field"], [])
    # Find item
    target_item = next((i for i in items if hasattr(i, "id") and i.id == item_id), None)
    
    if not target_item:
        await update.callback_query.edit_message_text("❌ Элемент не найден.")
        return await show_asset_list(update, context)
        
    text = f"{config['emoji']} *{target_item.name}*\n\n"
    text += f"{target_item.content}"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изм. Название", callback_data="asset_edit_name"),
         InlineKeyboardButton("📝 Изм. Текст", callback_data="asset_edit_content")],
        [InlineKeyboardButton("❌ Удалить", callback_data="asset_delete")],
        [InlineKeyboardButton("🔙 Назад", callback_data="asset_back")]
    ]
    
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ASSET_MENU

async def asset_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle actions inside detail view"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "asset_back":
        return await show_asset_list(update, context)
        
    if data == "asset_delete":
        # Delete confirm? maybe just delete for speed
        return await delete_asset(update, context)
        
    if data == "asset_edit_name":
        await query.edit_message_text("Введите новое *название*:", parse_mode="Markdown")
        context.user_data["edit_mode"] = "name"
        return ASSET_INPUT_NAME
        
    if data == "asset_edit_content":
        await query.edit_message_text("Введите новый *текст/ссылку*:", parse_mode="Markdown")
        context.user_data["edit_mode"] = "content"
        return ASSET_INPUT_CONTENT
        
    return ASSET_MENU

async def save_asset_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    user = update.effective_user
    asset_type = context.user_data["current_asset_type"]
    config = ASSET_CONFIG[asset_type]
    
    # Check if we are adding new or editing existing
    edit_mode = context.user_data.get("edit_mode")
    
    if edit_mode == "name":
        # Editing existing name
        item_id = context.user_data["current_asset_id"]
        found = False
        
        async with AsyncSessionLocal() as session:
            service = ProfileService(session)
            profile = await service.get_profile(user.id)
            items = getattr(profile, config["field"], [])
            
            for item in items:
                if item.id == item_id:
                    item.name = name
                    found = True
                    break
            
            if found:
                serialized_items = [i.model_dump(mode='json') for i in items]
                await service.update_profile_field(user.id, config["field"], serialized_items)
            
        if found:
            await update.message.reply_text("✅ Название обновлено!")
            return await show_asset_detail_message(update, context)
        else:
            await update.message.reply_text("❌ Элемент не найден.")
            return await show_asset_list(update, context)
    else:
        # Adding new -> First step is name, next is content
        context.user_data["new_asset_name"] = name
        await update.message.reply_text(
            f"Отлично. Теперь пришлите *текст* или ссылку для \"{name}\":",
            parse_mode="Markdown"
        )
        return ASSET_INPUT_CONTENT

async def save_asset_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text # Handle text only for now. TODO: files
    user = update.effective_user
    asset_type = context.user_data["current_asset_type"]
    config = ASSET_CONFIG[asset_type]
    
    edit_mode = context.user_data.get("edit_mode")
    
    found = True
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        items = getattr(profile, config["field"], [])
        
        if edit_mode == "content":
             item_id = context.user_data["current_asset_id"]
             found = False
             for item in items:
                if item.id == item_id:
                    item.content = content
                    found = True
                    break
        else:
            # Creating new
            name = context.user_data.get("new_asset_name", "Новый элемент")
            new_item = ContentItem(name=name, content=content, type="text")
            items.append(new_item)
            # Set ID for context so we can view it
            context.user_data["current_asset_id"] = new_item.id

        if found:
            serialized_items = [i.model_dump(mode='json') for i in items]
            await service.update_profile_field(user.id, config["field"], serialized_items)
        
    if found:
        await update.message.reply_text("✅ Сохранено!")
        if edit_mode:
            return await show_asset_detail_message(update, context)
        else:
            # If new item, show detail too, so they can see what they added
            return await show_asset_detail_message(update, context)
    else:
        await update.message.reply_text("❌ Элемент не найден.")
        return await show_asset_list(update, context)

async def delete_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = context.user_data.get("current_asset_id")
    asset_type = context.user_data.get("current_asset_type")
    config = ASSET_CONFIG[asset_type]
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
        items = getattr(profile, config["field"], [])
        
        # Filter out
        items = [i for i in items if i.id != item_id]
        
        serialized_items = [i.model_dump(mode='json') for i in items]
        await service.update_profile_field(user.id, config["field"], serialized_items)
        
    await update.callback_query.answer("🗑 Удалено")
    return await show_asset_list(update, context)

async def show_asset_detail_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Same as show_asset_detail but replies with new message (used after text input)
    asset_type = context.user_data.get("current_asset_type")
    item_id = context.user_data.get("current_asset_id")
    config = ASSET_CONFIG[asset_type]
    
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        service = ProfileService(session)
        profile = await service.get_profile(user.id)
    
    items = getattr(profile, config["field"], [])
    target_item = next((i for i in items if i.id == item_id), None)
    
    if not target_item:
        await update.message.reply_text("❌ Элемент не найден.")
        return await show_asset_list(update, context) # This sends new message
        
    text = f"{config['emoji']} *{target_item.name}*\n\n"
    text += f"{target_item.content}"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изм. Название", callback_data="asset_edit_name"),
         InlineKeyboardButton("📝 Изм. Текст", callback_data="asset_edit_content")],
        [InlineKeyboardButton("❌ Удалить", callback_data="asset_delete")],
        [InlineKeyboardButton("🔙 Назад", callback_data="asset_back")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ASSET_MENU

async def cancel_asset_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Отменено")
    return ConversationHandler.END

