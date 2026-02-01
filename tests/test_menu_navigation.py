import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers.menu_handlers import start_menu, menu_callback, MAIN_MENU, PROFILE_MENU

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.first_name = "Test"
    update.effective_user.username = "test_user"
    update.effective_user.last_name = None
    update.message.reply_text = AsyncMock()
    update.callback_query.message.message_id = 999
    update.callback_query.data = MAIN_MENU
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    # effective_chat is needed for cleanup
    update.effective_chat.id = 456
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    context.bot.delete_message = AsyncMock()
    return context

@pytest.mark.asyncio
async def test_start_menu_new_message(mock_update, mock_context):
    mock_update.callback_query = None # Emulate command
    
    with patch("app.bot.handlers.menu_handlers.AsyncSessionLocal"), \
         patch("app.bot.handlers.menu_handlers.UserService") as MockUserService:
         
        mock_user_service = MockUserService.return_value
        mock_user_service.get_or_create_user = AsyncMock()
        
        await start_menu(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        args = mock_update.message.reply_text.call_args
        assert "Главный пульт" in args[0][0] or "Привет" in args[0][0]

@pytest.mark.asyncio
async def test_start_menu_callback(mock_update, mock_context):
    # Setup callback
    mock_update.callback_query.data = MAIN_MENU
    
    with patch("app.bot.handlers.menu_handlers.AsyncSessionLocal"), \
         patch("app.bot.handlers.menu_handlers.UserService") as MockUserService:
         
        mock_user_service = MockUserService.return_value
        mock_user_service.get_or_create_user = AsyncMock()

        await start_menu(mock_update, mock_context)
        
        mock_update.callback_query.edit_message_text.assert_called_once()
        mock_update.callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_menu_callback_navigation(mock_update, mock_context):
    mock_update.callback_query.data = PROFILE_MENU
    
    with patch("app.bot.handlers.menu_handlers.AsyncSessionLocal"), \
         patch("app.bot.handlers.menu_handlers.UserService") as MockUserService, \
         patch("app.bot.handlers.menu_handlers.ProfileService") as MockProfileService:
         
        # Setup mock user service
        mock_user_service = MockUserService.return_value
        mock_user_service.get_or_create_user = AsyncMock()
         
        mock_profile = MagicMock()
        mock_profile.full_name = "Test Name"
        mock_profile.job_title = "Tester"
        mock_profile.company = "TestCo"
        mock_profile.interests = ["Coding"]
        
        MockProfileService.return_value.get_profile = AsyncMock(return_value=mock_profile)
        
        await menu_callback(mock_update, mock_context)
        
        mock_update.callback_query.edit_message_text.assert_called_once()
        args = mock_update.callback_query.edit_message_text.call_args
        assert "Ваш Профиль" in args[1]['text']
        assert "TestCo" in args[1]['text']
