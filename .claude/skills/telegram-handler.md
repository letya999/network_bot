# Telegram Handler Skill

## Description
Создает новый Telegram bot handler с правильной структурой, валидацией и обработкой ошибок.

## Usage
- `/telegram-handler <тип> <описание>`
- Типы: command, message, callback, voice, contact
- Пример: `/telegram-handler command /stats - показать статистику`

## Instructions

Когда вызван этот skill:

1. **Определи тип handler'а:**
   - `command` → CommandHandler для /команд
   - `message` → MessageHandler для текстовых сообщений
   - `callback` → CallbackQueryHandler для inline кнопок
   - `voice` → MessageHandler с фильтром voice
   - `contact` → MessageHandler с фильтром contact

2. **Создай handler функцию:**
   ```python
   # bot/handlers/<category>.py

   from telegram import Update
   from telegram.ext import ContextTypes
   from bot.middlewares.auth import require_user
   from bot.middlewares.logging import log_handler
   from bot.middlewares.rate_limit import rate_limit
   from core.errors import handle_service_error

   @require_user
   @log_handler
   @rate_limit
   async def handler_name(
       update: Update,
       context: ContextTypes.DEFAULT_TYPE
   ) -> None:
       """Handler description."""
       try:
           # Get user from context
           user = context.user_data['db_user']
           db = context.user_data['db']

           # Extract data from update
           ...

           # Call service
           from services.<service> import <Service>
           service = <Service>(db)
           result = await service.method(...)

           # Send response
           await update.message.reply_text(
               "Ответ пользователю",
               parse_mode="Markdown"
           )

       except Exception as e:
           await handle_service_error(update, e)
   ```

3. **Добавь в application:**
   ```python
   # bot/main.py
   from bot.handlers.<category> import handler_name
   from telegram.ext import CommandHandler  # или другой

   app.add_handler(CommandHandler("command", handler_name))
   ```

4. **Создай keyboard если нужно:**
   ```python
   # bot/keyboards/<name>.py

   from core.utils.telegram_utils import build_inline_keyboard

   def get_keyboard(data):
       return build_inline_keyboard([
           [{"text": "Кнопка 1", "callback_data": "action_1"}],
           [{"text": "Кнопка 2", "url": "https://..."}]
       ])
   ```

5. **Напиши тесты:**
   ```python
   # tests/integration/handlers/test_<category>.py

   @pytest.mark.asyncio
   async def test_handler_success():
       # Mock Update и Context
       update = AsyncMock()
       update.effective_user.id = 123
       update.message = AsyncMock()

       context = AsyncMock()

       # Mock service
       with patch('services.<Service>') as mock_service:
           mock_service.return_value.method.return_value = {...}

           await handler_name(update, context)

           # Assert
           update.message.reply_text.assert_called()
   ```

6. **Обработка ошибок:**
   - Оборачивай в try/except
   - Используй handle_service_error
   - Показывай user-friendly сообщения
   - Логируй ошибки

7. **Best Practices:**
   - Используй middlewares (auth, logging, rate_limit)
   - Валидируй входные данные
   - Chunk длинные сообщения (>4096 chars)
   - Используй parse_mode для форматирования
   - Добавь inline keyboards где уместно

## Examples for Different Types

### Command Handler

User: `/telegram-handler command /stats Show networking statistics`
Assistant:
```python
# bot/handlers/stats.py

@require_user
@log_handler
async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show user networking statistics."""
    try:
        user = context.user_data['db_user']
        db = context.user_data['db']

        # Get stats
        from services.analytics import AnalyticsService
        analytics = AnalyticsService(db)
        stats = await analytics.get_monthly_stats(user.id)

        # Format message
        message = f"""
📊 Статистика за январь 2025

Новых контактов: {stats['new_contacts']}
Follow-up отправлено: {stats['followups_sent']}
Встреч: {stats['meetings']}

Топ источники:
{chr(10).join(f"• {s['name']}: {s['count']}" for s in stats['top_events'])}
        """

        await update.message.reply_text(message)

    except Exception as e:
        await handle_service_error(update, e)
```

**Register:**
```python
# bot/main.py
app.add_handler(CommandHandler("stats", stats_command))
```

---

### Callback Handler

