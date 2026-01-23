import pytest
from app.services.contact_service import ContactService
from app.services.profile_service import ProfileService
from app.services.card_service import CardService
from app.models.contact import Contact
from app.schemas.profile import UserProfile
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_contact_service_create(mock_session):
    service = ContactService(mock_session)
    data = {"name": "Test Contact", "phone": "123"}
    user_id = "uuid-123"
    
    contact = await service.create_contact(user_id, data)
    
    assert contact.name == "Test Contact"
    assert contact.user_id == user_id
    # Called twice: 1 for Contact, 1 for Interaction
    assert mock_session.add.call_count == 2
    mock_session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_profile_service_update(mock_session):
    service = ProfileService(mock_session)
    # Mock user retrieval
    mock_user = MagicMock()
    mock_user.profile_data = {}
    mock_user.name = "Old Name"
    
    # We need to mock user_service result
    service.user_service.get_or_create_user = AsyncMock(return_value=mock_user)
    
    profile = await service.update_profile_field(12345, "full_name", "New Name")
    
    assert profile.full_name == "New Name"
    assert mock_user.name == "New Name" # Should synchronize
    mock_session.commit.assert_called_once()

def test_card_generation():
    profile = UserProfile(full_name="Alice", company="Wonderland Inc", job_title="Explorer")
    text_card = CardService.generate_text_card(profile)
    
    assert "Alice" in text_card
    assert "Wonderland Inc" in text_card
    assert "Explorer" in text_card

def test_card_generation_with_intro():
    profile = UserProfile(full_name="Bob")
    text_card = CardService.generate_text_card(profile, intro_text="Hello friend!")
    
    assert "Hello friend!" in text_card
    assert "Bob" in text_card
