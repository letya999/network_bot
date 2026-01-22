# NetworkingCRM — OpenSpec Specification

## Project Context

### Purpose

Персональный AI-ассистент для нетворкинга в формате Telegram-бота. Позволяет быстро фиксировать контакты голосом, обогащать их данными, генерировать персонализированные визитки и follow-up сообщения, анализировать сеть связей.

**Проблема:** После мероприятий/встреч контакты теряются, забываются договорённости, нет системного подхода к нетворкингу.

**Решение:** Голосовая заметка + пересланный контакт → структурированная карточка в CRM с напоминаниями и AI-помощником.

### Tech Stack

- **Language:** Python 3.11+
- **Bot Framework:** python-telegram-bot 21.x (async)
- **Backend:** FastAPI
- **AI:** Google Gemini API (транскрипция + LLM)
- **Database:** PostgreSQL + Redis
- **ORM:** SQLAlchemy 2.x (async)
- **Migrations:** Alembic
- **Task Queue:** Celery + Redis (для напоминаний, OSINT)
- **Exports:** notion-client, gspread
- **OSINT:** Google Custom Search API, опционально Proxycurl
- **Deploy:** Docker, Railway/Render или VPS

### Architecture Patterns

- Сервисный слой: handlers → services → repositories
- Dependency Injection через FastAPI
- Async everywhere
- Event-driven для напоминаний и матчинга

### Project Conventions

- Форматирование: ruff, black
- Type hints обязательны
- Docstrings для публичных методов
- Тесты: pytest-asyncio
- Env variables через pydantic-settings

---

## Domain Context

### Основные сущности

**User** — владелец бота (пока single-user, но с возможностью multi-tenant)
- profile: имя, контакты, ссылки, elevator pitches
- settings: timezone, default export, reminder preferences

**Contact** — карточка контакта в CRM
- basic_info: name, company, role, phone, telegram, email, linkedin
- context: event, date, introduced_by, raw_transcript
- interests: what_looking_for, can_help_with, topics
- status: active, sleeping, archived
- interactions: список взаимодействий

**Interaction** — история касаний с контактом
- type: met, message_sent, call, meeting
- date, notes, outcome

**Reminder** — напоминание о follow-up
- contact_id, trigger_date, message_template
- status: pending, sent, snoozed, completed

**Event** — мероприятие/контекст знакомства
- name, date, location
- используется для группировки контактов

### Ключевые процессы

1. **Capture:** Голосовое/контакт → извлечение → карточка
2. **Enrich:** OSINT обогащение публичными данными  
3. **Match:** Поиск синергий между контактами и целями пользователя
4. **Follow-up:** Напоминания + генерация сообщений
5. **Share:** Генерация персонализированных визиток
6. **Analyze:** Статистика и инсайты по нетворкингу

---

## Specifications by Priority

---

# PHASE 0: INFRASTRUCTURE (Must Have First)

## Requirement: Project Structure

Система SHALL иметь следующую структуру проекта:

