import logging
from telegram import Update, BotCommand
from telegram.request import HTTPXRequest
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, TypeHandler, ConversationHandler, CallbackQueryHandler
from app.core.config import settings
from app.core.scheduler import start_scheduler, shutdown_scheduler
from app.bot.handlers import (
    start, handle_voice, handle_contact, list_contacts, find_contact, export_contacts, handle_text_message,
    show_prompt, start_edit_prompt, save_prompt, cancel_prompt_edit, reset_prompt, WAITING_FOR_PROMPT,
    generate_card_callback, card_pitch_selection_callback, set_event_mode
)
from app.bot.profile_handlers import (
    show_profile, handle_edit_callback, save_profile_value, cancel_edit, 
    SELECT_FIELD, INPUT_VALUE, INPUT_CONTACT_LABEL, INPUT_CONTACT_VALUE,
    save_contact_label, save_contact_value, send_card, share_card
)
from app.bot.handlers.assets_handler import (
    start_assets, asset_menu_callback, asset_action_callback,
    save_asset_name, save_asset_content, cancel_asset_op, show_asset_list,
    ASSET_MENU, ASSET_INPUT_NAME, ASSET_INPUT_CONTENT
)
from app.bot.handlers.menu_handlers import (
    start_menu, menu_callback, 
    MAIN_MENU, PROFILE_MENU, MATERIALS_MENU, NETWORKING_MENU, TOOLS_MENU, SETTINGS_MENU
)
from app.bot.handlers.contact_detail_handlers import (
    view_contact, delete_contact_ask, delete_contact_confirm, edit_contact_start, cancel_contact_edit, handle_contact_edit_field,
    manage_contact_contacts_menu, delete_contact_field_handler, add_contact_start,
    CONTACT_VIEW_PREFIX, CONTACT_EDIT_PREFIX, CONTACT_EDIT_FIELD_PREFIX, 
    CONTACT_DEL_FIELD_PREFIX, CONTACT_ADD_FIELD_PREFIX,
    CONTACT_DEL_ASK_PREFIX, CONTACT_DEL_CONFIRM_PREFIX
)

from app.bot.reminder_handlers import list_reminders, reminder_action_callback
from app.bot.analytics_handlers import show_stats
from app.bot.match_handlers import find_matches_command, semantic_search_handler, semantic_search_callback
from app.bot.osint_handlers import (
    enrich_command, enrich_callback, show_osint_data,
    start_import, handle_csv_import, cancel_import, WAITING_FOR_CSV,
    enrichment_stats, batch_enrich_callback
)
from app.bot.integration_handlers import sync_command, export_contact_callback, sync_run_callback
from app.bot.rate_limiter import rate_limiter
from app.bot.handlers.credentials_handlers import (
    set_credentials_command, service_choice_callback, handle_input, cancel_creds,
    SELECT_SERVICE, WAITING_INPUT
)

logger = logging.getLogger(__name__)

# Wrappers for asset start to set type
async def start_pitches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_asset_type"] = "pitch"
    return await start_assets(update, context)

async def start_onepagers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_asset_type"] = "one_pager"
    return await start_assets(update, context)

async def start_greetings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_asset_type"] = "greeting"
    return await start_assets(update, context)

async def open_networking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_menu(update, context, menu_type=NETWORKING_MENU)

async def open_tools_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_menu(update, context, menu_type=TOOLS_MENU)

async def open_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_menu(update, context, menu_type=SETTINGS_MENU)

async def open_materials_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_menu(update, context, menu_type=MATERIALS_MENU)

