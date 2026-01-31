"""
Tests for integration handlers (sync commands).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers.integration_handlers import sync_command, sync_run_callback, sync_notion, sync_sheets
from app.models.user import User
from app.models.contact import Contact
import uuid


@pytest.mark.asyncio
async def test_sync_command_shows_service_selection(mock_update, mock_context):
    """Test that /sync without args shows service selection buttons."""
    mock_update.callback_query = None
    mock_context.args = []
    
    await sync_command(mock_update, mock_context)
    
    assert mock_update.message.reply_text.called
    call_kwargs = mock_update.message.reply_text.call_args[1]
    assert 'reply_markup' in call_kwargs


@pytest.mark.asyncio
async def test_sync_command_via_callback_shows_selection(mock_update, mock_context):
    """Test that sync command via callback query shows service selection."""
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.message = MagicMock()
    mock_update.callback_query.message.edit_text = AsyncMock()
    
    await sync_command(mock_update, mock_context)
    
    assert mock_update.callback_query.message.edit_text.called


@pytest.mark.asyncio
async def test_sync_run_callback_notion(mock_update, mock_context):
    """Test sync callback for Notion."""
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.data = "sync_run_notion"
    mock_update.effective_user = MagicMock(id=12345)
    mock_update.effective_message = MagicMock()
    mock_update.effective_message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        settings={
            "notion_api_key": "secret_key",
            "notion_database_id": "db_id"
        }
    )
    
    with patch("app.services.user_service.UserService.get_or_create_user", 
               AsyncMock(return_value=test_user)), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[])), \
         patch("app.services.notion_service.NotionService.sync_contacts", 
               AsyncMock(return_value={"created": 0, "updated": 0, "failed": 0})):
        
        await sync_run_callback(mock_update, mock_context)
        
        assert mock_update.callback_query.answer.called


@pytest.mark.asyncio
async def test_sync_notion_with_contacts(mock_update, mock_context):
    """Test Notion sync with actual contacts."""
    mock_update.effective_user = MagicMock(id=12345, username="testuser")
    mock_update.effective_message = MagicMock()
    mock_update.effective_message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        settings={
            "notion_api_key": "secret_key",
            "notion_database_id": "db_id"
        }
    )
    
    test_contacts = [
        Contact(id=uuid.uuid4(), name="Contact 1", company="Company A"),
        Contact(id=uuid.uuid4(), name="Contact 2", company="Company B")
    ]
    
    with patch("app.services.user_service.UserService.get_or_create_user", 
               AsyncMock(return_value=test_user)), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=test_contacts)), \
         patch("app.services.notion_service.NotionService.sync_contacts", 
               AsyncMock(return_value={"created": 2, "updated": 0, "failed": 0})) as mock_sync:
        
        await sync_notion(mock_update, mock_context)
        
        # Verify sync was called with contacts
        assert mock_sync.called
        assert mock_sync.call_args[0][0] == test_contacts


@pytest.mark.asyncio
async def test_sync_sheets_with_no_contacts(mock_update, mock_context):
    """Test Sheets sync with no contacts."""
    mock_update.effective_user = MagicMock(id=12345, username="testuser")
    mock_update.effective_message = MagicMock()
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(return_value=status_msg)
    
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        settings={
            "google_sheet_id": "sheet_id"
        }
    )
    
    with patch("app.services.user_service.UserService.get_or_create_user", 
               AsyncMock(return_value=test_user)), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[])):
        
        await sync_sheets(mock_update, mock_context)
        
        # Should show "no contacts" message
        assert status_msg.edit_text.called
        call_text = status_msg.edit_text.call_args[0][0]
        assert "Нет контактов" in call_text or "нет" in call_text.lower()


@pytest.mark.asyncio
async def test_sync_notion_handles_errors(mock_update, mock_context):
    """Test that Notion sync handles errors gracefully."""
    mock_update.effective_user = MagicMock(id=12345, username="testuser")
    mock_update.effective_message = MagicMock()
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    mock_update.effective_message.reply_text = AsyncMock(return_value=status_msg)
    
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        settings={
            "notion_api_key": "secret_key",
            "notion_database_id": "db_id"
        }
    )
    
    with patch("app.services.user_service.UserService.get_or_create_user", 
               AsyncMock(return_value=test_user)), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[Contact(id=uuid.uuid4(), name="Test")])), \
         patch("app.services.notion_service.NotionService.sync_contacts", 
               AsyncMock(return_value={"error": "API key invalid"})):
        
        await sync_notion(mock_update, mock_context)
        
        # Should show error message
        assert status_msg.edit_text.called
        call_text = status_msg.edit_text.call_args[0][0]
        assert "Ошибка" in call_text or "ошибка" in call_text.lower()
