# Project Roadmap: NetworkingCRM

Based on [OpenSpec Specification](context.md).

## Phase 0: Infrastructure
- [x] Task 0.1: Инициализация проекта (poetry/pip, структура папок)
- [x] Task 0.2: Docker + docker-compose (postgres, redis, app)
- [x] Task 0.3: Pydantic settings + .env.example
- [x] Task 0.4: SQLAlchemy models + Alembic setup
- [x] Task 0.5: Базовый FastAPI app + health check
- [x] Task 0.6: Базовый Telegram bot + /start handler

## Phase 1: Core MVP
- [x] Task 1.1: GeminiService — транскрипция + extraction
- [x] Task 1.2: Промпт для извлечения контакта (итеративно)
- [x] Task 1.3: Voice handler — приём и обработка голосовых
- [x] Task 1.4: Contact handler — приём TG контактов, vCard
- [x] Task 1.5: Merge logic — объединение голос + контакт
- [x] Task 1.6: Contact card display + inline keyboard
- [x] Task 1.7: ContactService — CRUD операции
- [x] Task 1.8: /list handler + пагинация
- [x] Task 1.9: /find handler — базовый поиск
- [x] Task 1.10: /export handler — CSV экспорт
- [x] Task 1.11: End-to-end тестирование MVP

## Phase 2: Profile & Cards
- [x] Task 2.1: User model + ProfileService
- [x] Task 2.2: /profile handler — просмотр и редактирование
- [x] Task 2.3: CardGeneratorService — генерация визиток
- [x] Task 2.4: /card handler — context-specific cards
- [x] Task 2.5: /share handler — генерация ссылок
- [x] Task 2.6: Deep link handling — приём контактов по ссылке
- [x] Task 2.7: Персонализация под конкретного контакта

## Phase 3: Follow-up
- [x] Task 3.1: Reminder model + ReminderService
- [x] Task 3.2: APScheduler setup + periodic tasks
- [x] Task 3.3: Auto-reminder extraction из голосового
- [x] Task 3.4: Manual reminder creation UI (via text extraction)
- [x] Task 3.5: Reminder notification sender
- [x] Task 3.6: Snooze/complete handlers
- [ ] Task 3.7: Follow-up message generation
- [x] Task 3.8: /reminders handler

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
