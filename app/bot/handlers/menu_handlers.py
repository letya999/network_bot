
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.profile_service import ProfileService
from html import escape

logger = logging.getLogger(__name__)

async def cleanup_conversation_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Helper to delete the conversation message if it exists.
    Stores message IDs in context.user_data['conversation_message_id']
    
    CRITICAL: Updates context to remove ID, but ONLY deletes message if it is NOT 
    the current callback message. If it IS the current message, we let the next handler 
    (e.g. start_menu) edit it instead of deleting it.
    """
    try:
        msg_id = context.user_data.get('conversation_message_id')
        current_msg_id = update.callback_query.message.message_id if update.callback_query and update.callback_query.message else None
        
        if msg_id:
            # If the tracked message is DIFFERENT from the current button interaction,
            # it means it's an old/orphaned message. Delete it.
            if current_msg_id and msg_id == current_msg_id:
                # We are interacting with the tracked message. Do NOT delete it.
                # Just clear the tracker so we don't try to delete it later.
                # The caller (menu navigation) is expected to EDIT this message.
                pass
            elif update.effective_chat:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=msg_id
                    )
                except Exception as e:
                    logger.debug(f"Could not delete conversation message {msg_id}: {e}")
            
            # Always clear the tracker
            context.user_data.pop('conversation_message_id', None)
            
    except Exception as e:
        logger.debug(f"Error in cleanup_conversation_message: {e}")

async def cleanup_and_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, menu_type: str = None):
    """
    Cleanup any active conversation messages and show the specified menu.
    If menu_type is None, shows main menu.
    """
    await cleanup_conversation_message(update, context)
    
    if menu_type:
        # Create a fake callback query data to reuse menu_callback logic
        if update.callback_query:
            original_data = update.callback_query.data
            # Set data to target menu
            update.callback_query.data = menu_type 
            await menu_callback(update, context)
            # Restore check? Actually we don't need to restore.
        else:
            # If triggered via Command, we need to adapt since menu_callback expects callback_query
            # But menu_callback logic relies on edit_message_text which might fail if no message to edit
            # So for commands, we should SEND a new message with the specific menu content.
            
            # Re-use menu_callback logic by extracting it? Or just call logic here.
            # Let's call a helper verify_menu_content(menu_type) -> (text, markup)
            # Actually easier: just delegate to menu_callback if we can "fake" it or duplicate logic.
            # Duplicating logic for "Command -> Submenu" is safer than faking callback.
            
            # Let's just implement the switching logic here for command-based entry.
            text = ""
            keyboard = []
            
            if menu_type == PROFILE_MENU:
                # Delegate to actual profile handler? No, just show menu
                 # ... (skip profile logic here, just default menu?)
                 # Actually PROFILE_MENU in menu_callback calls show_profile logic part.
                 pass
            
            # To avoid valid code duplication, let's just make start_menu smart enough.
            # Convert command "/networking" -> start_menu(menu_type='menu_net')
            
            # If we are here from command, just send the specific menu as a NEW message.
            # We can use the logic from menu_callback but adapted.
            
            # Hack: Create a dummy update object? No.
            # Let's just use the `menu_callback` logic but ensuring it handles `message.reply_text` if `query` is None.
            
            # Let's make menu_callback robust to non-callback updates if we pass specific data.
            # But menu_callback is designed for navigation (editing).
            # Command entry should SEND new message.
            
            # Let's just return to main menu if complex, or implemented simple logic.
            pass

    # Default fallback
    await start_menu_internal(update, context, initial_menu=menu_type)

async def start_menu_internal(update: Update, context: ContextTypes.DEFAULT_TYPE, initial_menu=None):
    """
    Internal helper to show menu, supporting sub-menus on first load.
    """
    user = update.effective_user
    
    target_menu = initial_menu or MAIN_MENU
    
    # We need to generate the content for the target_menu
    text, reply_markup = await get_menu_content(user, target_menu, context)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML" if target_menu == PROFILE_MENU else "Markdown")
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="HTML" if target_menu == PROFILE_MENU else "Markdown")


# Callback prefixes
MENU_PREFIX = "menu_"
MAIN_MENU = "menu_main"
PROFILE_MENU = "menu_profile"
MATERIALS_MENU = "menu_materials"
NETWORKING_MENU = "menu_net"
TOOLS_MENU = "menu_tools"
SETTINGS_MENU = "menu_settings"

async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, menu_type: str = None):
    """
    Shows the menu. Can handle specific sub-menus via menu_type argument.
    """
    user = update.effective_user
    logger.info(f"User {user.id} requested menu: {menu_type or 'main'}")

    target_menu = menu_type or MAIN_MENU
    
    # Ensure user exists (only needed once, really)
    # But get_menu_content might need profile
    
    text, reply_markup = await get_menu_content(user, target_menu, context)
    parse_mode = "HTML" if target_menu == PROFILE_MENU else "Markdown"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        # Send new message
        msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        # Track for cleanup if needed? usually main menu is permanent-ish but submenus might be transient
        # Actually we track conversation messages. Let's not overcomplicate for now.

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles menu navigation via callbacks.
    """
    query = update.callback_query
    data = query.data
    
    await query.answer()
    
    # Clean up any conversation messages when navigating menus
    await cleanup_conversation_message(update, context)
    
    # If data sends us to a command, we might need special handling if it's not a menu
    # But usually we use route_menu_command for cmd_ prefixes.
    # Here we handle 'menu_' prefixes.
    
    user = update.effective_user
    text, reply_markup = await get_menu_content(user, data, context)
    parse_mode = "HTML" if data == PROFILE_MENU else "Markdown"
    
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

