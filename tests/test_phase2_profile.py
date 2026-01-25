import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.bot.profile_handlers import show_profile, handle_edit_callback, save_profile_value
from app.models.user import User

@pytest.mark.asyncio
async def test_show_profile_creates_user(mock_update, mock_context, mock_session):
    # Simulate /profile command (no callback)
    mock_update.callback_query = None
    
    # Mock finding user -> None initially
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    mock_session.__aenter__.return_value = mock_session
    
    with patch("app.bot.profile_handlers.AsyncSessionLocal", return_value=mock_session):
        await show_profile(mock_update, mock_context)
        
    # verify user was added
    assert mock_session.add.called
    added_user = mock_session.add.call_args[0][0]
    assert isinstance(added_user, User)
    assert added_user.telegram_id == 12345
    
    # Verify reply sent
    assert mock_update.message.reply_text.called

@pytest.mark.asyncio
async def test_show_profile_existing_user(mock_update, mock_context, mock_session):
    # Simulate /profile command
    mock_update.callback_query = None

    # Mock existing user
    user = User(telegram_id=12345, name="Test", profile_data={"bio": "My Bio", "company": "Acme"})
    
    # Mock execute -> return user
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute.return_value = mock_result
    
    mock_session.__aenter__.return_value = mock_session
    
    with patch("app.bot.profile_handlers.AsyncSessionLocal", return_value=mock_session):
        await show_profile(mock_update, mock_context)
        
    # Verify reply contains bio and company
    args, _ = mock_update.message.reply_text.call_args
    text = args[0]
    assert "My Bio" in text
    assert "Acme" in text

@pytest.mark.asyncio
async def test_edit_profile_callback(mock_update, mock_context, mock_session):
    mock_update.callback_query.data = "edit_bio"
    # Note: handle_edit_callback calls query.edit_message_text, not reply_text
    
    await handle_edit_callback(mock_update, mock_context)
    
    # Check edit_message_text is called on the query
    assert mock_update.callback_query.edit_message_text.called
    assert "Напишите кратко о себе (био)" in mock_update.callback_query.edit_message_text.call_args[0][0]
    assert mock_context.user_data['edit_field'] == 'bio'

@pytest.mark.asyncio
async def test_save_profile_value(mock_update, mock_context, mock_session):
    mock_context.user_data['edit_field'] = 'company'
    mock_update.message.text = "New Company Inc"
    
    # Mock existing user
    user = User(telegram_id=12345, profile_data={})
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute.return_value = mock_result
    
    mock_session.__aenter__.return_value = mock_session
    
    with patch("app.bot.profile_handlers.AsyncSessionLocal", return_value=mock_session):
        res = await save_profile_value(mock_update, mock_context)
        
    # Verify DB update
    assert "company" in user.profile_data
    assert user.profile_data["company"] == "New Company Inc"
    assert mock_session.commit.called
    
    # Verify success message
    assert mock_update.message.reply_text.called
