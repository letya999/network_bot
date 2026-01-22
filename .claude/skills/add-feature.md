# Add Feature Skill

## Description
Добавляет новую фичу в проект следуя архитектуре и best practices.

## Usage
- `/add-feature <описание>`

## Instructions

Когда вызван этот skill:

1. **Проанализируй запрос:**
   - Какая именно фича требуется
   - В какой слой попадает (handler, service, repository)
   - Нужны ли изменения в моделях
   - Требуется ли AI интеграция

2. **Создай план:**
   ```
   План добавления фичи: <название>

   1. [ ] Модели: <изменения>
   2. [ ] Миграция: <если нужна>
   3. [ ] Repository: <новые методы>
   4. [ ] Service: <бизнес-логика>
   5. [ ] Schemas: <pydantic модели>
   6. [ ] Handler/API: <точка входа>
   7. [ ] Tests: <что тестировать>
   8. [ ] Prompts: <если нужны>
   ```

3. **Следуй структуре проекта:**
   - Models в `models/`
   - Repositories в `repositories/`
   - Services в `services/`
   - Schemas в `schemas/`
   - Handlers в `bot/handlers/`
   - API routes в `api/routes/`
   - Tests в `tests/`
   - Prompts в `prompts/`

4. **Для каждого компонента:**

   **Model (если нужно):**
   - Добавь поля с валидацией
   - Добавь индексы если нужны
   - Добавь relationships
   - Создай миграцию (`/migrate create`)

   **Repository:**
   - Добавь методы для data access
   - Только SQL/ORM код, без бизнес-логики
   - Async методы
   - Обработка ошибок

   **Service:**
   - Бизнес-логика
   - Валидация (Pydantic)
   - Вызовы repositories
   - Обработка ошибок (custom exceptions)

   **Schemas:**
   - Pydantic models для входных данных
   - Response models
   - Валидаторы

   **Handler/API:**
   - Telegram handler или FastAPI route
   - OpenAPI аннотации (для API)
   - Обработка ошибок с user-friendly сообщениями
   - Используй middlewares (auth, logging)

   **Tests:**
   - Unit тесты для service
   - Integration тесты для handler
   - Покрытие edge cases

5. **ОБЯЗАТЕЛЬНО пиши тесты сразу:**
   - Не откладывай тесты на потом
   - Минимум 3 теста: happy path, edge case, error case

6. **После реализации:**
   - Запусти тесты (`/test`)
   - Проверь что ничего не сломалось
   - Обнови документацию если нужно

## Examples

User: `/add-feature экспорт контактов в Notion`
Assistant: Анализирую фичу "экспорт контактов в Notion"...

План реализации:

1. [ ] Service: NotionService (интеграция с Notion API)
2. [ ] Repository: не нужно (используем ContactRepository)
3. [ ] Handler: добавить кнопку "В Notion" на карточке контакта
4. [ ] Tests: unit тесты для NotionService
5. [ ] Config: добавить NOTION_TOKEN и NOTION_DATABASE_ID

Начинаю реализацию:

**1. Создаю NotionService:**
```python
# services/notion.py
...
```

**2. Пишу тесты:**
```python
# tests/unit/services/test_notion.py
...
```

**3. Добавляю handler:**
```python
# bot/handlers/export.py
...
```

**4. Запускаю тесты:**
```
/test unit/services/test_notion.py
```

✅ Фича готова!

Что сделано:
- NotionService для экспорта
- Тесты покрывают основные сценарии
- Кнопка "В Notion" на карточках
- Обработка ошибок API

Хочешь протестировать в боте?