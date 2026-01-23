import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.bot.handlers import list_contacts, find_contact
from app.models.contact import Contact
import uuid

@pytest.mark.asyncio
async def test_list_contacts_empty(mock_update, mock_context, mock_session):
    with patch("app.bot.handlers.AsyncSessionLocal") as mock_db_cls:
        mock_db_cls.return_value.__aenter__.return_value = mock_session
        
        await list_contacts(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_with("У тебя пока нет контактов.")

@pytest.mark.asyncio
async def test_find_contact_results(mock_update, mock_context, mock_session):
    mock_context.args = ["John"]
    
    # Mock search results
    c1 = Contact(id=uuid.uuid4(), name="John Doe", company="Acme")
    
    # Mock returning result from scalar execution or scalars().all()
    # Logic in handler: await contact_service.find_contacts(...)
    # We rely on mocking the DB call inside service.
    
    # Easier: Mock ContactService inside handler
    with patch("app.bot.handlers.ContactService") as mock_service_cls, \
         patch("app.bot.handlers.UserService") as mock_user_cls, \
         patch("app.bot.handlers.AsyncSessionLocal"): 
         
        mock_service = mock_service_cls.return_value
        mock_service.find_contacts = AsyncMock(return_value=[c1])
        
        # Configure UserService mock
        mock_user_service = mock_user_cls.return_value
        # MUST be AsyncMock because it's awaited
        mock_user_service.get_or_create_user = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        
        await find_contact(mock_update, mock_context)
        
        # Verify reply contains contact info
        # handler sends 2 messages: 1. list, 2. buttons prompt
        # We need to check if ANY of the calls contained the contact name
        found_contact_text = False
        for call in mock_update.message.reply_text.call_args_list:
            args, _ = call
            if "John Doe" in args[0] and "Acme" in args[0]:
                found_contact_text = True
                break
        
        assert found_contact_text, "Contact info not found in any reply message"
        
        # Verify InlineKeyboard (button) was added since results <= 5 (Phase 2 feature)
        # Check the last call usually (or find the one with reply_markup)
        found_markup = False
        for call in mock_update.message.reply_text.call_args_list:
            _, kwargs = call
            if "reply_markup" in kwargs:
                found_markup = True
                break
                
        assert found_markup, "Inline keyboard for card generation not found"
        
        assert mock_update.message.reply_text.call_count >= 1
