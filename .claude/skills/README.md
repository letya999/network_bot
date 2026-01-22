# Skills для NetworkingCRM

## Доступные Skills

### `/test` - Test Runner
Запуск тестов с coverage и анализом ошибок.

### `/migrate` - Database Migration
Управление Alembic миграциями (create/up/down/status).

### `/add-feature` - Add Feature
Создание фичи по архитектуре: models → repository → service → handler → tests.

### `/api-endpoint` - API Endpoint
REST endpoint с OpenAPI docs и тестами.

### `/telegram-handler` - Telegram Handler
Bot handler с middlewares (auth, logging, rate_limit).

### `/fix-tests` - Fix Tests
Автоматическое исправление падающих тестов.

### `/review` - Code Review
Проверка кода по чеклисту проекта.

---

## Workflow

**Новая фича:**
```
/add-feature <описание>
/migrate create <name>  # если нужна БД
/migrate up
/test
/review
```

**API:**
```
/api-endpoint GET /path Description
/test integration
```

**Telegram:**
```
/telegram-handler command /cmd Description
/test integration
```

**Фикс:**
```
/test           # найти проблему
/fix-tests      # автофикс
/review         # проверка
```

---

См. [claude.md](../../claude.md) для деталей архитектуры.
