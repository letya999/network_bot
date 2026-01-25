import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes

@pytest.fixture
def mock_session():
    session = AsyncMock()
    
    # Setup execute result
    mock_result = MagicMock()
    # Ensure scalar_one_or_none returns a value, not a coroutine
    mock_result.scalar_one_or_none.return_value = None 
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalars.return_value.first.return_value = None
    
    # Configure session.execute to return this result when awaited
    session.execute.side_effect = None
    session.execute.return_value = mock_result
    
    # Configure session.get to return None by default
    session.get.return_value = None
    
    # Standard methods
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    
    return session

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    
    # User
    user = MagicMock(spec=User)
    user.id = 12345
    user.username = "test_user"
    user.first_name = "Test"
    update.effective_user = user
    
    # Message
    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 12345
    message.text = "Hello"
    message.reply_text = AsyncMock()
    message.reply_document = AsyncMock()
    update.message = message
    
    # Callback Query
    # Note: Important to link message here if callback edits it
    cb = MagicMock(spec=CallbackQuery)
    cb.data = "test_data"
    cb.message = message 
    cb.answer = AsyncMock()
    cb.edit_message_text = AsyncMock()
    cb.edit_message_reply_markup = AsyncMock()
    update.callback_query = cb
    
    return update

@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.args = []
    return context

@pytest.fixture
def mock_scheduler(monkeypatch):
    """Mock the global scheduler object in app.core.scheduler"""
    scheduler_mock = MagicMock()
    scheduler_mock.add_job = MagicMock()
    scheduler_mock.remove_job = MagicMock()
    
    # Patch the reference in potential import locations
    for target in ["app.core.scheduler.scheduler", "app.services.reminder_service.scheduler"]:
        try:
            monkeypatch.setattr(target, scheduler_mock)
        except AttributeError:
            pass # Module might not be imported yet
            
    return scheduler_mock