async def route_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dispatcher for menu commands (start with cmd_) that are NOT conversation entry points.
    """
    query = update.callback_query
    data = query.data
    cmd = data.replace("cmd_", "")
    
    if cmd == "card":
        return await send_card(update, context)
    elif cmd == "share":
        return await share_card(update, context)
         
    elif cmd == "list" or cmd.startswith("list_page_"):
        return await list_contacts(update, context)
    elif cmd == "find":
        return await find_contact(update, context)
    elif cmd == "matches":
        return await find_matches_command(update, context)
    elif cmd == "reminders":
        return await list_reminders(update, context)
        
    elif cmd == "export":
        return await export_contacts(update, context)
    elif cmd == "sync":
        return await sync_command(update, context)
        
    elif cmd == "prompt":
        return await show_prompt(update, context)
    elif cmd == "stats":
        return await show_stats(update, context)
    elif cmd == "event":
        return await set_event_mode(update, context)
        
    await query.answer("Опция в разработке...")

async def materials_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Используйте меню: /start -> Мои материалы")

async def post_init(application):
    """
    Post initialization hook to set bot commands.
    """
    bot = application.bot
    commands = [
        BotCommand("start", "🏠 Главное меню"),
        BotCommand("profile", "👤 Мой профиль"),
        BotCommand("materials", "📂 Мои материалы"),
        BotCommand("networking", "🤝 Нетворкинг"),
        BotCommand("tools", "🛠 Инструменты"),
        BotCommand("settings", "⚙️ Настройки"),
    ]
    await bot.set_my_commands(commands)
    logger.info(f"Bot commands set: {commands}")
    
    # Start Scheduler
    await start_scheduler()
    
    # Start rate limiter cleanup task
    rate_limiter.start_cleanup_task()
    logger.info("Rate limiter cleanup task started")

async def post_shutdown(application):
    """
    Post shutdown hook to stop scheduler.
    """
    await shutdown_scheduler()

async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Log usage of the bot to console.
    """
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    log_text = f"\n--- NEW UPDATE ---\n"
    if user:
         log_text += f"User: {user.first_name} (ID: {user.id}) @{user.username}\n"
    if chat:
        log_text += f"Chat: {chat.type} (ID: {chat.id})\n"
    
    if message:
        if message.text:
            log_text += f"Text: {message.text}\n"
        elif message.voice:
            log_text += f"Voice: {message.voice.file_id} ({message.voice.duration}s)\n"
        elif message.contact:
            log_text += f"Contact: {message.contact.phone_number} - {message.contact.first_name}\n"
        else:
            log_text += f"Message type: {message.chat.type}\n"
    else:
        log_text += f"Update type: {update}\n"
        
    logger.info(log_text)

