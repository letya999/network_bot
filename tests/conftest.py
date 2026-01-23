import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Message, Voice, Contact as TgContact, Chat
from telegram.ext import ContextTypes

@pytest.fixture
def mock_session():
    session = AsyncMock()
    # Mock execute result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result
    
    # session.add is synchronous in SQLAlchemy, so we mock it as a standard function/MagicMock
    # prevents "coroutine never awaited" warning and logic errors if code expects sync
    session.add = MagicMock()
    
    return session

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 12345
    update.effective_user.username = "test_user"
    update.effective_user.first_name = "Test"
    
    update.message = MagicMock(spec=Message)
    update.message.chat = MagicMock(spec=Chat)
    update.message.chat.id = 12345
    update.message.reply_text = AsyncMock()
    
    return update

@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    return context
