import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update

from app.bot.handlers.search_handlers import list_contacts
from app.bot.handlers.match_handlers import find_matches_command
from app.bot.handlers.reminder_handlers import list_reminders
from app.bot.handlers.event_handlers import set_event_mode
from app.models.contact import Contact
from app.models.reminder import Reminder, ReminderStatus
from datetime import datetime

@pytest.mark.asyncio
async def test_list_contacts_with_buttons(mock_update, mock_context, mock_session):
    """
    Verify that /list (list_contacts) returns an InlineKeyboardMarkup with buttons.
    """
    # Setup
    mock_contact_service = AsyncMock()
    mock_contact = MagicMock(spec=Contact)
    mock_contact.id = "c1"
    mock_contact.name = "John Doe"
    mock_contact.company = "OpenAI"
    mock_contact_service.get_recent_contacts.return_value = [mock_contact]
    
    # We need to verify UserService is also mocked properly as AsyncMock
    mock_user_service = AsyncMock()
    
    # We need to patch the Service instantiation inside the handler
    with patch("app.bot.handlers.search_handlers.ContactService", return_value=mock_contact_service), \
         patch("app.bot.handlers.search_handlers.UserService", return_value=mock_user_service):
        
        await list_contacts(mock_update, mock_context)
        
        # Verify reply was called
        # Depending on if it was callback or message
        message = mock_update.effective_message
        if mock_update.callback_query:
            assert message.edit_text.called or message.reply_text.called
        else:
            assert message.reply_text.called
        
        # Verify arguments
        if mock_update.callback_query:
            if message.edit_text.called:
                args, kwargs = message.edit_text.call_args
            else:
                args, kwargs = message.reply_text.call_args
        else:
             args, kwargs = message.reply_text.call_args
        assert "reply_markup" in kwargs
        markup = kwargs["reply_markup"]
        assert isinstance(markup, InlineKeyboardMarkup)
        
        # Verify button content
        # markup.inline_keyboard is a list of lists (rows of buttons)
        assert len(markup.inline_keyboard) == 2 # 1 contact row + 1 back row
        button = markup.inline_keyboard[0][0]
        assert "John Doe" in button.text
        assert button.callback_data == "contact_view_c1"

@pytest.mark.asyncio
async def test_find_matches_callback_handling(mock_update, mock_context, mock_session):
    """
    Verify find_matches_command handles callback queries (answers them) and uses effective_message.
    """
    # Setup callback query
    mock_update.callback_query.data = "cmd_matches"
    
    # Setup data
    mock_context.user_data = {"last_contact_id": "c1"}
    
    mock_match_service = AsyncMock()
    mock_match_service.get_user_matches.return_value = {"is_match": True, "synergy_summary": "Great match", "suggested_pitch": "Hi"}
    mock_match_service.find_peer_matches.return_value = []
    
    # Mock Contact retrieval: session.get(Contact, ...)
    mock_contact = MagicMock(spec=Contact)
    mock_contact.name = "Alice"
    mock_session.get.return_value = mock_contact
    
    mock_user_service = AsyncMock()

    with patch("app.bot.handlers.match_handlers.MatchService", return_value=mock_match_service), \
         patch("app.bot.handlers.match_handlers.UserService", return_value=mock_user_service):
         
        await find_matches_command(mock_update, mock_context)
        
        # Verify callback answer
        mock_update.callback_query.answer.assert_called_once()
        
        # Verify effective_message usage (status msg + result)
        assert mock_update.effective_message.reply_text.call_count >= 2

@pytest.mark.asyncio
async def test_list_reminders_callback_handling(mock_update, mock_context):
    """
    Verify list_reminders answers callback and uses effective_message.
    """
    mock_update.callback_query.data = "cmd_reminders"
    
    mock_reminder_service = AsyncMock()
    mock_reminder = MagicMock(spec=Reminder)
    mock_reminder.id = "r1"
    mock_reminder.title = "Call Bob"
    mock_reminder.due_at = datetime(2024, 1, 1, 12, 0)
    
    mock_reminder_service.get_user_reminders.return_value = [mock_reminder]
    
    mock_user_service = AsyncMock()
    
    with patch("app.bot.handlers.reminder_handlers.ReminderService", return_value=mock_reminder_service), \
         patch("app.bot.handlers.reminder_handlers.UserService", return_value=mock_user_service):
         
        await list_reminders(mock_update, mock_context)
        
        mock_update.callback_query.answer.assert_called_once()
        mock_update.effective_message.reply_text.assert_called()
        
        # Verify buttons
        args, kwargs = mock_update.effective_message.reply_text.call_args
        assert "reply_markup" in kwargs
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)

@pytest.mark.asyncio
async def test_set_event_mode_callback_handling(mock_update, mock_context):
    """
    Verify set_event_mode answers callback (e.g. from settings menu) and uses effective_message.
    """
    mock_update.callback_query.data = "cmd_event"
    # No args -> shows help or status
    mock_context.args = []
    mock_context.user_data = {}
    
    await set_event_mode(mock_update, mock_context)
    
    mock_update.callback_query.answer.assert_called_once()
    mock_update.effective_message.reply_text.assert_called()
    assert "Режим мероприятия" in mock_update.effective_message.reply_text.call_args[0][0]