User: `/telegram-handler callback Handle contact card actions`
Assistant:
```python
# bot/handlers/contact_actions.py

@log_handler
async def contact_action_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle actions on contact cards."""
    query = update.callback_query
    await query.answer()  # Acknowledge

    try:
        # Parse callback data: "action_contactId"
        action, contact_id = query.data.split('_', 1)

        user = context.user_data['db_user']
        db = context.user_data['db']

        from services.contact import ContactService
        service = ContactService(db)

        if action == "edit":
            # Show edit menu
            contact = await service.get_contact(contact_id, user.id)
            await query.edit_message_text(
                f"Редактирование: {contact.name}",
                reply_markup=get_edit_keyboard(contact.id)
            )

        elif action == "delete":
            # Confirm deletion
            await service.delete_contact(contact_id, user.id)
            await query.edit_message_text("✅ Контакт удалён")

    except Exception as e:
        await query.message.reply_text(
            "Произошла ошибка. Попробуй снова."
        )
```

**Register:**
```python
# bot/main.py
from telegram.ext import CallbackQueryHandler

app.add_handler(
    CallbackQueryHandler(
        contact_action_callback,
        pattern="^(edit|delete)_"
    )
)
```

---

### Voice Handler

User: `/telegram-handler voice Process voice messages for contact extraction`
Assistant:
```python
# bot/handlers/voice.py

@require_user
@log_handler
@rate_limit
async def voice_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process voice message and extract contact."""
    try:
        user = context.user_data['db_user']
        db = context.user_data['db']

        # Download voice file
        voice = await update.message.voice.get_file()
        file_path = f"/tmp/voice_{voice.file_id}.ogg"
        await voice.download_to_drive(file_path)

        # Show processing message
        status_msg = await update.message.reply_text(
            "🎙 Обрабатываю голосовое..."
        )

        # Extract contact
        from services.gemini import GeminiService
        gemini = GeminiService()

        # TODO: Transcribe audio first
        transcript = "..."  # Use Gemini or other service

        extracted = await gemini.extract_contact_from_voice(transcript)

        # Show extracted card
        from bot.keyboards.contact import get_contact_card_keyboard

        card_text = f"""
✅ {extracted.name}

🏢 {extracted.company or 'Не указано'}
📍 {extracted.event or 'Не указано'}

Хочешь сохранить?
        """

        await status_msg.edit_text(
            card_text,
            reply_markup=get_contact_card_keyboard()
        )

        # Store in context for later
        context.user_data['pending_contact'] = extracted.dict()

    except Exception as e:
        await handle_service_error(update, e)
```

**Register:**
```python
# bot/main.py
from telegram.ext import MessageHandler, filters

app.add_handler(
    MessageHandler(
        filters.VOICE,
        voice_handler
    )
)
```

---

## Testing Template

```python
# tests/integration/handlers/test_<handler>.py

import pytest
from unittest.mock import AsyncMock, patch
from telegram import Update, User, Message

@pytest.mark.asyncio
async def test_handler_success():
    """Test successful handler execution."""
    # Setup mocks
    user = User(id=123, first_name="Test", is_bot=False)
    message = AsyncMock()
    message.from_user = user

    update = AsyncMock()
    update.message = message
    update.effective_user = user

    context = AsyncMock()
    context.user_data = {
        'db_user': AsyncMock(id="user-uuid"),
        'db': AsyncMock()
    }

    # Mock service
    with patch('services.<Service>.<method>') as mock_method:
        mock_method.return_value = {"data": "value"}

        from bot.handlers.<handler> import handler_name
        await handler_name(update, context)

        # Assertions
        message.reply_text.assert_called_once()
        call_args = message.reply_text.call_args[0][0]
        assert "expected text" in call_args

@pytest.mark.asyncio
async def test_handler_error():
    """Test handler error handling."""
    # Setup mocks
    update = AsyncMock()
    context = AsyncMock()

    # Mock service to raise error
    with patch('services.<Service>.<method>') as mock_method:
        mock_method.side_effect = Exception("Test error")

        from bot.handlers.<handler> import handler_name
        await handler_name(update, context)

        # Should send error message
        update.message.reply_text.assert_called()
        error_msg = update.message.reply_text.call_args[0][0]
        assert "ошибка" in error_msg.lower()
```
