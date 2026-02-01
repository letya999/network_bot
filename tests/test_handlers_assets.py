import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram.ext import ConversationHandler
from app.bot.handlers.assets_handler import (
    start_assets, show_asset_list, asset_menu_callback, 
    show_asset_detail, asset_action_callback, save_asset_name, 
    save_asset_content, delete_asset, ASSET_MENU, ASSET_INPUT_NAME, 
    ASSET_INPUT_CONTENT
)
from app.schemas.profile import ContentItem, UserProfile
from app.models.user import User
import uuid

@pytest.fixture
def mock_profile_service():
    with patch("app.bot.handlers.assets_handler.ProfileService") as mock:
        yield mock

@pytest.fixture
def mock_session_local():
    with patch("app.bot.handlers.assets_handler.AsyncSessionLocal") as mock:
        yield mock

@pytest.mark.asyncio
async def test_start_assets_command(mock_update, mock_context, mock_session_local):
    """Test starting asset conversation via command."""
    mock_update.message.text = "/pitches"
    mock_update.callback_query = None  # Ensure it treats as message, not callback
    
    # Mock profile service
    mock_service = AsyncMock()
    mock_service.get_profile.return_value = UserProfile(pitches=[])
    mock_session_local.return_value.__aenter__.return_value = AsyncMock()
    
    # We also need to patch ProfileService(session) -> service
    with patch("app.bot.handlers.assets_handler.ProfileService", return_value=mock_service):
        res = await start_assets(mock_update, mock_context)
        
        assert res == ASSET_MENU
        assert mock_context.user_data["current_asset_type"] == "pitch"
        # Check that list was shown (empty)
        assert mock_update.message.reply_text.called
        assert "Ваши Питчи" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_start_assets_unknown(mock_update, mock_context):
    """Test starting with unknown command."""
    mock_update.message.text = "/unknown"
    mock_context.user_data = {}
    
    res = await start_assets(mock_update, mock_context)
    
    assert res == ConversationHandler.END
    assert "Неизвестная" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_asset_menu_callback_add(mock_update, mock_context):
    """Test clicking 'Add' in asset menu."""
    mock_update.callback_query.data = "asset_add"
    mock_context.user_data["current_asset_type"] = "pitch"
    
    res = await asset_menu_callback(mock_update, mock_context)
    
    assert res == ASSET_INPUT_NAME
    assert mock_update.callback_query.edit_message_text.called
    assert "название" in mock_update.callback_query.edit_message_text.call_args[0][0].lower()

@pytest.mark.asyncio
async def test_save_asset_flow(mock_update, mock_context, mock_session_local):
    """Test full flow of adding a new asset."""
    # 1. Save Name
    mock_update.message.text = "My Startup"
    mock_context.user_data["current_asset_type"] = "pitch"
    # Not in edit mode
    
    res = await save_asset_name(mock_update, mock_context)
    
    assert res == ASSET_INPUT_CONTENT
    assert mock_context.user_data["new_asset_name"] == "My Startup"
    assert "текст" in mock_update.message.reply_text.call_args[0][0].lower()
    
    # 2. Save Content
    mock_update.message.text = "We are disrupting X"
    
    mock_service = AsyncMock()
    mock_profile = MagicMock()
    # Mock getattr to return a list we can append to
    mock_profile.pitches = [] 
    mock_service.get_profile.return_value = mock_profile
    
    with patch("app.bot.handlers.assets_handler.ProfileService", return_value=mock_service):
        res = await save_asset_content(mock_update, mock_context)
        
        assert res == ASSET_MENU # show_asset_detail returns ASSET_MENU
        assert len(mock_profile.pitches) == 1
        assert mock_profile.pitches[0].name == "My Startup"
        assert mock_profile.pitches[0].content == "We are disrupting X"
        
        # Verify DB update called
        mock_service.update_profile_field.assert_called_once()
        assert mock_service.update_profile_field.call_args[0][1] == "pitches"
        
        # Verify success message and detail view
        # save_asset_content replies "Saved!" then calls show_asset_detail_message which replies with Detail View
        assert mock_update.message.reply_text.call_count >= 2

