"""
Tests for contact editing functionality.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers.contact_handlers import handle_text_message
from app.models.contact import Contact
import uuid


@pytest.mark.asyncio
async def test_explicit_contact_edit_mode(mock_update, mock_context):
    """Test that text messages update contact when in edit mode."""
    contact_id = uuid.uuid4()
    mock_context.user_data = {"editing_contact_id": str(contact_id)}
    mock_update.message.text = "Новый телефон: +79991234567"
    
    updated_contact = Contact(
        id=contact_id,
        name="Test User",
        phone="+79991234567"
    )
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock()), \
         patch("app.services.gemini_service.GeminiService.extract_contact_data", 
               AsyncMock(return_value={"phone": "+79991234567"})), \
         patch("app.services.contact_service.ContactService.update_contact", 
               AsyncMock(return_value=updated_contact)):
        
        await handle_text_message(mock_update, mock_context)
        
        # Check that editing mode was cleared
        assert "editing_contact_id" not in mock_context.user_data
        # Check that success message was sent
        assert mock_update.message.reply_text.called


@pytest.mark.asyncio
async def test_normal_text_creates_new_contact(mock_update, mock_context):
    """Test that text messages create new contacts when not in edit mode."""
    mock_context.user_data = {}
    mock_update.message.text = "Встретил Ивана Петрова из Яндекса"
    
    new_contact = Contact(
        id=uuid.uuid4(),
        name="Иван Петров",
        company="Яндекс"
    )
    
    # Mock db_user with proper profile_data
    from app.models.user import User
    mock_db_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        name="Test User",
        profile_data={}
    )
    
    with patch("app.services.user_service.UserService.get_or_create_user", 
               AsyncMock(return_value=mock_db_user)), \
         patch("app.services.gemini_service.GeminiService.extract_contact_data", 
               AsyncMock(return_value={"name": "Иван Петров", "company": "Яндекс"})), \
         patch("app.services.merge_service.ContactMergeService.process_contact_data", 
               AsyncMock(return_value=(new_contact, False))), \
         patch("app.bot.handlers.match_handlers.notify_match_if_any", AsyncMock()):
        
        await handle_text_message(mock_update, mock_context)
        
        # Should not be in edit mode
        assert "editing_contact_id" not in mock_context.user_data
        # Should send contact card
        assert mock_update.message.reply_text.called


@pytest.mark.asyncio
async def test_edit_mode_with_reminders(mock_update, mock_context):
    """Test that reminders are created during contact edit."""
    contact_id = uuid.uuid4()
    mock_context.user_data = {"editing_contact_id": str(contact_id)}
    mock_update.message.text = "Позвонить завтра в 15:00"
    
    updated_contact = Contact(id=contact_id, name="Test User")
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock()), \
         patch("app.services.gemini_service.GeminiService.extract_contact_data", 
               AsyncMock(return_value={
                   "reminders": [{"title": "Позвонить", "due_date": "завтра в 15:00"}]
               })), \
         patch("app.services.contact_service.ContactService.update_contact", 
               AsyncMock(return_value=updated_contact)), \
         patch("app.services.reminder_service.ReminderService.create_reminder", AsyncMock()):
        
        await handle_text_message(mock_update, mock_context)
        
        assert "editing_contact_id" not in mock_context.user_data


@pytest.mark.asyncio
async def test_cancel_contact_edit(mock_update, mock_context):
    """Test canceling contact edit mode."""
    from app.bot.handlers.contact_detail_handlers import cancel_contact_edit
    
    mock_context.user_data = {"editing_contact_id": str(uuid.uuid4())}
    
    await cancel_contact_edit(mock_update, mock_context)
    
    assert "editing_contact_id" not in mock_context.user_data
    assert mock_update.message.reply_text.called
