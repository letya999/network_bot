# NetworkingCRM — Development Guide for Claude

## Purpose

Этот документ описывает ключевые аспекты разработки проекта NetworkingCRM для эффективной работы с Claude Code. Здесь собраны паттерны, конвенции, структуры и примеры кода.

---

## Table of Contents

1. [Testing Strategy](#testing-strategy)
2. [OpenAPI Specification](#openapi-specification)
3. [Utilities](#utilities)
4. [Middlewares](#middlewares)
5. [Error Handling](#error-handling)
6. [Pydantic Validation](#pydantic-validation)
7. [ORM Validation](#orm-validation)
8. [Services Layer](#services-layer)
9. [Repository Pattern](#repository-pattern)
10. [Async Patterns](#async-patterns)
11. [AI Integration](#ai-integration)
12. [Background Tasks](#background-tasks)

---

## Testing Strategy

### Structure

```
tests/
├── __init__.py
├── conftest.py              # pytest fixtures
├── unit/
│   ├── services/
│   │   ├── test_gemini.py
│   │   ├── test_contact.py
│   │   └── test_reminder.py
│   ├── repositories/
│   │   └── test_contact_repository.py
│   └── utils/
│       └── test_validators.py
├── integration/
│   ├── test_handlers.py
│   ├── test_api.py
│   └── test_db.py
└── e2e/
    └── test_flows.py
```

### Test Conventions

**Всегда писать тесты вместе с кодом:**
- Новый service → сразу unit тесты
- Новый handler → сразу integration тесты
- Новая фича end-to-end → e2e тест

**Naming:**
- `test_<function>_<scenario>_<expected>`
- Пример: `test_extract_contact_from_voice_returns_structured_data`

**Fixtures:**

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient

from core.database import Base
from bot.main import app

@pytest.fixture
async def db_session():
    """Async database session for tests."""
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@localhost/test_networking",
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

@pytest.fixture
async def test_user(db_session):
    """Create test user."""
    from models.user import User
    user = User(
        telegram_id=123456789,
        name="Test User",
        profile_data={},
        settings={}
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def api_client():
    """FastAPI test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

**Service Tests:**

```python
# tests/unit/services/test_contact.py
import pytest
from services.contact import ContactService
from models.contact import Contact

@pytest.mark.asyncio
async def test_create_contact_with_valid_data_creates_contact(db_session, test_user):
    """Test creating contact with all required fields."""
    service = ContactService(db_session)

    contact_data = {
        "user_id": test_user.id,
        "name": "Марат Ибрагимов",
        "company": "Kolesa Group",
        "role": "CPO",
        "event_name": "Product Camp",
        "status": "active"
    }

    contact = await service.create_contact(**contact_data)

    assert contact.id is not None
    assert contact.name == "Марат Ибрагимов"
    assert contact.company == "Kolesa Group"
    assert contact.created_at is not None

@pytest.mark.asyncio
async def test_search_contacts_by_name_returns_matching_contacts(db_session, test_user):
    """Test search functionality finds contacts by name."""
    service = ContactService(db_session)

    # Create test contacts
    await service.create_contact(
        user_id=test_user.id,
        name="Марат Ибрагимов",
        company="Kolesa",
        status="active"
    )
    await service.create_contact(
        user_id=test_user.id,
        name="Алия Сатпаева",
        company="500 Startups",
        status="active"
    )

    results = await service.search_contacts(test_user.id, "Марат")

    assert len(results) == 1
    assert results[0].name == "Марат Ибрагимов"

@pytest.mark.asyncio
async def test_create_contact_without_name_raises_validation_error(db_session, test_user):
    """Test that contact without name raises error."""
    from pydantic import ValidationError
    service = ContactService(db_session)

    with pytest.raises(ValidationError):
        await service.create_contact(
            user_id=test_user.id,
            name="",  # Empty name
            company="Test"
        )
```

**Handler Tests:**

```python
# tests/integration/test_handlers.py
import pytest
from unittest.mock import AsyncMock, patch
from telegram import Update, User, Message

@pytest.mark.asyncio
async def test_voice_handler_processes_voice_and_creates_contact():
    """Test voice message handler flow."""
    # Mock Telegram objects
    user = User(id=123456789, first_name="Test", is_bot=False)
    voice = AsyncMock()
    voice.file_id = "test_file_id"
    voice.duration = 10

    message = AsyncMock()
    message.from_user = user
    message.voice = voice

    update = AsyncMock()
    update.message = message
    update.effective_user = user

    context = AsyncMock()

    # Mock services
    with patch('services.gemini.GeminiService.extract_contact_from_voice') as mock_extract:
        mock_extract.return_value = {
            "name": "Марат Ибрагимов",
            "company": "Kolesa",
            "role": "CPO",
            "event": "Product Camp"
        }

        from bot.handlers.voice import voice_handler
        await voice_handler(update, context)

        # Assert service was called
        mock_extract.assert_called_once()

        # Assert user received confirmation
        message.reply_text.assert_called()
```

**Running Tests:**

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=services --cov=models --cov-report=html

# Specific test
pytest tests/unit/services/test_contact.py::test_create_contact_with_valid_data

# Async tests
pytest -v --asyncio-mode=auto
```

---

## OpenAPI Specification

### FastAPI Integration

```python
# bot/main.py
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="NetworkingCRM API",
    description="AI-powered networking assistant",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="NetworkingCRM API",
        version="1.0.0",
        description="REST API for networking CRM system",
        routes=app.routes,
    )

    openapi_schema["info"]["x-logo"] = {
        "url": "https://example.com/logo.png"
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

### API Routes with OpenAPI Annotations

```python
# api/routes/contacts.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID

from api.schemas import ContactResponse, ContactCreate, ContactUpdate
from api.dependencies import get_current_user, get_db
from services.contact import ContactService

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

@router.get(
    "/",
    response_model=List[ContactResponse],
    summary="List contacts",
    description="Retrieve all contacts for the authenticated user with optional filtering",
    responses={
        200: {
            "description": "List of contacts",
            "content": {
                "application/json": {
                    "example": [{
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "name": "Марат Ибрагимов",
                        "company": "Kolesa Group",
                        "role": "CPO"
                    }]
                }
            }
        }
    }
)
async def list_contacts(
    status: Optional[str] = Query(None, description="Filter by status: active, sleeping, archived"),
    search: Optional[str] = Query(None, description="Search by name or company"),
    limit: int = Query(10, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    List all contacts for the current user.

    - **status**: Filter contacts by status
    - **search**: Full-text search across name and company
    - **limit**: Maximum number of results
    - **offset**: Skip first N results
    """
    service = ContactService(db)

    if search:
        contacts = await service.search_contacts(user.id, search, limit, offset)
    else:
        contacts = await service.get_contacts(user.id, status, limit, offset)

    return contacts

@router.post(
    "/",
    response_model=ContactResponse,
    status_code=201,
    summary="Create contact",
    description="Create a new contact"
)
async def create_contact(
    contact: ContactCreate,
    db = Depends(get_db),
    user = Depends(get_current_user)
):
    """Create a new contact for the authenticated user."""
    service = ContactService(db)
    return await service.create_contact(user_id=user.id, **contact.dict())

@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Get contact",
    description="Retrieve a single contact by ID"
)
async def get_contact(
    contact_id: UUID,
    db = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get contact details by ID."""
    service = ContactService(db)
    contact = await service.get_contact(contact_id, user.id)

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    return contact

@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Update contact"
)
async def update_contact(
    contact_id: UUID,
    contact_update: ContactUpdate,
    db = Depends(get_db),
    user = Depends(get_current_user)
):
    """Update contact fields."""
    service = ContactService(db)
    contact = await service.update_contact(
        contact_id,
        user.id,
        contact_update.dict(exclude_unset=True)
    )

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    return contact

@router.delete(
    "/{contact_id}",
    status_code=204,
    summary="Delete contact"
)
async def delete_contact(
    contact_id: UUID,
    db = Depends(get_db),
    user = Depends(get_current_user)
):
    """Soft delete a contact (set status to archived)."""
    service = ContactService(db)
    deleted = await service.delete_contact(contact_id, user.id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
```

### Pydantic Schemas for OpenAPI

```python
# api/schemas.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ContactBase(BaseModel):
    """Base contact schema."""
    name: str = Field(..., min_length=1, max_length=255, example="Марат Ибрагимов")
    company: Optional[str] = Field(None, max_length=255, example="Kolesa Group")
    role: Optional[str] = Field(None, max_length=255, example="CPO")
    phone: Optional[str] = Field(None, pattern=r'^\+?[0-9\s\-()]+$')
    telegram_username: Optional[str] = Field(None, pattern=r'^@?[a-zA-Z0-9_]+$')
    email: Optional[str] = Field(None, regex=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    linkedin_url: Optional[str] = None
    event_name: Optional[str] = None
    what_looking_for: Optional[str] = None
    can_help_with: Optional[str] = None
    topics: Optional[List[str]] = []
    agreements: Optional[List[str]] = []
    follow_up_action: Optional[str] = None
    raw_transcript: Optional[str] = None

class ContactCreate(ContactBase):
    """Schema for creating contact."""
    pass

class ContactUpdate(BaseModel):
    """Schema for updating contact (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = Field(None, regex='^(active|sleeping|archived)$')
    # ... other fields

class ContactResponse(ContactBase):
    """Schema for contact response."""
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "987e6543-e21b-12d3-a456-426614174000",
                "name": "Марат Ибрагимов",
                "company": "Kolesa Group",
                "role": "CPO",
                "status": "active",
                "created_at": "2025-01-15T12:00:00Z",
                "updated_at": "2025-01-15T12:00:00Z"
            }
        }
```

---

## Utilities

### Common Utilities Structure

```
core/
├── utils/
│   ├── __init__.py
│   ├── validators.py       # Input validation helpers
│   ├── formatters.py       # Text formatting
│   ├── date_utils.py       # Date/time helpers
│   ├── string_utils.py     # String manipulation
│   └── telegram_utils.py   # Telegram-specific helpers
```

### Validators

```python
# core/utils/validators.py
import re
from typing import Optional

def validate_phone(phone: Optional[str]) -> Optional[str]:
    """
    Validate and normalize phone number.

    Returns:
        Normalized phone or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digits
    digits = re.sub(r'\D', '', phone)

    # Must be 10-15 digits
    if len(digits) < 10 or len(digits) > 15:
        return None

    # Add + if not present
    return f"+{digits}" if not phone.startswith('+') else phone

def validate_telegram_username(username: Optional[str]) -> Optional[str]:
    """
    Validate and normalize Telegram username.

    Returns:
        Normalized username (with @) or None
    """
    if not username:
        return None

    # Remove @ if present
    username = username.lstrip('@')

    # Must be 5-32 alphanumeric + underscore
    if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
        return None

    return f"@{username}"

def validate_email(email: Optional[str]) -> Optional[str]:
    """Validate email format."""
    if not email:
        return None

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email.lower()):
        return email.lower()

    return None

def validate_linkedin_url(url: Optional[str]) -> Optional[str]:
    """Validate LinkedIn profile URL."""
    if not url:
        return None

    if 'linkedin.com/in/' in url:
        return url

    return None
```

### Date Utils

```python
# core/utils/date_utils.py
from datetime import datetime, timedelta
from typing import Optional
import pytz

def parse_relative_date(text: str, base: Optional[datetime] = None) -> Optional[datetime]:
    """
    Parse relative date expressions.

    Examples:
        "завтра" -> tomorrow
        "через 3 дня" -> 3 days from now
        "через неделю" -> 7 days from now
    """
    if base is None:
        base = datetime.now(pytz.UTC)

    text = text.lower().strip()

    if text in ['завтра', 'tomorrow']:
        return base + timedelta(days=1)

    if text in ['послезавтра']:
        return base + timedelta(days=2)

    if 'через' in text:
        # "через 3 дня"
        import re
        match = re.search(r'через\s+(\d+)\s+(день|дня|дней|день)', text)
        if match:
            days = int(match.group(1))
            return base + timedelta(days=days)

        # "через неделю"
        if 'неделю' in text or 'неделя' in text:
            return base + timedelta(weeks=1)

        # "через месяц"
        if 'месяц' in text:
            return base + timedelta(days=30)

    return None

def format_datetime_ru(dt: datetime) -> str:
    """Format datetime in Russian locale."""
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }

    return f"{dt.day} {months[dt.month]} {dt.year}"

def days_since(dt: datetime) -> int:
    """Calculate days since given datetime."""
    now = datetime.now(pytz.UTC)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)

    delta = now - dt
    return delta.days
```

### Telegram Utils

```python
# core/utils/telegram_utils.py
from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def build_inline_keyboard(buttons: List[List[dict]]) -> InlineKeyboardMarkup:
    """
    Build inline keyboard from button config.

    Args:
        buttons: List of rows, each row is list of button configs
                 Button config: {"text": str, "callback_data": str} or {"text": str, "url": str}

    Example:
        buttons = [
            [{"text": "✏️ Редактировать", "callback_data": "edit_123"}],
            [{"text": "LinkedIn", "url": "https://linkedin.com/in/user"}]
        ]
    """
    keyboard = []
    for row in buttons:
        keyboard_row = []
        for btn in row:
            if "url" in btn:
                keyboard_row.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
            else:
                keyboard_row.append(InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]))
        keyboard.append(keyboard_row)

    return InlineKeyboardMarkup(keyboard)

def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def chunk_message(text: str, max_length: int = 4096) -> List[str]:
    """Split long message into chunks for Telegram (max 4096 chars)."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Find last newline before max_length
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = max_length

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    return chunks
```

---

## Middlewares

### Structure

```
bot/middlewares/
├── __init__.py
├── auth.py          # User authentication
├── logging.py       # Request logging
├── error.py         # Error handling
└── rate_limit.py    # Rate limiting
```

### Authentication Middleware

```python
# bot/middlewares/auth.py
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
from functools import wraps

from services.user import UserService
from core.database import get_db

async def get_or_create_user(telegram_id: int, first_name: str, db):
    """Get or create user from Telegram ID."""
    service = UserService(db)
    user = await service.get_user_by_telegram_id(telegram_id)

    if not user:
        user = await service.create_user(
            telegram_id=telegram_id,
            name=first_name,
            profile_data={},
            settings={}
        )

    return user

def require_user(handler):
    """Decorator to ensure user exists before handler execution."""
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return

        # Get user from database
        async for db in get_db():
            user = await get_or_create_user(
                telegram_id=update.effective_user.id,
                first_name=update.effective_user.first_name,
                db=db
            )

            # Store in context for handler
            context.user_data['db_user'] = user
            context.user_data['db'] = db

            # Call original handler
            return await handler(update, context)

    return wrapper

class AuthMiddleware:
    """Middleware for authentication in FastAPI."""

    async def __call__(self, request, call_next):
        # TODO: Implement API authentication
        # For now, Telegram bot handles auth via Telegram user ID
        response = await call_next(request)
        return response
```

### Logging Middleware

```python
# bot/middlewares/logging.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from functools import wraps
import json
from datetime import datetime

logger = logging.getLogger(__name__)

def log_handler(handler):
    """Decorator to log handler execution."""
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        start_time = datetime.now()

        # Extract info
        user_id = update.effective_user.id if update.effective_user else None
        handler_name = handler.__name__

        # Log request
        logger.info(
            f"Handler started",
            extra={
                "handler": handler_name,
                "user_id": user_id,
                "update_type": type(update).__name__
            }
        )

        try:
            result = await handler(update, context)

            # Log success
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Handler completed",
                extra={
                    "handler": handler_name,
                    "user_id": user_id,
                    "duration_ms": duration * 1000
                }
            )

            return result

        except Exception as e:
            # Log error
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"Handler failed",
                extra={
                    "handler": handler_name,
                    "user_id": user_id,
                    "duration_ms": duration * 1000,
                    "error": str(e)
                },
                exc_info=True
            )
            raise

    return wrapper

class StructuredLogger:
    """Structured JSON logger for production."""

    def __init__(self):
        self.logger = logging.getLogger("networking_crm")

    def log(self, level: str, message: str, **kwargs):
        """Log structured message."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs
        }

        getattr(self.logger, level.lower())(json.dumps(log_entry))
```

### Error Handler Middleware

```python
# bot/middlewares/error.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
import traceback

logger = logging.getLogger(__name__)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for telegram bot."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Extract error info
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    # Log structured error
    error_info = {
        "error_type": type(context.error).__name__,
        "error_message": str(context.error),
        "traceback": tb_string,
        "update": update.to_dict() if update else None
    }

    logger.error(f"Error info: {error_info}")

    # Send user-friendly message
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Произошла ошибка при обработке запроса. Попробуй ещё раз.",
                parse_mode=None
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
```

### Rate Limiting

```python
# bot/middlewares/rate_limit.py
from telegram import Update
from telegram.ext import ContextTypes
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()

    async def is_allowed(self, user_id: int) -> bool:
        """Check if user is within rate limit."""
        async with self.lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=self.window_seconds)

            # Remove old requests
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if req_time > window_start
            ]

            # Check limit
            if len(self.requests[user_id]) >= self.max_requests:
                return False

            # Add new request
            self.requests[user_id].append(now)
            return True

# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

def rate_limit(handler):
    """Decorator to rate limit handler."""
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return

        if not await rate_limiter.is_allowed(update.effective_user.id):
            await update.effective_message.reply_text(
                "Слишком много запросов. Подожди минуту и попробуй снова."
            )
            return

        return await handler(update, context)

    return wrapper
```

---

## Error Handling

### Error Hierarchy

```python
# core/errors.py
from typing import Optional

class NetworkingCRMError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

# Domain errors
class ValidationError(NetworkingCRMError):
    """Validation failed."""
    pass

class NotFoundError(NetworkingCRMError):
    """Resource not found."""
    pass

class DuplicateError(NetworkingCRMError):
    """Resource already exists."""
    pass

class PermissionError(NetworkingCRMError):
    """User lacks permission."""
    pass

# External service errors
class ExternalServiceError(NetworkingCRMError):
    """External service failed."""
    pass

class GeminiAPIError(ExternalServiceError):
    """Gemini API error."""
    pass

class NotionAPIError(ExternalServiceError):
    """Notion API error."""
    pass

class TelegramAPIError(ExternalServiceError):
    """Telegram API error."""
    pass

# Database errors
class DatabaseError(NetworkingCRMError):
    """Database operation failed."""
    pass

class TransactionError(DatabaseError):
    """Transaction failed."""
    pass
```

### Error Handlers

```python
# core/error_handlers.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import ContextTypes

from core.errors import (
    NetworkingCRMError,
    ValidationError,
    NotFoundError,
    ExternalServiceError
)

# FastAPI error handlers
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "validation_error",
            "message": exc.message,
            "details": exc.details
        }
    )

async def not_found_error_handler(request: Request, exc: NotFoundError):
    """Handle not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "not_found",
            "message": exc.message
        }
    )

async def external_service_error_handler(request: Request, exc: ExternalServiceError):
    """Handle external service errors."""
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "error": "external_service_error",
            "message": "Внешний сервис временно недоступен"
        }
    )

# Telegram bot error messages
ERROR_MESSAGES = {
    "validation_error": "Неверные данные. Проверь и попробуй снова.",
    "not_found": "Контакт не найден.",
    "gemini_api_error": "Gemini API временно недоступен. Попробуй через минуту.",
    "notion_api_error": "Не удалось экспортировать в Notion. Проверь настройки.",
    "duplicate_error": "Контакт с таким именем уже существует.",
    "generic_error": "Произошла ошибка. Попробуй ещё раз."
}

async def handle_service_error(update: Update, error: Exception) -> None:
    """Handle service errors in Telegram handlers."""
    if isinstance(error, ValidationError):
        message = ERROR_MESSAGES["validation_error"]
    elif isinstance(error, NotFoundError):
        message = ERROR_MESSAGES["not_found"]
    elif isinstance(error, GeminiAPIError):
        message = ERROR_MESSAGES["gemini_api_error"]
    else:
        message = ERROR_MESSAGES["generic_error"]

    await update.effective_message.reply_text(message)
```

### Error Usage Example

```python
# services/contact.py
from core.errors import NotFoundError, ValidationError, DuplicateError

class ContactService:
    async def get_contact(self, contact_id: UUID, user_id: UUID):
        """Get contact by ID."""
        contact = await self.repository.get_by_id(contact_id)

        if not contact:
            raise NotFoundError(
                f"Contact {contact_id} not found",
                details={"contact_id": str(contact_id)}
            )

        if contact.user_id != user_id:
            raise PermissionError(
                "You don't have permission to access this contact"
            )

        return contact

    async def create_contact(self, user_id: UUID, name: str, **kwargs):
        """Create new contact."""
        if not name or len(name.strip()) == 0:
            raise ValidationError(
                "Contact name is required",
                details={"field": "name"}
            )

        # Check for duplicates
        existing = await self.repository.find_by_name_and_user(name, user_id)
        if existing:
            raise DuplicateError(
                f"Contact '{name}' already exists",
                details={"contact_id": str(existing.id)}
            )

        return await self.repository.create(user_id=user_id, name=name, **kwargs)
```

---

## Pydantic Validation

### Configuration Models

```python
# core/config.py
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Application settings with validation."""

    # Required settings
    telegram_bot_token: str = Field(..., min_length=40)
    gemini_api_key: str = Field(..., min_length=20)
    database_url: str = Field(..., regex=r'^postgresql\+asyncpg://.+')
    redis_url: str = Field(..., regex=r'^redis://.+')

    # Optional integrations
    notion_token: Optional[str] = None
    notion_database_id: Optional[str] = None
    google_sheets_credentials: Optional[str] = None
    google_cse_api_key: Optional[str] = None
    google_cse_cx: Optional[str] = None

    # App settings
    app_name: str = "NetworkingCRM"
    debug: bool = False
    log_level: str = Field("INFO", regex=r'^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$')

    # Rate limiting
    rate_limit_requests: int = Field(10, ge=1, le=100)
    rate_limit_window_seconds: int = Field(60, ge=1)

    @validator('database_url')
    def validate_database_url(cls, v):
        """Ensure database URL is for async driver."""
        if 'asyncpg' not in v:
            raise ValueError('Database URL must use asyncpg driver')
        return v

    @validator('notion_database_id')
    def validate_notion_config(cls, v, values):
        """If notion_database_id is set, notion_token must be set too."""
        if v and not values.get('notion_token'):
            raise ValueError('notion_token is required when notion_database_id is set')
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()
```

### Domain Models Validation

```python
# schemas/contact.py
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ContactExtracted(BaseModel):
    """Extracted contact data from voice/text."""

    name: str = Field(..., min_length=1, max_length=255)
    company: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    email: Optional[str] = None
    event: Optional[str] = None
    agreements: List[str] = Field(default_factory=list)
    follow_up_action: Optional[str] = None
    what_looking_for: Optional[str] = None
    can_help_with: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    raw_transcript: str

    @validator('name')
    def validate_name(cls, v):
        """Ensure name is not just whitespace."""
        if not v or not v.strip():
            return "Неизвестно"
        return v.strip()

    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone format."""
        if not v:
            return None

        from core.utils.validators import validate_phone
        validated = validate_phone(v)
        if not validated:
            raise ValueError(f"Invalid phone format: {v}")
        return validated

    @validator('telegram_username')
    def validate_telegram(cls, v):
        """Validate Telegram username."""
        if not v:
            return None

        from core.utils.validators import validate_telegram_username
        return validate_telegram_username(v)

    @validator('email')
    def validate_email(cls, v):
        """Validate email format."""
        if not v:
            return None

        from core.utils.validators import validate_email
        validated = validate_email(v)
        if not validated:
            raise ValueError(f"Invalid email format: {v}")
        return validated

    @root_validator
    def validate_has_contact_info(cls, values):
        """Ensure at least one contact method exists."""
        contact_fields = ['phone', 'telegram_username', 'email']
        has_contact = any(values.get(field) for field in contact_fields)

        if not has_contact and values.get('name') == 'Неизвестно':
            raise ValueError("Need at least name or contact method")

        return values

class ReminderCreate(BaseModel):
    """Create reminder schema."""

    contact_id: UUID
    trigger_at: datetime
    message_template: Optional[str] = None

    @validator('trigger_at')
    def validate_future_date(cls, v):
        """Ensure trigger_at is in the future."""
        if v <= datetime.now():
            raise ValueError("Reminder must be in the future")
        return v

class UserProfileUpdate(BaseModel):
    """Update user profile schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    photo_url: Optional[str] = Field(None, regex=r'^https?://.+')
    contacts: Optional[dict] = None
    roles: Optional[List[dict]] = None
    pitches: Optional[dict] = None

    @validator('pitches')
    def validate_pitches(cls, v):
        """Validate pitches structure."""
        if v is None:
            return v

        allowed_keys = {'general', 'investor', 'technical', 'product'}
        if not all(key in allowed_keys for key in v.keys()):
            raise ValueError(f"Pitch keys must be one of: {allowed_keys}")

        for pitch in v.values():
            if not isinstance(pitch, str) or len(pitch) > 500:
                raise ValueError("Each pitch must be string <= 500 chars")

        return v
```

---

## ORM Validation

### Model Constraints

```python
# models/contact.py
from sqlalchemy import Column, String, Text, ARRAY, Enum, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import validates, relationship
import uuid
from datetime import datetime

from core.database import Base
from core.utils.validators import validate_phone, validate_email, validate_telegram_username

class Contact(Base):
    __tablename__ = 'contacts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Basic info with constraints
    name = Column(String(255), nullable=False, index=True)
    company = Column(String(255), index=True)
    role = Column(String(255))

    # Contact methods
    phone = Column(String(50))
    telegram_username = Column(String(100))
    email = Column(String(255))
    linkedin_url = Column(String(500))

    # Context
    event_name = Column(String(255))
    event_date = Column(Date)
    introduced_by_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id'))

    # Details
    what_looking_for = Column(Text)
    can_help_with = Column(Text)
    topics = Column(ARRAY(String))
    agreements = Column(ARRAY(String))
    follow_up_action = Column(Text)
    raw_transcript = Column(Text)

    # Status
    status = Column(
        Enum('active', 'sleeping', 'archived', name='contact_status'),
        nullable=False,
        default='active',
        index=True
    )

    # Enrichment
    osint_data = Column(JSONB)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="contacts")
    interactions = relationship("Interaction", back_populates="contact", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="contact", cascade="all, delete-orphan")
    introduced_by = relationship("Contact", remote_side=[id], foreign_keys=[introduced_by_id])

    # Indexes
    __table_args__ = (
        Index('ix_contacts_user_status', 'user_id', 'status'),
        Index('ix_contacts_search', 'name', 'company', postgresql_using='gin', postgresql_ops={
            'name': 'gin_trgm_ops',
            'company': 'gin_trgm_ops'
        }),
        CheckConstraint('length(name) > 0', name='contact_name_not_empty'),
        CheckConstraint("status IN ('active', 'sleeping', 'archived')", name='valid_status'),
    )

    @validates('phone')
    def validate_phone_field(self, key, value):
        """Validate phone on model level."""
        if value:
            validated = validate_phone(value)
            if not validated:
                raise ValueError(f"Invalid phone: {value}")
            return validated
        return None

    @validates('email')
    def validate_email_field(self, key, value):
        """Validate email on model level."""
        if value:
            validated = validate_email(value)
            if not validated:
                raise ValueError(f"Invalid email: {value}")
            return validated
        return None

    @validates('telegram_username')
    def validate_telegram_field(self, key, value):
        """Validate Telegram username on model level."""
        if value:
            return validate_telegram_username(value)
        return None

    @validates('topics', 'agreements')
    def validate_array_length(self, key, value):
        """Limit array fields length."""
        if value and len(value) > 50:
            raise ValueError(f"{key} cannot have more than 50 items")
        return value

    def __repr__(self):
        return f"<Contact(id={self.id}, name='{self.name}', company='{self.company}')>"
```

### Repository Pattern with Validation

```python
# repositories/contact_repository.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.contact import Contact
from core.errors import NotFoundError, ValidationError

class ContactRepository:
    """Repository for contact data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> Contact:
        """Create new contact with validation."""
        try:
            contact = Contact(**kwargs)
            self.db.add(contact)
            await self.db.commit()
            await self.db.refresh(contact)
            return contact
        except ValueError as e:
            await self.db.rollback()
            raise ValidationError(str(e))
        except Exception as e:
            await self.db.rollback()
            raise

    async def get_by_id(self, contact_id: UUID) -> Optional[Contact]:
        """Get contact by ID."""
        result = await self.db.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        return result.scalar_one_or_none()

    async def find_by_user(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Contact]:
        """Find contacts for user."""
        query = select(Contact).where(Contact.user_id == user_id)

        if status:
            query = query.where(Contact.status == status)

        query = query.order_by(Contact.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search(
        self,
        user_id: UUID,
        query_text: str,
        limit: int = 10
    ) -> List[Contact]:
        """Full-text search in contacts."""
        search_pattern = f"%{query_text}%"

        query = select(Contact).where(
            Contact.user_id == user_id,
            or_(
                Contact.name.ilike(search_pattern),
                Contact.company.ilike(search_pattern),
                Contact.role.ilike(search_pattern)
            )
        ).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, contact_id: UUID, **kwargs) -> Optional[Contact]:
        """Update contact."""
        contact = await self.get_by_id(contact_id)
        if not contact:
            return None

        try:
            for key, value in kwargs.items():
                setattr(contact, key, value)

            await self.db.commit()
            await self.db.refresh(contact)
            return contact
        except ValueError as e:
            await self.db.rollback()
            raise ValidationError(str(e))

    async def delete(self, contact_id: UUID) -> bool:
        """Soft delete contact (set to archived)."""
        contact = await self.get_by_id(contact_id)
        if not contact:
            return False

        contact.status = 'archived'
        await self.db.commit()
        return True

    async def find_duplicates(
        self,
        user_id: UUID,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        telegram_username: Optional[str] = None
    ) -> List[Contact]:
        """Find potential duplicate contacts."""
        conditions = [Contact.user_id == user_id]

        if name:
            conditions.append(Contact.name.ilike(f"%{name}%"))

        if phone:
            conditions.append(Contact.phone == phone)

        if telegram_username:
            conditions.append(Contact.telegram_username == telegram_username)

        query = select(Contact).where(or_(*conditions))
        result = await self.db.execute(query)
        return list(result.scalars().all())
```

---

## Services Layer

### Service Pattern

```python
# services/contact.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.contact_repository import ContactRepository
from models.contact import Contact
from schemas.contact import ContactExtracted
from core.errors import NotFoundError, DuplicateError, ValidationError

class ContactService:
    """Business logic for contacts."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ContactRepository(db)

    async def create_contact_from_extraction(
        self,
        user_id: UUID,
        extracted: ContactExtracted,
        telegram_contact_data: Optional[dict] = None
    ) -> Contact:
        """
        Create contact from extracted data with merge logic.

        Args:
            user_id: User ID
            extracted: Extracted data from voice/text
            telegram_contact_data: Optional Telegram contact data to merge

        Returns:
            Created contact

        Raises:
            ValidationError: If data is invalid
            DuplicateError: If contact already exists
        """
        # Check for duplicates
        duplicates = await self.repository.find_duplicates(
            user_id=user_id,
            name=extracted.name,
            phone=extracted.phone,
            telegram_username=extracted.telegram_username
        )

        if duplicates:
            raise DuplicateError(
                f"Contact '{extracted.name}' may already exist",
                details={"duplicates": [str(d.id) for d in duplicates]}
            )

        # Merge Telegram contact data if provided
        contact_data = extracted.dict()
        if telegram_contact_data:
            # Telegram data has priority for basic fields
            contact_data['phone'] = telegram_contact_data.get('phone') or extracted.phone
            contact_data['name'] = telegram_contact_data.get('name') or extracted.name

        contact_data['user_id'] = user_id

        # Create contact
        contact = await self.repository.create(**contact_data)

        # Create initial interaction
        from services.interaction import InteractionService
        interaction_service = InteractionService(self.db)
        await interaction_service.create_interaction(
            contact_id=contact.id,
            type='met',
            notes=f"Добавлен в систему. Событие: {contact.event_name or 'не указано'}"
        )

        return contact

    async def get_contact(self, contact_id: UUID, user_id: UUID) -> Contact:
        """Get contact by ID with permission check."""
        contact = await self.repository.get_by_id(contact_id)

        if not contact:
            raise NotFoundError(f"Contact {contact_id} not found")

        if contact.user_id != user_id:
            raise PermissionError("Access denied")

        return contact

    async def search_contacts(
        self,
        user_id: UUID,
        query: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[Contact]:
        """Search contacts by query."""
        return await self.repository.search(user_id, query, limit)

    async def get_contacts(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Contact]:
        """Get all contacts for user."""
        return await self.repository.find_by_user(user_id, status, limit, offset)

    async def update_contact(
        self,
        contact_id: UUID,
        user_id: UUID,
        updates: dict
    ) -> Contact:
        """Update contact with permission check."""
        contact = await self.get_contact(contact_id, user_id)

        updated = await self.repository.update(contact_id, **updates)
        return updated

    async def delete_contact(self, contact_id: UUID, user_id: UUID) -> bool:
        """Delete contact (soft delete)."""
        await self.get_contact(contact_id, user_id)  # Permission check
        return await self.repository.delete(contact_id)
```

### Gemini Service

```python
# services/gemini.py
import google.generativeai as genai
from typing import Optional
import json
import asyncio
from pathlib import Path

from core.config import settings
from core.errors import GeminiAPIError, ValidationError
from schemas.contact import ContactExtracted

class GeminiService:
    """Service for Gemini API interactions."""

    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-pro')

        # Load prompts
        self.prompts_dir = Path(__file__).parent.parent / 'prompts'

    def _load_prompt(self, filename: str) -> str:
        """Load prompt from file."""
        prompt_path = self.prompts_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {filename}")

        return prompt_path.read_text(encoding='utf-8')

    async def extract_contact_from_voice(
        self,
        transcript: str
    ) -> ContactExtracted:
        """
        Extract structured contact data from voice transcript.

        Args:
            transcript: Transcribed text from voice message

        Returns:
            Extracted and validated contact data

        Raises:
            GeminiAPIError: If API call fails
            ValidationError: If extraction produces invalid data
        """
        try:
            # Load extraction prompt
            prompt_template = self._load_prompt('extract_contact.txt')
            prompt = prompt_template.format(transcript=transcript)

            # Call Gemini API (run in executor for async)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )

            # Parse JSON response
            json_text = response.text.strip()
            # Remove markdown if present
            if json_text.startswith('```json'):
                json_text = json_text[7:]
            if json_text.endswith('```'):
                json_text = json_text[:-3]
            json_text = json_text.strip()

            data = json.loads(json_text)

            # Validate with Pydantic
            extracted = ContactExtracted(**data, raw_transcript=transcript)
            return extracted

        except json.JSONDecodeError as e:
            raise ValidationError(f"Failed to parse Gemini response: {e}")
        except Exception as e:
            raise GeminiAPIError(f"Gemini API error: {e}")

    async def generate_followup_message(
        self,
        contact: dict,
        user_profile: dict,
        context: Optional[str] = None
    ) -> str:
        """Generate personalized follow-up message."""
        try:
            prompt_template = self._load_prompt('generate_followup.txt')
            prompt = prompt_template.format(
                contact=json.dumps(contact, ensure_ascii=False),
                user_profile=json.dumps(user_profile, ensure_ascii=False),
                context=context or ""
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )

            return response.text.strip()

        except Exception as e:
            raise GeminiAPIError(f"Failed to generate message: {e}")
```

---

## Repository Pattern

See [ORM Validation](#orm-validation) section for repository implementation.

**Key principles:**
- Repository = data access layer only
- No business logic in repositories
- Return domain models (ORM objects)
- Handle database errors
- Async methods for all operations

---

## Async Patterns

### Database Sessions

```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

from core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    """Initialize database (create tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Async Context Managers

```python
# Example: Async file operations
from aiofiles import open as aio_open
import aiohttp

async def download_voice_file(file_url: str, save_path: str):
    """Download voice file asynchronously."""
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as response:
            async with aio_open(save_path, 'wb') as f:
                await f.write(await response.read())

# Example: Redis cache
from aioredis import Redis

class AsyncCache:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def get(self, key: str) -> Optional[str]:
        return await self.redis.get(key)

    async def set(self, key: str, value: str, expire: int = 3600):
        await self.redis.setex(key, expire, value)
```

---

## AI Integration

### Prompts Management

```
prompts/
├── extract_contact.txt
├── generate_card.txt
├── generate_followup.txt
├── semantic_search.txt
└── match_analysis.txt
```

**Example: `prompts/extract_contact.txt`**

```
Ты — AI-ассистент для нетворкинга. Извлеки структурированные данные контакта из голосовой заметки.

ТРАНСКРИПЦИЯ:
{transcript}

ИНСТРУКЦИИ:
1. Извлеки все упомянутые данные
2. Если информация не упомянута, оставь поле пустым (null)
3. Для имени: если не понятно, используй "Неизвестно"
4. Для договорённостей: выдели конкретные действия
5. Верни ТОЛЬКО JSON, БЕЗ markdown

ФОРМАТ JSON:
{{
  "name": "Имя Фамилия",
  "company": "Название компании или null",
  "role": "Должность или null",
  "phone": "Телефон или null",
  "telegram_username": "@username или null",
  "email": "email@example.com или null",
  "event": "Где познакомились",
  "agreements": ["Договорённость 1", "Договорённость 2"],
  "follow_up_action": "Следующий шаг",
  "what_looking_for": "Что ищет человек",
  "can_help_with": "Чем может помочь",
  "topics": ["Тема 1", "Тема 2"],
  "notes": "Прочие заметки"
}}

ОТВЕТ (JSON):
```

---

## Background Tasks

### Celery Configuration

```python
# core/celery_app.py
from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    'networking_crm',
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
)

# Periodic tasks
celery_app.conf.beat_schedule = {
    'send-reminders-every-minute': {
        'task': 'tasks.reminders.send_due_reminders',
        'schedule': 60.0,  # every minute
    },
    'cleanup-expired-cards-daily': {
        'task': 'tasks.cleanup.cleanup_expired_share_cards',
        'schedule': crontab(hour=0, minute=0),  # midnight
    },
    'weekly-match-scan': {
        'task': 'tasks.matching.scan_for_matches',
        'schedule': crontab(day_of_week=1, hour=9),  # Monday 9 AM
    },
}
```

### Task Examples

```python
# tasks/reminders.py
from celery import shared_task
from datetime import datetime
import asyncio

from core.database import async_session_maker
from services.reminder import ReminderService
from services.telegram import TelegramService

@shared_task(name='tasks.reminders.send_due_reminders')
def send_due_reminders():
    """Send all due reminders."""
    asyncio.run(_send_reminders())

async def _send_reminders():
    """Async implementation."""
    async with async_session_maker() as db:
        reminder_service = ReminderService(db)
        telegram_service = TelegramService()

        # Get due reminders
        reminders = await reminder_service.get_due_reminders()

        for reminder in reminders:
            try:
                # Send notification
                await telegram_service.send_reminder_notification(
                    user_telegram_id=reminder.user.telegram_id,
                    reminder=reminder
                )

                # Mark as sent
                await reminder_service.mark_sent(reminder.id)

            except Exception as e:
                # Log error but continue with other reminders
                print(f"Failed to send reminder {reminder.id}: {e}")

@shared_task(name='tasks.osint.enrich_contact')
def enrich_contact_task(contact_id: str):
    """Background task for OSINT enrichment."""
    asyncio.run(_enrich_contact(contact_id))

async def _enrich_contact(contact_id: str):
    """Async OSINT enrichment."""
    from uuid import UUID
    from services.osint import OSINTService

    async with async_session_maker() as db:
        osint_service = OSINTService(db)
        await osint_service.enrich_contact(UUID(contact_id))
```

---

## Development Workflow

### Adding New Feature

1. **Define domain logic** in `services/`
2. **Write tests** in `tests/unit/services/`
3. **Create repository methods** if needed
4. **Add API routes** with OpenAPI annotations
5. **Create Pydantic schemas** for validation
6. **Add Telegram handlers** if needed
7. **Write integration tests**
8. **Update prompts** if using AI

### Testing Checklist

- [ ] Unit tests for service logic
- [ ] Unit tests for validators
- [ ] Integration tests for handlers
- [ ] Test error cases
- [ ] Test validation edge cases
- [ ] Check OpenAPI docs (`/api/docs`)
- [ ] Manual E2E testing in Telegram

### Code Review Checklist

- [ ] Type hints on all functions
- [ ] Docstrings for public methods
- [ ] Error handling with custom exceptions
- [ ] Proper async/await usage
- [ ] No blocking I/O in async functions
- [ ] Input validation (Pydantic + ORM)
- [ ] Security: no SQL injection, XSS, etc.
- [ ] Logging for important operations
- [ ] Tests passing

---

## Important Notes for Claude

1. **ВСЕГДА пиши тесты вместе с кодом** - это не опционально
2. **Используй Pydantic для валидации на границах системы** (API input, AI output)
3. **Используй ORM валидаторы для защиты данных** в базе
4. **Все промпты в отдельных файлах** - не хардкодить в коде
5. **Async everywhere** - нет синхронного кода в async функциях
6. **Structured logging** - логи в JSON для продакшена
7. **Graceful error handling** - пользователь не должен видеть технические ошибки
8. **OpenAPI документация автоматическая** - описывай endpoints подробно
9. **Repository pattern строго** - нет бизнес-логики в репозиториях
10. **Нет линтера, но код чистый** - следуй PEP 8, используй type hints

---

## Quick Reference Commands

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=services --cov=models --cov-report=html

# Run specific test
pytest tests/unit/services/test_contact.py -v

# Start bot
python -m bot.main

# Start FastAPI
uvicorn api.main:app --reload

# Celery worker
celery -A core.celery_app worker --loglevel=info

# Celery beat (scheduler)
celery -A core.celery_app beat --loglevel=info

# Alembic migrations
alembic revision --autogenerate -m "Description"
alembic upgrade head

# Check OpenAPI docs
# http://localhost:8000/api/docs
```
