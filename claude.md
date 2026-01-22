# NetworkingCRM — Claude Development Guide

## Purpose

AI-powered Telegram CRM для нетворкинга. Голосовое → структурированная карточка → напоминания → инсайты.

## Tech Stack

- **Language:** Python 3.11+
- **Bot:** python-telegram-bot 21.x (async)
- **Backend:** FastAPI
- **AI:** Google Gemini API
- **DB:** PostgreSQL + Redis
- **ORM:** SQLAlchemy 2.x (async)
- **Tasks:** Celery + Redis
- **Tests:** pytest-asyncio

## Architecture

**Pattern:** Handlers → Services → Repositories
- Async everywhere
- Dependency Injection (FastAPI)
- Repository pattern (no business logic in repos)
- Pydantic validation at boundaries
- ORM validation for data integrity

---

## Project Structure

```
networking-crm/
├── bot/
│   ├── handlers/          # Telegram handlers
│   ├── keyboards/         # Inline keyboards
│   └── middlewares/       # auth, logging, rate_limit
├── services/              # Business logic
│   ├── gemini.py         # AI service
│   ├── contact.py        # CRUD + search
│   ├── reminder.py       # Follow-up system
│   ├── export.py         # Notion, Sheets, CSV
│   └── osint.py          # Enrichment
├── models/               # SQLAlchemy models
├── repositories/         # Data access layer
├── core/
│   ├── config.py        # Pydantic settings
│   ├── database.py      # Async DB connection
│   └── errors.py        # Custom exceptions
├── prompts/             # AI prompts (отдельные файлы!)
└── tests/
```

---

## Testing Strategy

### Structure
```
tests/
├── unit/services/       # Service logic
├── unit/repositories/   # Data access
├── integration/         # Handlers, API
└── e2e/                 # Full flows
```

### Conventions
- **Naming:** `test_<function>_<scenario>_<expected>`
- **Always write tests with code:** service → unit, handler → integration
- **Fixtures:** `db_session`, `test_user`, `api_client` (см. tests/conftest.py)
- **Coverage:** `pytest --cov=services --cov=models --cov-report=html`

### Key Patterns
- Mock external APIs (Gemini, Telegram)
- Use AsyncMock for async code
- Test validation errors with pytest.raises
- Verify database state after operations

---

## API & Validation

### OpenAPI
- FastAPI auto-docs: `/api/docs`
- Используй `summary`, `description`, `responses` для endpoints
- Schemas с примерами в `json_schema_extra`

### Pydantic Schemas
**Где:** `api/schemas.py`, `schemas/contact.py`
**Зачем:** Валидация на границах системы (API input, AI output)

**Паттерны:**
- `BaseModel` для DTO
- `Field()` с валидацией: min_length, pattern, regex
- `@validator` для кастомной валидации
- `@root_validator` для cross-field валидации

---

## Utilities

**Где:** `core/utils/`

### validators.py
- `validate_phone()` - нормализация телефона
- `validate_telegram_username()` - валидация @username
- `validate_email()` - email format
- `validate_linkedin_url()` - LinkedIn URL

### date_utils.py
- `parse_relative_date()` - "завтра", "через неделю" → datetime
- `format_datetime_ru()` - datetime → "15 января 2025"
- `days_since()` - дней с даты

### telegram_utils.py
- `build_inline_keyboard()` - создание клавиатур
- `escape_markdown_v2()` - экранирование для Markdown
- `chunk_message()` - разбивка длинных сообщений (4096 chars limit)

---

## Middlewares

**Где:** `bot/middlewares/`

### auth.py
- `@require_user` decorator - auto get/create user from Telegram ID
- Stores `db_user` and `db` in `context.user_data`

### logging.py
- `@log_handler` decorator - structured logging
- Logs: handler name, user_id, duration, errors
- JSON format для продакшена

### error.py
- Global error handler для Telegram bot
- User-friendly messages вместо технических ошибок
- Логирование трейсбеков

### rate_limit.py
- `@rate_limit` decorator - защита от спама
- In-memory rate limiter (10 req/min default)

---

## Error Handling

### Custom Exceptions
**Где:** `core/errors.py`

**Hierarchy:**
- `NetworkingCRMError` (base)
  - `ValidationError` - неверные данные
  - `NotFoundError` - ресурс не найден
  - `DuplicateError` - дубликат
  - `PermissionError` - нет доступа
  - `ExternalServiceError` (GeminiAPIError, NotionAPIError, etc.)
  - `DatabaseError` (TransactionError, etc.)

### Usage
```python
# In services
if not contact:
    raise NotFoundError(f"Contact {id} not found", details={"contact_id": str(id)})

# In handlers
try:
    contact = await service.get_contact(id)
except NotFoundError:
    await update.message.reply_text("Контакт не найден")
```

---

## ORM Models

**Где:** `models/`

### Key Patterns
- UUID primary keys
- SQLAlchemy `@validates` decorators для полей
- CheckConstraints для data integrity
- Indexes: (user_id, status), GIN для full-text search
- `created_at`, `updated_at` timestamps
- JSONB для semi-structured data (profile_data, osint_data)

### Main Models
- **User:** telegram_id, profile_data (JSONB), settings (JSONB)
- **Contact:** все поля контакта + status (active/sleeping/archived)
- **Interaction:** история касаний (met, message_sent, call, meeting)
- **Reminder:** trigger_at, status (pending/sent/snoozed), message_template

---

## Services Layer

