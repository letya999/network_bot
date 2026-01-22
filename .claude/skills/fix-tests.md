# Fix Tests Skill

## Description
Исправляет падающие тесты, анализируя ошибки и внося необходимые изменения.

## Usage
- `/fix-tests` - исправить все падающие тесты
- `/fix-tests <path>` - исправить конкретный тест

## Instructions

Когда вызван этот skill:

1. **Запусти тесты чтобы увидеть ошибки:**
   ```bash
   pytest <path> -v
   ```

2. **Проанализируй ошибки:**
   - Assertion failures → логическая ошибка в коде или тесте
   - Import errors → отсутствующие модули/зависимости
   - Fixture errors → проблемы с pytest fixtures
   - Async errors → неправильное использование async/await
   - Database errors → проблемы с миграциями/fixtures

3. **Для каждого типа ошибки:**

   **Assertion Failure:**
   - Прочитай тест и код
   - Определи что на самом деле возвращается
   - Исправь либо код либо assertion (зависит от ожидания)

   **Import Error:**
   - Проверь что модуль существует
   - Проверь правильность import path
   - Добавь в requirements.txt если нужно

   **Fixture Error:**
   - Проверь conftest.py
   - Убедись что fixture правильно объявлен
   - Проверь dependencies между fixtures

   **Async Error:**
   - Добавь @pytest.mark.asyncio
   - Проверь все await
   - Убедись что async fixtures правильно используются

4. **Исправь код:**
   - Сделай минимальные изменения
   - Не меняй логику если это не баг
   - Сохрани назначение теста

5. **Перезапусти тесты:**
   ```bash
   pytest <path> -v
   ```

6. **Если всё ещё падает:**
   - Проанализируй новую ошибку
   - Повтори процесс
   - Максимум 3 итерации, потом спроси пользователя

7. **После успеха:**
   - Запусти все тесты чтобы убедиться что ничего не сломалось
   - Покажи summary исправлений

## Common Fixes

### Fix 1: Missing Async Marker
```python
# Before
def test_async_function():
    result = service.async_method()

# After
@pytest.mark.asyncio
async def test_async_function():
    result = await service.async_method()
```

### Fix 2: Wrong Assertion
```python
# Before
assert contact.name == "Марат"  # Fails: returns "Марат Ибрагимов"

# After
assert "Марат" in contact.name  # or
assert contact.name == "Марат Ибрагимов"
```

### Fix 3: Missing Mock
```python
# Before
async def test_create_contact():
    contact = await service.create_contact(name="Test")
    assert contact.id  # Fails: no database

# After
async def test_create_contact(db_session):  # Add fixture
    service = ContactService(db_session)
    contact = await service.create_contact(name="Test")
    assert contact.id
```

### Fix 4: Fixture Scope
```python
# Before
@pytest.fixture
async def db_session():  # Creates new session each test
    ...

# After
@pytest.fixture(scope="function")  # Explicit scope
async def db_session():
    ...
```

## Examples

User: `/fix-tests`
Assistant: Запускаю все тесты...
```bash
pytest -v
```

Найдено 3 падающих теста:

❌ test_contact.py::test_create_contact_with_phone
   AssertionError: "+77771234567" != "77771234567"

❌ test_gemini.py::test_extract_contact
   ImportError: cannot import name 'GeminiService'

❌ test_handlers.py::test_voice_handler
   RuntimeError: coroutine was never awaited

Исправляю...

**1. test_create_contact_with_phone:**
Проблема: phone validation добавляет "+", тест ожидает без него

Исправление в tests/unit/services/test_contact.py:
```python
assert contact.phone == "+77771234567"  # было без +
```

**2. test_extract_contact:**
Проблема: неправильный import path

Исправление:
```python
from services.gemini import GeminiService  # было from gemini import
```

**3. test_voice_handler:**
Проблема: забыли await

Исправление:
```python
@pytest.mark.asyncio  # добавил
async def test_voice_handler():  # добавил async
    await voice_handler(update, context)  # добавил await
```

Перезапускаю тесты...
```bash
pytest -v
```

✅ Все тесты прошли! (47/47)

Исправлено:
- 1 assertion
- 1 import
- 1 async issue

---

User: `/fix-tests tests/unit/services/test_reminder.py`
Assistant: Запускаю тесты для ReminderService...
```bash
pytest tests/unit/services/test_reminder.py -v
```

❌ test_create_reminder_in_past_fails
   ValidationError not raised

Анализирую...

Проблема: validator не проверяет что trigger_at в будущем

Исправление в schemas/reminder.py:
```python
@validator('trigger_at')
def validate_future_date(cls, v):
    from datetime import datetime
    if v <= datetime.now():
        raise ValueError("Reminder must be in the future")
    return v
```

Перезапускаю...
✅ Тест прошёл!

Запускаю все тесты для уверенности...
✅ Все тесты OK (47/47)