```
networking-crm/
├── bot/
│   ├── __init__.py
│   ├── main.py              # entry point
│   ├── handlers/            # telegram handlers
│   ├── keyboards/           # inline keyboards
│   └── middlewares/         # auth, logging
├── services/
│   ├── gemini.py            # AI service
│   ├── contact.py           # contact CRUD + search
│   ├── profile.py           # user profile
│   ├── reminder.py          # follow-up system
│   ├── export.py            # notion, sheets, csv
│   ├── osint.py             # enrichment
│   ├── match.py             # synergy detection
│   ├── analytics.py         # stats
│   └── card_generator.py    # визитки
├── models/
│   ├── user.py
│   ├── contact.py
│   ├── interaction.py
│   └── reminder.py
├── repositories/
│   └── ...                  # data access layer
├── core/
│   ├── config.py            # settings
│   ├── database.py          # db connection
│   └── redis.py             # cache
├── prompts/
│   └── ...                  # AI prompts (отдельные файлы)
├── tests/
├── alembic/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Scenario: Clean Architecture
- **GIVEN** разработчик хочет добавить новую функцию
- **WHEN** он следует структуре проекта
- **THEN** ясно где разместить handler, service, repository

---

## Requirement: Configuration Management

Система SHALL загружать конфигурацию из environment variables.

### Required Variables
- `TELEGRAM_BOT_TOKEN` — токен бота
- `GEMINI_API_KEY` — ключ Gemini API
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string

### Optional Variables
- `NOTION_TOKEN` — для экспорта в Notion
- `NOTION_DATABASE_ID` — ID базы Notion
- `GOOGLE_SHEETS_CREDENTIALS` — path to service account JSON
- `GOOGLE_SHEETS_ID` — ID таблицы
- `GOOGLE_CSE_API_KEY` — для OSINT поиска
- `GOOGLE_CSE_CX` — Custom Search Engine ID
- `PROXYCURL_API_KEY` — для LinkedIn (опционально)

### Scenario: Missing Required Config
- **GIVEN** отсутствует обязательная переменная
- **WHEN** приложение запускается
- **THEN** оно падает с понятной ошибкой

---

## Requirement: Database Schema

Система SHALL использовать PostgreSQL со следующей схемой.

### Tables

**users**
- id: UUID PK
- telegram_id: BIGINT UNIQUE
- name: VARCHAR(255)
- profile_data: JSONB (контакты, питчи, ссылки)
- settings: JSONB
- created_at, updated_at: TIMESTAMP

**contacts**
- id: UUID PK
- user_id: UUID FK → users
- name: VARCHAR(255) NOT NULL
- company: VARCHAR(255)
- role: VARCHAR(255)
- phone: VARCHAR(50)
- telegram_username: VARCHAR(100)
- email: VARCHAR(255)
- linkedin_url: VARCHAR(500)
- event_name: VARCHAR(255)
- event_date: DATE
- introduced_by_id: UUID FK → contacts (nullable)
- what_looking_for: TEXT
- can_help_with: TEXT
- topics: TEXT[]
- agreements: TEXT[]
- follow_up_action: TEXT
- raw_transcript: TEXT
- status: ENUM('active', 'sleeping', 'archived')
- osint_data: JSONB
- created_at, updated_at: TIMESTAMP

**interactions**
- id: UUID PK
- contact_id: UUID FK → contacts
- type: ENUM('met', 'message_sent', 'message_received', 'call', 'meeting')
- date: TIMESTAMP
- notes: TEXT
- outcome: TEXT

**reminders**
- id: UUID PK
- user_id: UUID FK → users
- contact_id: UUID FK → contacts
- trigger_at: TIMESTAMP
- message_template: TEXT
- status: ENUM('pending', 'sent', 'snoozed', 'completed', 'cancelled')
- snoozed_until: TIMESTAMP (nullable)
- created_at: TIMESTAMP

**shared_cards**
- id: UUID PK
- user_id: UUID FK → users
- target_contact_id: UUID FK → contacts (nullable)
- card_type: VARCHAR(50) (general, investor, technical, etc.)
- token: VARCHAR(100) UNIQUE
- expires_at: TIMESTAMP
- views_count: INT DEFAULT 0
- created_at: TIMESTAMP

### Indexes
- contacts: (user_id), (user_id, status), GIN(name, company) для поиска
- reminders: (user_id, status, trigger_at)
- shared_cards: (token), (user_id)

---

# PHASE 1: CORE MVP (Must Have)

Минимальная рабочая версия: голосовое → карточка → сохранение.

---

## Requirement: Voice Message Processing

Система SHALL принимать голосовые сообщения и преобразовывать их в структурированные данные контакта.

### Scenario: Basic Voice Transcription
- **GIVEN** пользователь отправляет голосовое сообщение
- **WHEN** бот его получает
- **THEN** голосовое отправляется в Gemini API
- **AND** возвращается структурированный JSON с полями контакта

### Scenario: Russian Language Support
- **GIVEN** голосовое на русском языке
- **WHEN** обрабатывается Gemini
- **THEN** транскрипция и извлечение корректны для русского

### Extracted Fields
- name (обязательно, "Неизвестно" если не понятно)
- company (опционально)
- role (опционально)
- event (где познакомились)
- telegram_username (если упомянут @username)
- phone (если упомянут)
- email (если упомянут)
- agreements[] (о чём договорились)
- follow_up_action (следующий шаг)
- what_looking_for (что ищет человек)
- can_help_with (чем может помочь)
- topics[] (темы для разговора)
- notes (прочее)
- raw_transcript (полная транскрипция)

### AI Prompt Requirements
- Промпт SHALL быть в отдельном файле prompts/extract_contact.txt
- Промпт SHALL требовать JSON output без markdown
- Промпт SHALL обрабатывать неполную информацию gracefully

---

## Requirement: Telegram Contact Handling

Система SHALL принимать пересланные Telegram-контакты и извлекать данные.

### Scenario: Contact Shared via Button
- **GIVEN** пользователь нажал "Поделиться контактом" в Telegram
- **WHEN** бот получает Contact object
- **THEN** извлекаются: first_name, last_name, phone_number, user_id

### Scenario: Forwarded Message
- **GIVEN** пользователь переслал сообщение от другого пользователя
- **WHEN** бот получает forward_from
- **THEN** извлекаются: first_name, last_name, username

### Scenario: vCard File
- **GIVEN** пользователь отправил .vcf файл
- **WHEN** бот получает document
- **THEN** парсится vCard и извлекаются все поля

---

## Requirement: Voice + Contact Merge

Система SHALL объединять данные из голосового и контакта в единую карточку.

### Scenario: Voice Then Contact
- **GIVEN** пользователь отправил голосовое
- **WHEN** в течение 5 минут отправляет контакт
- **THEN** данные мержатся, приоритет контакта для имени/телефона

### Scenario: Contact Then Voice
- **GIVEN** пользователь переслал контакт
- **WHEN** в течение 5 минут отправляет голосовое
- **THEN** данные мержатся

### Scenario: Voice Only
- **GIVEN** пользователь отправил только голосовое
- **WHEN** прошло 5 минут или он нажал "Сохранить"
- **THEN** карточка создаётся только из голосового

### Scenario: Contact Only
- **GIVEN** пользователь переслал только контакт
- **WHEN** он нажал "Сохранить без заметки"
- **THEN** карточка создаётся с минимальными данными

### Merge Rules
1. name: TG контакт > голосовое
2. phone: TG контакт > голосовое
3. telegram_username: голосовое (в контакте его нет)
4. company, role, agreements, etc.: только из голосового
5. raw_transcript: всегда сохраняется

---

## Requirement: Contact Card Display

Система SHALL показывать созданную карточку пользователю для подтверждения.

### Card Format
```
✅ {name}

