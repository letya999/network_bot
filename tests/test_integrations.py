
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.notion_service import NotionService
from app.services.sheets_service import SheetsService
from app.bot.integration_handlers import sync_command, export_contact_callback
from app.models.contact import Contact

# -----------------------------------------------------------------------------
# NotionService Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "secret_123")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db_123")

@pytest.mark.asyncio
async def test_notion_sync_contacts_success(mock_notion_env):
    # Mock settings in the module where they are used
    with patch("app.services.notion_service.settings") as mock_settings, \
         patch("app.services.notion_service.aiohttp.ClientSession") as MockSession:
        
        mock_settings.NOTION_API_KEY = "secret_123"
        mock_settings.NOTION_DATABASE_ID = "db_123"

        # Session context manager (MockSession()) returns a session object
        # The session object itself should NOT be AsyncMock for methods like post/get if we use 'async with session.post()' 
        # because AsyncMock methods return coroutines, but 'async with' expects a CM object immediately from the call, 
        # (unless the function is async def, but here we invoke it and context manage the RESULT).
        # Actually aiohttp.post() returns a RequestContextManager which is awaitable.
        # But for mocking, it's easier to make session.post return a MagicMock that is an async CM.
        
        session = MagicMock()
        MockSession.return_value.__aenter__.return_value = session
        
        # Prepare Response objects (which act as Context Managers)
        # 1. Query Response
        resp_query = AsyncMock()
        resp_query.status = 200
        resp_query.json.return_value = {"results": [], "has_more": False}
        resp_query.__aenter__.return_value = resp_query
        
        # 2. Create Response
        resp_create = AsyncMock()
        resp_create.status = 200
        resp_create.__aenter__.return_value = resp_create
        
        # session.post should return these objects directly (not wrapped in coroutine)
        session.post.side_effect = [resp_query, resp_create]
        
        service = NotionService()
        contact = Contact(name="Test User", phone="+1234567890")
        
        result = await service.sync_contacts([contact])
        
        assert result["created"] == 1
        assert result["failed"] == 0

@pytest.mark.asyncio
async def test_notion_sync_contacts_missing_creds(monkeypatch):
    # We patch settings to have None
    with patch("app.services.notion_service.settings") as mock_settings:
        mock_settings.NOTION_API_KEY = None
        mock_settings.NOTION_DATABASE_ID = None
        
        service = NotionService()
        result = await service.sync_contacts([])
        assert "error" in result

# -----------------------------------------------------------------------------
# SheetsService Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_sheets_env(monkeypatch):
    # This fixture might not be enough if we need to patch settings object directly
    pass

@pytest.mark.asyncio
async def test_sheets_sync_contacts_success(): 
    # Mock settings and gspread
    with patch("app.services.sheets_service.settings") as mock_settings, \
         patch("app.services.sheets_service.HAS_GSPREAD", True), \
         patch("app.services.sheets_service.gspread.authorize") as mock_auth, \
         patch("app.services.sheets_service.Credentials.from_service_account_info"):
        
        # Setup settings
        mock_settings.GOOGLE_SHEET_ID = "sheet_123"
        mock_settings.GOOGLE_CLIENT_EMAIL = "email@test.com"
        mock_settings.GOOGLE_PRIVATE_KEY = "key"
        mock_settings.GOOGLE_PRIVATE_KEY_ID = "keyid"
        mock_settings.GOOGLE_PROJ_ID = "proj"

        mock_client = MagicMock()
        mock_auth.return_value = mock_client
        
        mock_sheet = MagicMock()
        mock_client.open_by_key.return_value = mock_sheet
        
        mock_ws = MagicMock()
        mock_sheet.worksheet.return_value = mock_ws
        
        # Mock get_all_values
        mock_ws.get_all_values.return_value = [
            ["Name", "Company", "Role"], # Header
        ]
        
        service = SheetsService()
        contact = Contact(name="Test User", updated_at=None, topics=[])
        
        # Run sync (it runs in thread so we just await it)
        result = await service.sync_contacts([contact])
        
        assert result["created"] == 1
        mock_ws.append_rows.assert_called()

# -----------------------------------------------------------------------------
# Bot Handler Tests (Integration Handlers)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_command_notion(mock_update, mock_context):
    mock_context.args = ["notion"]
    mock_user = MagicMock(id=123, username="test")
    mock_update.effective_user = mock_user
    
    # Setup message mocks with AsyncMock for reply_text and edit_text
    status_msg_mock = MagicMock()
    status_msg_mock.edit_text = AsyncMock()
    mock_update.message.reply_text = AsyncMock(return_value=status_msg_mock)
    mock_update.effective_message = mock_update.message
    
    # Mock mocks
    with patch("app.bot.integration_handlers.AsyncSessionLocal"), \
         patch("app.bot.integration_handlers.UserService") as MockUserSvc, \
         patch("app.bot.integration_handlers.ContactService") as MockContactSvc, \
         patch("app.bot.integration_handlers.NotionService") as MockNotionSvc:
         
        # Ensure the instance method is an AsyncMock
        mock_notion_instance = MockNotionSvc.return_value
        # Important: Assign AsyncMock to the METHOD, not the return value of method
        mock_notion_instance.sync_contacts = AsyncMock(return_value={"created": 1, "updated": 0, "failed": 0})
        
        mock_contact_svc = MockContactSvc.return_value
        # Ensure return value is iterable
        mock_contact_svc.get_all_contacts = AsyncMock(return_value=[MagicMock()])
        
        # Fix: ensure user service returns user with settings
        mock_db_user = MagicMock()
        mock_db_user.id = 1
        mock_db_user.settings = {}
        MockUserSvc.return_value.get_or_create_user = AsyncMock(return_value=mock_db_user)

        await sync_command(mock_update, mock_context)
        
        # Verify success message
        mock_update.message.reply_text.assert_called()
        # Check that edit_text was called on the return value of reply_text (the status message)
        status_msg_mock.edit_text.assert_called()
        args = status_msg_mock.edit_text.call_args[0][0]
        assert "Синхронизация завершена" in args

@pytest.mark.asyncio
async def test_export_callback_flow(mock_update, mock_context):
    mock_update.callback_query.data = "export_notion_12345"
    
    mock_session = AsyncMock()
    
    with patch("app.bot.integration_handlers.AsyncSessionLocal", return_value=mock_session), \
         patch("app.bot.integration_handlers.NotionService") as MockNotionSvc:
        
        mock_session.__aenter__.return_value = mock_session
        
        # Mock get contact
        mock_contact = MagicMock()
        mock_contact.name = "Test Contact"
        mock_session.get.return_value = mock_contact
        
        # Mock service
        mock_notion_instance = MockNotionSvc.return_value
        mock_notion_instance.sync_contacts = AsyncMock(return_value={"created": 1, "updated": 0, "failed": 0})
        
        await export_contact_callback(mock_update, mock_context)
        
        mock_session.get.assert_called()
        mock_notion_instance.sync_contacts.assert_called_with([mock_contact])
        
        # message.reply_text might be called on query.message
        assert "добавлен" in mock_update.callback_query.message.reply_text.call_args[0][0]
