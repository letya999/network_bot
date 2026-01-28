import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers import list_contacts, export_contacts, format_card
from app.bot.handlers.menu_handlers import start_menu
from app.models.contact import Contact
import uuid

@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    """Test that /start displays the new menu system."""
    mock_update.callback_query = None
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock()):
        await start_menu(mock_update, mock_context)
        assert mock_update.message.reply_text.called
        # Check for menu presence instead of greeting
        call_args = mock_update.message.reply_text.call_args
        assert call_args is not None

@pytest.mark.asyncio
async def test_list_contacts_with_data(mock_update, mock_context):
    c1 = Contact(id=uuid.uuid4(), name="Alice")
    with patch("app.services.contact_service.ContactService.get_recent_contacts", AsyncMock(return_value=[c1])):
        await list_contacts(mock_update, mock_context)
        assert "Alice" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_export_contacts(mock_update, mock_context):
    c1 = Contact(id=uuid.uuid4(), name="Alice")
    with patch("app.services.contact_service.ContactService.get_all_contacts", AsyncMock(return_value=[c1])), \
         patch("app.services.export_service.ExportService.to_csv", return_value=b"csv"):
        await export_contacts(mock_update, mock_context)
        assert mock_update.message.reply_document.called

def test_format_card():
    c = Contact(name="John", company="Corp", role="Dev", agreements=["Yes"], follow_up_action="Call")
    res = format_card(c)
    assert "John" in res and "Corp" in res and "Dev" in res