🏢 {company} · {role}
📱 {phone}
💬 {telegram_username}
📧 {email}

📍 {event} ({date})

📝 Договорённости:
• {agreement_1}
• {agreement_2}

🎯 Следующий шаг: {follow_up_action}

💡 Ищет: {what_looking_for}
🤝 Может помочь: {can_help_with}
```

### Inline Keyboard
- [В Notion] [В Sheets] [CSV]
- [✏️ Редактировать] [🗑 Удалить]
- [⏰ Напомнить] — если есть follow_up_action

---

## Requirement: Basic Contact Storage

Система SHALL сохранять контакты в PostgreSQL.

### Scenario: Save New Contact
- **GIVEN** карточка подтверждена пользователем
- **WHEN** он нажимает кнопку экспорта или "Сохранить"
- **THEN** контакт сохраняется в БД
- **AND** создаётся interaction типа 'met'

### Scenario: Duplicate Detection
- **GIVEN** контакт с таким же telegram_username или phone уже существует
- **WHEN** пользователь сохраняет новый
- **THEN** показывается предупреждение с опцией "Обновить" или "Создать новый"

---

## Requirement: Contact List

Система SHALL показывать список сохранённых контактов.

### Command: /list

### Scenario: Show Recent Contacts
- **GIVEN** пользователь вводит /list
- **WHEN** команда обрабатывается
- **THEN** показываются последние 10 контактов
- **AND** есть пагинация "← Назад | Вперёд →"

### List Format
```
📋 Твои контакты (всего: 47)

1. Марат Ибрагимов — CPO @ Kolesa
   📍 Product Camp · 15 янв
   
2. Алия Сатпаева — Partner @ 500 Startups
   📍 Astana Hub · 12 янв
   
...

