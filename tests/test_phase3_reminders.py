import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime
from app.services.reminder_service import ReminderService, ReminderStatus
from app.bot.reminder_handlers import list_reminders, reminder_action_callback
from app.models.user import User
from app.models.reminder import Reminder

@pytest.mark.asyncio
async def test_create_reminder_service(mock_session, mock_scheduler):
    service = ReminderService(mock_session)
    user_id = uuid.uuid4()
    due_at = datetime.now()
    
    await service.create_reminder(user_id, "Buy Milk", due_at)
    
    # Verify DB add
    assert mock_session.add.called
    reminder = mock_session.add.call_args[0][0]
    assert isinstance(reminder, Reminder)
    assert reminder.title == "Buy Milk"
    assert reminder.status == ReminderStatus.PENDING
    
    # Verify Scheduler Call
    assert mock_scheduler.add_job.called
    assert mock_scheduler.add_job.call_args[1]['run_date'] == due_at

@pytest.mark.asyncio
async def test_list_reminders_handler(mock_update, mock_context, mock_session):
    # Mock user
    user = User(telegram_id=12345, id=uuid.uuid4())
    mock_session.execute.return_value.scalar_one_or_none.return_value = user
    
    # Mock reminders result
    r1 = Reminder(id=uuid.uuid4(), title="Task 1", due_at=datetime(2025, 1, 1, 10, 0), status=ReminderStatus.PENDING)
    mock_session.execute.return_value.scalars.return_value.all.return_value = [r1]
    
    mock_session.__aenter__.return_value = mock_session
    
    with patch("app.bot.reminder_handlers.AsyncSessionLocal", return_value=mock_session):
        await list_reminders(mock_update, mock_context)
        
    args, kwargs = mock_update.message.reply_text.call_args
    text = args[0]
    assert "Task 1" in text
    assert "Активные напоминания" in text

@pytest.mark.asyncio
async def test_complete_reminder_action(mock_update, mock_context, mock_session, mock_scheduler):
    rem_id = uuid.uuid4()
    mock_update.callback_query.data = f"rem_done_{rem_id}"
    
    # Mock existing reminder
    # Important: Create a real object so we can verify attribute changes
    reminder = Reminder(id=rem_id, status=ReminderStatus.PENDING)
    mock_session.get.return_value = reminder
    
    mock_session.__aenter__.return_value = mock_session
    
    with patch("app.bot.reminder_handlers.AsyncSessionLocal", return_value=mock_session):
        await reminder_action_callback(mock_update, mock_context)
        
    # Verify status change
    assert reminder.status == ReminderStatus.COMPLETED
    assert mock_session.commit.called
    
    # Verify scheduler job removal attempt
    assert mock_scheduler.remove_job.called
    
    # Verify UI feedback
    assert mock_update.callback_query.message.reply_text.called
    assert "отмечено выполненным" in mock_update.callback_query.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_reminder_extraction_from_text(mock_update, mock_context, mock_session, mock_scheduler):
    from app.bot.handlers import handle_text_message
    
    # Mock text input
    mock_update.message.text = "Remind me to call John in 5 mins"
    
    # Mock Gemini Service response
    mock_gemini_instance = AsyncMock()
    mock_gemini_instance.extract_contact_data.return_value = {
        "reminders": [
            {"title": "Call John", "due_date": "in 5 mins", "description": None}
        ],
        "name": "Неизвестно" # Triggers is_reminder_only logic
    }
    
    mock_session.__aenter__.return_value = mock_session
    
    # Check duplicate logic needs finding nothing or something
    mock_session.execute.return_value.scalar_one_or_none.return_value = None # No existing contact conflict
    
    with patch("app.bot.handlers.GeminiService", return_value=mock_gemini_instance), \
         patch("app.bot.handlers.AsyncSessionLocal", return_value=mock_session), \
         patch("app.bot.handlers.UserService") as mock_user_service_cls:
             
        # Mock user service getting user
        mock_user_service = mock_user_service_cls.return_value
        # Since get_or_create_user is async, we must mock it as an awaitable
        mock_user_service.get_or_create_user = AsyncMock(return_value=User(id=uuid.uuid4(), custom_prompt=None))
        
        await handle_text_message(mock_update, mock_context)
        
    # Verify reminder created
    assert mock_session.add.called
    
    # Iterate through calls to find a Reminder
    # Note: UserService might call session.add(user). So we filter.
    added_objs = [call[0][0] for call in mock_session.add.call_args_list]
    reminders = [obj for obj in added_objs if isinstance(obj, Reminder)]
    
    assert len(reminders) == 1
    assert reminders[0].title == "Call John"
    
    # Verify successful reply
    args, _ = mock_update.message.reply_text.call_args
    assert "Создано напоминаний: 1" in args[0]
