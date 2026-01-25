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
async def test_extract_contact_data_mock():
    mock_model = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = '{"name": "John Doe"}'
    mock_model.generate_content_async.return_value = mock_response
    
    with patch("google.generativeai.GenerativeModel", return_value=mock_model), \
         patch("app.core.config.settings.GEMINI_API_KEY", "fake"):
        service = GeminiService()
        result = await service.extract_contact_data(text="test")
        assert result["name"] == "John Doe"

@pytest.mark.asyncio
async def test_customize_card_intro_mock():
    mock_model = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = "Hello"
    mock_model.generate_content_async.return_value = mock_response
    
    with patch("google.generativeai.GenerativeModel", return_value=mock_model), \
         patch("app.core.config.settings.GEMINI_API_KEY", "fake"):
        service = GeminiService()
        result = await service.customize_card_intro("Profile", "Target")
        assert result == "Hello"
