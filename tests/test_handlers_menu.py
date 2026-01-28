"""
Tests for menu navigation handlers.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers.menu_handlers import start_menu, menu_callback
from app.bot.handlers.contact_detail_handlers import (
    view_contact, delete_contact_ask, delete_contact_confirm, edit_contact_start
)
from app.models.contact import Contact
import uuid


@pytest.mark.asyncio
async def test_start_menu_displays_main_menu(mock_update, mock_context):
    """Test that /start displays the main menu with all sections."""
    mock_update.callback_query = None
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock()):
        await start_menu(mock_update, mock_context)
        
        assert mock_update.message.reply_text.called
        call_args = mock_update.message.reply_text.call_args
        
        # Check if text is in args or kwargs
        if call_args[0]:
            text = call_args[0][0]
        else:
            text = call_args[1].get('text', '')
        
        # Check main menu sections are present
        assert "меню" in text.lower() or "главн" in text.lower()


@pytest.mark.asyncio
async def test_menu_callback_navigation(mock_update, mock_context):
    """Test menu navigation between sections."""
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = "menu_profile"
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock()):
        await menu_callback(mock_update, mock_context)
        
        assert mock_update.callback_query.answer.called
        assert mock_update.callback_query.edit_message_text.called


@pytest.mark.asyncio
async def test_view_contact_detail(mock_update, mock_context):
    """Test viewing contact details."""
    contact_id = uuid.uuid4()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = f"contact_view_{contact_id}"
    
    test_contact = Contact(
        id=contact_id,
        name="Test User",
        company="Test Corp",
        role="Developer",
        phone="+1234567890"
    )
    
    with patch("app.services.contact_service.ContactService.get_contact_by_id", AsyncMock(return_value=test_contact)):
        await view_contact(mock_update, mock_context)
        
        assert mock_update.callback_query.edit_message_text.called
        call_text = mock_update.callback_query.edit_message_text.call_args[1]['text']
        assert "Test User" in call_text
        assert "Test Corp" in call_text


@pytest.mark.asyncio
async def test_delete_contact_confirmation_flow(mock_update, mock_context):
    """Test delete contact confirmation flow."""
    contact_id = uuid.uuid4()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = f"contact_del_ask_{contact_id}"
    
    test_contact = Contact(id=contact_id, name="Test User")
    
    with patch("app.services.contact_service.ContactService.get_contact_by_id", AsyncMock(return_value=test_contact)):
        await delete_contact_ask(mock_update, mock_context)
        
        assert mock_update.callback_query.edit_message_text.called
        call_text = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "удалить" in call_text.lower()


@pytest.mark.asyncio
async def test_delete_contact_confirm(mock_update, mock_context):
    """Test actual contact deletion."""
    contact_id = uuid.uuid4()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = f"contact_del_yes_{contact_id}"
    
    with patch("app.services.contact_service.ContactService.delete_contact", AsyncMock(return_value=True)):
        await delete_contact_confirm(mock_update, mock_context)
        
        assert mock_update.callback_query.edit_message_text.called
        call_text = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "удален" in call_text.lower() or "✅" in call_text


@pytest.mark.asyncio
async def test_edit_contact_start_sets_context(mock_update, mock_context):
    """Test that edit contact sets editing mode in context."""
    contact_id = uuid.uuid4()
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = f"contact_edit_{contact_id}"
    mock_context.user_data = {}
    
    test_contact = Contact(id=contact_id, name="Test User")
    
    with patch("app.services.contact_service.ContactService.get_contact_by_id", AsyncMock(return_value=test_contact)):
        await edit_contact_start(mock_update, mock_context)
        
        # Check that editing_contact_id is set
        assert "editing_contact_id" in mock_context.user_data
        assert str(mock_context.user_data["editing_contact_id"]) == str(contact_id)


@pytest.mark.asyncio
async def test_menu_callback_handles_back_navigation(mock_update, mock_context):
    """Test back button navigation."""
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = "menu_main"
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock()):
        await menu_callback(mock_update, mock_context)
        
        assert mock_update.callback_query.edit_message_text.called
        # Should show main menu
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert call_args is not None
