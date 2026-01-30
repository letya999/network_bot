import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.bot.handlers.contact_handlers import handle_voice, handle_contact, handle_text_message
from app.models.contact import Contact
from app.models.user import User
import uuid


@pytest.mark.asyncio
async def test_triangulation_notification_on_voice_contact(mock_update, mock_context):
    """Test that triangulation notification is sent when voice creates contact with matching company"""
    user_id = 12345
    mock_update.effective_user.id = user_id
    mock_update.message.voice.duration = 10
    mock_update.message.voice.file_size = 1000
    mock_update.message.voice.file_id = "test_file_id"
    
    # Mock bot.get_file
    mock_file = AsyncMock()
    mock_file.download_to_drive = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)
    
    # Mock the database user
    db_user = User(id=uuid.uuid4(), telegram_id=user_id, name="Test User")
    
    # New contact from voice
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Alice Johnson",
        company="TechCorp",
        status="active"
    )
    
    # Existing contact from same company
    existing_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Bob Smith",
        company="TechCorp",
        role="CEO",
        status="active"
    )
    
    # Mock file content to simulate OGG file
    mock_file_content = b'OggS' + b'\x00' * 100
    
    with patch("app.bot.handlers.contact_handlers.rate_limit_middleware", AsyncMock(return_value=True)), \
         patch("app.bot.handlers.contact_handlers.UserService") as MockUserSvc, \
         patch("app.bot.handlers.contact_handlers.GeminiService") as MockGemini, \
         patch("app.bot.handlers.contact_handlers.ContactMergeService") as MockMerge, \
         patch("app.bot.handlers.contact_handlers.notify_match_if_any", AsyncMock()), \
         patch("app.bot.handlers.contact_handlers.PulseService") as MockPulse, \
         patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=mock_file_content)))))), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove"), \
         patch("os.rmdir"), \
         patch("tempfile.mkdtemp", return_value="/tmp/test"):
        
        # Configure mocks
        MockUserSvc.return_value.get_or_create_user = AsyncMock(return_value=db_user)
        MockGemini.return_value.extract_contact_data = AsyncMock(return_value={"name": "Alice Johnson", "company": "TechCorp"})
        MockMerge.return_value.process_contact_data = AsyncMock(return_value=(new_contact, False))
        MockMerge.return_value.is_reminder_only = MagicMock(return_value=False)
        MockPulse.return_value.detect_company_triangulation = AsyncMock(return_value=[existing_contact])
        MockPulse.return_value.generate_triangulation_message = MagicMock(return_value="🔺 *Триангуляция обнаружена!*\n\nAlice Johnson работает в TechCorp\n\nДругие контакты:\n• Bob Smith")
        
        await handle_voice(mock_update, mock_context)
        
        # Check that triangulation message was sent
        calls = mock_update.message.reply_text.call_args_list
        triangulation_sent = False
        for call in calls:
            if "Триангуляция обнаружена" in call[0][0]:
                triangulation_sent = True
                assert "Alice Johnson" in call[0][0]
                assert "TechCorp" in call[0][0]
                assert "Bob Smith" in call[0][0]
                break
        
        assert triangulation_sent, "Triangulation notification was not sent"


@pytest.mark.asyncio
async def test_no_triangulation_when_merged(mock_update, mock_context):
    """Test that triangulation is NOT triggered when contact is merged"""
    user_id = 12345
    mock_update.effective_user.id = user_id
    mock_update.message.voice.duration = 10
    mock_update.message.voice.file_size = 1000
    mock_update.message.voice.file_id = "test_file_id"
    
    # Mock bot.get_file
    mock_file = AsyncMock()
    mock_file.download_to_drive = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)
    
    db_user = User(id=uuid.uuid4(), telegram_id=user_id, name="Test User")
    
    merged_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Alice Johnson",
        company="TechCorp",
        status="active"
    )
    
    # Mock file content to simulate OGG file
    mock_file_content = b'OggS' + b'\x00' * 100
    
    with patch("app.bot.handlers.contact_handlers.rate_limit_middleware", AsyncMock(return_value=True)), \
         patch("app.services.user_service.UserService.get_or_create_user", AsyncMock(return_value=db_user)), \
         patch("app.services.gemini_service.GeminiService.extract_contact_data", AsyncMock(return_value={"name": "Alice Johnson", "company": "TechCorp"})), \
         patch("app.services.merge_service.ContactMergeService.process_contact_data", AsyncMock(return_value=(merged_contact, True))), \
         patch("app.services.merge_service.ContactMergeService.is_reminder_only", return_value=False), \
         patch("app.bot.handlers.match_handlers.notify_match_if_any", AsyncMock()), \
         patch("app.services.pulse_service.PulseService.detect_company_triangulation", AsyncMock()) as mock_triangulation, \
         patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=mock_file_content)))))), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove"), \
         patch("os.rmdir"), \
         patch("tempfile.mkdtemp", return_value="/tmp/test"):
        
        await handle_voice(mock_update, mock_context)
        
        # Triangulation should NOT be called when contact was merged
        mock_triangulation.assert_not_called()


