"""
Tests for scheduled sync functionality.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.core.scheduler import scheduled_sync_job
from app.models.user import User
import uuid


@pytest.mark.asyncio
async def test_scheduled_sync_job_with_notion_credentials():
    """Test that scheduled sync runs for users with Notion credentials."""
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        name="Test User",
        settings={
            "notion_api_key": "secret_test_key",
            "notion_database_id": "test_db_id"
        }
    )
    
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch("app.db.session.AsyncSessionLocal", return_value=mock_session), \
         patch("app.services.user_service.UserService.get_all_users", 
               AsyncMock(return_value=[test_user])), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[MagicMock(id=uuid.uuid4())])), \
         patch("app.services.notion_service.NotionService.sync_contacts", 
               AsyncMock(return_value={"created": 0, "updated": 0, "failed": 0})) as mock_sync:
        
        await scheduled_sync_job()
        
        # Verify that Notion sync was called
        assert mock_sync.called


@pytest.mark.asyncio
async def test_scheduled_sync_job_with_sheets_credentials():
    """Test that scheduled sync runs for users with Google Sheets credentials."""
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        name="Test User",
        settings={
            "google_sheet_id": "test_sheet_id",
            "google_proj_id": "test_project",
            "google_client_email": "test@example.com",
            "google_private_key": "test_key"
        }
    )
    
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch("app.db.session.AsyncSessionLocal", return_value=mock_session), \
         patch("app.services.user_service.UserService.get_all_users", 
               AsyncMock(return_value=[test_user])), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[MagicMock(id=uuid.uuid4())])), \
         patch("app.services.sheets_service.SheetsService.sync_contacts", 
               AsyncMock(return_value={"created": 0, "updated": 0, "failed": 0})) as mock_sync:
        
        await scheduled_sync_job()
        
        # Verify that Sheets sync was called
        assert mock_sync.called


@pytest.mark.asyncio
async def test_scheduled_sync_job_skips_users_without_credentials():
    """Test that scheduled sync skips users without any credentials."""
    test_user = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        name="Test User",
        settings={}
    )
    
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch("app.db.session.AsyncSessionLocal", return_value=mock_session), \
         patch("app.services.user_service.UserService.get_all_users", 
               AsyncMock(return_value=[test_user])), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[])), \
         patch("app.services.notion_service.NotionService.sync_contacts", 
               AsyncMock()) as mock_notion, \
         patch("app.services.sheets_service.SheetsService.sync_contacts", 
               AsyncMock()) as mock_sheets:
        
        await scheduled_sync_job()
        
        # Verify that no sync was called
        assert not mock_notion.called
        assert not mock_sheets.called


@pytest.mark.asyncio
async def test_scheduled_sync_job_handles_errors_gracefully():
    """Test that scheduled sync continues even if one user's sync fails."""
    user1 = User(
        id=uuid.uuid4(),
        telegram_id=12345,
        name="User 1",
        settings={
            "notion_api_key": "secret_key_1",
            "notion_database_id": "db_id_1"
        }
    )
    
    user2 = User(
        id=uuid.uuid4(),
        telegram_id=67890,
        name="User 2",
        settings={
            "notion_api_key": "secret_key_2",
            "notion_database_id": "db_id_2"
        }
    )
    
    call_count = 0
    
    async def mock_sync_with_error(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Sync failed for user 1")
        return {"created": 0, "updated": 0, "failed": 0}
    
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch("app.db.session.AsyncSessionLocal", return_value=mock_session), \
         patch("app.services.user_service.UserService.get_all_users", 
               AsyncMock(return_value=[user1, user2])), \
         patch("app.services.contact_service.ContactService.get_all_contacts", 
               AsyncMock(return_value=[MagicMock(id=uuid.uuid4())])), \
         patch("app.services.notion_service.NotionService.sync_contacts", 
               side_effect=mock_sync_with_error):
        
        # Should not raise exception
        await scheduled_sync_job()
        
        # Both users should have been attempted
        assert call_count == 2
