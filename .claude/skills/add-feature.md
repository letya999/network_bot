# Add Feature

Добавляет фичу следуя архитектуре проекта.

## Usage
`/add-feature <описание>`

## Instructions

1. **План:**
   - Models (если нужно)
   - Миграция (если нужно)
   - Repository методы
   - Service (бизнес-логика)
   - Pydantic schemas
   - Handler/API
   - Tests

2. **Структура:**
   - `models/` - ORM модели с валидацией
   - `repositories/` - data access, только SQL
   - `services/` - бизнес-логика
   - `schemas/` - Pydantic validation
   - `bot/handlers/` или `api/routes/` - точка входа
   - `tests/` - unit + integration

3. **ОБЯЗАТЕЛЬНО:**
   - Type hints везде
   - Async функции для I/O
   - Тесты сразу (минимум 3: happy path, edge case, error)
   - Custom exceptions из `core.errors`

4. После реализации:
   - `/test`
   - `/review`
