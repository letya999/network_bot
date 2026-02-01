
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

# States
SELECT_SERVICE = 1
WAITING_INPUT = 2

# Services
SERVICE_GEMINI = "gemini"
SERVICE_TAVILY = "tavily"
SERVICE_OPENAI = "openai"
SERVICE_NOTION = "notion"
SERVICE_SHEETS = "sheets"
SERVICE_AUTO = "auto" # for pasting the whole block
SERVICE_AI_PROVIDER = "ai_provider"

async def set_credentials_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the credentials setup process."""
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
        
    keyboard = [
        [InlineKeyboardButton("🧠 Gemini AI", callback_data=SERVICE_GEMINI)],
        [InlineKeyboardButton("🧠 OpenAI GPT", callback_data=SERVICE_OPENAI)],
        [InlineKeyboardButton("🕵️ Tavily OSINT", callback_data=SERVICE_TAVILY)],
        [InlineKeyboardButton("📝 Notion", callback_data=SERVICE_NOTION)],
        [InlineKeyboardButton("📊 Google Sheets", callback_data=SERVICE_SHEETS)],
        [InlineKeyboardButton("📄 Вставить всё списком", callback_data=SERVICE_AUTO)],
        [InlineKeyboardButton("🤖 Выбрать AI провайдера", callback_data=SERVICE_AI_PROVIDER)],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "⚙️ *Настройка доступов*\n\n"
        "Выберите сервис, для которого хотите настроить ключи, или выберите 'Вставить всё списком', чтобы загрузить всё сразу.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return SELECT_SERVICE

async def service_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "cancel":
        await query.edit_message_text("❌ Настройка отменена.")
        return ConversationHandler.END

    if choice == "back_to_creds":
        return await set_credentials_command(update, context)

    if choice.startswith("set_provider_"):
        provider = choice.replace("set_provider_", "")
        if provider == "none": provider = None
        
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            db_user = await user_service.get_or_create_user(query.from_user.id)
            settings_data = db_user.settings or {}
            settings_data["ai_provider"] = provider
            db_user.settings = settings_data
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(db_user, "settings")
            await session.commit()
        
        prov_name = "Авторазрешение" if not provider else ("Google Gemini" if provider == "gemini" else "OpenAI GPT")
        await query.edit_message_text(f"✅ Основным провайдером выбран: *{prov_name}*", parse_mode="Markdown")
        return ConversationHandler.END

    context.user_data["creds_service"] = choice
    
    if choice == SERVICE_GEMINI:
        msg = "🔑 Введите *Gemini API Key*:"
    elif choice == SERVICE_OPENAI:
        msg = "🔑 Введите *OpenAI API Key*:"
    elif choice == SERVICE_TAVILY:
        msg = "🔑 Введите *Tavily API Key*:"
    elif choice == SERVICE_NOTION:
        msg = (
            "📝 Для Notion нужно 2 параметра.\n"
            "Пришлите их в формате:\n"
            "`KEY: secret_...`\n"
            "`DB: database_id`\n\n"
            "Или просто пришлите *Notion API Key* (начнем с него)."
        )
    elif choice == SERVICE_SHEETS:
        msg = (
            "📊 Для Google Sheets нужны credentials JSON и ID таблицы.\n"
            "Вы можете прислать содержимое JSON файла сервисного аккаунта, или список ключей как в .env:\n"
            "`GOOGLE_PROJ_ID=...`\n"
            "`GOOGLE_PRIVATE_KEY=...`\n"
            "и т.д."
        )
    elif choice == SERVICE_AUTO:
        msg = (
            "📄 Пришлите список переменных (как в .env).\n"
            "Я попытаюсь распознать: Gemini, Tavily, Notion, Google Sheets.\n\n"
            "Пример:\n"
            "GEMINI_API_KEY=...\n"
            "OPENAI_API_KEY=...\n"
            "NOTION_API_KEY=..."
        )
    elif choice == SERVICE_AI_PROVIDER:
        keyboard = [
            [InlineKeyboardButton("Gemini (Google)", callback_data="set_provider_gemini")],
            [InlineKeyboardButton("GPT-4o (OpenAI)", callback_data="set_provider_openai")],
            [InlineKeyboardButton("Авто (Gemini > OpenAI)", callback_data="set_provider_none")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_creds")]
        ]
        await query.edit_message_text(
            "🤖 *Выбор основного провайдера*\n\n"
            "Выберите, какую нейросеть использовать по умолчанию. "
            "Если основная недоступна или закончились квоты, бот попробует использовать вторую.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SELECT_SERVICE
    else:
        msg = "Ошибка выбора."

    await query.edit_message_text(msg, parse_mode="Markdown")
    return WAITING_INPUT

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        await update.message.reply_text("❌ Текст не найден.")
        return WAITING_INPUT
        
    service = context.user_data.get("creds_service")
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id, user.username)
        
        current_settings = db_user.settings or {}
        
        response_text = ""
        
        if service == SERVICE_GEMINI:
            # Assuming just the key
            key = text.strip().split("=")[-1].strip() # Handle KEY=value if user pastes that
            current_settings["gemini_api_key"] = key
            response_text = "✅ Gemini API Key сохранен!"

        elif service == SERVICE_OPENAI:
            key = text.strip().split("=")[-1].strip()
            current_settings["openai_api_key"] = key
            response_text = "✅ OpenAI API Key сохранен!"
            
        elif service == SERVICE_TAVILY:
            key = text.strip().split("=")[-1].strip()
            current_settings["tavily_api_key"] = key
            response_text = "✅ Tavily API Key сохранен!"
            
        elif service == SERVICE_NOTION:
            # Try parsing
            updated_count = 0
            lines = text.split("\n")
            for line in lines:
                if "NOTION_API_KEY" in line or line.startswith("ntn_") or line.startswith("secret_"):
                    # Basic heuristic
                    val = line.split("=")[-1].strip() if "=" in line else line.strip()
                    current_settings["notion_api_key"] = val
                    updated_count += 1
                elif "NOTION_DATABASE_ID" in line or (len(line.strip()) == 32 and "-" not in line):
                    val = line.split("=")[-1].strip() if "=" in line else line.strip()
                    current_settings["notion_database_id"] = val
                    updated_count += 1
            
            if updated_count > 0:
                response_text = f"✅ Notion: обновлено {updated_count} полей."
            else:
                response_text = "⚠️ Не удалось распознать ключи Notion. Убедитесь, что там API Key (secret_...) и Database ID."

        elif service == SERVICE_SHEETS:
            # Parse Google Envs from text
            # Mapping env names to settings keys
            env_map = {
                "GOOGLE_PROJ_ID": "google_proj_id",
                "GOOGLE_PRIVATE_KEY_ID": "google_private_key_id",
                "GOOGLE_PRIVATE_KEY": "google_private_key",
                "GOOGLE_CLIENT_EMAIL": "google_client_email",
                "GOOGLE_SHEET_ID": "google_sheet_id"
            }
            
            updated_count = 0
            lines = text.split("\n")
            
            # Handle multiline private key?
            # User text might contain newlines inside the key if not properly escaped.
            # But typically in .env it's one line with \n
            
            # If the user pasted the raw private key block:
            # -----BEGIN PRIVATE KEY----- ...
            # it might be spread across lines.
            
            # Simple line-by-line parsing for KEY=VALUE
            # If simple parsing fails, we might need regex.
            
            # Let's try to parse the block the user provided which has "key=value" format mostly.
            
            # We will process line by line.
            current_key = None
            buffer = ""
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                # Check if line starts with known key
                found_key = False
                for env_key, setting_key in env_map.items():
                    if line.startswith(env_key + "="):
                        # Save previous if any
                        if current_key:
                             current_settings[env_map[current_key]] = buffer
                        
                        current_key = env_key
                        buffer = line.split("=", 1)[1].strip()
                        if buffer.startswith('"') and buffer.endswith('"'):
                             buffer = buffer[1:-1]
                        if buffer.startswith("'") and buffer.endswith("'"):
                             buffer = buffer[1:-1]
                        found_key = True
                        break
                
                if not found_key and current_key == "GOOGLE_PRIVATE_KEY":
                    # Continuation of private key?
                    # The sample showed explicit \n characters "MIIEvQ...", but maybe user pastes real newlines.
                    # If it's real newlines, we append.
                    buffer += "\n" + line
                elif not found_key:
                     # Maybe a standalone key without name? Unlikely for Sheets.
                     pass
            
            # Save last
            if current_key:
                 current_settings[env_map[current_key]] = buffer
                 
            # Check how many we found
            found = [k for k in env_map.values() if k in current_settings]
            updated_count = len(found)
            
            response_text = f"✅ Google Sheets: обновлено {updated_count} параметров."

        elif service == SERVICE_AUTO:
            # Try to everything
            lines = text.split("\n")
            updated = []
            
            # Mappings
            mappings = {
                "GEMINI_API_KEY": "gemini_api_key",
                "OPENAI_API_KEY": "openai_api_key",
                "TAVILY_API_KEY": "tavily_api_key",
                "NOTION_API_KEY": "notion_api_key",
                "NOTION_DATABASE_ID": "notion_database_id",
                "GOOGLE_PROJ_ID": "google_proj_id",
                "GOOGLE_PRIVATE_KEY_ID": "google_private_key_id",
                # GOOGLE_PRIVATE_KEY is special handling
                "GOOGLE_CLIENT_EMAIL": "google_client_email",
                "GOOGLE_SHEET_ID": "google_sheet_id"
            }
            
            current_key = None
            buffer = ""
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                # Check for keys
                found_key = False
                for env_key, setting_key in mappings.items():
                    if line.startswith(env_key + "="):
                         if current_key == "GOOGLE_PRIVATE_KEY":
                             current_settings["google_private_key"] = buffer
                             updated.append("google_private_key")
                         
                         current_key = env_key
                         val = line.split("=", 1)[1].strip()
                         # clean quotes
                         if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                             val = val[1:-1]
                         
                         if env_key == "GOOGLE_PRIVATE_KEY":
                             buffer = val
                         else:
                             current_settings[setting_key] = val
                             updated.append(setting_key)
                             current_key = None # Reset unless private key
                         
                         found_key = True
                         break
                
                if not found_key and current_key == "GOOGLE_PRIVATE_KEY":
                    buffer += "\n" + line

            if current_key == "GOOGLE_PRIVATE_KEY":
                 current_settings["google_private_key"] = buffer
                 updated.append("google_private_key")
            
            response_text = f"✅ Авто-определение: сохранено {len(set(updated))} параметров.\n"
            response_text += f"Найдены: {', '.join(set(updated))}"

        # Save to DB
        db_user.settings = current_settings
        # Force update flag if needed (SQLAlchemy JSON tracking)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(db_user, "settings")
        
        await session.commit()
    
    await update.message.reply_text(response_text)
    return ConversationHandler.END

async def cancel_creds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Настройка отменена.")
    return ConversationHandler.END