[← Назад] [1/5] [Вперёд →]
```

### Scenario: View Contact Details
- **GIVEN** пользователь нажимает на контакт в списке
- **WHEN** открывается детальная карточка
- **THEN** показываются все данные + история взаимодействий

---

## Requirement: Basic Search

Система SHALL искать контакты по имени и компании.

### Command: /find {query}

### Scenario: Search by Name
- **GIVEN** пользователь вводит `/find Марат`
- **WHEN** выполняется поиск
- **THEN** возвращаются контакты где name содержит "Марат"

### Scenario: Search by Company
- **GIVEN** пользователь вводит `/find Kolesa`
- **WHEN** выполняется поиск
- **THEN** возвращаются контакты где company содержит "Kolesa"

### Scenario: No Results
- **GIVEN** поиск не нашёл результатов
- **WHEN** показывается ответ
- **THEN** "Контакты не найдены. Попробуй другой запрос."

---

## Requirement: CSV Export

Система SHALL экспортировать контакты в CSV.

### Command: /export

### Scenario: Export All Contacts
- **GIVEN** пользователь вводит /export
- **WHEN** команда обрабатывается
- **THEN** генерируется CSV файл со всеми контактами
- **AND** файл отправляется пользователю

### CSV Columns
name, company, role, phone, telegram, email, linkedin, event, date, agreements, follow_up, notes

---

# PHASE 2: USER PROFILE & SMART CARDS (Should Have)

---

## Requirement: User Profile Setup

Система SHALL хранить профиль пользователя для генерации визиток.

### Command: /profile

### Profile Data Structure
```json
{
  "name": "Иван Петров",
  "photo_url": "...",
  "contacts": {
    "telegram": "@ivanpetrov",
    "phone": "+7 777 123 4567",
    "email": "ivan@curestry.com",
    "linkedin": "linkedin.com/in/ivanpetrov",
    "calendly": "calendly.com/ivanpetrov"
  },
  "roles": [
    {
      "title": "Founder",
      "company": "Curestry",
      "description": "AI debugging platform"
    },
    {
      "title": "Senior TPM", 
      "company": "Twinby",
      "description": "Dating app, 2M users"
    }
  ],
  "pitches": {
    "general": "Помогаю компаниям понять почему их AI лажает",
    "investor": "Curestry — Datadog для AI агентов. $50K ARR, 10 пилотов.",
    "technical": "Трейсинг и дебаг LLM в проде. Интеграция за час.",
    "product": "Видим почему AI галлюцинирует на реальных данных."
  },
  "links": {
    "deck": "https://...",
    "one_pager": "https://...",
    "demo": "https://...",
    "articles": ["https://..."]
  },
  "looking_for": ["Пилотные клиенты", "Pre-seed инвесторы", "CTO для advisory"],
  "can_help_with": ["AI/ML консультации", "Продуктовый менторинг", "Интро в Казахстане"]
}
```

### Scenario: Edit Profile via Bot
- **GIVEN** пользователь вводит /profile
- **WHEN** показывается текущий профиль
- **THEN** есть кнопки для редактирования каждой секции

### Scenario: Add Elevator Pitch
- **GIVEN** пользователь нажимает "Добавить питч"
- **WHEN** вводит название контекста и текст
- **THEN** питч сохраняется в профиле

---

## Requirement: Smart Card Generation

Система SHALL генерировать персонализированные визитки.

### Command: /card {context}

### Scenario: General Card
- **GIVEN** пользователь вводит `/card`
- **WHEN** генерируется визитка
- **THEN** используется general pitch и все контакты

### Scenario: Context-Specific Card
- **GIVEN** пользователь вводит `/card для инвестора`
- **WHEN** генерируется визитка
- **THEN** используется investor pitch
- **AND** добавляются ссылки на deck и метрики

### Scenario: Person-Specific Card
- **GIVEN** пользователь вводит `/card для Марат`
- **WHEN** контакт Марат найден в базе
- **THEN** визитка персонализируется под него:
  - Релевантный pitch
  - Общие интересы/знакомые
  - Как пользователь может быть полезен Марату

### Card Output Format
Текстовое сообщение + inline keyboard с ссылками.

```
👤 Иван Петров
Founder @ Curestry

"Помогаем понять почему ваш AI галлюцинирует"

💡 Марат, мы оба работаем с AI в продакшене — 
   Curestry может помочь с модерацией в Kolesa.

[LinkedIn] [Telegram] [Calendly]
[📎 Презентация]

