# Fix Tests

Исправляет падающие тесты.

## Usage
- `/fix-tests` - все
- `/fix-tests <path>` - конкретный

## Instructions

1. Запусти тесты, найди ошибки

2. **Типичные фиксы:**
   - Missing `@pytest.mark.asyncio` + `async def` + `await`
   - Wrong assertion → исправь expected value
   - Missing mock → добавь fixture/mock
   - Import error → проверь path
   - Fixture error → проверь conftest.py

3. Исправь, перезапусти

4. Максимум 3 итерации, потом спроси пользователя
