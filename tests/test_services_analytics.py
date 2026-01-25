import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.analytics_service import AnalyticsService
from app.models.interaction import InteractionType
from datetime import datetime, timedelta
import uuid

@pytest.mark.asyncio
async def test_analytics_service_stats(mock_session):
    service = AnalyticsService(mock_session)
    user_id = uuid.uuid4()
    
    m1 = MagicMock()
    m1.scalar.return_value = 5 
    
    m2 = MagicMock()
    m2.all.return_value = [("Tech Event", 3), (None, 2)] 
    
    m3 = MagicMock()
    m3.all.return_value = [(InteractionType.MESSAGE_SENT.value, 2)] 
    
    m4 = MagicMock()
    m4.all.return_value = [("PM", 2)] 
    
    mock_session.execute.side_effect = [m1, m2, m3, m4]
    
    stats = await service.get_networking_stats(user_id)
    
    assert stats["total_new_contacts"] == 5
    assert stats["by_event"]["Tech Event"] == 3
    assert stats["funnel"]["follow_ups"] == 2
    assert stats["by_role"]["PM"] == 2

@pytest.mark.asyncio
async def test_analytics_service_inactive(mock_session):
    service = AnalyticsService(mock_session)
    user_id = uuid.uuid4()
    
    from app.models.contact import Contact
    c1 = Contact(id=uuid.uuid4(), name="Ghost")
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [c1]
    mock_session.execute.return_value = mock_result
    
    inactive = await service.get_inactive_contacts(user_id)
    
    assert len(inactive) == 1
    assert inactive[0].name == "Ghost"
