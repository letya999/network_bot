# Test Runner

Запускает тесты проекта с coverage.

## Usage
- `/test` - все тесты
- `/test unit` - только unit
- `/test integration` - только integration
- `/test <path>` - конкретный файл/тест

## Instructions

1. Запусти pytest:
   ```bash
   pytest --cov=services --cov=models --cov=repositories --cov-report=term-missing -v
   ```

2. Покажи результат:
   - ✅ если все прошли
   - ❌ детали ошибок если упали
   - Coverage %

3. При ошибках предложи исправить
