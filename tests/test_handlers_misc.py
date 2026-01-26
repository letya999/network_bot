import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers import (
    set_event_mode, show_prompt, start_edit_prompt, 
    save_prompt, reset_prompt, WAITING_FOR_PROMPT
)
from telegram.ext import ConversationHandler

@pytest.fixture(autouse=True)
def mock_user_service():
    with patch("app.bot.handlers.UserService") as mock:
        service_instance = AsyncMock()
        mock.return_value = service_instance
        yield service_instance

@pytest.mark.asyncio
async def test_set_event_mode(mock_update, mock_context):
    mock_context.args = ["Tech Conference"]
    await set_event_mode(mock_update, mock_context)
    
    assert mock_context.user_data["current_event"] == "Tech Conference"
    assert "режим мероприятия" in mock_update.message.reply_text.call_args[0][0].lower()

@pytest.mark.asyncio
async def test_set_event_mode_status_empty(mock_update, mock_context):
    mock_context.args = []
    await set_event_mode(mock_update, mock_context)
    
    # Empty args just shows help or status
    assert "Используй" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_set_event_mode_stop(mock_update, mock_context):
    mock_context.args = ["stop"]
    mock_context.user_data["current_event"] = "Old Event"
    
    await set_event_mode(mock_update, mock_context)
    
    assert "current_event" not in mock_context.user_data
    assert "выключен" in mock_update.message.reply_text.call_args[0][0].lower()

from app.bot.profile_handlers import send_card, share_card

@pytest.mark.asyncio
async def test_send_card(mock_update, mock_context, mock_user_service):
    mock_profile = MagicMock(full_name="Alice", bio="Bio")
    
    with patch("app.services.profile_service.ProfileService.get_profile", AsyncMock(return_value=mock_profile)), \
         patch("app.services.card_service.CardService.generate_text_card", return_value="Card Text"):
        
        await send_card(mock_update, mock_context)
        
        assert "Card Text" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_share_card(mock_update, mock_context):
    mock_context.bot.username = "bot"
    mock_update.effective_user.id = 123
    
    await share_card(mock_update, mock_context)
    
    assert "t.me/bot?start=c_123" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_show_prompt_custom(mock_update, mock_context, mock_user_service):
    # Mock user having a custom prompt
    mock_user = MagicMock(custom_prompt="My Custom Prompt")
    mock_user_service.get_or_create_user = AsyncMock(return_value=mock_user)
    
    await show_prompt(mock_update, mock_context)
    
    assert "My Custom Prompt" in mock_update.message.reply_text.call_args[0][0]
    assert "Custom (Saved in DB)" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_show_prompt_default(mock_update, mock_context, mock_user_service):
    # Mock user having NO custom prompt
    mock_user = MagicMock(custom_prompt=None)
    mock_user_service.get_or_create_user = AsyncMock(return_value=mock_user)
    
    with patch("app.bot.handlers.GeminiService") as MockGemini:
        mock_gemini = MockGemini.return_value
        mock_gemini.get_prompt.return_value = "System Prompt"
        
        await show_prompt(mock_update, mock_context)
        
        assert "System Prompt" in mock_update.message.reply_text.call_args[0][0]
        assert "Default (System)" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_start_edit_prompt(mock_update, mock_context):
    result = await start_edit_prompt(mock_update, mock_context)
    
    assert mock_update.message.reply_text.called
    assert result == WAITING_FOR_PROMPT

@pytest.mark.asyncio
async def test_save_prompt(mock_update, mock_context, mock_user_service):
    mock_update.message.text = "New Prompt Content"
    mock_user = MagicMock(id=123)
    mock_user_service.get_or_create_user = AsyncMock(return_value=mock_user)
    
    result = await save_prompt(mock_update, mock_context)
    
    mock_user_service.update_custom_prompt.assert_called_once()
    assert result == ConversationHandler.END
    assert "сохранен" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_reset_prompt(mock_update, mock_context, mock_user_service):
    mock_user = MagicMock(id=123)
    mock_user_service.get_or_create_user = AsyncMock(return_value=mock_user)
    
    await reset_prompt(mock_update, mock_context)
    
    # called with None
    args = mock_user_service.update_custom_prompt.call_args
    assert args[0][1] is None 
    assert "сброшен" in mock_update.message.reply_text.call_args[0][0]
