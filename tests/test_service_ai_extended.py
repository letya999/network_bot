import pytest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from app.services.ai_service import AIService
import json
import os

@pytest.fixture
def mock_genai():
    with patch("app.services.ai_service.genai") as mock:
        yield mock

@pytest.fixture
def mock_openai():
    with patch("app.services.ai_service.AsyncOpenAI") as mock:
        yield mock

@pytest.mark.asyncio
async def test_init_no_keys():
    """Test initialization with no keys."""
    with patch("app.core.config.settings.GEMINI_API_KEY", None), \
         patch("app.core.config.settings.OPENAI_API_KEY", None):
        service = AIService()
        assert service.provider is None

@pytest.mark.asyncio
async def test_get_prompt(tmp_path):
    """Test loading prompt from file."""
    service = AIService()
    
    # Mock os.path.join within the class or just mock open
    with patch("builtins.open", mock_open(read_data="Prompt content")) as mock_file:
         with patch("os.path.join", return_value="path/to/prompt.txt"):
             res = service.get_prompt("test")
             assert res == "Prompt content"

    # Test not found
    with patch("builtins.open", side_effect=FileNotFoundError):
        res = service.get_prompt("missing")
        assert res == ""

@pytest.mark.asyncio
async def test_extract_contact_data_no_provider():
    """Test extraction when no provider is configured."""
    service = AIService()
    service.provider = None
    res = await service.extract_contact_data(text="test")
    assert res["name"] == "Test User"
    assert "disabled" in res["notes"]

@pytest.mark.asyncio
async def test_extract_gemini_success(mock_genai):
    """Test successful extraction with Gemini."""
    service = AIService(gemini_api_key="key", preferred_provider="gemini")
    
    # Mock model response
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"name": "Gemini Contact"}'
    mock_model.generate_content.return_value = mock_response
    service.gemini_model = mock_model
    
    res = await service.extract_contact_data(text="Hi my name is Gemini Contact")
    
    assert res["name"] == "Gemini Contact"
    mock_model.generate_content.assert_called_once()

@pytest.mark.asyncio
async def test_extract_openai_success(mock_openai):
    """Test successful extraction with OpenAI."""
    service = AIService(openai_api_key="key", preferred_provider="openai")
    
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"name": "OpenAI Contact"}'
    mock_client.chat.completions.create.return_value = mock_response
    service.openai_client = mock_client
    
    res = await service.extract_contact_data(text="Hi my name is OpenAI Contact")
    
    assert res["name"] == "OpenAI Contact"
    mock_client.chat.completions.create.assert_called_once()

@pytest.mark.asyncio
async def test_extract_audio_gemini(mock_genai):
    """Test audio extraction flow with Gemini."""
    service = AIService(gemini_api_key="key", preferred_provider="gemini")
    service.gemini_model = MagicMock()
    service.gemini_model.generate_content.return_value.text = "{}"
    
    with patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("app.services.ai_service.genai.upload_file") as mock_upload:
         
         await service.extract_contact_data(audio_path="test.ogg")
         
         mock_upload.assert_called_once()

@pytest.mark.asyncio
async def test_extract_audio_openai(mock_openai):
    """Test audio extraction flow with OpenAI Whisper."""
    service = AIService(openai_api_key="key", preferred_provider="openai")
    mock_client = AsyncMock()
    mock_client.audio.transcriptions.create.return_value.text = "Transcribed text"
    mock_client.chat.completions.create.return_value.choices[0].message.content = "{}"
    service.openai_client = mock_client
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=b"audio")):
         
         await service.extract_contact_data(audio_path="test.ogg")
         
         mock_client.audio.transcriptions.create.assert_called_once()
         # Check that transcript was passed to chat completion
         args = mock_client.chat.completions.create.call_args
         assert "Transcribed text" in str(args)

@pytest.mark.asyncio
async def test_parse_json_response_clean():
    """Test JSON cleaning logic."""
    service = AIService()
    
    # Markdown block
    valid = service._parse_json_response("```json\n{\"a\": 1}\n```")
    assert valid["a"] == 1
    
    # Plain text
    valid2 = service._parse_json_response("{\"b\": 2}")
    assert valid2["b"] == 2
    
    # Invalid
    invalid = service._parse_json_response("invalid json")
    assert invalid["name"] == "Неизвестно"

@pytest.mark.asyncio
async def test_customize_card_intro(mock_genai):
    """Test customize_card_intro."""
    service = AIService(gemini_api_key="key", preferred_provider="gemini")
    service.gemini_model = AsyncMock() # use AsyncMock for async method
    service.gemini_model.generate_content_async.return_value.text = '{"message": "Hello"}'
    
    res = await service.customize_card_intro("Me", "Target")
    assert res["message"] == "Hello"

@pytest.mark.asyncio
async def test_generate_json_gemini(mock_genai):
    """Test generic generate_json with Gemini."""
    service = AIService(gemini_api_key="key", preferred_provider="gemini")
    service.gemini_model = MagicMock()
    service.gemini_model.generate_content.return_value.text = '{"res": "ok"}'
    
    # Not async method in class (generate_content is sync, wrapped in to_thread)
    # The METHOD generate_json is async
    res = await service.generate_json("System", "User")
    assert res["res"] == "ok"
