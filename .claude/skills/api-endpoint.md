# API Endpoint

Создает REST endpoint с OpenAPI docs.

## Usage
`/api-endpoint <METHOD> <path> <description>`

Пример: `/api-endpoint GET /api/v1/contacts/:id Get contact`

## Instructions

1. **Pydantic schemas** в `schemas/`:
   ```python
   class EntityRequest(BaseModel): ...
   class EntityResponse(BaseModel): ...
   ```

2. **Route** в `api/routes/`:
   ```python
   @router.get("/<path>", response_model=Response, summary="...")
   async def name(db = Depends(get_db), user = Depends(get_current_user)):
       service = Service(db)
       return await service.method()
   ```

3. **Tests** в `tests/integration/api/`:
   - Success case
   - Error cases (404, 400, etc.)

4. Зарегистрируй router в `api/main.py`

5. Проверь `/api/docs`
