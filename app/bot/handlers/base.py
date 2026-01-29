import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.profile_service import ProfileService
from app.services.card_service import CardService

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /start command. Handles deep linking for card sharing.
    """
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.get_or_create_user(user.id, user.username, user.first_name)
        
        # Handle Deep Linking (sharing cards)
        if context.args and context.args[0].startswith("c_"):
            try:
                target_id = int(context.args[0][2:])
                target_user = await user_service.get_user(target_id)
                
                if target_user:
                    profile_service = ProfileService(session)
                    profile = await profile_service.get_profile(target_id)
                    card_text = CardService.generate_text_card(profile)
                    
                    await update.message.reply_text(
                        f"👋 Привет! Вот визитка, которой с тобой поделились:\n\n{card_text}\n\n"
                        "<i>Нажми /save чтобы сохранить (WIP)</i>", 
                        parse_mode="HTML"
                    )
                else:
                    await update.message.reply_text("❌ Профиль не найден или удален.")
            except (ValueError, IndexError):
                pass
        
    await update.message.reply_text(
        f"Привет {user.first_name}! Я Networking Bot.\n"
        "Отправь мне голосовое сообщение или контакт, чтобы я сохранил его.\n"
        "Команды:\n"
        "/list - мои контакты\n"
        "/find <query> - поиск\n"
        "/export - скачать CSV"
    )
