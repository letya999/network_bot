import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.bot.reminder_handlers import list_reminders, reminder_action_callback
from app.models.reminder import Reminder
import uuid
from datetime import datetime

@pytest.mark.asyncio
async def test_list_reminders_empty(mock_update, mock_context):
    with patch("app.services.reminder_service.ReminderService.get_user_reminders", AsyncMock(return_value=[])):
        await list_reminders(mock_update, mock_context)
        assert "активных напоминаний" in mock_update.message.reply_text.call_args[0][0].lower()

@pytest.mark.asyncio
async def test_reminder_done_callback(mock_update, mock_context):
    rem_id = uuid.uuid4()
    mock_update.callback_query.data = f"rem_done_{rem_id}"
    with patch("app.services.reminder_service.ReminderService.complete_reminder", AsyncMock()) as mock_done:
        await reminder_action_callback(mock_update, mock_context)
        mock_done.assert_called_once_with(rem_id)
        assert "Напоминание выполнено" in mock_update.callback_query.answer.call_args[0][0]
