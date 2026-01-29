
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
            update.callback_query._data = menu_type
            await menu_callback(update, context)
            update.callback_query._data = original_data
        else:
            await start_menu(update, context)
    else:
        await start_menu(update, context)

# Callback prefixes
MENU_PREFIX = "menu_"
MAIN_MENU = "menu_main"
PROFILE_MENU = "menu_profile"
MATERIALS_MENU = "menu_materials"
NETWORKING_MENU = "menu_net"
TOOLS_MENU = "menu_tools"
SETTINGS_MENU = "menu_settings"

async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the main menu. Replaces the standard /start command or calls this from callback.
    """
    user = update.effective_user
    logger.info(f"User {user.id} requested menu.")

    # Ensure user exists
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.get_or_create_user(user.id, user.username, user.first_name, user.last_name)

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
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles menu navigation.
    Cleans up any active conversation messages before navigating.
    """
    query = update.callback_query
    data = query.data
    
    await query.answer()
    
    # Clean up any conversation messages when navigating menus
    await cleanup_conversation_message(update, context)
    
    if data == MAIN_MENU:
        await start_menu(update, context)
        return

    text = ""
    keyboard = []
    
    if data == PROFILE_MENU:
        # Show actual profile instead of generic text
        user = update.effective_user
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
            
        # Contacts
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
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        return
        
    elif data == MATERIALS_MENU:
        text = "📂 **Мои материалы**\n\nБыстрый доступ к твоим ассетам."
        keyboard = [
            [InlineKeyboardButton("🚀 Питчи", callback_data="cmd_pitches")],
            [InlineKeyboardButton("📄 Ванпейджеры", callback_data="cmd_onepagers")],
            [InlineKeyboardButton("👋 Приветствия", callback_data="cmd_greetings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif data == NETWORKING_MENU:
        text = "🤝 **Нетворкинг**\n\nРабота с контактами и базой."
        keyboard = [
            [InlineKeyboardButton("📋 Список контактов", callback_data="cmd_list")],
            [InlineKeyboardButton("🔍 Поиск (Semantic)", callback_data="cmd_find")],
            [InlineKeyboardButton("✨ Синергии (Matches)", callback_data="cmd_matches")],
            [InlineKeyboardButton("⏰ Напоминания", callback_data="cmd_reminders")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif data == TOOLS_MENU:
        text = "🛠 **Инструменты**\n\nИмпорт, экспорт и синхронизация."
        keyboard = [
            [InlineKeyboardButton("📥 Импорт (LinkedIn)", callback_data="cmd_import")],
            [InlineKeyboardButton("📤 Экспорт CSV", callback_data="cmd_export")],
             [InlineKeyboardButton("🔄 Синхронизация", callback_data="cmd_sync")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    elif data == SETTINGS_MENU:
        text = "⚙️ **Настройки**\n\nКонфигурация бота."
        keyboard = [
            [InlineKeyboardButton("🔑 API Ключи", callback_data="cmd_credentials")],
            [InlineKeyboardButton("🧠 AI Промпты", callback_data="cmd_prompt")],
            [InlineKeyboardButton("📊 Статистика", callback_data="cmd_stats")],
            [InlineKeyboardButton("🎭 Режим (Event Mode)", callback_data="cmd_event")],
            [InlineKeyboardButton("⬅️ Назад", callback_data=MAIN_MENU)]
        ]
        
    # Proxy handlers for commands that might be triggered via buttons but need to act like commands
    # Note: For actual functionality, we might need to trigger existing handlers or show intermediate text.
    # Since existing handlers expect message updates mainly, using buttons to trigger them might require adaptation.
    # However, for now, we will assume we can route them or user sees text instructions?
    # Better: Trigger the functions directly or set state?
    # To keep it simple, we'll implement simple wrappers or just text navigation for now if Complex.
    
    # Actually, the proposal implies these buttons Trigger the functionality.
    # We will handle "cmd_" prefixes in a separate handler or here. 
    # But wait, if I click "My Profile", I want to invoke `show_profile`.
    # `show_profile` expects an Update with Message or CallbackQuery?
    # Existing `show_profile` is a CommandHandler entry point.
    
    if text:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

# We need a bridge to call command functions from callbacks.
# Or we just tell the user what command to run? No, that's bad UX.
# We should call the functions.

