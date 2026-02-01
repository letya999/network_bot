import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram.ext import ConversationHandler
from app.bot.handlers.credentials_handlers import (
    set_credentials_command, service_choice_callback, handle_input,
    cancel_creds, SELECT_SERVICE, WAITING_INPUT,
    SERVICE_GEMINI, SERVICE_TAVILY, SERVICE_OPENAI, SERVICE_NOTION, SERVICE_SHEETS, SERVICE_AUTO, SERVICE_AI_PROVIDER
)
from app.models.user import User
import uuid

@pytest.fixture
def mock_user_service():
    with patch("app.bot.handlers.credentials_handlers.UserService") as mock:
        yield mock

@pytest.fixture
def mock_session_local():
    with patch("app.bot.handlers.credentials_handlers.AsyncSessionLocal") as mock:
        yield mock

@pytest.mark.asyncio
async def test_start_credentials(mock_update, mock_context):
    """Test opening credentials menu."""
    res = await set_credentials_command(mock_update, mock_context)
    
    assert res == SELECT_SERVICE
    assert "Настройка доступов" in mock_update.message.reply_text.call_args[0][0]
    assert mock_update.message.reply_text.call_args[1]["reply_markup"] # check keyboard exists

@pytest.mark.asyncio
async def test_service_choice_provider_menus(mock_update, mock_context):
    """Test selecting a service to prompt for input."""
    # Test simple service
    mock_update.callback_query.data = SERVICE_GEMINI
    
    res = await service_choice_callback(mock_update, mock_context)
    
    assert res == WAITING_INPUT
    assert mock_context.user_data["creds_service"] == SERVICE_GEMINI
    assert "Gemini API Key" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_service_choice_ai_provider(mock_update, mock_context):
    """Test entering AI provider submenu."""
    mock_update.callback_query.data = SERVICE_AI_PROVIDER
    
    res = await service_choice_callback(mock_update, mock_context)
    
    assert res == SELECT_SERVICE # Stay in menu but show wrapper
    assert "Выбор основного провайдера" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_service_choice_set_provider_setting(mock_update, mock_context, mock_session_local, mock_user_service):
    """Test actually setting the provider."""
    mock_update.callback_query.data = "set_provider_openai"
    mock_update.callback_query.from_user.id = 12345
    
    mock_user = MagicMock()
    mock_user.settings = {}
    mock_user_service.return_value.get_or_create_user.return_value = mock_user
    
    service_instance = AsyncMock()
    service_instance.get_or_create_user.return_value = mock_user
    mock_user_service.return_value = service_instance
    
    res = await service_choice_callback(mock_update, mock_context)
    
    assert res == ConversationHandler.END
    assert mock_user.settings["ai_provider"] == "openai"
    assert "OpenAI GPT" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_handle_input_simple_key(mock_update, mock_context, mock_session_local, mock_user_service):
    """Test entering simple API key."""
    mock_update.message.text = "sk-123456"
    mock_context.user_data["creds_service"] = SERVICE_OPENAI
    
    mock_user = MagicMock()
    mock_user.settings = {}
    service_instance = AsyncMock()
    service_instance.get_or_create_user.return_value = mock_user
    mock_user_service.return_value = service_instance
    
    res = await handle_input(mock_update, mock_context)
    
    assert res == ConversationHandler.END
    assert mock_user.settings["openai_api_key"] == "sk-123456"
    assert "OpenAI API Key сохранен" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_handle_input_notion(mock_update, mock_context, mock_session_local, mock_user_service):
    """Test parsing notion input."""
    # multiline input
    mock_update.message.text = "secret_abc123\ndatabase_id_32chars"
    mock_context.user_data["creds_service"] = SERVICE_NOTION
    
    mock_user = MagicMock()
    mock_user.settings = {}
    service_instance = AsyncMock()
    service_instance.get_or_create_user.return_value = mock_user
    mock_user_service.return_value = service_instance
    
    res = await handle_input(mock_update, mock_context)
    
    assert res == ConversationHandler.END
    # Our simple parser looks for "secret_" and 32 chars
    assert mock_user.settings["notion_api_key"] == "secret_abc123"
    # assert mock_user.settings["notion_database_id"] == "database_id_32chars" 
    # Logic: len(line.strip()) == 32 and "-" not in line => database_id_32chars is < 32 chars? no it's 19 chars.
    # Wait, 32 chars is typical uuid without dashes. "database_id_32chars" is 19.
    
    # Let's fix input to match logic
    mock_update.message.text = "secret_abc123\n12345678901234567890123456789012" # 32 chars
    
    await handle_input(mock_update, mock_context)
    assert mock_user.settings.get("notion_database_id") == "12345678901234567890123456789012"


@pytest.mark.asyncio
async def test_handle_input_sheets(mock_update, mock_context, mock_session_local, mock_user_service):
    """Test parsing sheets env vars."""
    text = (
        "GOOGLE_PROJ_ID=my-project\n"
        "GOOGLE_CLIENT_EMAIL=\"bot@email.com\"\n"
        "GOOGLE_PRIVATE_KEY=\"-----BEGIN PRIVATE KEY-----\\nMIIEvQ...\\n-----END PRIVATE KEY-----\"\n"
    )
    mock_update.message.text = text
    mock_context.user_data["creds_service"] = SERVICE_SHEETS
    
    mock_user = MagicMock()
    mock_user.settings = {}
    service_instance = AsyncMock()
    service_instance.get_or_create_user.return_value = mock_user
    mock_user_service.return_value = service_instance
    
    res = await handle_input(mock_update, mock_context)
    
    assert res == ConversationHandler.END
    assert mock_user.settings["google_proj_id"] == "my-project"
    assert mock_user.settings["google_client_email"] == "bot@email.com"
    assert "-----BEGIN PRIVATE KEY-----" in mock_user.settings["google_private_key"] 

@pytest.mark.asyncio
async def test_handle_input_auto(mock_update, mock_context, mock_session_local, mock_user_service):
    """Test auto parsing of multiple keys."""
    text = (
        "OPENAI_API_KEY=sk-test\n"
        "GEMINI_API_KEY=AIzaSy\n"
        "# Comment\n"
        "\n"
        "TAVILY_API_KEY=tvly-123"
    )
    mock_update.message.text = text
    mock_context.user_data["creds_service"] = SERVICE_AUTO
    
    mock_user = MagicMock()
    mock_user.settings = {}
    service_instance = AsyncMock()
    service_instance.get_or_create_user.return_value = mock_user
    mock_user_service.return_value = service_instance
    
    res = await handle_input(mock_update, mock_context)
    
    assert res == ConversationHandler.END
    assert mock_user.settings["openai_api_key"] == "sk-test"
    assert mock_user.settings["gemini_api_key"] == "AIzaSy"
    assert mock_user.settings["tavily_api_key"] == "tvly-123"
