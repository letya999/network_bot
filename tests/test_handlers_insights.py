import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.match_handlers import find_matches_command, semantic_search_handler, semantic_search_callback
from app.bot.analytics_handlers import show_stats
from app.models.contact import Contact
import uuid

@pytest.mark.asyncio
async def test_find_matches_manual(mock_update, mock_context, mock_session):
    contact_id = uuid.uuid4()
    mock_context.user_data["last_contact_id"] = contact_id
    mock_session.get.return_value = Contact(id=contact_id, name="AI Dev")
    
    with patch("app.services.match_service.MatchService.get_user_matches", AsyncMock(return_value={"is_match": True, "synergy_summary": "Sync"})), \
         patch("app.services.match_service.MatchService.find_peer_matches", AsyncMock(return_value=[])):
        await find_matches_command(mock_update, mock_context)
        assert "Sync" in mock_update.message.reply_text.call_args_list[-1][0][0]

@pytest.mark.asyncio
async def test_semantic_search_handler(mock_update, mock_context, mock_session):
    mock_context.args = ["expert"]
    contact_id = str(uuid.uuid4())
    # Mock session.get for the contact found by semantic search
    mock_session.get.return_value = Contact(name="Alice")
    
    with patch("app.services.contact_service.ContactService.find_contacts", AsyncMock(return_value=[])), \
         patch("app.services.match_service.MatchService.semantic_search", AsyncMock(return_value=[{"contact_id": contact_id, "reason": "Reason"}])):
        await semantic_search_handler(mock_update, mock_context)
        
        found = False
        for call in mock_update.message.reply_text.call_args_list:
            if "Reason" in call[0][0]:
                found = True
        assert found

@pytest.mark.asyncio
async def test_show_stats_with_chart(mock_update, mock_context):
    # Need at least 2 events to trigger the chart
    stats = {"total_new_contacts": 2, "by_event": {"A": 1, "B": 1}, "funnel": {"contacts": 2, "follow_ups": 0, "responses": 0, "meetings": 0}, "by_role": {}}
    with patch("app.services.analytics_service.AnalyticsService.get_networking_stats", AsyncMock(return_value=stats)), \
         patch("app.services.analytics_service.AnalyticsService.get_inactive_contacts", AsyncMock(return_value=[])), \
         patch("matplotlib.pyplot.savefig"), patch("matplotlib.pyplot.close"):
        await show_stats(mock_update, mock_context)
        assert "🆕 Новых контактов: 2" in mock_update.message.reply_text.call_args[0][0]
        assert mock_update.message.reply_photo.called
