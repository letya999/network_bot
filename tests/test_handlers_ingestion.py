import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.handlers import handle_text_message, handle_contact, handle_voice
from app.models.contact import Contact
import uuid
import time
from telegram.error import BadRequest

@pytest.fixture(autouse=True)
def mock_match_notify():
    with patch("app.bot.match_handlers.notify_match_if_any", AsyncMock()) as mock:
        yield mock

def assert_msg_contains(mock_reply_text, substring):
    found = False
    for call in mock_reply_text.call_args_list:
        if substring in call[0][0]:
            found = True
            break
    assert found, f"Message containing '{substring}' not found"

@pytest.mark.asyncio
async def test_handle_text_contact_creation(mock_update, mock_context):
    mock_update.message.text = "John Doe @johndoe"
    mock_data = {"name": "John Doe", "telegram_username": "johndoe"}
    
    with patch("app.services.gemini_service.GeminiService.extract_contact_data", AsyncMock(return_value=mock_data)), \
         patch("app.bot.handlers.extract_contact_info", return_value={"telegram_username": "johndoe"}), \
         patch("app.services.contact_service.ContactService.find_by_identifiers", AsyncMock(return_value=None)), \
         patch("app.services.contact_service.ContactService.create_contact", AsyncMock(return_value=Contact(**mock_data))):
        
        mock_context.bot.get_chat = AsyncMock(return_value=MagicMock(username="johndoe"))
        await handle_text_message(mock_update, mock_context)
        assert_msg_contains(mock_update.message.reply_text, "Контакт сохранен")

@pytest.mark.asyncio
async def test_handle_contact_shared(mock_update, mock_context):
    mock_update.message.contact = MagicMock(phone_number="+123", first_name="John")
    with patch("app.services.contact_service.ContactService.find_by_identifiers", AsyncMock(return_value=None)), \
         patch("app.services.contact_service.ContactService.create_contact", AsyncMock(return_value=Contact(name="John", phone="+123"))):
        await handle_contact(mock_update, mock_context)
        assert_msg_contains(mock_update.message.reply_text, "John")

@pytest.mark.asyncio
async def test_handle_voice_merge(mock_update, mock_context):
    mock_context.user_data["last_contact_id"] = uuid.uuid4()
    mock_context.user_data["last_contact_time"] = time.time()
    mock_update.message.voice = MagicMock(file_id="v1", duration=5, file_size=100)
    
    with patch("app.services.gemini_service.GeminiService.extract_contact_data", AsyncMock(return_value={"agreements": ["Test"]})), \
         patch("app.services.contact_service.ContactService.update_contact", AsyncMock(return_value=Contact(name="Merged"))), \
         patch("app.bot.handlers.open", MagicMock()) as mock_open:
        
        mock_open.return_value.__enter__.return_value.read.return_value = b'OggS'
        with patch("os.path.exists", return_value=True), patch("os.remove"), patch("os.rmdir"), patch("tempfile.mkdtemp", return_value="tmp"):
            await handle_voice(mock_update, mock_context)
            assert_msg_contains(mock_update.message.reply_text, "Merged")

@pytest.mark.asyncio
async def test_voice_too_large(mock_update, mock_context):
    mock_update.message.voice = MagicMock(file_size=25 * 1024 * 1024)
    await handle_voice(mock_update, mock_context)
    assert_msg_contains(mock_update.message.reply_text, "слишком большой")
