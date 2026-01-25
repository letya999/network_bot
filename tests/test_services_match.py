import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.match_service import MatchService
from app.models.contact import Contact
from app.models.user import User
import uuid
import json

@pytest.fixture
def mock_gemini(monkeypatch):
    mock = MagicMock()
    mock.extract_contact_data = AsyncMock()
    mock.get_prompt = MagicMock(return_value="Prompt template {profile_a} {profile_b}")
    monkeypatch.setattr("app.services.match_service.GeminiService", lambda: mock)
    return mock

@pytest.mark.asyncio
async def test_match_service_get_user_matches(mock_session, mock_gemini):
    service = MatchService(mock_session)
    user = User(id=uuid.uuid4(), profile_data={"bio": "AI expert"})
    contact = Contact(id=uuid.uuid4(), name="Target", what_looking_for="AI help")
    
    mock_gemini.extract_contact_data.return_value = {
        "is_match": True,
        "match_score": 90,
        "synergy_summary": "Both like AI",
        "suggested_pitch": "Let's talk AI"
    }
    
    result = await service.get_user_matches(contact, user)
    
    assert result["is_match"] is True
    assert result["match_score"] == 90
    mock_gemini.extract_contact_data.assert_called_once()

@pytest.mark.asyncio
async def test_match_service_find_peer_matches(mock_session, mock_gemini):
    service = MatchService(mock_session)
    contact = Contact(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Person A", what_looking_for="Design")
    peer = Contact(id=uuid.uuid4(), name="Person B", can_help_with="Design help")
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [peer]
    mock_session.execute.return_value = mock_result
    
    mock_gemini.extract_contact_data.return_value = {
        "is_match": True,
        "match_score": 85,
        "synergy_summary": "Design match"
    }
    
    matches = await service.find_peer_matches(contact)
    
    assert len(matches) == 1
    assert matches[0]["peer_name"] == "Person B"

@pytest.mark.asyncio
async def test_match_service_semantic_search(mock_session, mock_gemini):
    service = MatchService(mock_session)
    user_id = uuid.uuid4()
    
    c1 = Contact(id=uuid.uuid4(), name="Alice")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [c1]
    mock_session.execute.return_value = mock_result
    
    mock_gemini.extract_contact_data.return_value = {
        "matches": [{"contact_id": str(c1.id), "reason": "Expert"}]
    }
    
    results = await service.semantic_search(user_id, "expert")
    assert len(results) == 1
    assert results[0]["contact_id"] == str(c1.id)
