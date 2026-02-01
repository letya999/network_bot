import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers import handle_text_message, handle_contact, handle_voice
from app.models.contact import Contact
import uuid
import time
from telegram.error import BadRequest

@pytest.fixture(autouse=True)
def mock_match_notify():
    with patch("app.bot.handlers.contact_handlers.notify_match_if_any", AsyncMock()) as mock:
        yield mock

def assert_msg_contains(mock_reply_text, substring):
    found = False
    for call in mock_reply_text.call_args_list:
        if substring in call[0][0]:
            found = True
            break
    assert found, f"Message containing '{substring}' not found. Calls: {mock_reply_text.call_args_list}"

@pytest.mark.asyncio
async def test_handle_text_contact_creation(mock_update, mock_context):
    mock_update.message.text = "John Doe @johndoe"
    mock_data = {"name": "John Doe", "telegram_username": "johndoe"}
    
    # Mock AIService
    mock_ai_instance = MagicMock()
    mock_ai_instance.extract_contact_data = AsyncMock(return_value=mock_data)
    
    with patch("app.bot.handlers.contact_handlers.AIService", return_value=mock_ai_instance) as MockAI, \
         patch("app.bot.handlers.contact_handlers.extract_contact_info", return_value={"telegram_username": "johndoe"}), \
         patch("app.services.contact_service.ContactService.find_by_identifiers", AsyncMock(return_value=None)), \
         patch("app.services.contact_service.ContactService.create_contact", AsyncMock(return_value=Contact(**mock_data))), \
         patch("app.bot.handlers.contact_handlers.UserService") as MockUserService, \
         patch("app.bot.handlers.contact_handlers.AsyncSessionLocal") as session_ctx:

        # Setup User Service to return settings
        mock_user = MagicMock(id=uuid.uuid4(), custom_prompt=None)
        mock_user.settings = {"ai_provider": "openai", "openai_api_key": "sk-...", "gemini_api_key": "A..."}
        mock_user_service = MockUserService.return_value
        mock_user_service.get_or_create_user = AsyncMock(return_value=mock_user)
        
        session_ctx.return_value.__aenter__.return_value = AsyncMock()

        mock_context.bot.get_chat = AsyncMock(return_value=MagicMock(username="johndoe"))
        
        await handle_text_message(mock_update, mock_context)
        
        # Verify AIService initialized with keys from settings
        MockAI.assert_called_with(
            gemini_api_key="A...",
            openai_api_key="sk-...",
            preferred_provider="openai"
        )
        assert_msg_contains(mock_update.message.reply_text, "Contact saved")

@pytest.mark.asyncio
async def test_handle_contact_shared(mock_update, mock_context):
    mock_update.message.contact = MagicMock(phone_number="+123", first_name="John")
    mock_contact = Contact(name="John", phone="+123", id=uuid.uuid4())
    
    with patch("app.services.contact_service.ContactService.find_by_identifiers", AsyncMock(return_value=None)), \
         patch("app.services.contact_service.ContactService.create_contact", AsyncMock(return_value=mock_contact)), \
         patch("app.bot.handlers.contact_handlers.UserService") as MockUserService, \
         patch("app.bot.handlers.contact_handlers.AsyncSessionLocal"):
            
             MockUserService.return_value.get_or_create_user = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
             await handle_contact(mock_update, mock_context)
             assert_msg_contains(mock_update.message.reply_text, "John")

@pytest.mark.asyncio
async def test_handle_voice_merge(mock_update, mock_context):
    mock_context.user_data["last_contact_id"] = uuid.uuid4()
    mock_context.user_data["last_contact_time"] = time.time()
    mock_update.message.voice = MagicMock(file_id="v1", duration=5, file_size=100)
    
    # Mock Open
    with patch("builtins.open", MagicMock()) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b'OggS'
        
        # Mock other dependencies
        mock_ai_instance = MagicMock()
        mock_ai_instance.extract_contact_data = AsyncMock(return_value={"agreements": ["Test"]})

        with patch("app.bot.handlers.contact_handlers.AIService", return_value=mock_ai_instance), \
             patch("os.path.exists", return_value=True), patch("os.remove"), patch("os.rmdir"), patch("tempfile.mkdtemp", return_value="tmp"), \
             patch("app.bot.handlers.contact_handlers.ContactMergeService") as MockMergeService:
            
            # Setup mock merge service to return merged=True
            mock_service_instance = MockMergeService.return_value
            # Returns (Contact, was_merged)
            mock_service_instance.process_contact_data = AsyncMock(return_value=(Contact(id=uuid.uuid4(), name="Merged Contact"), True))
            mock_service_instance.is_reminder_only.return_value = False
            
            # Mock Session for post-processing check
            mock_session = AsyncMock()
            mock_session.get.return_value = Contact(name="Merged Contact", telegram_username="merged", id=uuid.uuid4())
            mock_session.close = AsyncMock()
            
            # Mock AsyncSessionLocal context manager
            mock_session_ctx = MagicMock()
            mock_session_ctx.__aenter__.return_value = mock_session
            mock_session_ctx.__aexit__.return_value = None
            
            with patch("app.bot.handlers.contact_handlers.AsyncSessionLocal", return_value=mock_session_ctx), \
                 patch("app.bot.handlers.contact_handlers.UserService") as MockUserService:
                
                # Setup mock user service
                mock_user_service = MockUserService.return_value
                mock_user_service.get_or_create_user = AsyncMock(return_value=MagicMock(id=uuid.uuid4(), custom_prompt=None))

                await handle_voice(mock_update, mock_context)
            
            # The status message is returned by the first reply_text call
            status_msg_mock = mock_update.message.reply_text.return_value
            
            # Check for merge confirmation message (it's an edit to the status message)
            assert_msg_contains(status_msg_mock.edit_text, "Merged")
            
            # Check validation of final card (sent via reply_text)
            last_call_args = mock_update.message.reply_text.call_args
            assert "Merged Contact" in last_call_args[0][0]

@pytest.mark.asyncio
async def test_voice_too_large(mock_update, mock_context):
    mock_update.message.voice = MagicMock(file_size=25 * 1024 * 1024)
    await handle_voice(mock_update, mock_context)
    assert_msg_contains(mock_update.message.reply_text, "File too large")
