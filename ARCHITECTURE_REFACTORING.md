# Отчет по архитектурному анализу и План рефакторинга Network Bot

## Краткое резюме (Executive Summary)
Текущая архитектура проекта базируется на слоях (Handlers-Services-Models), что является хорошим началом. Однако, по мере роста функционала, границы слоев размылись.

Основные проблемы:
1.  **Нарушение SRP (Single Responsibility Principle)**: Хендлеры занимаются работой с БД, парсингом CSV и логикой. Сервисы занимаются форматированием текста (View).
2.  **Непоследовательная структура**: Часть файлов лежит в корне `app/bot/`, часть в `app/bot/handlers/`. Именование файлов хаотично.
3.  **Божественные объекты (God Objects)**: `main.py` знает обо всем проекте, `common.py` стал свалкой утилит.
4.  **Нарушение DRY (Don't Repeat Yourself)**: Повторяющийся код управления сессиями БД во всех хендлерах.

---

## 1. Выявленные проблемы (Architecture Review)

### 1.1. Файловая структура и Организация
*   **Смешивание уровней**: Файлы `osint_handlers.py`, `match_handlers.py`, `profile_handlers.py` находятся в корне `app/bot/`, тогда как другие лежат в `app/bot/handlers/`.
*   **Путаница в именах**: Файлы `contact.py`, `card.py` в папке `handlers` называются так же, как модели данных. Это создает путаницу (Model vs Handler).
*   **Свалка кода**: Файл `app/bot/handlers/common.py` содержит форматирование карточек, клавиатур и закомментированный код. Это классический "anti-pattern".

### 1.2. Нарушение разделения ответственности (SoC)
*   **View в Services**: В `app/services/osint_service.py` метод `format_osint_data` генерирует Markdown-разметку. Сервисы должны возвращать данные (Dict/DTO), а форматированием должен заниматься слой представления (View).
*   **Logic в Handlers**: В `app/bot/osint_handlers.py` (строки 309-380) происходит скачивание файла и парсинг CSV. Эта логика принадлежит сервисному слою (`ImportService`).
*   **Infrastructure в Logic**: `OSINTService` напрямую использует `aiohttp` для запросов к Tavily API, вместо использования отдельного API-клиента.

### 1.3. Принципы YAGNI и KISS
*   **Manual Routing (KISS)**: В `main.py` (функция `route_menu_command`) вручную парсятся строки вида `cmd_...`. Это усложняет код. Лучше использовать возможности фреймворка (Pattern matching) или отдельные CallbackQueryHandler.
*   **Dead Code (YAGNI)**: В `common.py` есть неиспользуемые переменные (например, логика `show_tg_line`, которая закомментирована/не работает как задумано).

---

## 2. План рефакторинга (Roadmap)

### Этап 1: Наведение порядка в структуре (High Priority)
Цель: Унификация расположения файлов и их именования.

- [ ] **Переместить файлы хендлеров**:
    Перенести из `app/bot/` в `app/bot/handlers/`:
    - `osint_handlers.py`
    - `match_handlers.py`
    - `profile_handlers.py`
    - `analytics_handlers.py`
    - `integration_handlers.py`
    - `reminder_handlers.py`
    - `run.py` (оставить в корне или `app/`)
- [ ] **Переименовать файлы (Convention)**:
    Добавить суффикс `_handlers.py` всем файлам в `app/bot/handlers/`, конфликтующим с именами моделей:
    - `contact.py` -> `contact_handlers.py` (!!! Критично)
    - `card.py` -> `card_handlers.py`
    - `search.py` -> `search_handlers.py`
    - `prompt.py` -> `prompt_handlers.py`
    - `event.py` -> `event_handlers.py`
    - `assets_handler.py` -> `assets_handlers.py` (Plural)

### Этап 2: Выделение слоя View (Presentation Layer)
Цель: Создать "Дизайн-систему" кода (централизованное форматирование).

- [ ] **Создать пакет `app/bot/views/`**.
- [ ] **Contact View**: Перенести `format_card` и `get_contact_keyboard` из `common.py` в `app/bot/views/contact_view.py`.
- [ ] **OSINT View**: Извлечь `format_osint_data` из `osint_service.py` в `app/bot/views/osint_view.py`.
- [ ] **Progress Bar**: Перенести логику progress bar из `osint_handlers.py` в `app/bot/views/components.py`.
- [ ] **Удалить** `app/bot/handlers/common.py`.

### Этап 3: Чистка Сервисов и Хендлеров (Refactoring)
Цель: Разгрузить классы от лишней ответственности.

- [ ] **Infrastructure Clients**: Создать `app/infrastructure/clients/tavily.py`. Перенести туда логику HTTP-запросов из `OSINTService`.
- [ ] **CSV Import Logic**: Вынести логику парсинга CSV из `osint_handlers.py` в `ContactImportService` или `ImportService`.
- [ ] **Database Session Decorator**: Внедрить декоратор `@with_session` (или middleware), чтобы убрать шаблонный код `async with AsyncSessionLocal()` из каждого хендлера.

### Этап 4: Модульность и Точка входа
Цель: Упростить `main.py` и сделать добавление новых фич простым.

- [ ] **Router Pattern**: В каждом файле хендлеров (например, `osint_handlers.py`) создать функцию `register_handlers(app: Application)`.
- [ ] **Refactor Main**: В `app/bot/main.py` заменить "простыню" импортов и вызовов `add_handler` на вызов функций регистрации из модулей.

---

## 3. Рекомендации по "System Design" (UI/UX)
Для улучшения UX бота (дизайна взаимодействия) рекомендуется:

1.  **Централизация текстов**: Вынести все текстовые сообщения в `app/resources/strings.py` или JSON-файлы. Это позволит легко править тексты и emojis без изменения кода.
2.  **Унификация навигации**: Использовать единый базовый класс для меню, чтобы кнопка "Назад" и "Главное меню" работали одинаково во всех разделах (Single Source of Truth).
