import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.profile_handlers import show_profile, handle_edit_callback, save_profile_value
from app.bot.handlers import generate_card_callback
from app.models.user import User
from app.models.contact import Contact
import uuid

def assert_msg_contains(mock_reply_text, substring):
    found = False
    for call in mock_reply_text.call_args_list:
        if substring in call[0][0]: found = True; break
    assert found, f"Message containing '{substring}' not found"

@pytest.mark.asyncio
async def test_show_profile(mock_update, mock_context):
    mock_db_user = User(telegram_id=12345, name="Test User", profile_data={})
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock(return_value=mock_db_user)):
        mock_update.callback_query = None
        await show_profile(mock_update, mock_context)
        assert "Test User" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_edit_profile_callback(mock_update, mock_context):
    mock_update.callback_query.data = "edit_full_name"
    await handle_edit_callback(mock_update, mock_context)
    assert "полное имя" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_save_profile_value(mock_update, mock_context):
    mock_context.user_data["edit_field"] = "bio"
    mock_update.message.text = "New Bio"
    with patch("app.services.profile_service.ProfileService.update_profile_field", AsyncMock()) as mock_upd:
        from app.schemas.profile import UserProfile
        mock_upd.return_value = UserProfile(bio="New Bio")
        await save_profile_value(mock_update, mock_context)
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