@pytest.mark.asyncio
async def test_show_asset_detail(mock_update, mock_context, mock_session_local):
    """Test viewing a specific asset."""
    asset_id = "uuid-123"
    mock_context.user_data["current_asset_type"] = "pitch"
    mock_context.user_data["current_asset_id"] = asset_id
    
    mock_service = AsyncMock()
    item = ContentItem(name="Test Pitch", content="Content", type="text")
    item.id = asset_id # override check
    mock_profile = MagicMock()
    mock_profile.pitches = [item]
    mock_service.get_profile.return_value = mock_profile
    
    with patch("app.bot.handlers.assets_handler.ProfileService", return_value=mock_service):
        res = await show_asset_detail(mock_update, mock_context)
        
        assert res == ASSET_MENU
        assert "Test Pitch" in mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Content" in mock_update.callback_query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_delete_asset(mock_update, mock_context, mock_session_local):
    """Test deleting an asset."""
    asset_id = "uuid-123"
    mock_context.user_data["current_asset_type"] = "pitch"
    mock_context.user_data["current_asset_id"] = asset_id
    
    mock_service = AsyncMock()
    item = ContentItem(name="Test Pitch", content="Content", type="text")
    item.id = asset_id
    mock_profile = MagicMock()
    mock_profile.pitches = [item]
    mock_service.get_profile.return_value = mock_profile
    
    with patch("app.bot.handlers.assets_handler.ProfileService", return_value=mock_service):
        res = await delete_asset(mock_update, mock_context)
        
        # Should call update with EMPTY list
        mock_service.update_profile_field.assert_called_once()
        assert mock_service.update_profile_field.call_args[0][2] == []
        
        assert res == ASSET_MENU # returns show_asset_list
        assert mock_update.callback_query.answer.called

@pytest.mark.asyncio
async def test_edit_asset_flow(mock_update, mock_context, mock_session_local):
    """Test editing an existing asset."""
    asset_id = "uuid-123"
    mock_context.user_data["current_asset_type"] = "pitch"
    mock_context.user_data["current_asset_id"] = asset_id
    mock_context.user_data["edit_mode"] = "name"
    
    mock_update.message.text = "Updated Name"
    
    mock_service = AsyncMock()
    item = ContentItem(name="Old Name", content="Content", type="text")
    item.id = asset_id
    mock_profile = MagicMock()
    mock_profile.pitches = [item]
    mock_service.get_profile.return_value = mock_profile
    
    with patch("app.bot.handlers.assets_handler.ProfileService", return_value=mock_service):
        res = await save_asset_name(mock_update, mock_context)
        
        # Verify item updated
        assert item.name == "Updated Name"
        mock_service.update_profile_field.assert_called()
        
        # Check for success message in one of the calls
        messages = [args[0] for args, _ in mock_update.message.reply_text.call_args_list]
        assert any("обновлено" in m.lower() for m in messages)

@pytest.mark.asyncio
async def test_asset_action_callbacks(mock_update, mock_context):
    """Test callbacks inside detail view."""
    # Edit Name
    mock_update.callback_query.data = "asset_edit_name"
    res = await asset_action_callback(mock_update, mock_context)
    assert res == ASSET_INPUT_NAME
    assert mock_context.user_data["edit_mode"] == "name"
    
    # Edit Content
    mock_update.callback_query.data = "asset_edit_content"
    res = await asset_action_callback(mock_update, mock_context)
    assert res == ASSET_INPUT_CONTENT
    assert mock_context.user_data["edit_mode"] == "content"
    
    # Back
    mock_update.callback_query.data = "asset_back"
    with patch("app.bot.handlers.assets_handler.show_asset_list", new_callable=AsyncMock) as mock_list:
         await asset_action_callback(mock_update, mock_context)
         mock_list.assert_called_once()
