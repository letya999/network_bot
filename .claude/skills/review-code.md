# Code Review

Проверяет код по чеклисту проекта.

## Usage
- `/review` - uncommitted changes
- `/review <file>` - конкретный файл

## Instructions

1. `git diff` для изменений

2. **Чеклист:**
   - [ ] Architecture: handler → service → repository
   - [ ] Type hints везде
   - [ ] Async для I/O
   - [ ] Pydantic validation на входе
   - [ ] Custom exceptions из core.errors
   - [ ] Try/except для внешних вызовов
   - [ ] Нет SQL injection / XSS
   - [ ] Есть тесты

3. **Отчет:**
   ```
   [CRITICAL] file.py:123 - проблема
   [MAJOR] file.py:456 - проблема
   [MINOR] file.py:789 - suggestion

   Рекомендация: APPROVE / REQUEST CHANGES
   ```

4. Предложи автофикс для critical/major
