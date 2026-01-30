# NetworkingCRM — Developer Guide

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
network-bot/
├── app/
│   ├── bot/                 # Telegram Application
│   │   ├── handlers/        # Telegram handlers
│   │   ├── keyboards/       # Inline keyboards
│   │   ├── middlewares/     # auth, logging, rate_limit
│   │   ├── main.py          # Bot factory
│   │   └── run.py           # Entry point
│   ├── services/            # Business logic (AI, Contacts, Reminders, OSINT)
│   ├── models/              # SQLAlchemy models
│   ├── repositories/        # Data access layer
│   ├── core/
│   │   ├── config.py        # Pydantic settings
│   │   ├── database.py      # Async DB connection
│   │   └── errors.py        # Custom exceptions
│   └── api/                 # FastAPI routes
├── prompts/                 # AI prompts (отдельные файлы!)
├── tests/
└── alembic/                 # DB Migrations
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
- **Coverage:** `pytest --cov=app --cov-report=html`

### Key Patterns
- Mock external APIs (Gemini, Telegram)
- Use AsyncMock for async code
- Test validation errors with pytest.raises
- Verify database state after operations

---

## API & Validation

### Pydantic Schemas
**Где:** `app/schemas/`
**Зачем:** Валидация на границах системы (API input, AI output)

**Паттерны:**
- `BaseModel` для DTO
- `Field()` с валидацией: min_length, pattern, regex
- `@validator` для кастомной валидации

---

## Middlewares

**Где:** `app/bot/middlewares/`

- **auth.py**: `@require_user` decorator - auto get/create user from Telegram ID
- **logging.py**: `@log_handler` decorator - structured logging
- **error.py**: Global error handler for Telegram bot
- **rate_limiter.py**: Защита от спама

---

## Application Layers

### ORM Models (`app/models/`)
- UUID primary keys
- SQLAlchemy `@validates` decorators
- `CheckConstraints` для data integrity
- Indexes: (user_id, status), GIN для full-text search

### Services Layer (`app/services/`)
- Service = orchestration + business logic
- Uses repositories for data access
- NO database queries in services directly
- Raise custom exceptions (not HTTP errors)

### Repository Pattern (`app/repositories/`)
- Data access ONLY
- No business logic
- Async methods everywhere

---

## AI Integration

### Prompts
**Где:** `prompts/` (отдельные .txt файлы!)

**Files:**
- `extract_contact.txt` - голосовое → структурированный JSON
- `generate_card.txt` - персонализированная визитка
- `generate_followup.txt` - follow-up сообщение

---

## Development Guidelines

1. **ВСЕГДА пиши тесты вместе с кодом**
2. **Pydantic для валидации на границах**
3. **ORM валидаторы для защиты данных**
4. **Prompts в отдельных файлах**
5. **Async everywhere**
6. **Structured logging**
7. **Graceful error handling**
8. **Type hints обязательны**

---

## Configuration

**Где:** `app/core/config.py` (Pydantic Settings)

### Required Env Variables
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `DATABASE_URL` (postgresql+asyncpg://...)
- `REDIS_URL`

---

## Quick Commands

```bash
# Tests
pytest                                  # All tests
pytest tests/unit/                      # Unit only
pytest --cov=app --cov-report=html      # With coverage

# Run Bot
python -m app.bot.run

# Run API
uvicorn app.main:app --reload

# Celery
celery -A app.core.celery_app worker --loglevel=info

# DB Migrations
alembic revision --autogenerate -m "Description"
alembic upgrade head
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

См. **[context.md](context.md)** для детальной информации о фичах.