def create_bot():
    if not settings.TELEGRAM_BOT_TOKEN:
       logger.error("No TELEGRAM_BOT_TOKEN found. Bot will not start.")
       return None
       
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0
    )

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).request(request).post_init(post_init).post_shutdown(post_shutdown).build()
    
    # Log all updates
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    
    # Override /start to use new menu
    app.add_handler(CommandHandler("start", start_menu))
    
    # Standard Commands
    app.add_handler(CommandHandler("menu", start_menu))
    app.add_handler(CommandHandler("list", list_contacts))
    app.add_handler(CommandHandler("find", semantic_search_handler)) # Keep semantic search on /find
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("matches", find_matches_command))
    app.add_handler(CommandHandler("export", export_contacts))
    app.add_handler(CommandHandler("prompt", show_prompt))
    app.add_handler(CommandHandler("reset_prompt", reset_prompt))
    app.add_handler(CommandHandler("event", set_event_mode))
    app.add_handler(CommandHandler("sync", sync_command))
    
    # Redirect new menu commands to start_menu (which handles submenus via args or we can dispatch)
    # Actually, we should map them to opening specific menus if possible.
    # start_menu accepts args? No.
    # But we can use route_menu_command or similar.
    # For now, let's just open the main menu or specific submenus if we had them as separate functions.
    # Since start_menu just sends MAIN_MENU, we might want to extend it.
    
    # We can use a simple wrapper to open specific menus
    async def open_networking(update, context): await start_menu(update, context, menu_type="networking")
    async def open_tools(update, context): await start_menu(update, context, menu_type="tools")
    async def open_settings(update, context): await start_menu(update, context, menu_type="settings")
    
    # But start_menu signature in menu_handlers might need update. 
    # Let's just point them to start_menu for now, or update menu_handlers.
    # Given the file view earlier, start_menu seemed simple.
    # Let's just point to start_menu for simplicity as "Hub".
    
    app.add_handler(CommandHandler("networking", open_networking_menu))
    app.add_handler(CommandHandler("tools", open_tools_menu))
    app.add_handler(CommandHandler("settings", open_settings_menu))
    
    # Materials shortcut
    app.add_handler(CommandHandler("materials", open_materials_menu)) 

    prompt_conv = ConversationHandler(
        entry_points=[CommandHandler("edit_prompt", start_edit_prompt)],
        states={
            WAITING_FOR_PROMPT: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_prompt)],
        },
        fallbacks=[CommandHandler("cancel", cancel_prompt_edit)]
    )
    app.add_handler(prompt_conv)

    profile_conv = ConversationHandler(
        entry_points=[
            CommandHandler("profile", show_profile),
            CallbackQueryHandler(show_profile, pattern="^cmd_profile$"),

            CommandHandler("pitches", start_assets),
            CallbackQueryHandler(start_pitches, pattern="^cmd_pitches$"),

            CommandHandler("onepagers", start_assets),
            CallbackQueryHandler(start_onepagers, pattern="^cmd_onepagers$"),

            CommandHandler("greetings", start_assets),
            CallbackQueryHandler(start_greetings, pattern="^cmd_greetings$"),
        ],
        states={
            SELECT_FIELD: [CallbackQueryHandler(handle_edit_callback)],
            INPUT_VALUE: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_profile_value)],
            INPUT_CONTACT_LABEL: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_contact_label)],
            INPUT_CONTACT_VALUE: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_contact_value)],
            # Asset states
            ASSET_MENU: [
                CallbackQueryHandler(asset_menu_callback, pattern="^(asset_add|asset_view_.*|asset_exit|menu_.*)$"),
                CallbackQueryHandler(asset_action_callback, pattern="^(asset_back|asset_delete|asset_edit_name|asset_edit_content)$")
            ],
            ASSET_INPUT_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_asset_name)],
            ASSET_INPUT_CONTENT: [MessageHandler(filters.TEXT & (~filters.COMMAND), save_asset_content)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_edit),
            CommandHandler("pitches", start_assets),
            CommandHandler("onepagers", start_assets),
            CommandHandler("greetings", start_assets),
            CommandHandler("profile", show_profile),
            CommandHandler("start", start_menu),
            CommandHandler("menu", start_menu)
        ]
    )
    app.add_handler(profile_conv)
    
    # Reminders
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CallbackQueryHandler(reminder_action_callback, pattern="^rem_"))

    # OSINT & Enrichment
    app.add_handler(CommandHandler("enrich", enrich_command))
    app.add_handler(CommandHandler("osint", show_osint_data))
    app.add_handler(CommandHandler("enrich_stats", enrichment_stats))
    app.add_handler(CallbackQueryHandler(enrich_callback, pattern="^enrich_"))
    app.add_handler(CallbackQueryHandler(batch_enrich_callback, pattern="^batch_enrich$"))

    # LinkedIn CSV Import
    import_conv = ConversationHandler(
        entry_points=[
            CommandHandler("import", start_import),
            CallbackQueryHandler(start_import, pattern="^cmd_import$")
        ],
        states={
            WAITING_FOR_CSV: [MessageHandler(filters.Document.ALL, handle_csv_import)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_import),
            CommandHandler("start", start_menu),
            CommandHandler("menu", start_menu)
        ]
    )
    app.add_handler(import_conv)

    # Credentials Setup
    creds_conv = ConversationHandler(
        entry_points=[
            CommandHandler("set_credentials", set_credentials_command),
            CallbackQueryHandler(set_credentials_command, pattern="^cmd_credentials$")
        ],
        states={
            SELECT_SERVICE: [CallbackQueryHandler(service_choice_callback)],
            WAITING_INPUT: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_creds),
            CommandHandler("start", start_menu),
            CommandHandler("menu", start_menu)
        ]
    )
    app.add_handler(creds_conv)

    app.add_handler(CommandHandler("card", send_card))
    app.add_handler(CommandHandler("share", share_card))
    
    # --- New Menu Handlers ---
    # Menu navigation
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    # Command routing from menu (exclude asset commands which are handled by profile_conv)
    app.add_handler(CallbackQueryHandler(route_menu_command, pattern="^cmd_(?!pitches|onepagers|greetings|profile)"))
    
    # Detail Handlers
    app.add_handler(CallbackQueryHandler(view_contact, pattern=f"^{CONTACT_VIEW_PREFIX}"))
    app.add_handler(CallbackQueryHandler(edit_contact_start, pattern=f"^{CONTACT_EDIT_PREFIX}"))
    app.add_handler(CallbackQueryHandler(handle_contact_edit_field, pattern=f"^{CONTACT_EDIT_FIELD_PREFIX}"))
    app.add_handler(CallbackQueryHandler(manage_contact_contacts_menu, pattern="^contact_manage_contacts$"))
    app.add_handler(CallbackQueryHandler(delete_contact_field_handler, pattern=f"^{CONTACT_DEL_FIELD_PREFIX}"))
    app.add_handler(CallbackQueryHandler(add_contact_start, pattern=f"^{CONTACT_ADD_FIELD_PREFIX}"))
    app.add_handler(CallbackQueryHandler(delete_contact_ask, pattern=f"^{CONTACT_DEL_ASK_PREFIX}"))
    app.add_handler(CallbackQueryHandler(delete_contact_confirm, pattern=f"^{CONTACT_DEL_CONFIRM_PREFIX}"))

    # Global Cancel for non-conversation states (e.g. contact edit)
    app.add_handler(CommandHandler("cancel", cancel_contact_edit))

    # Existing Callbacks
    app.add_handler(CallbackQueryHandler(generate_card_callback, pattern="^gen_card_"))
    app.add_handler(CallbackQueryHandler(card_pitch_selection_callback, pattern="^card_pitch_"))
    app.add_handler(CallbackQueryHandler(find_matches_command, pattern="^matches_"))
    app.add_handler(CallbackQueryHandler(semantic_search_callback, pattern="^semantic_"))
    app.add_handler(CallbackQueryHandler(export_contact_callback, pattern="^export_"))
    app.add_handler(CallbackQueryHandler(sync_run_callback, pattern="^sync_run_"))
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))
    
    return app