[📤 Переслать] [🔗 Получить ссылку]
```

---

## Requirement: Shareable Card Link

Система SHALL генерировать одноразовые ссылки на визитку.

### Command: /share {contact?}

### Scenario: Generate Share Link
- **GIVEN** пользователь вводит `/share`
- **WHEN** генерируется ссылка
- **THEN** создаётся токен в shared_cards
- **AND** ссылка действует 24 часа

### Scenario: Personalized Share Link
- **GIVEN** пользователь вводит `/share Марат`
- **WHEN** генерируется ссылка
- **THEN** визитка будет персонализирована под Марата

### Scenario: Recipient Opens Link
- **GIVEN** получатель открывает t.me/bot?start=card_xyz
- **WHEN** бот обрабатывает deep link
- **THEN** показывается визитка отправителя
- **AND** есть кнопка "Поделиться своим контактом"

### Scenario: Recipient Shares Back
- **GIVEN** получатель нажимает "Поделиться контактом"
- **WHEN** он отправляет свой контакт или голосовое
- **THEN** отправитель получает уведомление о новом контакте

---

# PHASE 3: FOLLOW-UP SYSTEM (Should Have)

---

## Requirement: Reminder Creation

Система SHALL создавать напоминания о follow-up.

### Scenario: Auto-Reminder from Voice
- **GIVEN** в голосовом упомянуто "созвониться через неделю"
- **WHEN** контакт сохраняется
- **THEN** бот предлагает создать напоминание на +7 дней

### Scenario: Manual Reminder
- **GIVEN** пользователь нажимает "⏰ Напомнить" на карточке
- **WHEN** показывается выбор срока
- **THEN** опции: [Завтра] [Через 3 дня] [Через неделю] [Выбрать дату]

### Scenario: Reminder with Template
- **GIVEN** создаётся напоминание
- **WHEN** есть follow_up_action у контакта
- **THEN** он сохраняется как message_template

---

## Requirement: Reminder Notifications

Система SHALL отправлять напоминания в заданное время.

### Scenario: Send Reminder
- **GIVEN** наступило trigger_at напоминания
- **WHEN** Celery задача выполняется
- **THEN** пользователь получает сообщение:

```
⏰ Напоминание: Марат (Kolesa)

Договаривались: демо Curestry
Прошло дней: 5

[📝 Написать сообщение] [✅ Готово] [⏰ Отложить]
```

### Scenario: Snooze Reminder
- **GIVEN** пользователь нажимает "Отложить"
- **WHEN** выбирает новый срок
- **THEN** reminder.snoozed_until обновляется

### Scenario: Complete Reminder
- **GIVEN** пользователь нажимает "Готово"
- **WHEN** статус меняется
- **THEN** создаётся interaction типа 'message_sent'

---

## Requirement: Follow-up Message Generation

Система SHALL генерировать персонализированные follow-up сообщения.

### Scenario: Generate Message
- **GIVEN** пользователь нажимает "Написать сообщение"
- **WHEN** вызывается Gemini
- **THEN** генерируется сообщение на основе:
  - Контекста знакомства
  - Договорённостей
  - Профиля пользователя
  - Времени с последнего контакта

### Generated Message Example
```
Привет, Марат!

Рад был познакомиться на Product Camp.

Как обсуждали, вот краткая презентация Curestry — [ссылка].
Думаю, может помочь с модерацией в Kolesa.

Готов показать демо когда удобно. Как насчёт четверга?
```

### Scenario: Edit and Send
- **GIVEN** сообщение сгенерировано
- **WHEN** пользователь нажимает "Отправить в TG"
- **THEN** если есть telegram_username — открывается ссылка t.me/username
- **AND** текст копируется в буфер (или показывается для копирования)

---

## Requirement: Pending Follow-ups List

Система SHALL показывать список предстоящих напоминаний.

### Command: /reminders

### Output
```
⏰ Предстоящие напоминания:

Сегодня:
• Марат (Kolesa) — демо Curestry

Завтра:
• Алия (500 Startups) — отправить deck

На этой неделе:
• Серик (MOST) — узнать про раунд
• Дамир (Founder X) — интро к инвестору

[Показать все]
```

---

# PHASE 4: MATCHING & INSIGHTS (Nice to Have)

---

## Requirement: Interest Matching

Система SHALL находить синергии между контактами и целями пользователя.

### Scenario: Match on Contact Add
- **GIVEN** добавлен контакт с what_looking_for = "AI решение для модерации"
- **WHEN** у пользователя в профиле есть Curestry (AI debugging)
- **THEN** показывается матч:

```
🎯 Потенциальный матч!

Марат ищет: AI для модерации
Ты делаешь: Curestry (AI debugging)

Возможный питч: [сгенерированный текст]

[Напомнить написать]
```

### Scenario: Periodic Match Scan
- **GIVEN** в базе есть контакты с looking_for/can_help_with
- **WHEN** раз в неделю запускается задача
- **THEN** находятся новые матчи и отправляются пользователю

---

## Requirement: Semantic Search

Система SHALL искать контакты по смыслу, не только по ключевым словам.

### Command: /find {natural language query}

### Scenario: Search by Need
- **GIVEN** пользователь вводит `/find кто может помочь с инвестициями`
- **WHEN** Gemini анализирует запрос и контакты
- **THEN** возвращаются релевантные контакты с объяснением

### Scenario: Search by Event
- **GIVEN** пользователь вводит `/find с кем познакомился на Product Camp`
- **WHEN** выполняется поиск
- **THEN** фильтруются контакты по event

### Scenario: Search by Recency
- **GIVEN** пользователь вводит `/find с кем давно не общался`
- **WHEN** анализируются interactions
- **THEN** возвращаются контакты без взаимодействий >30 дней

---

## Requirement: Networking Analytics

Система SHALL показывать статистику нетворкинга.

### Command: /stats {period?}

### Scenario: Monthly Stats
- **GIVEN** пользователь вводит `/stats` или `/stats январь`
- **WHEN** агрегируются данные
- **THEN** показывается отчёт:

```
📊 Нетворкинг: Январь 2025

