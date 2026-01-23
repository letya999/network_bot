import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.gemini_service import GeminiService

@pytest.mark.asyncio
async def test_extract_contact_data_no_api_key():
    with patch("app.core.config.settings.GEMINI_API_KEY", None):
        service = GeminiService()
        result = await service.extract_contact_data(text="test")
        assert result["notes"] == "Gemini disabled"

@pytest.mark.asyncio
async def test_customize_card_intro_mock():
    # Mock usage of client
    service = GeminiService()
    service.client = MagicMock()
    # Mock generate_content
    service.client.aio.models.generate_content = AsyncMock()
    service.client.aio.models.generate_content.return_value.text = "Mock Intro"
    
    result = await service.customize_card_intro("My Profile", "Target")
    assert result == "Mock Intro"