**Где:** `services/`

### Pattern
- Service = orchestration + business logic
- Uses repositories for data access
- NO database queries in services directly
- Raise custom exceptions (not HTTP errors)
- Return domain models

### Key Services
- **ContactService:** CRUD, search, duplicate detection, merge logic
- **GeminiService:** extraction, message generation, prompts loading
- **ReminderService:** create, snooze, mark_sent
- **ExportService:** Notion, Sheets, CSV
- **OSINTService:** enrichment orchestration

---

## Repository Pattern

**Где:** `repositories/`

### Rules
- Repository = data access ONLY
- No business logic (валидация только на уровне ORM)
- Return ORM models or None
- Async methods everywhere
- Graceful error handling (catch DB errors, raise ValidationError)

### Common Methods
- `create(**kwargs)` → Model
- `get_by_id(id)` → Model | None
- `find_by_user(user_id, filters)` → List[Model]
- `update(id, **kwargs)` → Model | None
- `delete(id)` → bool

---

## Async Patterns

### Database Sessions
```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

### Key Rules
- **ALWAYS** use `await` для async функций
- **NO** blocking I/O в async code (используй aiofiles, aiohttp)
- **Session management:** через dependency injection `Depends(get_db)`
- **Context managers:** `async with` для файлов, HTTP клиентов

---

## AI Integration

### Prompts
**Где:** `prompts/` (отдельные .txt файлы!)

**Files:**
- `extract_contact.txt` - голосовое → структурированный JSON
- `generate_card.txt` - персонализированная визитка
- `generate_followup.txt` - follow-up сообщение
- `semantic_search.txt` - семантический поиск

### GeminiService Pattern
```python
# services/gemini.py
def _load_prompt(filename: str) -> str:
    return (Path(__file__).parent.parent / 'prompts' / filename).read_text()

async def extract_contact_from_voice(transcript: str) -> ContactExtracted:
    prompt = self._load_prompt('extract_contact.txt').format(transcript=transcript)
    # Call Gemini in executor (it's sync)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, lambda: self.model.generate_content(prompt))
    # Parse JSON, validate with Pydantic
    return ContactExtracted(**json.loads(response.text))
```

---

## Background Tasks

### Celery
**Где:** `core/celery_app.py`, `tasks/`

**Tasks:**
- `tasks.reminders.send_due_reminders` - каждую минуту
- `tasks.osint.enrich_contact` - фоновое обогащение
- `tasks.cleanup.cleanup_expired_share_cards` - daily

**Pattern:**
```python
@shared_task(name='tasks.reminders.send_due_reminders')
def send_due_reminders():
    asyncio.run(_send_reminders())  # Wrap async code

async def _send_reminders():
    async with async_session_maker() as db:
        # Async logic here
```

---

## Workflow Patterns

### New Feature
1. Define domain logic in `services/`
2. Write unit tests in `tests/unit/services/`
3. Create repository methods if needed
4. Add API routes with OpenAPI annotations
5. Create Pydantic schemas for validation
6. Add Telegram handlers if needed
7. Write integration tests
8. Update prompts if using AI

### Testing Checklist
- [ ] Unit tests for service logic
- [ ] Unit tests for validators
- [ ] Integration tests for handlers
- [ ] Test error cases
- [ ] Test validation edge cases
- [ ] Check OpenAPI docs (`/api/docs`)
- [ ] Manual E2E testing in Telegram

---

## Important Rules for Claude

1. **ВСЕГДА пиши тесты вместе с кодом** - это не опционально
2. **Pydantic для валидации на границах** (API input, AI output)
3. **ORM валидаторы для защиты данных** в базе
4. **Все промпты в отдельных файлах** (`prompts/`) - не хардкодить в коде
5. **Async everywhere** - нет синхронного кода в async функциях
6. **Structured logging** - JSON для продакшена
7. **Graceful error handling** - user-friendly messages
8. **Repository pattern строго** - нет бизнес-логики в репозиториях
9. **Type hints обязательны** - на всех публичных методах
10. **Docstrings для публичных методов** - описать что делает функция

---

## Configuration

**Где:** `core/config.py` (Pydantic Settings)

### Required Env Variables
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `DATABASE_URL` (postgresql+asyncpg://...)
- `REDIS_URL`

### Optional
- `NOTION_TOKEN`, `NOTION_DATABASE_ID`
- `GOOGLE_SHEETS_CREDENTIALS`, `GOOGLE_SHEETS_ID`
- `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX`

---

## Quick Commands

```bash
# Tests
pytest                                  # All tests
pytest tests/unit/                      # Unit only
pytest --cov=services --cov-report=html # With coverage

# Run
python -m bot.main                      # Start bot
uvicorn api.main:app --reload          # Start API

# Celery
celery -A core.celery_app worker --loglevel=info
celery -A core.celery_app beat --loglevel=info

# DB Migrations
alembic revision --autogenerate -m "Description"
alembic upgrade head

# Docs
# http://localhost:8000/api/docs
```

---

## Skills Reference

См. `.claude/skills/` для готовых workflows:
- `/test` - Run tests with coverage
- `/migrate` - DB migrations
- `/add-feature` - Create feature (models → services → handlers)
- `/api-endpoint` - REST endpoint with OpenAPI
- `/telegram-handler` - Bot handler with middlewares
- `/fix-tests` - Auto-fix failing tests
- `/review` - Code review по чеклисту

---

См. **[context.md](context.md)** для полной спецификации проекта.