@pytest.mark.asyncio
async def test_triangulation_on_shared_contact(mock_update, mock_context):
    """Test triangulation when Telegram contact is shared"""
    user_id = 12345
    mock_update.effective_user.id = user_id
    mock_update.message.contact.first_name = "Alice"
    mock_update.message.contact.last_name = "Johnson"
    mock_update.message.contact.phone_number = "+1234567890"
    
    db_user = User(id=uuid.uuid4(), telegram_id=user_id, name="Test User")
    
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Alice Johnson",
        company="TechCorp",
        phone="+1234567890",
        status="active"
    )
    
    existing_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Bob Smith",
        company="TechCorp",
        status="active"
    )
    
    with patch("app.bot.handlers.contact_handlers.rate_limit_middleware", AsyncMock(return_value=True)), \
         patch("app.services.user_service.UserService.get_or_create_user", AsyncMock(return_value=db_user)), \
         patch("app.services.merge_service.ContactMergeService.process_contact_data", AsyncMock(return_value=(new_contact, False))), \
         patch("app.bot.handlers.match_handlers.notify_match_if_any", AsyncMock()), \
         patch("app.services.pulse_service.PulseService.detect_company_triangulation", AsyncMock(return_value=[existing_contact])):
        
        await handle_contact(mock_update, mock_context)
        
        # Check triangulation message
        calls = mock_update.message.reply_text.call_args_list
        triangulation_sent = any("Триангуляция" in str(call) for call in calls)
        assert triangulation_sent


@pytest.mark.asyncio
async def test_triangulation_on_text_contact(mock_update, mock_context):
    """Test triangulation when contact is created from text message"""
    user_id = 12345
    mock_update.effective_user.id = user_id
    mock_update.message.text = "Met Alice Johnson from TechCorp, she's the new CTO"
    
    db_user = User(id=uuid.uuid4(), telegram_id=user_id, name="Test User")
    
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Alice Johnson",
        company="TechCorp",
        role="CTO",
        status="active"
    )
    
    existing_contacts = [
        Contact(id=uuid.uuid4(), user_id=db_user.id, name="Bob Smith", company="TechCorp", status="active"),
        Contact(id=uuid.uuid4(), user_id=db_user.id, name="Carol White", company="TechCorp", status="active"),
    ]
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock(return_value=db_user)), \
         patch("app.services.gemini_service.GeminiService.extract_contact_data", AsyncMock(return_value={"name": "Alice Johnson", "company": "TechCorp", "role": "CTO"})), \
         patch("app.services.merge_service.ContactMergeService.process_contact_data", AsyncMock(return_value=(new_contact, False))), \
         patch("app.services.merge_service.ContactMergeService.is_reminder_only", return_value=False), \
         patch("app.bot.handlers.match_handlers.notify_match_if_any", AsyncMock()), \
         patch("app.services.pulse_service.PulseService.detect_company_triangulation", AsyncMock(return_value=existing_contacts)):
        
        await handle_text_message(mock_update, mock_context)
        
        # Check that triangulation message mentions multiple contacts
        calls = mock_update.message.reply_text.call_args_list
        triangulation_sent = False
        for call in calls:
            if "Триангуляция" in call[0][0] and "2 контакт" in call[0][0]:
                triangulation_sent = True
                assert "Bob Smith" in call[0][0]
                assert "Carol White" in call[0][0]
                break
        
        assert triangulation_sent, "Multi-contact triangulation notification was not sent"


@pytest.mark.asyncio
async def test_no_triangulation_without_company(mock_update, mock_context):
    """Test that no triangulation happens when contact has no company"""
    user_id = 12345
    mock_update.effective_user.id = user_id
    mock_update.message.text = "Met Alice Johnson, great person"
    
    db_user = User(id=uuid.uuid4(), telegram_id=user_id, name="Test User")
    
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=db_user.id,
        name="Alice Johnson",
        company=None,  # No company
        status="active"
    )
    
    with patch("app.services.user_service.UserService.get_or_create_user", AsyncMock(return_value=db_user)), \
         patch("app.services.gemini_service.GeminiService.extract_contact_data", AsyncMock(return_value={"name": "Alice Johnson"})), \
         patch("app.services.merge_service.ContactMergeService.process_contact_data", AsyncMock(return_value=(new_contact, False))), \
         patch("app.services.merge_service.ContactMergeService.is_reminder_only", return_value=False), \
         patch("app.bot.handlers.match_handlers.notify_match_if_any", AsyncMock()), \
         patch("app.services.pulse_service.PulseService.detect_company_triangulation", AsyncMock(return_value=[])) as mock_triangulation:
        
        await handle_text_message(mock_update, mock_context)
        
        # Triangulation should be called but return empty list
        mock_triangulation.assert_called_once()
        
        # No triangulation message should be sent
        calls = mock_update.message.reply_text.call_args_list
        triangulation_sent = any("Триангуляция" in str(call) for call in calls)
        assert not triangulation_sent
