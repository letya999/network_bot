# Code Review Skill

## Description
Проводит code review изменений, проверяя соответствие best practices проекта.

## Usage
- `/review` - проверить все uncommitted изменения
- `/review <file>` - проверить конкретный файл

## Instructions

Когда вызван этот skill:

1. **Получи изменения:**
   ```bash
   # Для uncommitted
   git diff

   # Для конкретного файла
   git diff <file>
   ```

2. **Проверь по чеклисту:**

   ### Architecture & Structure
   - [ ] Правильный слой (handler → service → repository)
   - [ ] Нет бизнес-логики в handlers/repositories
   - [ ] Нет прямых SQL запросов в services
   - [ ] Сервисы используют repositories

   ### Code Quality
   - [ ] Type hints на всех функциях
   - [ ] Docstrings для публичных методов
   - [ ] Нет дублирования кода
   - [ ] Функции < 50 строк
   - [ ] Классы < 300 строк

   ### Async/Await
   - [ ] Async функции везде где I/O
   - [ ] Нет blocking operations в async функциях
   - [ ] Правильное использование await
   - [ ] Нет синхронных вызовов БД/API

   ### Validation
   - [ ] Pydantic schemas для входных данных
   - [ ] ORM validators где нужно
   - [ ] Проверка permissions
   - [ ] Sanitization user input

   ### Error Handling
   - [ ] Try/except для внешних вызовов
   - [ ] Custom exceptions из core.errors
   - [ ] User-friendly error messages
   - [ ] Логирование ошибок

   ### Security
   - [ ] Нет SQL injection
   - [ ] Нет hardcoded secrets
   - [ ] Валидация всех входных данных
   - [ ] Проверка авторизации

   ### Testing
   - [ ] Есть unit тесты для сервисов
   - [ ] Есть integration тесты для handlers
   - [ ] Покрыты edge cases
   - [ ] Тесты проходят

   ### Documentation
   - [ ] OpenAPI аннотации для API
   - [ ] Понятные названия переменных
   - [ ] Комментарии для сложной логики
   - [ ] README обновлен если нужно

3. **Для каждой проблемы:**
   - Укажи файл и строку
   - Объясни проблему
   - Предложи исправление
   - Оцени severity (critical/major/minor)

4. **Формат отчета:**
   ```
   📋 Code Review для <files>

   ✅ Хорошо:
   - List good practices found

   ⚠️ Замечания:

   [MAJOR] file.py:123
   Проблема: Описание
   Предложение: Как исправить

   [MINOR] file.py:456
   ...

   📊 Итого:
   - Critical: X
   - Major: Y
   - Minor: Z

   Рекомендация: [Approve / Request Changes]
   ```

## Review Examples

### Good Code
```python
# services/contact.py

class ContactService:
    """Service for contact management."""  # ✅ Docstring

    def __init__(self, db: AsyncSession):  # ✅ Type hints
        self.db = db
        self.repository = ContactRepository(db)  # ✅ Uses repository

    async def create_contact(  # ✅ Async for I/O
        self,
        user_id: UUID,
        data: ContactCreate  # ✅ Pydantic validation
    ) -> Contact:
        """Create new contact with validation."""
        try:
            # ✅ Business logic in service
            if not data.name:
                raise ValidationError("Name required")

            # ✅ Repository for data access
            contact = await self.repository.create(
                user_id=user_id,
                **data.dict()
            )

            return contact

        except ValueError as e:
            # ✅ Custom exceptions
            raise ValidationError(str(e))
```

### Bad Code
```python
# services/contact.py

class ContactService:  # ❌ No docstring

    def __init__(self, db):  # ❌ No type hints
        self.db = db

    def create_contact(self, user_id, name):  # ❌ Sync function with I/O
        # ❌ Direct SQL instead of repository
        result = self.db.execute(
            "INSERT INTO contacts (user_id, name) VALUES (?, ?)",
            (user_id, name)
        )

        # ❌ No validation
        # ❌ No error handling

        return result
```

**Review:**
```
📋 Code Review: services/contact.py

❌ Критические проблемы:

[CRITICAL] Line 3-10
Проблема: Synchronous function with database I/O
- Должна быть async def
- Должен быть await для db операций
Предложение:
```python
async def create_contact(self, user_id: UUID, name: str) -> Contact:
    contact = await self.repository.create(user_id=user_id, name=name)
```

[CRITICAL] Line 6-9
Проблема: Raw SQL вместо repository/ORM
- SQL injection risk
- Нарушает архитектуру
Предложение: Использовать ContactRepository

[MAJOR] Line 3
Проблема: Missing type hints
Предложение: Добавить типы для всех параметров

[MAJOR] Line 1
Проблема: Missing docstring
Предложение: Добавить описание класса

[MAJOR] Line 11
Проблема: No input validation
Предложение: Использовать Pydantic schema ContactCreate

📊 Итого:
- Critical: 2
- Major: 3
- Minor: 0

Рекомендация: ❌ REQUEST CHANGES
Нужно исправить критические проблемы перед merge.
```

## Examples

User: `/review`
Assistant: Проверяю uncommitted изменения...
```bash
git diff --name-only
```

Файлы:
- services/notion.py (new)
- bot/handlers/export.py (modified)
- tests/unit/services/test_notion.py (new)

Анализирую...

📋 Code Review

**services/notion.py:**

✅ Хорошо:
- Async функции
- Type hints везде
- Error handling с custom exceptions
- Docstrings

⚠️ Замечания:

[MINOR] Line 45
```python
headers = {"Authorization": f"Bearer {settings.notion_token}"}
```
Предложение: Вынести в _get_headers() метод для переиспользования

**bot/handlers/export.py:**

✅ Хорошо:
- Используется @require_user middleware
- User-friendly error messages
- Правильная структура handler'а

⚠️ Замечания:

[MAJOR] Line 23
```python
service = NotionService(db)
result = service.export_contact(contact_id)  # ❌ No await!
```
Проблема: Забыли await для async функции
Исправление:
```python
result = await service.export_contact(contact_id)
```

**tests/unit/services/test_notion.py:**

✅ Хорошо:
- Покрыты основные сценарии
- Используются mocks для API
- Async тесты

📊 Итого:
- Critical: 0
- Major: 1 (missing await)
- Minor: 1

Рекомендация: ⚠️ REQUEST CHANGES
Исправить major issue с await, затем можно мержить.

Исправить автоматически?

---

User: `/review services/gemini.py`
Assistant: Проверяю services/gemini.py...

📋 Code Review: services/gemini.py

✅ Отлично:
- Все async функции с await
- Промпты загружаются из файлов
- Pydantic валидация результатов
- Обработка JSON parsing errors
- Custom GeminiAPIError exceptions
- Хорошие docstrings
- Type hints везде

⚠️ Suggestions (необязательно):

[MINOR] Line 67
Можно добавить retry logic для API calls:
```python
from tenacity import retry, stop_after_attempt

@retry(stop=stop_after_attempt(3))
async def _call_gemini(self, prompt: str):
    ...
```

[MINOR] Line 89
Можно кэшировать промпты:
```python
from functools import lru_cache

@lru_cache(maxsize=10)
def _load_prompt(self, filename: str) -> str:
    ...
```

📊 Итого:
- Critical: 0
- Major: 0
- Minor: 2 (suggestions)

Рекомендация: ✅ APPROVE
Код отличный, suggestions опциональны.
