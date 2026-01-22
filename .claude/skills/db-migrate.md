# Database Migration Skill

## Description
Управляет миграциями базы данных через Alembic.

## Usage
- `/migrate create <description>` - создать новую миграцию
- `/migrate up` - применить миграции
- `/migrate down` - откатить последнюю миграцию
- `/migrate status` - показать статус миграций
- `/migrate history` - показать историю миграций

## Instructions

Когда вызван этот skill:

1. **Определи команду:**
   - `create` → создать новую миграцию
   - `up` → применить pending миграции
   - `down` → откатить последнюю
   - `status` → показать текущее состояние
   - `history` → показать всю историю

2. **Для `create <description>`:**
   ```bash
   # Сначала проверь что модели изменились
   # Затем создай миграцию
   alembic revision --autogenerate -m "<description>"
   ```
   - Проверь созданный файл миграции
   - Убедись что upgrade() и downgrade() корректны
   - Покажи пользователю что будет изменено

3. **Для `up`:**
   ```bash
   # Сначала покажи что будет применено
   alembic current
   alembic history

   # Затем примени
   alembic upgrade head
   ```
   - Покажи результат
   - Проверь что миграция прошла успешно

4. **Для `down`:**
   ```bash
   # Покажи текущую ревизию
   alembic current

   # Откати на одну назад
   alembic downgrade -1
   ```
   - ⚠️ Предупреди что это может потерять данные
   - Спроси подтверждение если есть риск

5. **Для `status`:**
   ```bash
   alembic current
   alembic history
   ```
   - Покажи текущую ревизию
   - Покажи pending миграции если есть

6. **Best Practices:**
   - Всегда проверяй сгенерированные миграции вручную
   - Не создавай миграции если модели не изменились
   - Бэкап БД перед сложными миграциями
   - Тестируй миграции на dev окружении

## Examples

User: `/migrate create add_osint_data_to_contacts`
Assistant: Создаю миграцию для добавления OSINT данных...

Изменения в моделях:
- Contact: добавлено поле osint_data (JSONB)

```bash
alembic revision --autogenerate -m "add osint_data to contacts"
```

✅ Создан файл: alembic/versions/abc123_add_osint_data.py

Содержимое:
```python
def upgrade():
    op.add_column('contacts', sa.Column('osint_data', postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('contacts', 'osint_data')
```

Выглядит корректно. Применить миграцию? (`/migrate up`)

---

User: `/migrate up`
Assistant: Применяю миграции...

Текущая ревизия: xyz789
Pending миграции: abc123 (add osint_data to contacts)

```bash
alembic upgrade head
```

✅ Миграция применена успешно
Новая ревизия: abc123

---

User: `/migrate down`
Assistant: ⚠️ Откат миграции abc123 (add osint_data to contacts)

Это удалит колонку osint_data из таблицы contacts.
Все данные в этой колонке будут потеряны.

Продолжить? (yes/no)
