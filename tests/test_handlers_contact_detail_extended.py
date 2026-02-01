import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import InlineKeyboardMarkup
from app.bot.handlers.contact_detail_handlers import (
    manage_contact_contacts_menu, delete_contact_field_handler,
    add_contact_start, handle_contact_edit_field,
    CONTACT_DEL_FIELD_PREFIX
)
from app.models.contact import Contact
import uuid

@pytest.fixture
def mock_contact_service():
    with patch("app.bot.handlers.contact_detail_handlers.ContactService") as mock:
        yield mock

@pytest.fixture
def mock_session():
    with patch("app.bot.handlers.contact_detail_handlers.AsyncSessionLocal") as mock:
        yield mock

@pytest.mark.asyncio
async def test_manage_contact_contacts_menu(mock_update, mock_context, mock_session, mock_contact_service):
    """Test displaying contact management menu."""
    contact_id = uuid.uuid4()
    mock_context.user_data = {"editing_contact_id": str(contact_id)}
    
    mock_contact = MagicMock()
    mock_contact.name = "Test User"
    mock_contact.phone = "123"
    mock_contact.telegram_username = "tguser"
    mock_contact.attributes = {
        "custom_contacts": [{"label": "Custom", "value": "Val"}]
    }
    mock_contact_service.return_value.get_contact_by_id = AsyncMock(return_value=mock_contact)
    
    mock_session.return_value.__aenter__.return_value = AsyncMock() # session
    
    await manage_contact_contacts_menu(mock_update, mock_context)
    
    assert mock_update.effective_message.reply_text.called
    args, kwargs = mock_update.effective_message.reply_text.call_args
    assert "Контакты (Test User)" in kwargs.get("text", "")
    
    # Check keyboard entries
    keyboard = kwargs.get("reply_markup").inline_keyboard
    assert any("Телефон: 123" in b.text for row in keyboard for b in row)
    assert any("Custom: Val" in b.text for row in keyboard for b in row)

@pytest.mark.asyncio
async def test_delete_contact_field_standard(mock_update, mock_context, mock_session, mock_contact_service):
    """Test deleting a standard field (phone)."""
    contact_id = uuid.uuid4()
    mock_context.user_data = {"editing_contact_id": str(contact_id)}
    mock_update.callback_query.data = f"{CONTACT_DEL_FIELD_PREFIX}phone"
    
    mock_contact = MagicMock()
    mock_contact.id = contact_id
    mock_contact_service.return_value.get_contact_by_id.return_value = mock_contact
    
    mock_svc_instance = AsyncMock()
    mock_svc_instance.get_contact_by_id.return_value = mock_contact
    mock_contact_service.return_value = mock_svc_instance
    
    # Needs to patch recursively calling manage_contact_contacts_menu
    with patch("app.bot.handlers.contact_detail_handlers.manage_contact_contacts_menu", new_callable=AsyncMock) as mock_menu:
        await delete_contact_field_handler(mock_update, mock_context)
        
        mock_svc_instance.update_contact.assert_called_once()
        assert mock_svc_instance.update_contact.call_args[0][1] == {"phone": None}
        mock_menu.assert_called_once()

@pytest.mark.asyncio
async def test_delete_contact_field_custom(mock_update, mock_context, mock_session, mock_contact_service):
    """Test deleting a custom field by index."""
    contact_id = uuid.uuid4()
    mock_context.user_data = {"editing_contact_id": str(contact_id)}
    # Delete index 0
    mock_update.callback_query.data = f"{CONTACT_DEL_FIELD_PREFIX}custom_0"
    
    mock_contact = MagicMock()
    mock_contact.id = contact_id
    mock_contact.attributes = {
        "custom_contacts": [
            {"label": "Keep", "value": "1"}, 
            {"label": "Delete", "value": "2"}
        ]
    }
    
    mock_svc_instance = AsyncMock()
    mock_svc_instance.get_contact_by_id.return_value = mock_contact
    mock_contact_service.return_value = mock_svc_instance
    
    with patch("app.bot.handlers.contact_detail_handlers.manage_contact_contacts_menu", new_callable=AsyncMock):
        await delete_contact_field_handler(mock_update, mock_context)
        
        mock_svc_instance.update_contact.assert_called_once()
        # Should have popped index 0 ("Keep")? Wait, logic test:
        # If I want to delete index 0, result list should be just index 1.
        args = mock_svc_instance.update_contact.call_args[0][1]
        assert "custom_contacts" in args
        assert len(args["custom_contacts"]) == 1
        assert args["custom_contacts"][0]["label"] == "Delete" # wait, if I popped 0, 1 remains.

@pytest.mark.asyncio
async def test_add_contact_start(mock_update, mock_context):
    """Test starting add contact wizard."""
    await add_contact_start(mock_update, mock_context)
    
    assert mock_context.user_data['edit_contact_field'] == 'add_contact_label'
    mock_context.bot.send_message.assert_called_once()
    assert "название" in mock_context.bot.send_message.call_args[1]['text'].lower()

@pytest.mark.asyncio
async def test_handle_contact_edit_field(mock_update, mock_context):
    """Test explicit field selection for editing."""
    # Prefix + field name
    mock_update.callback_query.data = "contact_field_company"
    
    await handle_contact_edit_field(mock_update, mock_context)
    
    assert mock_context.user_data['edit_contact_field'] == 'company'
    mock_context.bot.send_message.assert_called_once()
    assert "Компания" in mock_context.bot.send_message.call_args[1]['text']
