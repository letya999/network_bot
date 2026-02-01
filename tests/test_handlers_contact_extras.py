import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers.contact_handlers import handle_text_message
from app.models.contact import Contact
import uuid

@pytest.mark.asyncio
async def test_handle_text_gemini_quota_exceeded(mock_update, mock_context):
    mock_update.message.text = "John Doe"
    
    with patch("app.bot.handlers.contact_handlers.AsyncSessionLocal"), \
         patch("app.bot.handlers.contact_handlers.UserService") as MockUserService, \
         patch("app.bot.handlers.contact_handlers.AIService") as MockGemini:
         
         mock_user = MagicMock(id=uuid.uuid4(), custom_prompt=None)
         MockUserService.return_value.get_or_create_user = AsyncMock(return_value=mock_user)
         
         # Mock Gemini returning error
         MockGemini.return_value.extract_contact_data = AsyncMock(return_value={"error": "Quota Exceeded"})
         
         await handle_text_message(mock_update, mock_context)
         
         # Should reply with error info
         mock_update.message.reply_text.assert_called()
         # It calls reply_text multiple times or once?
         # Code: await update.message.reply_text(..., f"Error: {error_msg}")
         found = False
         for call in mock_update.message.reply_text.call_args_list:
             if "limit exceeded" in call[0][0] or "Quota Exceeded" in call[0][0]:
                 found = True
         assert found

@pytest.mark.asyncio
async def test_handle_text_explicit_edit_name(mock_update, mock_context):
    mock_update.message.text = "New Name"
    # Setup context for editing
    editing_id = uuid.uuid4()
    mock_context.user_data = {"editing_contact_id": str(editing_id), "edit_contact_field": "name"}
    
    with patch("app.bot.handlers.contact_handlers.AsyncSessionLocal"), \
         patch("app.bot.handlers.contact_handlers.UserService") as MockUserService, \
         patch("app.bot.handlers.contact_handlers.ContactService") as MockContactService, \
         patch("app.bot.handlers.contact_handlers.AIService") as MockGemini:
         
         mock_user = MagicMock(id=uuid.uuid4())
         MockUserService.return_value.get_or_create_user = AsyncMock(return_value=mock_user)
         MockGemini.return_value.extract_contact_data = AsyncMock(return_value={"name": "New Name"}) # Gemini runs anyway
         
         # Contact service update
         updated_contact = Contact(id=editing_id, name="New Name", telegram_username="user")
         MockContactService.return_value.update_contact = AsyncMock(return_value=updated_contact)
         MockContactService.return_value.get_contact_by_id = AsyncMock(return_value=updated_contact)
         
         await handle_text_message(mock_update, mock_context)
         
         # Check if update called
         MockContactService.return_value.update_contact.assert_called_once()
         # Check that we cleared the state
         assert "edit_contact_field" not in mock_context.user_data
         
         # Check reply
         # First reply: "Field updated."
         # Second reply: Menu text
         calls = mock_update.message.reply_text.call_args_list
         assert any("Field updated" in c[0][0] for c in calls)
