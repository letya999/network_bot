import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.pulse_service import PulseService
from app.models.contact import Contact
from app.models.user import User
import uuid


@pytest.mark.asyncio
async def test_detect_company_triangulation_found(mock_session):
    """Test triangulation detection when contacts from same company exist"""
    user_id = uuid.uuid4()
    
    # New contact
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Alice Johnson",
        company="TechCorp",
        role="CTO",
        status="active"
    )
    
    # Existing contacts from same company
    existing_contact1 = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Bob Smith",
        company="TechCorp",
        role="CEO",
        status="active"
    )
    
    existing_contact2 = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Carol White",
        company="TechCorp Inc",  # Partial match
        role="VP",
        status="active"
    )
    
    # Mock the query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [existing_contact1, existing_contact2]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    service = PulseService(mock_session)
    triangulation = await service.detect_company_triangulation(user_id, new_contact)
    
    assert len(triangulation) == 2
    assert existing_contact1 in triangulation
    assert existing_contact2 in triangulation


@pytest.mark.asyncio
async def test_detect_company_triangulation_none_found(mock_session):
    """Test triangulation when no matching company contacts exist"""
    user_id = uuid.uuid4()
    
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Alice Johnson",
        company="TechCorp",
        status="active"
    )
    
    # Mock empty result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    service = PulseService(mock_session)
    triangulation = await service.detect_company_triangulation(user_id, new_contact)
    
    assert len(triangulation) == 0


@pytest.mark.asyncio
async def test_detect_company_triangulation_no_company(mock_session):
    """Test triangulation when new contact has no company"""
    user_id = uuid.uuid4()
    
    new_contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Alice Johnson",
        company=None,
        status="active"
    )
    
    service = PulseService(mock_session)
    triangulation = await service.detect_company_triangulation(user_id, new_contact)
    
    # Should return empty list without querying
    assert len(triangulation) == 0
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_detect_topic_overlap(mock_session):
    """Test topic overlap detection"""
    user_id = uuid.uuid4()
    
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Alice Johnson",
        topics=["AI", "Machine Learning", "Python"],
        status="active"
    )
    
    overlapping_contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Bob Smith",
        topics=["AI", "Data Science"],
        status="active"
    )
    
    # Mock the query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [overlapping_contact]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    service = PulseService(mock_session)
    overlaps = await service.detect_topic_overlap(user_id, contact)
    
    assert len(overlaps) == 1
    assert overlapping_contact in overlaps


@pytest.mark.asyncio
async def test_detect_topic_overlap_min_shared(mock_session):
    """Test topic overlap with minimum shared topics requirement"""
    user_id = uuid.uuid4()
    
    contact = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Alice Johnson",
        topics=["AI", "Machine Learning", "Python"],
        status="active"
    )
    
    # Contact with 2 shared topics
    contact_2_shared = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Bob Smith",
        topics=["AI", "Machine Learning", "Java"],
        status="active"
    )
    
    # Contact with 1 shared topic
    contact_1_shared = Contact(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Carol White",
        topics=["AI", "Blockchain"],
        status="active"
    )
    
    # Mock the query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [contact_2_shared, contact_1_shared]
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    service = PulseService(mock_session)
    overlaps = await service.detect_topic_overlap(user_id, contact, min_shared_topics=2)
    
    # Only contact with 2+ shared topics should be returned
    assert len(overlaps) == 1
    assert contact_2_shared in overlaps


def test_generate_triangulation_message_single():
    """Test triangulation message generation for single contact"""
    new_contact = Contact(
        name="Alice Johnson",
        company="TechCorp"
    )
    
    existing_contact = Contact(
        name="Bob Smith",
        company="TechCorp",
        role="CEO"
    )
    
    service = PulseService(MagicMock())
    message = service.generate_triangulation_message(new_contact, [existing_contact])
    
    assert "Триангуляция обнаружена" in message
    assert "Alice Johnson" in message
    assert "TechCorp" in message
    assert "Bob Smith" in message
    assert "CEO" in message
    assert "Повод написать" in message


def test_generate_triangulation_message_multiple():
    """Test triangulation message generation for multiple contacts"""
    new_contact = Contact(
        name="Alice Johnson",
        company="TechCorp"
    )
    
    existing_contacts = [
        Contact(name="Bob Smith", company="TechCorp", role="CEO"),
        Contact(name="Carol White", company="TechCorp", role="CTO"),
        Contact(name="Dave Brown", company="TechCorp", role="VP"),
    ]
    
    service = PulseService(MagicMock())
    message = service.generate_triangulation_message(new_contact, existing_contacts)
    
    assert "Триангуляция обнаружена" in message
    assert "3 контакт" in message
    assert "Bob Smith" in message
    assert "Carol White" in message
    assert "Dave Brown" in message


def test_generate_triangulation_message_empty():
    """Test triangulation message with no contacts"""
    new_contact = Contact(
        name="Alice Johnson",
        company="TechCorp"
    )
    
    service = PulseService(MagicMock())
    message = service.generate_triangulation_message(new_contact, [])
    
    assert message == ""


def test_generate_topic_overlap_message():
    """Test topic overlap message generation"""
    contact = Contact(
        name="Alice Johnson",
        topics=["AI", "Machine Learning"]
    )
    
    overlapping_contacts = [
        Contact(name="Bob Smith", topics=["AI", "Data Science"]),
        Contact(name="Carol White", topics=["Machine Learning", "Python"]),
    ]
    
    service = PulseService(MagicMock())
    message = service.generate_topic_overlap_message(contact, overlapping_contacts)
    
    assert "Общие интересы найдены" in message
    assert "Alice Johnson" in message
    assert "AI" in message
    assert "Machine Learning" in message
    assert "Bob Smith" in message
    assert "Carol White" in message


def test_generate_topic_overlap_message_empty():
    """Test topic overlap message with no overlaps"""
    contact = Contact(
        name="Alice Johnson",
        topics=["AI"]
    )
    
    service = PulseService(MagicMock())
    message = service.generate_topic_overlap_message(contact, [])
    
    assert message == ""
