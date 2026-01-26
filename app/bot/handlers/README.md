# Handlers Architecture

Модульная архитектура обработчиков Telegram бота.

## Структура

```
app/bot/handlers/
├── __init__.py           # Экспорты всех handlers
├── base.py              # Базовый handler (/start)
├── common.py            # Утилиты форматирования (format_card, get_contact_keyboard)
├── contact.py           # Обработка контактов (voice, contact, text)
├── search.py            # Поиск и экспорт (/list, /find, /export)
├── prompt.py            # Управление промптами (/prompt, /edit_prompt)
├── event.py             # Режим мероприятия (/event)
└── card.py              # Генерация визиток (callback)
```

## Использование

### Импорт handlers

```python
# Из пакета (рекомендуется)
from app.bot.handlers import (
    start, handle_voice, handle_contact, 
    list_contacts, find_contact
)

# Или напрямую из модуля
from app.bot.handlers.contact import handle_voice
from app.bot.handlers.search import list_contacts
```

### Регистрация в main.py

```python
from app.bot.handlers import (
    start, handle_voice, handle_contact, handle_text_message,
    list_contacts, find_contact, export_contacts,
    show_prompt, start_edit_prompt, save_prompt,
    generate_card_callback, set_event_mode
)

# CommandHandlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_contacts))
app.add_handler(CommandHandler("find", find_contact))

# MessageHandlers
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
app.add_handler(MessageHandler(filters.TEXT, handle_text_message))

# CallbackQueryHandlers
app.add_handler(CallbackQueryHandler(generate_card_callback, pattern="^gen_card_"))
```

## Модули

### base.py
**Назначение:** Точка входа в бота  
**Handlers:**
- `start()` - Приветствие + deep linking для визиток

### common.py
**Назначение:** Утилиты форматирования  
**Функции:**
- `format_card(contact)` - Форматирование карточки контакта в Markdown
- `get_contact_keyboard(contact)` - Генерация inline клавиатуры для контакта

### contact.py
**Назначение:** Обработка входящих контактов  
**Handlers:**
- `handle_voice()` - Голосовые сообщения (транскрипция + извлечение данных)
- `handle_contact()` - Shared Telegram контакты
- `handle_text_message()` - Текстовые сообщения с контактной информацией

**Особенности:**
- Использует `ContactMergeService` для умного слияния
- Поддерживает режим мероприятия (event mode)
- Автоматическое создание напоминаний

### search.py
**Назначение:** Поиск и экспорт контактов  
**Handlers:**
- `list_contacts()` - Показать последние контакты
- `find_contact()` - Поиск по имени/компании
- `export_contacts()` - Экспорт в CSV

### prompt.py
**Назначение:** Управление кастомными промптами  
**Handlers:**
- `show_prompt()` - Показать текущий промпт
- `start_edit_prompt()` - Начать редактирование
- `save_prompt()` - Сохранить новый промпт
- `cancel_prompt_edit()` - Отменить редактирование
- `reset_prompt()` - Сбросить к дефолтному

**States:**
- `WAITING_FOR_PROMPT` - ConversationHandler state

### event.py
**Назначение:** Режим мероприятия  
**Handlers:**
- `set_event_mode()` - Включить/выключить режим мероприятия

**Использование:**
```
/event TechCrunch 2024  # Включить
/event                  # Выключить
```

### card.py
**Назначение:** Генерация персонализированных визиток  
**Handlers:**
- `generate_card_callback()` - Callback для кнопки "Визитка для него"

**Особенности:**
- Использует Gemini для персонализации intro
- Учитывает профили обоих пользователей

## Сервисы

Handlers используют следующие сервисы:

- **ContactService** - CRUD операции с контактами
- **ContactMergeService** - Умное слияние контактов
- **UserService** - Управление пользователями
- **GeminiService** - AI извлечение данных
- **ReminderService** - Создание напоминаний
- **ProfileService** - Управление профилями
- **CardService** - Генерация визиток
- **ExportService** - Экспорт данных

## Best Practices

### 1. Rate Limiting
Все handlers, которые делают тяжёлые операции, должны использовать rate limiter:

```python
from app.bot.rate_limiter import rate_limit_middleware

async def my_handler(update, context):
    if not await rate_limit_middleware(update, context):
        return
    # ... остальная логика
```

### 2. Error Handling
Используйте `logger.exception()` для полных stack traces:

```python
try:
    # ... код
except Exception:
    logger.exception("Description of what failed")
```

### 3. Session Management
Всегда используйте async context manager для сессий:

```python
async with AsyncSessionLocal() as session:
    user_service = UserService(session)
    # ... работа с БД
```

### 4. Константы
Используйте константы из `app.config.constants`:

```python
from app.config.constants import (
    MAX_SEARCH_QUERY_LENGTH,
    UNKNOWN_CONTACT_NAME
)
```

## Миграция со старого handlers.py

Старый файл `app/bot/handlers.py` больше не используется. Если он всё ещё существует, удалите его:

```bash
rm app/bot/handlers.py
# или переименуйте
mv app/bot/handlers.py app/bot/handlers.py.old
```

Python будет автоматически использовать пакет `handlers/` вместо файла.

## Тестирование

Пример теста для handler:

```python
import pytest
from app.bot.handlers.contact import handle_voice

@pytest.mark.asyncio
async def test_handle_voice(mock_update, mock_context):
    # Setup
    mock_update.message.voice.duration = 30
    
    # Execute
    await handle_voice(mock_update, mock_context)
    
    # Assert
    assert mock_update.message.reply_text.called
```

## Troubleshooting

### Import Error: "No module named 'app.bot.handlers'"
- Убедитесь, что `__init__.py` существует в `app/bot/handlers/`
- Проверьте, что старый `handlers.py` удалён или переименован

### Handler не вызывается
- Проверьте регистрацию в `main.py`
- Убедитесь, что pattern в CallbackQueryHandler правильный
- Проверьте порядок handlers (более специфичные должны быть выше)

### Circular Import
- Избегайте импорта handlers друг из друга
- Используйте общие утилиты из `common.py`
- Сервисы должны быть в `app/services/`, не в handlers

---

**Версия:** 2.0  
**Последнее обновление:** 2026-01-26
