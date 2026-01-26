# План рефакторинга NetworkBot

> **Дата анализа:** 2026-01-26
> **Проанализировано строк кода:** 4,400
> **Обнаружено критических проблем:** 45+
> **Технический долг:** Высокий

---

## 📋 Содержание

1. [Краткое резюме](#краткое-резюме)
2. [Критические проблемы производительности](#1-критические-проблемы-производительности)
3. [Нарушения Clean Code](#2-нарушения-clean-code)
4. [Архитектурные проблемы](#3-архитектурные-проблемы)
5. [Оптимизация базы данных](#4-оптимизация-базы-данных)
6. [Таблица критических проблем](#5-таблица-критических-проблем)
7. [Дорожная карта исправлений](#6-дорожная-карта-исправлений)

---

## Краткое резюме

### 🔴 Критические проблемы

| # | Проблема | Файл | Строки | Влияние |
|---|----------|------|--------|---------|
| 1 | N+1 запросы при семантическом поиске | `match_service.py` | 151-164 | O(n) память, падение при 1000+ контактов |
| 2 | God Object в handlers.py (819 строк) | `handlers.py` | 1-820 | Невозможность поддержки |
| 3 | Отсутствие Dependency Injection | Все сервисы | - | Невозможность тестирования |
| 4 | Отсутствуют индексы БД | `contact.py` | 43-46 | Медленные запросы |

### 🟡 Высокий приоритет

- Последовательные API вызовы (замедление в 2x)
- Дублирование логики слияния контактов (3 места)
- Жёсткая связанность между сервисами
- Бизнес-логика в UI-обработчиках

### 🟢 Средний приоритет

- Хардкод магических строк/чисел (6+ файлов)
- Функции >150 строк
- Незавершённая реализация синхронизации Sheets
- Утечки памяти в rate limiter

---

## 1. Критические проблемы производительности

### 1.1 N+1 Query Problem в семантическом поиске

**Файл:** `app/services/match_service.py:151-164`

**Проблема:**
```python
# Загружает ВСЕ контакты пользователя в память
stmt = select(Contact).where(Contact.user_id == user_id)
result = await self.session.execute(stmt)
contacts = result.scalars().all()  # O(n) память!

contact_list_str = ""
for c in contacts:  # Итерация по всем контактам
    contact_list_str += self._format_contact_context(c) + "\n---\n"
```

**Влияние:**
- Линейное использование памяти O(n)
- Падение приложения при 1000+ контактов
- Длинный промпт для AI (увеличение стоимости и времени)

**Решение:**
```python
# Вариант 1: Пагинация + фильтрация
stmt = (
    select(Contact)
    .where(Contact.user_id == user_id)
    .order_by(Contact.last_interaction_date.desc())
    .limit(50)  # Только последние 50 контактов
)

# Вариант 2: Векторные эмбеддинги (долгосрочное решение)
# Использовать pgvector для семантического поиска в БД
```

**Приоритет:** 🔴 Критический
**Сложность:** Средняя
**Время:** 4-6 часов

---

### 1.2 Последовательные API вызовы вместо параллельных

**Файл:** `app/services/osint_service.py:196-219`

**Проблема:**
```python
async def enrich_contact_final(self, contact_id, linkedin_url):
    # Ждём первого вызова
    profile_results = await self._tavily_search(linkedin_url)
    # Только потом делаем второй
    content_results = await self._tavily_search(content_query)
    all_results = profile_results + content_results
```

**Влияние:**
- 20-40 секунд вместо 10-20 секунд
- Плохой UX для пользователя

**Решение:**
```python
async def enrich_contact_final(self, contact_id, linkedin_url):
    # Параллельное выполнение
    profile_task = self._tavily_search(linkedin_url)
    content_task = self._tavily_search(content_query)

    profile_results, content_results = await asyncio.gather(
        profile_task,
        content_task,
        return_exceptions=True  # Один упал - второй продолжает
    )

    all_results = []
    if not isinstance(profile_results, Exception):
        all_results.extend(profile_results)
    if not isinstance(content_results, Exception):
        all_results.extend(content_results)
```

**Приоритет:** 🔴 Критический
**Сложность:** Низкая
**Время:** 1-2 часа

---

### 1.3 Искусственные задержки в batch enrichment

**Файл:** `app/services/osint_service.py:346`

**Проблема:**
```python
for contact in contacts:
    try:
        res = await osint_service.enrich_contact(contact.id)
        if res["status"] == "success":
            enriched += 1
        await asyncio.sleep(1)  # 😱 Жёсткая задержка 1 секунда!
```

**Влияние:**
- 5 контактов = 5+ секунд
- Должно быть ~1-2 секунды с правильным rate limiting

**Решение:**
```python
# Используем semaphore для rate limiting
from asyncio import Semaphore

class OSINTService:
    def __init__(self, session, rate_limit=5):
        self._semaphore = Semaphore(rate_limit)  # Макс 5 одновременно
        self._rate_limiter = TokenBucket(rate=10, per_second=1)

    async def enrich_contact(self, contact_id):
        async with self._semaphore:
            await self._rate_limiter.acquire()
            # Выполняем enrichment
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 2-3 часа

---

### 1.4 Notion синхронизация загружает все страницы каждый раз

**Файл:** `app/services/notion_service.py:59-103`

**Проблема:**
```python
# При каждой синхронизации загружаем ВСЕ страницы из Notion
existing_pages = await self._get_existing_pages(session)
for page in results:
    # ... итерация через пагинацию
```

**Влияние:**
- При 500+ контактах в Notion каждая синхронизация загружает все
- Достижение rate limits Notion API

**Решение:**
```python
# Вариант 1: Хранить sync metadata
class NotionSyncMetadata(Base):
    __tablename__ = "notion_sync_metadata"
    user_id = Column(UUID, primary_key=True)
    last_sync_time = Column(DateTime)
    notion_last_edited_time = Column(DateTime)

# Вариант 2: Использовать фильтры Notion API
query = {
    "filter": {
        "property": "Last edited time",
        "date": {
            "after": last_sync_time.isoformat()
        }
    }
}
results = await notion.databases.query(database_id, **query)
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 3-4 часа

---

### 1.5 Google Sheets не использует batch updates

**Файл:** `app/services/sheets_service.py:136-146`

**Проблема:**
```python
if contact.name in name_map:
    # Update existing
    row_idx = name_map[contact.name]
    # ws.update(f"A{row_idx+1}:M{row_idx+1}", [row_data])  # ЗАКОММЕНТИРОВАНО!
    # This is slow in loop.
    stats["updated"] += 1  # Помечает как обновлённый, но ничего не делает!
```

**Влияние:**
- Обновления не сохраняются
- Утверждает успех, но молча проваливается
- Обманчивая статистика

**Решение:**
```python
def sync_contacts_to_sheet(self, contacts):
    # Собираем все обновления
    updates = []
    for contact in contacts:
        if contact.name in name_map:
            row_idx = name_map[contact.name]
            updates.append({
                'range': f'A{row_idx+1}:M{row_idx+1}',
                'values': [row_data]
            })

    # Одно batch обновление
    if updates:
        ws.batch_update(updates)
```

**Приоритет:** 🔴 Критический (баг)
**Сложность:** Низкая
**Время:** 1-2 часа

---

### 1.6 Отсутствуют индексы базы данных

**Файл:** `app/models/contact.py:43-46`

**Проблема:**
```python
__table_args__ = (
    # Indexes are defined in spec but usually we define them via Column(index=True) or Index construct
    # contacts: (user_id), (user_id, status)
)  # ОТСУТСТВУЮТ: (user_id, status), (user_id, created_at)
```

**Влияние:**
- Медленные запросы для `find_recent_contacts`, `get_inactive_contacts`
- Index scans вместо index seeks

**Решение:**
```python
from sqlalchemy import Index

class Contact(Base):
    __tablename__ = "contacts"

    # ... поля ...

    __table_args__ = (
        Index('ix_contact_user_status', 'user_id', 'status'),
        Index('ix_contact_user_created', 'user_id', 'created_at'),
        Index('ix_contact_user_name', 'user_id', 'name'),
        Index('ix_contact_user_last_interaction', 'user_id', 'last_interaction_date'),
    )
```

**Миграция Alembic:**
```python
# alembic/versions/xxx_add_composite_indexes.py
def upgrade():
    op.create_index('ix_contact_user_status', 'contacts', ['user_id', 'status'])
    op.create_index('ix_contact_user_created', 'contacts', ['user_id', 'created_at'])
    op.create_index('ix_contact_user_name', 'contacts', ['user_id', 'name'])
    op.create_index('ix_contact_user_last_interaction', 'contacts', ['user_id', 'last_interaction_date'])
```

**Приоритет:** 🔴 Критический
**Сложность:** Низкая
**Время:** 1 час

---

### 1.7 Утечка памяти в rate limiter

**Файл:** `app/bot/rate_limiter.py:42-53`

**Проблема:**
```python
self.request_history: Dict[int, list] = defaultdict(list)
self.voice_history: Dict[int, list] = defaultdict(list)
# _clean_old_requests() удаляет устаревшие, но записи для неактивных пользователей остаются
```

**Влияние:**
- Долгоработающий бот накапливает записи для всех пользователей
- Утечка памяти со временем

**Решение:**
```python
# Вариант 1: Периодическая очистка неактивных пользователей
async def _cleanup_inactive_users(self):
    """Удаляет пользователей без активности 24+ часа"""
    now = time.time()
    cutoff = now - 86400  # 24 часа

    inactive_users = [
        user_id for user_id, history in self.request_history.items()
        if history and max(history) < cutoff
    ]

    for user_id in inactive_users:
        del self.request_history[user_id]
        del self.voice_history[user_id]

# Вариант 2: Redis для распределённого rate limiting
class RedisRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(self, user_id: int, limit: int, window: int):
        key = f"rate_limit:{user_id}"
        async with self.redis.pipeline() as pipe:
            pipe.zadd(key, {time.time(): time.time()})
            pipe.zremrangebyscore(key, 0, time.time() - window)
            pipe.zcard(key)
            pipe.expire(key, window)
            _, _, count, _ = await pipe.execute()
        return count <= limit
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя (Вариант 1), Высокая (Вариант 2)
**Время:** 2 часа (Вариант 1), 4-6 часов (Вариант 2)

---

## 2. Нарушения Clean Code

### 2.1 Monolithic Handlers File (God Object)

**Файл:** `app/bot/handlers.py` (819 строк!)

**Проблема:**
```python
# Один файл смешивает 12+ обработчиков для разных целей:
- start()
- format_card()
- handle_voice()
- handle_contact()
- list_contacts()
- find_contact()
- generate_card_callback()
- export_contacts()
- handle_text_message()
- show_prompt()
- start_edit_prompt()
- save_prompt()
- reset_prompt()
- set_event_mode()
```

**Влияние:**
- Невозможность найти нужный код
- Merge conflicts при командной работе
- Нарушение Single Responsibility Principle

**Решение:**
```
app/bot/
├── handlers/
│   ├── __init__.py
│   ├── contact_handlers.py      # handle_voice, handle_contact, handle_text_message
│   ├── search_handlers.py       # find_contact, list_contacts, export_contacts
│   ├── profile_handlers.py      # generate_card_callback
│   ├── prompt_handlers.py       # show_prompt, start_edit_prompt, save_prompt, reset_prompt
│   ├── event_handlers.py        # set_event_mode
│   └── common.py                # start, format_card (utility functions)
```

**Миграция:**
```python
# handlers/__init__.py
from .contact_handlers import handle_voice, handle_contact, handle_text_message
from .search_handlers import find_contact, list_contacts, export_contacts
from .profile_handlers import generate_card_callback
from .prompt_handlers import show_prompt, start_edit_prompt, save_prompt, reset_prompt
from .event_handlers import set_event_mode
from .common import start, format_card

__all__ = [
    'handle_voice', 'handle_contact', 'handle_text_message',
    'find_contact', 'list_contacts', 'export_contacts',
    'generate_card_callback',
    'show_prompt', 'start_edit_prompt', 'save_prompt', 'reset_prompt',
    'set_event_mode',
    'start', 'format_card'
]
```

**Приоритет:** 🔴 Критический
**Сложность:** Средняя
**Время:** 6-8 часов

---

### 2.2 Дублирование логики слияния контактов

**Файл:** `app/bot/handlers.py` (3 места!)

**Проблема:**
```python
# Место 1: handle_contact (строки 348-376)
existing = await contact_service.find_by_identifiers(db_user.id, phone=data['phone'])
if existing:
    # ... проверка и ответ

# Место 2: handle_text_message (строки 613-652)
existing_contact = await contact_service.find_by_identifiers(db_user.id, phone, tg)
if existing_contact:
    # ... та же проверка и ответ

# Место 3: handle_voice (строки 232-293)
now = time.time()
last_contact_time = context.user_data.get("last_contact_time", 0)
last_contact_id = context.user_data.get("last_contact_id")

if last_contact_id and (now - last_contact_time < 300):
    contact = await contact_service.update_contact(last_contact_id, data)
    # ... ещё логика
```

**Влияние:**
- Изменения нужно делать в 3 местах
- Риск несогласованности
- Нарушение DRY

**Решение:**
```python
# app/services/contact_merge_service.py
class ContactMergeService:
    MERGE_TIMEOUT_SECONDS = 300  # 5 минут

    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_service = ContactService(session)

    async def merge_or_create_contact(
        self,
        user_id: uuid.UUID,
        contact_data: dict,
        active_contact_id: Optional[uuid.UUID] = None,
        active_contact_time: Optional[float] = None
    ) -> tuple[Contact, bool]:  # (contact, was_merged)
        """
        Создаёт новый контакт или обновляет существующий.

        Returns:
            (Contact, bool): Контакт и флаг был ли он объединён с существующим
        """
        # Проверка на слияние с активным контактом
        if active_contact_id and active_contact_time:
            now = time.time()
            if now - active_contact_time < self.MERGE_TIMEOUT_SECONDS:
                contact = await self.contact_service.update_contact(
                    active_contact_id,
                    contact_data
                )
                return contact, True

        # Проверка на дубликаты по идентификаторам
        existing = await self.contact_service.find_by_identifiers(
            user_id,
            phone=contact_data.get('phone'),
            telegram_username=contact_data.get('telegram_username'),
            email=contact_data.get('email')
        )

        if existing:
            # Спросить у пользователя о слиянии
            return existing, False

        # Создать новый контакт
        contact = await self.contact_service.create_contact(user_id, contact_data)
        return contact, False

# Использование в handlers:
merge_service = ContactMergeService(session)
contact, was_merged = await merge_service.merge_or_create_contact(
    db_user.id,
    data,
    active_contact_id=context.user_data.get("last_contact_id"),
    active_contact_time=context.user_data.get("last_contact_time")
)
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 3-4 часа

---

### 2.3 Hardcoded Magic Strings

**Проблема:** "Неизвестно" используется в 6+ файлах

**Файлы:**
- `app/bot/handlers.py:241, 272`
- `app/services/contact_service.py:22, 147, 329`
- `app/services/osint_service.py:272`
- `app/services/match_service.py:93`

**Решение:**
```python
# app/config/constants.py
"""Константы приложения"""

# Контакты
UNKNOWN_CONTACT_NAME = "Неизвестно"
UNKNOWN_VALUE = "Не указано"

# Тайминги
CONTACT_MERGE_TIMEOUT_SECONDS = 300  # 5 минут
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_REQUESTS_PER_MINUTE = 20
MAX_VOICE_REQUESTS_PER_MINUTE = 5

# Поиск
MAX_SEARCH_QUERY_LENGTH = 100
MIN_SEARCH_QUERY_LENGTH = 1
DEFAULT_SEARCH_RESULTS_LIMIT = 10

# AI
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
MAX_SEMANTIC_SEARCH_CONTACTS = 50

# Enrichment
OSINT_ENRICHMENT_DELAY_DAYS = 30
BATCH_ENRICHMENT_RATE_LIMIT = 5  # одновременных запросов

# Экспорт
EXPORT_FORMATS = ['csv', 'json', 'vcard']
```

**Использование:**
```python
from app.config.constants import UNKNOWN_CONTACT_NAME, CONTACT_MERGE_TIMEOUT_SECONDS

# Вместо:
name = data.get('name') or "Неизвестно"

# Используем:
name = data.get('name') or UNKNOWN_CONTACT_NAME

# Вместо:
if now - last_contact_time < 300:

# Используем:
if now - last_contact_time < CONTACT_MERGE_TIMEOUT_SECONDS:
```

**Приоритет:** 🟢 Средний
**Сложность:** Низкая
**Время:** 1-2 часа

---

### 2.4 Чрезмерно длинные функции

**Файл:** `app/bot/handlers.py`

**Проблема 1:** `handle_voice()` - 146 строк (175-320)
```python
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 146 строк кода:
    # - Скачивание голосового файла
    # - Извлечение данных через Gemini
    # - Создание/обновление контакта
    # - Создание напоминаний
    # - Поиск совпадений
    # - Форматирование ответа
```

**Проблема 2:** `handle_text_message()` - 182 строки (558-739)

**Влияние:**
- Cyclomatic Complexity >8 (должно быть <5)
- Тяжело понять, что делает функция
- Невозможно тестировать изолированно
- Смешано несколько ответственностей

**Решение:**
```python
# app/bot/handlers/contact_handlers.py

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений - координатор"""
    session = AsyncSessionLocal()
    try:
        # 1. Загрузить и обработать голосовое сообщение
        voice_data = await _process_voice_file(update, context)

        # 2. Извлечь данные контакта
        contact_data = await _extract_contact_data(voice_data)

        # 3. Создать/обновить контакт
        db_user = await _get_or_create_user(session, update.effective_user.id)
        contact = await _handle_contact_merge(
            session,
            db_user,
            contact_data,
            context
        )

        # 4. Обработать напоминания
        await _create_reminders(session, contact, contact_data)

        # 5. Найти совпадения
        matches = await _find_and_format_matches(session, contact, db_user)

        # 6. Отправить ответ
        await _send_contact_response(update, contact, matches)

    finally:
        await session.close()

# Вспомогательные функции
async def _process_voice_file(update, context) -> dict:
    """Скачивает и конвертирует голосовое сообщение"""
    # ~20 строк

async def _extract_contact_data(voice_data: dict) -> dict:
    """Извлекает данные контакта через Gemini"""
    # ~30 строк

async def _handle_contact_merge(session, db_user, contact_data, context) -> Contact:
    """Создаёт или объединяет контакт"""
    # ~40 строк

async def _create_reminders(session, contact, contact_data):
    """Создаёт напоминания для контакта"""
    # ~20 строк

async def _find_and_format_matches(session, contact, db_user) -> str:
    """Находит совпадения и форматирует результат"""
    # ~25 строк

async def _send_contact_response(update, contact, matches):
    """Отправляет ответ пользователю"""
    # ~10 строк
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 4-6 часов

---

### 2.5 Закомментированный код

**Проблема:** Dead code оставлен в production

**Примеры:**
```python
# app/bot/handlers.py:382
# context.user_data.pop("last_voice_id", None) # Keep open for chaining?

# app/services/sheets_service.py:141-142
# ws.update(f"A{row_idx+1}:M{row_idx+1}", [row_data])  # COMMENTED OUT!
# This is slow in loop.
```

**Влияние:**
- Путаница для будущих разработчиков
- Неясно, нужен ли этот код или нет

**Решение:**
- Удалить весь закомментированный код
- Использовать Git историю для восстановления при необходимости

**Приоритет:** 🟢 Средний
**Сложность:** Низкая
**Время:** 30 минут

---

### 2.6 Плохие имена переменных

**Проблема:** Однобуквенные переменные по всему коду

**Примеры:**
```python
# app/services/match_service.py:48-71
for p in previous:  # Что такое 'p'?
    p_str = f"{p.get('role', 'Empl')} @ {p.get('company', 'Unknown')}"

for u in universities:  # Что такое 'u'?
    u_str = u.get("name", "")

for c in courses:  # Что такое 'c'?
    course_list = [c.get("name", "") for c in courses if c.get("name")]

# app/bot/handlers.py:412-416
for i, c in enumerate(contacts, 1):  # Что такое 'c'?
    text += f"{i}. {c.name}"
```

**Решение:**
```python
# Описательные имена
for position in previous_positions:
    position_str = f"{position.get('role', 'Employee')} @ {position.get('company', 'Unknown')}"

for university in universities:
    university_name = university.get("name", "")

for course in courses:
    course_list = [course.get("name", "") for course in courses if course.get("name")]

for index, contact in enumerate(contacts, 1):
    text += f"{index}. {contact.name}"
```

**Приоритет:** 🟢 Средний
**Сложность:** Низкая
**Время:** 2-3 часа

---

### 2.7 Отсутствует контекст ошибок

**Проблема:** Широкий catch без stack trace

**Примеры:**
```python
# app/services/notion_service.py:53-55
except Exception as e:
    logger.error(f"Failed to sync contact {contact.name}: {e}")
    stats["failed"] += 1
```

**Влияние:**
- Теряется stack trace
- Сложно отлаживать ошибки

**Решение:**
```python
# Правильный способ
except Exception as e:
    logger.exception(f"Failed to sync contact {contact.name}")  # Автоматически логирует stack trace
    stats["failed"] += 1

# Или более явно
except Exception:
    logger.error(
        f"Failed to sync contact {contact.name}",
        exc_info=True  # Включает stack trace
    )
    stats["failed"] += 1
```

**Приоритет:** 🟡 Высокий
**Сложность:** Низкая
**Время:** 1 час

---

### 2.8 Несогласованные паттерны обработки ошибок

**Проблема:** Разные сервисы используют разные стили отчётов об ошибках

**Примеры:**
```python
# NotionService - возвращает словарь с "error"
return {"error": str(e)}

# SheetsService - возвращает словарь или бросает исключение
return {"error": str(e)}
# или
raise Exception("Failed to authenticate")

# OSINTService - возвращает словарь со "status"
return {"status": "error", "message": str(e)}
# или
return {"status": "cached", "data": cached}

# ContactService - возвращает None или бросает исключение
return None
# или
raise ValueError("Invalid contact data")
```

**Влияние:**
- Код handlers должен проверять разные форматы ответов
- Несогласованность затрудняет обработку ошибок

**Решение:**
```python
# app/core/result.py
from typing import Generic, TypeVar, Union
from dataclasses import dataclass

T = TypeVar('T')
E = TypeVar('E')

@dataclass
class Success(Generic[T]):
    value: T

    def is_success(self) -> bool:
        return True

    def is_error(self) -> bool:
        return False

@dataclass
class Error(Generic[E]):
    error: E
    message: str

    def is_success(self) -> bool:
        return False

    def is_error(self) -> bool:
        return True

Result = Union[Success[T], Error[E]]

# Использование в сервисах:
class ContactService:
    async def create_contact(self, user_id, data) -> Result[Contact, str]:
        try:
            contact = Contact(**data)
            self.session.add(contact)
            await self.session.commit()
            return Success(contact)
        except Exception as e:
            logger.exception("Failed to create contact")
            return Error(error=str(e), message="Failed to create contact")

# В handlers:
result = await contact_service.create_contact(user_id, data)
if result.is_success():
    contact = result.value
    await update.message.reply_text(f"Создан контакт: {contact.name}")
else:
    await update.message.reply_text(f"Ошибка: {result.message}")
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 4-6 часов

---

## 3. Архитектурные проблемы

### 3.1 Отсутствие Dependency Injection

**Проблема:** Сервисы создаются напрямую везде

**Примеры:**
```python
# app/bot/handlers.py
# Строка 215
gemini = GeminiService()  # Прямое создание

# Строка 229
contact_service = ContactService(session)  # Прямое создание
```

**Влияние:**
- Невозможно тестировать (нельзя подменить mock)
- Сервисы создаются многократно без необходимости
- Конфигурация передаётся через несколько слоёв

**Решение:**
```python
# app/core/container.py
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class ServiceContainer:
    """Контейнер для dependency injection"""
    session: AsyncSession

    # Ленивая инициализация сервисов
    _contact_service: ContactService = None
    _osint_service: OSINTService = None
    _gemini_service: GeminiService = None
    _notion_service: NotionService = None
    _sheets_service: SheetsService = None
    _match_service: MatchService = None
    _analytics_service: AnalyticsService = None

    @property
    def contact(self) -> ContactService:
        if self._contact_service is None:
            self._contact_service = ContactService(self.session)
        return self._contact_service

    @property
    def osint(self) -> OSINTService:
        if self._osint_service is None:
            self._osint_service = OSINTService(self.session)
        return self._osint_service

    @property
    def gemini(self) -> GeminiService:
        if self._gemini_service is None:
            self._gemini_service = GeminiService()
        return self._gemini_service

    # ... остальные сервисы

# Использование в handlers:
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        services = ServiceContainer(session)

        # Теперь все сервисы доступны через контейнер
        contact = await services.contact.create_contact(...)
        enrichment = await services.osint.enrich_contact(...)

# Для тестирования:
class MockServiceContainer(ServiceContainer):
    def __init__(self, session, mock_contact_service=None):
        super().__init__(session)
        self._contact_service = mock_contact_service or MockContactService()

# В тестах:
mock_services = MockServiceContainer(session, mock_contact_service)
```

**Приоритет:** 🔴 Критический
**Сложность:** Средняя
**Время:** 6-8 часов

---

### 3.2 Жёсткая связанность между сервисами

**Проблема:** ContactService импортирует и вызывает ReminderService

**Файл:** `app/services/contact_service.py:6, 59-80`

```python
from app.services.reminder_service import ReminderService

# В create_contact:
reminder_service = ReminderService(self.session)
for rem_data in data["reminders"]:
    await reminder_service.create_reminder(...)
```

**Влияние:**
- Риск циклических зависимостей (reminders может нуждаться в contacts)
- Смешивание ответственностей
- Сложно тестировать ContactService независимо

**Решение - Event-Driven Architecture:**
```python
# app/core/events.py
from typing import Callable, Dict, List
from dataclasses import dataclass
from enum import Enum

class EventType(str, Enum):
    CONTACT_CREATED = "contact_created"
    CONTACT_UPDATED = "contact_updated"
    CONTACT_DELETED = "contact_deleted"
    ENRICHMENT_COMPLETED = "enrichment_completed"

@dataclass
class Event:
    type: EventType
    data: dict

class EventBus:
    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event):
        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                await handler(event)

# Глобальный event bus
event_bus = EventBus()

# app/services/contact_service.py
class ContactService:
    async def create_contact(self, user_id, data):
        contact = Contact(...)
        self.session.add(contact)
        await self.session.commit()

        # Публикуем событие вместо прямого вызова
        await event_bus.publish(Event(
            type=EventType.CONTACT_CREATED,
            data={
                "contact_id": contact.id,
                "reminders": data.get("reminders", [])
            }
        ))

        return contact

# app/services/reminder_service.py
class ReminderService:
    def __init__(self, session):
        self.session = session
        # Подписываемся на события
        event_bus.subscribe(EventType.CONTACT_CREATED, self.on_contact_created)

    async def on_contact_created(self, event: Event):
        """Обработчик события создания контакта"""
        contact_id = event.data["contact_id"]
        reminders = event.data.get("reminders", [])

        for rem_data in reminders:
            await self.create_reminder(contact_id, rem_data)
```

**Приоритет:** 🟡 Высокий
**Сложность:** Высокая
**Время:** 8-12 часов

---

### 3.3 Бизнес-логика в handlers

**Проблема:** Логика слияния контактов реализована в handlers, а не в сервисах

**Файл:** `app/bot/handlers.py:232-293`

```python
# В handle_voice handler:
now = time.time()
last_contact_time = context.user_data.get("last_contact_time", 0)
last_contact_id = context.user_data.get("last_contact_id")

if last_contact_id and (now - last_contact_time < 300):
    contact = await contact_service.update_contact(last_contact_id, data)
    # ... больше логики
```

**Влияние:**
- Та же логика дублируется в 3 handlers
- Логика привязана к Telegram UI context
- Сложно переиспользовать или тестировать

**Решение:**
См. раздел 2.2 - Создание `ContactMergeService`

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 3-4 часа

---

### 3.4 Управление сессиями разбросано по кодовой базе

**Проблема:** `AsyncSessionLocal()` создаётся в каждом handler

**Файлы:**
- `app/bot/handlers.py:45, 217, 342, 400, 442` (10+ мест)
- `app/bot/osint_handlers.py:43, 122, 157`

**Влияние:**
- Нет централизованного управления сессиями
- Неясная ответственность за очистку ресурсов
- Сложно реализовать границы транзакций

**Решение:**
```python
# app/core/database.py
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

@asynccontextmanager
async def get_session() -> AsyncSession:
    """Context manager для сессий БД с автоматическим commit/rollback"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Использование в handlers:
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session() as session:
        services = ServiceContainer(session)

        contact = await services.contact.create_contact(...)
        # При успехе - автоматический commit
        # При ошибке - автоматический rollback
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 2-3 часа

---

### 3.5 Ненадёжные scheduler jobs

**Проблема:** Нет логики повтора для проваленных фоновых задач

**Файл:** `app/core/scheduler.py:11-27`

```python
async def auto_enrich_contact_job(contact_id: uuid.UUID):
    try:
        async with AsyncSessionLocal() as session:
            osint_service = OSINTService(session)
            result = await osint_service.enrich_contact(contact_id)
    except Exception as e:
        logger.exception(f"Auto-enrichment failed for {contact_id}: {e}")
        # Нет повтора! Задача просто умирает.
```

**Влияние:**
- Сбой сети = потеря возможности enrichment
- Нет восстановления после временных ошибок

**Решение:**
```python
# app/core/scheduler.py
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

async def auto_enrich_contact_job(contact_id: uuid.UUID, retry_count: int = 0):
    """
    Задача автоматического enrichment с retry логикой

    Args:
        contact_id: ID контакта для enrichment
        retry_count: Количество попыток (для экспоненциальной задержки)
    """
    MAX_RETRIES = 3

    try:
        async with AsyncSessionLocal() as session:
            osint_service = OSINTService(session)
            result = await osint_service.enrich_contact(contact_id)

            if result["status"] == "error" and retry_count < MAX_RETRIES:
                # Перепланировать с экспоненциальной задержкой
                delay_minutes = 2 ** retry_count  # 1, 2, 4 минуты
                retry_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

                scheduler.add_job(
                    auto_enrich_contact_job,
                    trigger=DateTrigger(run_date=retry_time),
                    args=[contact_id, retry_count + 1],
                    id=f"enrich_{contact_id}_retry_{retry_count + 1}",
                    replace_existing=True
                )

                logger.warning(
                    f"Enrichment failed for {contact_id}, "
                    f"retry {retry_count + 1}/{MAX_RETRIES} scheduled in {delay_minutes}m"
                )
            elif result["status"] == "error":
                logger.error(
                    f"Enrichment failed for {contact_id} after {MAX_RETRIES} retries"
                )

    except Exception as e:
        logger.exception(f"Critical error in enrichment job for {contact_id}")

        if retry_count < MAX_RETRIES:
            # Перепланировать даже при критической ошибке
            delay_minutes = 2 ** retry_count
            retry_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

            scheduler.add_job(
                auto_enrich_contact_job,
                trigger=DateTrigger(run_date=retry_time),
                args=[contact_id, retry_count + 1],
                id=f"enrich_{contact_id}_retry_{retry_count + 1}",
                replace_existing=True
            )
```

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 3-4 часа

---

### 3.6 Нет абстракции для внешних API

**Проблема:** Каждый сервис напрямую вызывает внешние API

**Файлы:**
- `app/services/osint_service.py` - Tavily API
- `app/services/notion_service.py` - Notion API
- `app/services/sheets_service.py` - Google Sheets API

**Влияние:**
- Нельзя заменить реализацию (например, использовать другой поисковый провайдер)
- Нет централизованной обработки ошибок
- Изменения API ломают несколько сервисов

**Решение:**
```python
# app/core/providers.py
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class ProfileSearchResult:
    name: str
    company: Optional[str]
    role: Optional[str]
    linkedin_url: Optional[str]
    summary: str
    source: str

class EnrichmentProvider(ABC):
    """Абстрактный интерфейс для провайдера enrichment"""

    @abstractmethod
    async def search_profiles(
        self,
        name: str,
        company: Optional[str] = None,
        role: Optional[str] = None
    ) -> List[ProfileSearchResult]:
        """Поиск профилей по имени, компании и роли"""
        pass

    @abstractmethod
    async def search_content(
        self,
        query: str
    ) -> List[ProfileSearchResult]:
        """Поиск контента по запросу"""
        pass

# app/services/providers/tavily_provider.py
class TavilyEnrichmentProvider(EnrichmentProvider):
    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key=api_key)

    async def search_profiles(
        self,
        name: str,
        company: Optional[str] = None,
        role: Optional[str] = None
    ) -> List[ProfileSearchResult]:
        """Реализация Tavily"""
        query = self._build_linkedin_query(name, company, role)
        results = await self.client.search(query)

        return [
            ProfileSearchResult(
                name=name,
                company=company,
                role=role,
                linkedin_url=result.get('url'),
                summary=result.get('content'),
                source='tavily'
            )
            for result in results
        ]

    async def search_content(self, query: str) -> List[ProfileSearchResult]:
        """Поиск контента через Tavily"""
        results = await self.client.search(query)
        return [self._parse_result(r) for r in results]

# app/services/providers/mock_provider.py (для тестирования)
class MockEnrichmentProvider(EnrichmentProvider):
    async def search_profiles(self, name, company, role) -> List[ProfileSearchResult]:
        return [
            ProfileSearchResult(
                name=name,
                company=company or "Mock Company",
                role=role or "Mock Role",
                linkedin_url="https://linkedin.com/in/mock",
                summary="Mock profile data",
                source='mock'
            )
        ]

    async def search_content(self, query) -> List[ProfileSearchResult]:
        return []

# app/services/osint_service.py
class OSINTService:
    def __init__(
        self,
        session: AsyncSession,
        enrichment_provider: EnrichmentProvider = None
    ):
        self.session = session
        # DI: провайдер передаётся извне
        self.enrichment_provider = enrichment_provider or TavilyEnrichmentProvider(
            api_key=settings.TAVILY_API_KEY
        )

    async def enrich_contact(self, contact_id: uuid.UUID):
        """Теперь не зависит от конкретного провайдера"""
        contact = await self._get_contact(contact_id)

        # Используем абстрактный интерфейс
        results = await self.enrichment_provider.search_profiles(
            name=contact.name,
            company=contact.company,
            role=contact.role
        )

        # Обработка результатов...

# В тестах:
def test_osint_service():
    mock_provider = MockEnrichmentProvider()
    osint_service = OSINTService(session, enrichment_provider=mock_provider)
    # Тестирование без реальных API вызовов
```

**Приоритет:** 🟢 Средний
**Сложность:** Высокая
**Время:** 8-10 часов

---

### 3.7 Нет Data Transfer Objects (DTO)

**Проблема:** Сервисы передают raw ORM модели напрямую

**Влияние:**
- Изменения схемы API/БД ломают всё
- Сложно отследить, какие данные используются
- Утечка деталей реализации базы данных

**Решение:**
```python
# app/schemas/contact_schemas.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import uuid

class ContactBase(BaseModel):
    """Базовая схема контакта"""
    name: str = Field(..., min_length=1, max_length=200)
    company: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram_username: Optional[str] = None
    linkedin_url: Optional[str] = None

class ContactCreate(ContactBase):
    """Схема для создания контакта"""
    tags: List[str] = []
    notes: Optional[str] = None

    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Invalid email format')
        return v

class ContactUpdate(BaseModel):
    """Схема для обновления контакта (все поля optional)"""
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram_username: Optional[str] = None
    linkedin_url: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None

class ContactDTO(ContactBase):
    """DTO для возврата контакта"""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    last_interaction_date: Optional[datetime]
    status: str
    osint_enriched: bool
    tags: List[str]
    notes: Optional[str]

    class Config:
        from_attributes = True  # Для Pydantic v2 (orm_mode в v1)

# app/services/contact_service.py
class ContactService:
    async def create_contact(
        self,
        user_id: uuid.UUID,
        data: ContactCreate  # Принимаем DTO
    ) -> ContactDTO:  # Возвращаем DTO
        """Создаёт контакт"""
        contact = Contact(
            user_id=user_id,
            **data.model_dump(exclude_unset=True)
        )
        self.session.add(contact)
        await self.session.commit()
        await self.session.refresh(contact)

        # Конвертируем ORM в DTO
        return ContactDTO.model_validate(contact)

    async def get_contact(self, contact_id: uuid.UUID) -> Optional[ContactDTO]:
        """Получает контакт по ID"""
        stmt = select(Contact).where(Contact.id == contact_id)
        result = await self.session.execute(stmt)
        contact = result.scalar_one_or_none()

        if contact is None:
            return None

        return ContactDTO.model_validate(contact)

    async def update_contact(
        self,
        contact_id: uuid.UUID,
        data: ContactUpdate
    ) -> ContactDTO:
        """Обновляет контакт"""
        contact = await self._get_contact_model(contact_id)

        # Обновляем только переданные поля
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(contact, field, value)

        await self.session.commit()
        await self.session.refresh(contact)

        return ContactDTO.model_validate(contact)

# Использование в handlers:
from app.schemas.contact_schemas import ContactCreate, ContactDTO

async def handle_voice(update, context):
    # ...
    contact_data = ContactCreate(
        name=extracted_data['name'],
        company=extracted_data.get('company'),
        role=extracted_data.get('role'),
        phone=extracted_data.get('phone'),
        tags=extracted_data.get('tags', [])
    )

    # Валидация происходит автоматически
    contact: ContactDTO = await services.contact.create_contact(db_user.id, contact_data)

    # Теперь работаем с DTO, а не ORM моделью
    await update.message.reply_text(f"Создан контакт: {contact.name}")
```

**Преимущества:**
- ✅ Автоматическая валидация данных через Pydantic
- ✅ Чёткое разделение между слоями
- ✅ Лёгкая сериализация в JSON
- ✅ Автодокументация через типы
- ✅ Изменения ORM не ломают API

**Приоритет:** 🟡 Высокий
**Сложность:** Средняя
**Время:** 6-8 часов

---

### 3.8 Глобальный экземпляр Scheduler

**Проблема:** Scheduler создан как глобальная переменная на уровне модуля

**Файл:** `app/core/scheduler.py:59`

```python
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
```

**Влияние:**
- Невозможно создать несколько экземпляров бота
- Тестирование требует мокирования глобального состояния
- Неявная зависимость

**Решение:**
```python
# app/core/scheduler.py
class SchedulerManager:
    """Singleton manager для scheduler"""
    _instance = None
    _scheduler = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, jobstores: dict = None):
        """Инициализирует scheduler (вызывается при старте приложения)"""
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores or {},
                timezone="UTC"
            )
        return self._scheduler

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """Получить scheduler"""
        if self._scheduler is None:
            raise RuntimeError("Scheduler not initialized. Call initialize() first.")
        return self._scheduler

    def start(self):
        """Запустить scheduler"""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self):
        """Остановить scheduler"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()

# Глобальный менеджер
scheduler_manager = SchedulerManager()

# app/main.py
async def main():
    # Инициализация при старте
    scheduler = scheduler_manager.initialize(jobstores={
        'default': MemoryJobStore()
    })
    scheduler_manager.start()

    # Запуск бота
    application = Application.builder().token(settings.BOT_TOKEN).build()
    # ...

# Использование в сервисах:
from app.core.scheduler import scheduler_manager

async def schedule_enrichment(contact_id: uuid.UUID):
    scheduler = scheduler_manager.scheduler
    scheduler.add_job(...)
```

**Приоритет:** 🟢 Средний
**Сложность:** Низкая
**Время:** 2 часа

---

### 3.9 State хранится в Telegram context

**Проблема:** Состояние приложения хранится в эфемерном user_data

**Файл:** `app/bot/handlers.py:818`

```python
context.user_data["current_event"] = query
```

**Влияние:**
- Не сохраняется при перезапуске
- Недоступно в фоновых задачах
- Расшарено между всеми handlers

**Решение:**
```python
# app/models/user_session.py
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid

class UserSession(Base):
    """Сессия пользователя для хранения состояния"""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)

    # Состояние
    current_event = Column(String(200), nullable=True)
    last_contact_id = Column(UUID(as_uuid=True), nullable=True)
    last_contact_time = Column(DateTime(timezone=True), nullable=True)

    # Настройки
    notification_enabled = Column(Boolean, default=True)
    auto_enrichment_enabled = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# app/services/session_service.py
class SessionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_session(self, user_id: uuid.UUID) -> UserSession:
        """Получить или создать сессию пользователя"""
        stmt = select(UserSession).where(UserSession.user_id == user_id)
        result = await self.session.execute(stmt)
        user_session = result.scalar_one_or_none()

        if user_session is None:
            user_session = UserSession(user_id=user_id)
            self.session.add(user_session)
            await self.session.commit()

        return user_session

    async def update_session(
        self,
        user_id: uuid.UUID,
        **kwargs
    ) -> UserSession:
        """Обновить сессию пользователя"""
        user_session = await self.get_or_create_session(user_id)

        for key, value in kwargs.items():
            if hasattr(user_session, key):
                setattr(user_session, key, value)

        user_session.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(user_session)

        return user_session

# Использование в handlers:
async def handle_voice(update, context):
    async with get_session() as db_session:
        services = ServiceContainer(db_session)
        session_service = SessionService(db_session)

        # Получить состояние из БД
        user_session = await session_service.get_or_create_session(db_user.id)

        # Проверка на слияние с последним контактом
        if user_session.last_contact_id and user_session.last_contact_time:
            now = datetime.now(timezone.utc)
            time_diff = (now - user_session.last_contact_time).total_seconds()

            if time_diff < CONTACT_MERGE_TIMEOUT_SECONDS:
                # Слияние
                contact = await services.contact.update_contact(...)

        # Обновить состояние
        await session_service.update_session(
            db_user.id,
            last_contact_id=contact.id,
            last_contact_time=datetime.now(timezone.utc)
        )
```

**Приоритет:** 🟢 Средний
**Сложность:** Средняя
**Время:** 4-5 часов

---

## 4. Оптимизация базы данных

### 4.1 Отсутствуют составные индексы

**Текущее состояние:**
```python
# contact.py - Только индекс по user_id
id = Column(..., primary_key=True)
user_id = Column(..., ForeignKey(...), index=True)  # Только одноколоночный индекс
```

**Нужные индексы:**

```python
# app/models/contact.py
from sqlalchemy import Index

class Contact(Base):
    __tablename__ = "contacts"

    # ... existing fields ...

    __table_args__ = (
        # Для get_inactive_contacts (analytics_service.py:86)
        Index('ix_contact_user_status', 'user_id', 'status'),

        # Для get_recent_contacts (contact_service.py:103)
        Index('ix_contact_user_created_desc', 'user_id', 'created_at'),

        # Для find_contacts (contact_service.py:117)
        Index('ix_contact_user_name', 'user_id', 'name'),

        # Для get_contacts_by_last_interaction
        Index('ix_contact_user_last_interaction', 'user_id', 'last_interaction_date'),

        # Для поиска по osint статусу
        Index('ix_contact_user_osint', 'user_id', 'osint_enriched'),
    )
```

**Alembic миграция:**
```python
# alembic/versions/xxx_add_composite_indexes.py
"""Add composite indexes for contact queries

Revision ID: xxx
Revises: yyy
Create Date: 2026-01-26

"""
from alembic import op

def upgrade():
    # Составные индексы для оптимизации запросов
    op.create_index(
        'ix_contact_user_status',
        'contacts',
        ['user_id', 'status']
    )
    op.create_index(
        'ix_contact_user_created_desc',
        'contacts',
        ['user_id', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_contact_user_name',
        'contacts',
        ['user_id', 'name']
    )
    op.create_index(
        'ix_contact_user_last_interaction',
        'contacts',
        ['user_id', 'last_interaction_date'],
        postgresql_using='btree'
    )
    op.create_index(
        'ix_contact_user_osint',
        'contacts',
        ['user_id', 'osint_enriched']
    )

def downgrade():
    op.drop_index('ix_contact_user_osint', table_name='contacts')
    op.drop_index('ix_contact_user_last_interaction', table_name='contacts')
    op.drop_index('ix_contact_user_name', table_name='contacts')
    op.drop_index('ix_contact_user_created_desc', table_name='contacts')
    op.drop_index('ix_contact_user_status', table_name='contacts')
```

**Приоритет:** 🔴 Критический
**Сложность:** Низкая
**Время:** 1 час

---

## 5. Таблица критических проблем

| Приоритет | Категория | Проблема | Файл | Строки | Влияние | Время |
|-----------|-----------|----------|------|--------|---------|-------|
| 🔴 | Performance | N+1 семантический поиск | match_service.py | 151-164 | O(n) память, падение при 1000+ | 4-6ч |
| 🔴 | Architecture | God Object handlers | handlers.py | 1-820 | 819 строк, невозможность поддержки | 6-8ч |
| 🔴 | Architecture | Нет DI | Все сервисы | - | Невозможность тестирования | 6-8ч |
| 🔴 | Performance | Отсутствуют индексы | contact.py | 43-46 | Медленные запросы | 1ч |
| 🔴 | Bug | Sheets не обновляет | sheets_service.py | 136-146 | Утверждает успех, но ничего не делает | 1-2ч |
| 🟡 | Performance | Последовательные API вызовы | osint_service.py | 196-219 | Замедление в 2x | 1-2ч |
| 🟡 | Performance | Искусственные задержки | osint_service.py | 346 | 5x замедление batch enrichment | 2-3ч |
| 🟡 | Performance | Notion загружает всё | notion_service.py | 59-103 | Rate limit при 500+ контактов | 3-4ч |
| 🟡 | Performance | Утечка памяти в rate limiter | rate_limiter.py | 42-53 | Рост памяти со временем | 2ч |
| 🟡 | Clean Code | Дублирование merge логики | handlers.py | 3 места | DRY нарушение | 3-4ч |
| 🟡 | Clean Code | Длинные функции | handlers.py | 175-320, 558-739 | Высокая сложность | 4-6ч |
| 🟡 | Clean Code | Несогласованные ошибки | Все сервисы | - | Сложная обработка | 4-6ч |
| 🟡 | Architecture | Жёсткая связанность | contact_service.py | 59-80 | Циклические зависимости | 8-12ч |
| 🟡 | Architecture | Бизнес-логика в handlers | handlers.py | 232-293 | Нельзя переиспользовать | 3-4ч |
| 🟡 | Architecture | Управление сессиями | Все handlers | Много мест | Нет границ транзакций | 2-3ч |
| 🟡 | Architecture | Ненадёжные jobs | scheduler.py | 11-27 | Потеря данных при сбоях | 3-4ч |
| 🟡 | Architecture | Нет DTO | Все сервисы | - | Утечка деталей реализации | 6-8ч |
| 🟢 | Clean Code | Хардкод строк | 6+ файлов | Много мест | Сложность изменений | 1-2ч |
| 🟢 | Clean Code | Закомментированный код | handlers.py, sheets_service.py | Несколько | Путаница | 30мин |
| 🟢 | Clean Code | Плохие имена | match_service.py | 48-71 | Читаемость | 2-3ч |
| 🟢 | Clean Code | Отсутствует контекст ошибок | notion_service.py | 53-55 | Сложность отладки | 1ч |
| 🟢 | Architecture | Нет абстракции API | Несколько сервисов | - | Нельзя заменить провайдера | 8-10ч |
| 🟢 | Architecture | Глобальный scheduler | scheduler.py | 59 | Проблемы с тестированием | 2ч |
| 🟢 | Architecture | State в Telegram context | handlers.py | 818 | Не сохраняется при рестарте | 4-5ч |

**Всего времени на исправление:** ~95-125 часов (12-16 рабочих дней)

---

## 6. Дорожная карта исправлений

### Фаза 1: Быстрые победы (1-2 недели) ⚡

**Цель:** Исправить критические баги и улучшить производительность

**Задачи:**

1. **Добавить индексы БД** [1ч] 🔴
   - Создать Alembic миграцию
   - Добавить 5 составных индексов
   - Тестировать производительность запросов

2. **Параллелизовать API вызовы Tavily** [1-2ч] 🟡
   - Использовать `asyncio.gather()` в `osint_service.py:215-219`
   - Добавить обработку исключений
   - Замерить улучшение производительности

3. **Исправить Sheets sync** [1-2ч] 🔴
   - Реализовать batch updates
   - Удалить закомментированный код
   - Добавить тесты

4. **Извлечь константы** [1-2ч] 🟢
   - Создать `config/constants.py`
   - Заменить hardcoded значения
   - Обновить все импорты

5. **Удалить закомментированный код** [30мин] 🟢
   - Пройтись по всем файлам
   - Удалить мёртвый код

**Результат:**
- ✅ Критические баги исправлены
- ✅ 50% улучшение производительности запросов
- ✅ 2x ускорение enrichment
- ✅ Улучшенная читаемость кода

---

### Фаза 2: Рефакторинг структуры (2-4 недели) 🏗️

**Цель:** Улучшить архитектуру и поддерживаемость

**Задачи:**

1. **Разделить handlers.py** [6-8ч] 🔴
   - Создать структуру `handlers/`
   - Разделить на 6 модулей
   - Обновить импорты в main.py
   - Проверить, что всё работает

2. **Создать ContactMergeService** [3-4ч] 🟡
   - Извлечь логику слияния из handlers
   - Удалить дублирование
   - Добавить юнит-тесты

3. **Добавить пагинацию к семантическому поиску** [4-6ч] 🔴
   - Лимитировать запросы к БД
   - Добавить фильтрацию по дате взаимодействия
   - Оптимизировать форматирование контекста

4. **Рефакторинг длинных функций** [4-6ч] 🟡
   - Разбить `handle_voice()` на 6 функций
   - Разбить `handle_text_message()` на функции
   - Добавить документацию

5. **Исправить rate limiter утечку памяти** [2ч] 🟡
   - Добавить периодическую очистку
   - Тестировать на длительной работе

6. **Улучшить обработку ошибок** [1ч] 🟢
   - Заменить `logger.error()` на `logger.exception()`
   - Добавить stack traces

7. **Улучшить имена переменных** [2-3ч] 🟢
   - Заменить однобуквенные имена
   - Добавить type hints где отсутствуют

**Результат:**
- ✅ Модульная структура кода
- ✅ Нет дублирования
- ✅ Поддержка 1000+ контактов
- ✅ Лучшая читаемость и поддерживаемость

---

### Фаза 3: Архитектурные улучшения (4-8 недель) 🎯

**Цель:** Создать надёжную, тестируемую архитектуру

**Задачи:**

1. **Реализовать Dependency Injection** [6-8ч] 🔴
   - Создать `ServiceContainer`
   - Обновить все handlers
   - Добавить поддержку тестирования

2. **Создать единый формат ошибок** [4-6ч] 🟡
   - Реализовать `Result[T, E]` тип
   - Обновить все сервисы
   - Обновить handlers

3. **Централизовать управление сессиями** [2-3ч] 🟡
   - Создать `get_session()` context manager
   - Обновить все handlers
   - Добавить автоматический commit/rollback

4. **Добавить retry логику в scheduler** [3-4ч] 🟡
   - Реализовать экспоненциальный backoff
   - Добавить логирование
   - Тестировать восстановление после сбоев

5. **Создать Data Transfer Objects** [6-8ч] 🟡
   - Определить Pydantic схемы
   - Обновить все сервисы
   - Добавить валидацию

6. **Улучшить Notion sync** [3-4ч] 🟡
   - Хранить метаданные синхронизации
   - Использовать фильтры Notion API
   - Тестировать с большими датасетами

7. **Оптимизировать batch enrichment** [2-3ч] 🟡
   - Заменить sleep на proper rate limiting
   - Использовать semaphore
   - Тестировать производительность

**Результат:**
- ✅ Тестируемая кодовая база
- ✅ Согласованная обработка ошибок
- ✅ Надёжные фоновые задачи
- ✅ Валидация данных
- ✅ Готовность к масштабированию

---

### Фаза 4: Продвинутые возможности (8+ недель) 🚀

**Цель:** Оптимизировать для масштаба и гибкости

**Задачи:**

1. **Event-Driven Architecture** [8-12ч] 🟡
   - Создать EventBus
   - Отвязать ContactService от ReminderService
   - Реализовать подписчиков событий
   - Добавить async event handlers

2. **Абстракция провайдеров** [8-10ч] 🟢
   - Создать интерфейсы провайдеров
   - Реализовать для Tavily, Notion, Sheets
   - Добавить mock провайдеры для тестов
   - Поддержка плагинов

3. **Векторные эмбеддинги для семантического поиска** [12-16ч]
   - Интегрировать pgvector
   - Создать эмбеддинги для контактов
   - Реализовать векторный поиск
   - Миграция существующих данных

4. **Хранение состояния в БД** [4-5ч] 🟢
   - Создать таблицу UserSession
   - Миграция с Telegram context
   - Обновить handlers

5. **Менеджер Scheduler** [2ч] 🟢
   - Создать SchedulerManager singleton
   - Proper initialization
   - Graceful shutdown

6. **Распределённый rate limiting с Redis** [4-6ч]
   - Настроить Redis
   - Реализовать RedisRateLimiter
   - Миграция с in-memory

7. **Comprehensive тестирование** [20-30ч]
   - Юнит-тесты для всех сервисов
   - Интеграционные тесты
   - E2E тесты для handlers
   - Coverage >80%

**Результат:**
- ✅ Отвязанная архитектура
- ✅ Плагинная система
- ✅ Масштабируемый поиск
- ✅ Персистентное состояние
- ✅ Распределённая система
- ✅ Высокое покрытие тестами

---

## Приоритизация по Quick Wins

### 🔥 Сделать СЕЙЧАС (< 5 часов работы, высокое влияние)

1. **Добавить индексы БД** - 1ч ⚡
2. **Исправить Sheets sync** - 1-2ч ⚡
3. **Параллелизовать Tavily вызовы** - 1-2ч ⚡
4. **Извлечь константы** - 1-2ч ⚡

**Итого:** ~5-7 часов, **огромное влияние** на производительность и корректность

---

### 📊 Сделать на этой неделе (< 2 недели)

5. **Разделить handlers.py** - 6-8ч
6. **ContactMergeService** - 3-4ч
7. **Пагинация семантического поиска** - 4-6ч
8. **Рефакторинг длинных функций** - 4-6ч

**Итого:** ~17-24 часов дополнительно

---

### 🎯 Следующий спринт (2-4 недели)

9. **Dependency Injection** - 6-8ч
10. **Единый формат ошибок** - 4-6ч
11. **DTO с Pydantic** - 6-8ч
12. **Retry логика scheduler** - 3-4ч

---

## Метрики успеха

### Performance
- [ ] Запросы к БД < 100ms (сейчас: ~500ms+)
- [ ] Enrichment < 15 секунд (сейчас: ~30-40 секунд)
- [ ] Семантический поиск работает с 5000+ контактов

### Code Quality
- [ ] Нет файлов > 300 строк
- [ ] Нет функций > 50 строк
- [ ] Нет дублирования кода
- [ ] Test coverage > 80%

### Architecture
- [ ] Все сервисы с DI
- [ ] Согласованная обработка ошибок
- [ ] Нет циклических зависимостей
- [ ] Слабая связанность (loose coupling)

### Reliability
- [ ] Нет потерь данных при сбоях
- [ ] Graceful degradation при недоступности API
- [ ] Автоматическое восстановление задач

---

## Инструменты для мониторинга прогресса

```bash
# Code metrics
poetry run radon cc app/ -a -nb  # Cyclomatic complexity
poetry run radon mi app/ -nb     # Maintainability index

# Test coverage
poetry run pytest --cov=app --cov-report=html
open htmlcov/index.html

# Performance profiling
poetry run py-spy record -o profile.svg -- python app/main.py

# Memory profiling
poetry run memray run app/main.py
poetry run memray flamegraph output.bin
```

---

## Заключение

Этот план рефакторинга превратит NetworkBot из MVP в production-ready приложение с:

✅ **Высокой производительностью** - оптимизированные запросы и параллельные API вызовы
✅ **Чистым кодом** - модульная структура, DRY принцип, хорошие практики
✅ **Надёжной архитектурой** - DI, event-driven, слабая связанность
✅ **Тестируемостью** - покрытие тестами >80%
✅ **Масштабируемостью** - поддержка тысяч контактов и пользователей

**Рекомендуемый подход:** Начать с Фазы 1 и 2 (quick wins + структурный рефакторинг), затем постепенно внедрять Фазу 3 и 4 по мере роста продукта.

---

**Автор плана:** Claude (Anthropic)
**Дата:** 2026-01-26
**Версия:** 1.0