async def get_menu_content(user, menu_type, context):
    """
    Returns (text, reply_markup) for the given menu type and user.
    """
    text = ""
    keyboard = []
    
    # Ensure user exists in DB for profile checks
    if menu_type == PROFILE_MENU or menu_type == MAIN_MENU:
         async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            await user_service.get_or_create_user(user.id, user.username, user.first_name, user.last_name)

    if menu_type == MAIN_MENU:
        text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Главный пульт управления твоим нетворкингом.\n"
            "Выбери раздел:"
        )
        keyboard = [
            [
                InlineKeyboardButton("👤 Мой профиль", callback_data=PROFILE_MENU),
                InlineKeyboardButton("📂 Мои материалы", callback_data=MATERIALS_MENU)
            ],
            [
                InlineKeyboardButton("🤝 Нетворкинг", callback_data=NETWORKING_MENU)
            ],
            [
                InlineKeyboardButton("🛠 Инструменты", callback_data=TOOLS_MENU),
                InlineKeyboardButton("⚙️ Настройки", callback_data=SETTINGS_MENU)
            ]
        ]
        
    elif menu_type == PROFILE_MENU:
        async with AsyncSessionLocal() as session:
            service = ProfileService(session)
            profile = await service.get_profile(user.id)
            
        text = f"👤 <b>Ваш Профиль</b>\n\n"
        name = profile.full_name or user.first_name or "Без имени"
        text += f"<b>{escape(name)}</b>\n"
        
        if profile.job_title:
            text += f"💼 {escape(profile.job_title)}"
            if profile.company:
                text += f" @ {escape(profile.company)}"
            text += "\n"
        elif profile.company:
            text += f"🏢 {escape(profile.company)}\n"
            
        if profile.location:
            text += f"📍 {escape(profile.location)}\n"
        
        if profile.bio:
            text += f"\n<i>{escape(profile.bio)}</i>\n"
            
        if profile.interests:
            text += f"\n⭐ <b>Интересы</b>: {escape(', '.join(profile.interests))}\n"
            
        text += "\n📞 <b>Контакты</b>:\n"
        has_contacts = False
        if profile.custom_contacts:
            for cc in profile.custom_contacts:
                if cc.value.startswith("http") or cc.value.startswith("t.me"):
                     text += f"• <a href=\"{escape(cc.value)}\">{escape(cc.label)}</a>\n"
                else:
                     text += f"• {escape(cc.label)}: {escape(cc.value)}\n"
            has_contacts = True
        
        if not has_contacts:
            text += "_(пусто)_\n"
            
        keyboard = [
            [InlineKeyboardButton("✏️ Редактировать профиль", callback_data="cmd_profile")],
            [InlineKeyboardButton("🔗 Поделиться профилем", callback_data="cmd_share")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif menu_type == MATERIALS_MENU:
        text = "📂 **Мои материалы**\n\nБыстрый доступ к твоим ассетам."
        keyboard = [
            [InlineKeyboardButton("🚀 Питчи", callback_data="cmd_pitches")],
            [InlineKeyboardButton("📄 Ванпейджеры", callback_data="cmd_onepagers")],
            [InlineKeyboardButton("👋 Приветствия", callback_data="cmd_greetings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif menu_type == NETWORKING_MENU:
        text = "🤝 **Нетворкинг**\n\nРабота с контактами и базой."
        keyboard = [
            [InlineKeyboardButton("📋 Список контактов", callback_data="cmd_list")],
            [InlineKeyboardButton("🔍 Поиск (Semantic)", callback_data="cmd_find")],
            [InlineKeyboardButton("✨ Синергии (Matches)", callback_data="cmd_matches")],
            [InlineKeyboardButton("⏰ Напоминания", callback_data="cmd_reminders")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif menu_type == TOOLS_MENU:
        text = "🛠 **Инструменты**\n\nИмпорт, экспорт и синхронизация."
        keyboard = [
            [InlineKeyboardButton("📥 Импорт (LinkedIn)", callback_data="cmd_import")],
            [InlineKeyboardButton("📤 Экспорт CSV", callback_data="cmd_export")],
             [InlineKeyboardButton("🔄 Синхронизация", callback_data="cmd_sync")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif menu_type == SETTINGS_MENU:
        text = "⚙️ **Настройки**\n\nКонфигурация бота."
        keyboard = [
            [InlineKeyboardButton("🔑 API Ключи", callback_data="cmd_credentials")],
            [InlineKeyboardButton("🧠 AI Промпты", callback_data="cmd_prompt")],
            [InlineKeyboardButton("📊 Статистика", callback_data="cmd_stats")],
            [InlineKeyboardButton("🎭 Режим (Event Mode)", callback_data="cmd_event")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    return text, InlineKeyboardMarkup(keyboard)

# We need a bridge to call command functions from callbacks.
# Or we just tell the user what command to run? No, that's bad UX.
# We should call the functions.

