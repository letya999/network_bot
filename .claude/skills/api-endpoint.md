# API Endpoint Skill

## Description
Создает новый REST API endpoint с OpenAPI документацией, валидацией и тестами.

## Usage
- `/api-endpoint <HTTP метод> <путь> <описание>`
- Пример: `/api-endpoint GET /api/v1/contacts/:id Get contact by ID`

## Instructions

Когда вызван этот skill:

1. **Распарси параметры:**
   - HTTP метод (GET, POST, PUT, PATCH, DELETE)
   - Путь endpoint'а
   - Краткое описание

2. **Определи требования:**
   - Какие данные на входе (query params, path params, body)
   - Какие данные на выходе
   - Авторизация нужна?
   - Какой service использовать

3. **Создай Pydantic schemas:**
   ```python
   # schemas/<entity>.py

   class <Entity>Request(BaseModel):
       """Request schema с валидацией."""
       field: str = Field(..., description="...")

   class <Entity>Response(BaseModel):
       """Response schema."""
       id: UUID
       ...

       class Config:
           from_attributes = True
   ```

4. **Создай route:**
   ```python
   # api/routes/<entity>.py

   @router.get(
       "/<path>",
       response_model=<Entity>Response,
       summary="Short description",
       description="Detailed description",
       responses={
           200: {"description": "Success"},
           404: {"description": "Not found"},
       }
   )
   async def endpoint_name(
       param: str = Path(..., description="..."),
       db = Depends(get_db),
       user = Depends(get_current_user)
   ):
       """Docstring."""
       service = <Entity>Service(db)
       result = await service.method(param)
       return result
   ```

5. **Добавь OpenAPI examples:**
   - Примеры в response_model
   - Примеры в параметрах
   - Примеры ошибок

6. **Напиши тесты:**
   ```python
   # tests/integration/api/test_<entity>.py

   @pytest.mark.asyncio
   async def test_endpoint_success(api_client, test_user):
       """Test successful response."""
       response = await api_client.get("/api/v1/...")
       assert response.status_code == 200
       data = response.json()
       assert data["field"] == "value"

   @pytest.mark.asyncio
   async def test_endpoint_not_found(api_client):
       """Test 404 error."""
       response = await api_client.get("/api/v1/nonexistent")
       assert response.status_code == 404
   ```

7. **Зарегистрируй router:**
   ```python
   # api/main.py
   from api.routes import <entity>
   app.include_router(<entity>.router)
   ```

8. **Проверь документацию:**
   - Запусти сервер
   - Открой /api/docs
   - Проверь что endpoint виден
   - Протестируй через Swagger UI

9. **Запусти тесты:**
   ```bash
   /test integration/api/test_<entity>.py
   ```

## Best Practices

- **Валидация:** Всегда используй Pydantic для входных данных
- **Ошибки:** Используй HTTPException с понятными сообщениями
- **Авторизация:** Используй Depends(get_current_user) где нужно
- **Документация:** Заполни summary, description, examples
- **Тесты:** Минимум success + error cases
- **Versioning:** Используй /api/v1/ в путях

## Examples

User: `/api-endpoint POST /api/v1/contacts Create new contact`
Assistant: Создаю POST endpoint для создания контакта...

**1. Schemas:**
```python
# schemas/contact.py

class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, example="Марат Ибрагимов")
    company: Optional[str] = Field(None, example="Kolesa Group")
    ...

class ContactResponse(BaseModel):
    id: UUID
    name: str
    company: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
```

**2. Route:**
```python
# api/routes/contacts.py

@router.post(
    "/",
    response_model=ContactResponse,
    status_code=201,
    summary="Create contact",
    description="Create a new contact for authenticated user"
)
async def create_contact(
    contact: ContactCreate,
    db = Depends(get_db),
    user = Depends(get_current_user)
):
    service = ContactService(db)
    return await service.create_contact(
        user_id=user.id,
        **contact.dict()
    )
```

**3. Tests:**
```python
# tests/integration/api/test_contacts.py

@pytest.mark.asyncio
async def test_create_contact_success(api_client, test_user):
    response = await api_client.post(
        "/api/v1/contacts/",
        json={
            "name": "Test Contact",
            "company": "Test Company"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Contact"
```

**4. Проверяю:**
- ✅ Schemas созданы
- ✅ Route добавлен
- ✅ Тесты написаны
- ✅ Документация в OpenAPI

Запускаю тесты...
```
/test integration/api/test_contacts.py
```

✅ Все тесты прошли!

Endpoint готов. Проверь документацию: http://localhost:8000/api/docs
