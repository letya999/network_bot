import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.ai_service import AIService

@pytest.mark.asyncio
async def test_init_with_preference():
    """Test that preference is respected in initialization."""
    with patch("google.generativeai.configure"), \
         patch("app.services.ai_service.AsyncOpenAI"):
        
        # 1. Prefer Gemini, both keys present
        service = AIService(gemini_api_key="g", openai_api_key="o", preferred_provider="gemini")
        assert service.provider == "gemini"
        
        # 2. Prefer OpenAI, both keys present
        service2 = AIService(gemini_api_key="g", openai_api_key="o", preferred_provider="openai")
        assert service2.provider == "openai"

@pytest.mark.asyncio
async def test_init_fallback():
    """Test fallback logic."""
    with patch("google.generativeai.configure"), \
         patch("app.services.ai_service.AsyncOpenAI"):
        
        # Prefer Gemini, but no key -> fallback to OpenAI
        service = AIService(gemini_api_key=None, openai_api_key="o", preferred_provider="gemini")
        assert service.provider == "openai"
        
        # Prefer OpenAI, but no key -> fallback to Gemini
        service2 = AIService(gemini_api_key="g", openai_api_key=None, preferred_provider="openai")
        assert service2.provider == "gemini"

@pytest.mark.asyncio
async def test_extract_contact_data_provider_dispatch():
    """Test that extract_contact_data calls the correct internal method."""
    service = AIService()
    service.provider = "openai"
    service._extract_openai = AsyncMock(return_value={"name": "OpenAI User"})
    service._extract_gemini = AsyncMock(return_value={"name": "Gemini User"})
    
    result = await service.extract_contact_data(text="test")
    assert result["name"] == "OpenAI User"
    service._extract_openai.assert_called_once()
    service._extract_gemini.assert_not_called()

    service.provider = "gemini"
    result = await service.extract_contact_data(text="test")
    assert result["name"] == "Gemini User"
    service._extract_gemini.assert_called_once()