Новых контактов: 23
├── Product Camp Almaty: 12
├── Astana Hub Demo Day: 8
└── Случайные: 3

По ролям:
├── CPO/PM: 8 (35%)
├── CTO/Tech: 6 (26%)
├── Founders: 5 (22%)
└── Инвесторы: 4 (17%)

Воронка:
├── Контакты: 23
├── Follow-up отправлен: 18 (78%)
├── Ответили: 12 (52%)
└── Встречи: 7 (30%)

💡 Инсайты:
• Product Camp — твой лучший источник
• 5 контактов без follow-up — догнать?

[📈 Детальный отчёт] [📤 Экспорт]
```

---

# PHASE 5: WARM INTROS & GRAPH (Nice to Have)

---

## Requirement: Connection Graph

Система SHALL строить граф связей между контактами.

### Data Model
- Связь contact A → contact B через поле introduced_by или вручную
- Связь contact ↔ company (extracted from company field)
- Связь contact → contact через общие events

### Scenario: Manual Connection
- **GIVEN** пользователь на карточке контакта нажимает "Добавить связь"
- **WHEN** выбирает другой контакт
- **THEN** создаётся связь с типом (knows, worked_with, etc.)

---

## Requirement: Warm Intro Path Finding

Система SHALL находить пути для тёплых интро.

### Command: /intro {target}

### Scenario: Find Intro Path
- **GIVEN** пользователь вводит `/intro CEO Chocofamily`
- **WHEN** ищутся пути в графе
- **THEN** показываются варианты:

```
🔗 Пути к Рамилю (CEO Chocofamily):

Путь 1 (сильный):
Ты → Марат (работал в Chocofamily 3 года) → Рамиль

Путь 2 (средний):
Ты → Серик (инвестор Chocofamily) → Рамиль

Рекомендация: попросить Марата

[📝 Сгенерировать просьбу для Марата]
```

### Scenario: Generate Intro Request
- **GIVEN** пользователь выбирает путь через Марата
- **WHEN** нажимает "Сгенерировать просьбу"
- **THEN** Gemini создаёт сообщение для Марата с просьбой об интро

---

## Requirement: Meeting Preparation

Система SHALL помогать готовиться к встречам.

### Command: /prep {contact}

### Scenario: Generate Briefing
- **GIVEN** пользователь вводит `/prep Марат`
- **WHEN** собираются данные из БД + OSINT
- **THEN** показывается брифинг:

```
📋 Подготовка к встрече: Марат Ибрагимов

Из твоих заметок:
• CPO @ Kolesa Group, 5+ лет
• Познакомились: Product Camp, 15 января
• Интерес: AI для модерации
• Договорённость: демо Curestry
• Общий знакомый: Айдар

Из открытых источников:
• До Kolesa: Product в Chocofamily (3 года)
• Недавний пост: "ML в маркетплейсах"
• Общие LinkedIn связи: Айдар, Серик

Рекомендации:
• Упомянуть его пост про ML — показать что следишь
• Подготовить демо на кейсе модерации
• Айдар может дать рекомендацию

