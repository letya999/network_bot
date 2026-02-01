import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.contact_service import ContactService, UNKNOWN_CONTACT_NAME
from app.models.contact import Contact

@pytest.mark.asyncio
async def test_create_contact(mock_session):
    # Setup
    mock_session = AsyncMock()
    service = ContactService(mock_session)
    user_id = uuid.uuid4()
    data = {"name": "Test", "notes": "Note"}
    
    # Run
    contact = await service.create_contact(user_id, data)
    
    # Verify
    assert contact.name == "Test"
    assert contact.user_id == user_id
    mock_session.add.assert_called() # one for contact, one for interaction
    mock_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_update_contact_smart_merge():
    mock_session = AsyncMock()
    service = ContactService(mock_session)
    
    # Mock existing contact
    contact_id = uuid.uuid4()
    existing_contact = Contact(id=contact_id, name="Old Name", company="Old Co", attributes={})
    
    # Mock return from select
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_contact
    mock_session.execute.return_value = mock_result
    
    # Update data
    data = {
        "name": "New Name",
        "company": None, # Should be ignored
        "role": "   ", # Should be ignored (empty string)
        "notes": "New Note" # Attribute merge
    }
    
    # We rely on real inspect(Contact) so we don't patch it.
    
    updated = await service.update_contact(contact_id, data)
    
    assert updated.name == "New Name"
    assert updated.company == "Old Co"
    # attributes should happen even if not a column?
    # Code: if field not in valid_columns: continue
    # But later: 
    # if contact.attributes is None: ...
    # current_attrs.update(data)
    # The attributes update logic (lines 183+) uses 'data' (the whole dict).
    # So 'notes' in data -> updates attributes['notes'].
    assert updated.attributes['notes'] == "New Note"
    
    mock_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_update_contact_ignore_unknown_name():
    mock_session = AsyncMock()
    service = ContactService(mock_session)
    
    existing_contact = Contact(id=uuid.uuid4(), name="Real Name")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_contact
    mock_session.execute.return_value = mock_result
    
    data = {"name": UNKNOWN_CONTACT_NAME}
    
    await service.update_contact(existing_contact.id, data)
    
    assert existing_contact.name == "Real Name"

@pytest.mark.asyncio
async def test_find_by_identifiers():
    mock_session = AsyncMock()
    service = ContactService(mock_session)
    user_id = uuid.uuid4()
    
    # Mock result
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = Contact(name="Found")
    mock_session.execute.return_value = mock_result
    
    # Test valid phone
    res = await service.find_by_identifiers(user_id, phone="123")
    assert res.name == "Found"
    
    # Test no identifiers
    res = await service.find_by_identifiers(user_id)
    assert res is None

