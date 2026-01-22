# Database Migration

Управляет миграциями через Alembic.

## Usage
- `/migrate create <description>` - создать
- `/migrate up` - применить
- `/migrate down` - откатить
- `/migrate status` - статус

## Instructions

**Create:**
```bash
alembic revision --autogenerate -m "<description>"
```
Проверь сгенерированный файл, покажи что изменится.

**Up:**
```bash
alembic upgrade head
```

**Down:**
⚠️ Предупреди о потере данных, спроси подтверждение.
```bash
alembic downgrade -1
```

**Status:**
```bash
alembic current
alembic history
```
