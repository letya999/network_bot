import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.profile_handlers import show_profile, handle_edit_callback, save_profile_value
from app.bot.handlers.card import generate_card_callback
from app.models.user import User
from app.models.contact import Contact
import uuid

def assert_msg_contains(mock_reply_text, substring):
    found = False
    for call in mock_reply_text.call_args_list:
        if substring in call[0][0]: found = True; break
    assert found, f"Message containing '{substring}' not found"

@pytest.mark.asyncio
async def test_show_profile_with_assets(mock_update, mock_context):
    from app.schemas.profile import UserProfile
    profile = UserProfile(
        full_name="Asset Master",
        pitches=["Pitch 1", "Pitch 2"],
        one_pagers=["http://one.pager"],
        welcome_messages=["Hello!"]
    )
    mock_db_user = User(telegram_id=12345, name="Asset Master", profile_data=profile.model_dump())
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock(return_value=mock_db_user)):
        mock_update.callback_query = None
        await show_profile(mock_update, mock_context)
        output = mock_update.message.reply_text.call_args[0][0]
        assert "*Питчи*: 2" in output
        assert "*Ванпейджеры*: 1" in output
        assert "*Приветствия*: 1" in output

@pytest.mark.asyncio
async def test_edit_assets_callbacks(mock_update, mock_context):
    """Test that asset callbacks trigger the asset management flow."""
    from app.bot.handlers.assets_handler import start_assets, ASSET_MENU
    
    # Mock db_user
    mock_db_user = User(
        telegram_id=12345,
        name="Test User",
        profile_data={"pitches": [], "one_pagers": [], "welcome_messages": []}
    )
    
    # Setup message text to valid command so start_assets can parse it
    mock_update.message.text = "/pitches"
    
    with patch("app.services.user_service.UserService.get_or_create_user", 
               AsyncMock(return_value=mock_db_user)):
        result = await start_assets(mock_update, mock_context)
        
        # Should return ASSET_MENU state and set type
        assert result == ASSET_MENU
        assert mock_context.user_data["current_asset_type"] == "pitch"

@pytest.mark.asyncio
async def test_edit_profile_callback(mock_update, mock_context):
    mock_update.callback_query.data = "edit_full_name"
    await handle_edit_callback(mock_update, mock_context)
    assert "полное имя" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_save_interests_list(mock_update, mock_context):
    """Test saving distinct list of interests."""
    mock_context.user_data["edit_field"] = "interests"
    mock_update.message.text = "AI, Python, Networking"
    
    with patch("app.services.profile_service.ProfileService.update_profile_field", AsyncMock()) as mock_upd:
        with patch("app.bot.profile_handlers.show_profile", AsyncMock()):
            await save_profile_value(mock_update, mock_context)
            
            # Verify call arguments
            # ProfileService.update_profile_field(user_id, field, value)
            mock_upd.assert_called_once()
            assert mock_upd.call_args[0][1] == "interests"
            # Should be list of stripped strings
            assert mock_upd.call_args[0][2] == ["AI", "Python", "Networking"]
            assert_msg_contains(mock_update.message.reply_text, "Сохранено")

@pytest.mark.asyncio
async def test_generate_card_callback(mock_update, mock_context, mock_session):
    mock_update.callback_query.data = f"gen_card_{uuid.uuid4()}"
    mock_session.get.return_value = Contact(name="Recipient")
    with patch("app.services.profile_service.ProfileService.get_profile", AsyncMock(return_value=MagicMock(full_name="Me"))), \
         patch("app.services.gemini_service.GeminiService.customize_card_intro", AsyncMock(return_value="Hi")), \
         patch("app.services.card_service.CardService.generate_text_card", return_value="Card"):
        await generate_card_callback(mock_update, mock_context)
        assert_msg_contains(mock_update.callback_query.message.reply_text, "Card")
        # The status message is "⏳ Читаю профили..."
        assert_msg_contains(mock_update.callback_query.message.reply_text, "Читаю профили")
        # Actually checking the final call
        found_final = False
        for call in mock_update.callback_query.message.reply_text.call_args_list:
            if "Card" in call[0][0] and "Персонализированная" in call[0][0]:
                found_final = True
        assert found_final, "Final personalized card was not sent"
