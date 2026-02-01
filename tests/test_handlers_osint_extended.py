import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram.ext import ConversationHandler
from app.bot.handlers.osint_handlers import (
    handle_csv_import, enrich_callback, WAITING_FOR_CSV
)

@pytest.mark.asyncio
async def test_handle_csv_import_success(mock_update, mock_context):
    """Test successful CSV import."""
    # Setup mock file
    mock_file = AsyncMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=b"name,company\nJohn,Corp")
    mock_context.bot.get_file = AsyncMock(return_value=mock_file)
    
    mock_update.message.document.file_name = "contacts.csv"
    mock_update.message.document.file_size = 100
    
    # Configure reply_text return value (status_message) to have awaitable edit_text
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    mock_update.message.reply_text.return_value = status_msg
    
    with patch("app.bot.handlers.osint_handlers.rate_limit_middleware", return_value=True), \
         patch("app.bot.handlers.osint_handlers.AsyncSessionLocal") as mock_db, \
         patch("app.bot.handlers.osint_handlers.UserService") as mock_user_svc, \
         patch("app.bot.handlers.osint_handlers.format_osint_data", return_value="Stats"), \
         patch("app.bot.handlers.osint_handlers.CSVImportService") as mock_csv_svc:
         
         mock_user_svc.return_value.get_or_create_user = AsyncMock()
         mock_user = MagicMock(settings={})
         mock_user.id = 1
         mock_user_svc.return_value.get_or_create_user.return_value = mock_user

         mock_csv_svc.validate_csv_file.return_value = None  # Validation success
         mock_csv_svc.return_value.import_linkedin_csv = AsyncMock(return_value=(5, 2, [])) # imported, skipped, error
         
         res = await handle_csv_import(mock_update, mock_context)
         
         assert res == ConversationHandler.END
         # Check that status message was edited with result
         status_msg = mock_update.message.reply_text.return_value
         assert "Импортировано: 5" in status_msg.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_handle_csv_import_invalid_file(mock_update, mock_context):
    """Test invalid file handling."""
    mock_update.message.document = None
    
    with patch("app.bot.handlers.osint_handlers.rate_limit_middleware", return_value=True):
        res = await handle_csv_import(mock_update, mock_context)
        assert res == WAITING_FOR_CSV
        assert "отправь CSV" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_enrich_callback_select(mock_update, mock_context):
    """Test selecting a candidate from enrich search."""
    # Data format: enrich_select_{contact_id}_{index}
    valid_uuid = "12345678-1234-5678-1234-567812345678"
    mock_update.callback_query.data = f"enrich_select_{valid_uuid}_0"
    
    # Prepare context data
    mock_context.user_data = {
        f"enrich_candidates_{valid_uuid}": [{"name": "Cand 1", "url": "http://linkedin.com/in/cand1"}]
    }
    
    with patch("app.bot.handlers.osint_handlers.AsyncSessionLocal"), \
         patch("app.bot.handlers.osint_handlers.format_osint_data", return_value="Raw Data"), \
         patch("app.bot.handlers.osint_handlers.UserService") as mock_user_svc, \
         patch("app.bot.handlers.osint_handlers.OSINTService") as mock_osint:
         
         mock_user_svc.return_value.get_or_create_user = AsyncMock()
         mock_user = MagicMock(settings={})
         mock_user.id = 1
         mock_user_svc.return_value.get_or_create_user.return_value = mock_user

         mock_osint.return_value.enrich_contact_final = AsyncMock(return_value={
             "status": "success", 
             "data": {"education": []}
         })
         
         await enrich_callback(mock_update, mock_context)
         
         mock_osint.return_value.enrich_contact_final.assert_called_once()
         assert "Информация обновлена" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_enrich_callback_start(mock_update, mock_context):
    """Test enrich_start (ambiguous name resolution)."""
    valid_uuid = "12345678-1234-5678-1234-567812345678"
    mock_update.callback_query.data = f"enrich_start_{valid_uuid}"
    
    with patch("app.bot.handlers.osint_handlers.AsyncSessionLocal") as mock_db, \
         patch("app.bot.handlers.osint_handlers.UserService") as mock_user_svc, \
         patch("app.bot.handlers.osint_handlers.OSINTService") as mock_osint:
         
         # Mock session get contact
         mock_contact = MagicMock()
         mock_contact.name = "John Doe"
         mock_contact.id = valid_uuid
         # mock_db session.get is async
         mock_db.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_contact)
         
         # Mock user service
         mock_user_svc.return_value.get_or_create_user = AsyncMock()
         mock_user_svc.return_value.get_or_create_user.return_value = MagicMock(settings={})
         
         mock_osint.return_value.search_potential_profiles = AsyncMock(return_value=[{"name": "John", "url": "url"}])
         
         await enrich_callback(mock_update, mock_context)
         
         assert "Нашел профили" in mock_update.callback_query.edit_message_text.call_args[0][0]
         mock_osint.return_value.search_potential_profiles.assert_called_once()
