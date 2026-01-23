import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.bot.handlers import handle_text_message

@pytest.mark.asyncio
async def test_handle_text_message_flow(mock_update, mock_context, mock_session):
    mock_update.message.text = "Contact: John Doe 89991234567"
    
    # Mock extract_contact_info to return something (it's regex)
    # The real regex might work if the text matches.
    # Let's use a text that matches: "tel: +12345"
    mock_update.message.text = "Call me at +1-555-0199"
    
    with patch("app.bot.handlers.AsyncSessionLocal") as mock_db_cls, \
         patch("app.bot.handlers.GeminiService") as mock_gemini_cls:
         
        # Setup DB Mock
        mock_db_cls.return_value.__aenter__.return_value = mock_session
        
        # Setup Gemini Mock
        mock_gemini = mock_gemini_cls.return_value
        mock_gemini.extract_contact_data = AsyncMock(return_value={
            "name": "John Doe",
            "phone": "+15550199",
            "notes": "Test Note"
        })
        
        await handle_text_message(mock_update, mock_context)
        
        # Assertions
        # 1. Gemini called
        mock_gemini.extract_contact_data.assert_called_once()
        
        # 2. DB Commit called (User create + Contact create)
        assert mock_session.commit.called
        
        # 3. Reply sent
        mock_update.message.reply_text.assert_called()
        args, _ = mock_update.message.reply_text.call_args
        assert "John Doe" in args[0]
