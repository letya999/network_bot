import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app.db.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# Prompt Conversation States
WAITING_FOR_PROMPT = 1

async def show_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the current extraction prompt for the user.
    """
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
        
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        db_user = await user_service.get_or_create_user(user.id)
        
        prompt = db_user.custom_prompt
        source = "Custom (Saved in DB)"
        
        if not prompt:
            ai = AIService()
            prompt = ai.get_prompt("extract_contact")
            source = "Default (System)"
            
        await message.reply_text(
            f"📜 *Текущий Промпт* ({source}):\n\n"
            f"```\n{prompt}\n```\n\n"
            "Используй /edit_prompt чтобы изменить его.\n"
            "Используй /reset_prompt чтобы сбросить.",
            parse_mode="Markdown"
        )

async def start_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Starts the conversation to edit the prompt.
    """
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message

    await message.reply_text(
        "Пришли мне новый текст промпта.\n"
        "Ты можешь скопировать текущий (/prompt) и отредактировать его.\n"
        "Отправь /cancel чтобы отменить."
    )
    return WAITING_FOR_PROMPT

async def save_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Saves the new prompt provided by the user.
    """
    user = update.effective_user
    new_prompt = update.message.text
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.update_custom_prompt(user.id, new_prompt)
        
    await update.message.reply_text("✅ Новый промпт сохранен!")
    return ConversationHandler.END

async def cancel_prompt_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels the prompt editing process.
    """
    await update.message.reply_text("🚫 Редактирование отменено.")
    return ConversationHandler.END

async def reset_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Resets the prompt to the system default.
    """
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        await user_service.update_custom_prompt(user.id, None)
        
    await update.message.reply_text("🔄 Промпт сброшен до стандартного.")