Talking points:
• Боли модерации в маркетплейсах
• Как Curestry ловит edge cases
• Пилот на 2 недели бесплатно
```

---

# PHASE 6: OSINT & ENRICHMENT (Nice to Have)

---

## Requirement: Basic OSINT Enrichment

Система SHALL обогащать контакты публичными данными.

### Scenario: Auto-Enrich on Save
- **GIVEN** контакт сохраняется с именем и компанией
- **WHEN** запускается фоновая задача
- **THEN** ищется LinkedIn профиль через Google CSE
- **AND** результаты сохраняются в osint_data

### Scenario: Manual Enrich
- **GIVEN** пользователь на карточке нажимает "🔍 Найти информацию"
- **WHEN** запускается OSINT
- **THEN** показываются найденные данные для подтверждения

### OSINT Data Sources (по приоритету)
1. Google Custom Search: "{name} {company} site:linkedin.com"
2. Google Custom Search: "{name} {company}" (статьи, выступления)
3. Proxycurl API (опционально, платный): LinkedIn профиль

### OSINT Data Structure
```json
{
  "linkedin": {
    "url": "...",
    "headline": "...",
    "experience": [...],
    "education": [...]
  },
  "google_results": [
    {"title": "...", "url": "...", "snippet": "..."}
  ],
  "enriched_at": "2025-01-15T12:00:00Z"
}
```

---

## Requirement: LinkedIn Import

Система SHALL импортировать connections из LinkedIn.

### Command: /import linkedin

### Scenario: Upload LinkedIn Export
- **GIVEN** пользователь скачал connections.csv из LinkedIn
- **WHEN** загружает файл в бота
- **THEN** контакты парсятся и добавляются в базу
- **AND** строятся связи для графа

### LinkedIn CSV Fields
First Name, Last Name, Email Address, Company, Position, Connected On

---

# PHASE 7: INTEGRATIONS (Nice to Have)

---

## Requirement: Notion Export

Система SHALL экспортировать контакты в Notion database.

### Scenario: Export Single Contact
- **GIVEN** пользователь нажимает "В Notion" на карточке
- **WHEN** вызывается Notion API
- **THEN** создаётся страница в настроенной базе

### Scenario: Sync All Contacts
- **GIVEN** пользователь вводит `/sync notion`
- **WHEN** запускается синхронизация
- **THEN** все контакты экспортируются/обновляются в Notion

### Notion Database Properties
- Name (title)
- Company (text)
- Role (text)
- Phone (phone)
- Telegram (text)
- Email (email)
- LinkedIn (url)
- Event (text)
- Date Met (date)
- Agreements (text)
- Follow-up (text)
- Status (select)
- Last Interaction (date)

---

## Requirement: Google Sheets Export

Система SHALL экспортировать контакты в Google Sheets.

### Scenario: Export to Sheets
- **GIVEN** пользователь нажимает "В Sheets" на карточке
- **WHEN** вызывается Sheets API
- **THEN** контакт добавляется строкой в таблицу

### Scenario: Full Sync
- **GIVEN** пользователь вводит `/sync sheets`
- **WHEN** запускается синхронизация
- **THEN** таблица полностью обновляется

---

## Requirement: Event Context Mode

Система SHALL поддерживать режим мероприятия.

### Command: /event {name}

### Scenario: Start Event Mode
- **GIVEN** пользователь вводит `/event Product Camp Almaty`
- **WHEN** режим активируется
- **THEN** все новые контакты автоматически получают этот event

### Scenario: End Event Mode
- **GIVEN** пользователь вводит `/event stop`
- **WHEN** режим деактивируется
- **THEN** новые контакты не получают автоматический event

### Scenario: Event Indicator
- **GIVEN** режим мероприятия активен
- **WHEN** бот показывает любое сообщение
- **THEN** в начале есть индикатор: "📍 Product Camp Almaty"

---

# NON-FUNCTIONAL REQUIREMENTS

---

## Requirement: Performance

- Обработка голосового: < 10 секунд
- Поиск контактов: < 500ms
- Генерация визитки: < 5 секунд
- Напоминания: отправка в течение 1 минуты от trigger_at

---

## Requirement: Reliability

- Graceful degradation при недоступности Gemini API
- Retry logic для внешних API (3 попытки с exponential backoff)
- Сохранение голосовых в raw виде для повторной обработки

---

## Requirement: Security

- Все токены/ключи через environment variables
- Telegram user_id для авторизации
- Share links с ограниченным сроком жизни
- Нет хранения чужих паролей/токенов

---

## Requirement: Observability

- Structured logging (JSON)
- Метрики: количество контактов, голосовых, ошибок Gemini
- Alerting при высоком error rate

---

# IMPLEMENTATION TASKS

## Phase 0: Infrastructure
- [ ] Task 0.1: Инициализация проекта (poetry/pip, структура папок)
- [ ] Task 0.2: Docker + docker-compose (postgres, redis, app)
- [ ] Task 0.3: Pydantic settings + .env.example
- [ ] Task 0.4: SQLAlchemy models + Alembic setup
- [ ] Task 0.5: Базовый FastAPI app + health check
- [ ] Task 0.6: Базовый Telegram bot + /start handler

## Phase 1: Core MVP
- [ ] Task 1.1: GeminiService — транскрипция + extraction
- [ ] Task 1.2: Промпт для извлечения контакта (итеративно)
- [ ] Task 1.3: Voice handler — приём и обработка голосовых
- [ ] Task 1.4: Contact handler — приём TG контактов, vCard
- [ ] Task 1.5: Merge logic — объединение голос + контакт
- [ ] Task 1.6: Contact card display + inline keyboard
- [ ] Task 1.7: ContactService — CRUD операции
- [ ] Task 1.8: /list handler + пагинация
- [ ] Task 1.9: /find handler — базовый поиск
- [ ] Task 1.10: /export handler — CSV экспорт
- [ ] Task 1.11: End-to-end тестирование MVP

## Phase 2: Profile & Cards
- [ ] Task 2.1: User model + ProfileService
- [ ] Task 2.2: /profile handler — просмотр и редактирование
- [ ] Task 2.3: CardGeneratorService — генерация визиток
- [ ] Task 2.4: /card handler — context-specific cards
- [ ] Task 2.5: /share handler — генерация ссылок
- [ ] Task 2.6: Deep link handling — приём контактов по ссылке
- [ ] Task 2.7: Персонализация под конкретного контакта

## Phase 3: Follow-up
- [ ] Task 3.1: Reminder model + ReminderService
- [ ] Task 3.2: Celery setup + periodic tasks
- [ ] Task 3.3: Auto-reminder extraction из голосового
- [ ] Task 3.4: Manual reminder creation UI
- [ ] Task 3.5: Reminder notification sender
- [ ] Task 3.6: Snooze/complete handlers
- [ ] Task 3.7: Follow-up message generation
- [ ] Task 3.8: /reminders handler

## Phase 4: Matching & Insights
- [ ] Task 4.1: MatchService — поиск синергий
- [ ] Task 4.2: Match notification при добавлении контакта
- [ ] Task 4.3: Semantic search через Gemini
- [ ] Task 4.4: AnalyticsService — агрегация статистики
- [ ] Task 4.5: /stats handler + визуализация
- [ ] Task 4.6: /matches handler

## Phase 5: Graph & Intros
- [ ] Task 5.1: Connection model + GraphService
- [ ] Task 5.2: UI для добавления связей
- [ ] Task 5.3: Path finding algorithm (BFS/Dijkstra)
- [ ] Task 5.4: /intro handler
- [ ] Task 5.5: Intro request generation
- [ ] Task 5.6: /prep handler — meeting briefing

## Phase 6: OSINT
- [ ] Task 6.1: Google Custom Search integration
- [ ] Task 6.2: OSINTService — orchestration
- [ ] Task 6.3: Background enrichment task
- [ ] Task 6.4: Proxycurl integration (optional)
- [ ] Task 6.5: LinkedIn CSV import
- [ ] Task 6.6: OSINT data display в карточке

## Phase 7: Integrations
- [ ] Task 7.1: NotionService + export handler
- [ ] Task 7.2: SheetsService + export handler
- [ ] Task 7.3: Full sync commands
- [ ] Task 7.4: /event handler — event mode
- [ ] Task 7.5: Google Calendar integration (optional)

---

# APPENDIX

## AI Prompts Location

Все промпты хранятся в `/prompts/` как отдельные .txt файлы:

- `extract_contact.txt` — извлечение данных из голосового
- `generate_card.txt` — генерация персонализированной визитки
- `generate_followup.txt` — генерация follow-up сообщения
- `generate_intro_request.txt` — генерация просьбы об интро
- `semantic_search.txt` — семантический поиск по контактам
- `meeting_prep.txt` — подготовка брифинга к встрече
- `match_analysis.txt` — анализ синергий

## Error Messages (RU)

- "Не удалось распознать голосовое. Попробуй ещё раз или отправь текстом."
- "Контакт сохранён ✅"
- "Контакты не найдены. Попробуй другой запрос."
- "Gemini API временно недоступен. Попробуй через минуту."
- "Напоминание создано на {date}"

## Telegram Commands Summary

```
/start — начало работы
/help — справка
/profile — настройка профиля
/list — список контактов
/find {query} — поиск
/card {context?} — генерация визитки
/share {contact?} — ссылка для шаринга
/reminders — предстоящие напоминания
/stats {period?} — статистика
/export — экспорт в CSV
/sync {notion|sheets} — синхронизация
/event {name|stop} — режим мероприятия
/intro {target} — поиск пути для интро
/prep {contact} — подготовка к встрече
/matches — потенциальные синергии
```