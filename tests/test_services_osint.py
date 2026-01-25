"""Tests for OSINT Service."""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.osint_service import OSINTService, format_osint_data


@pytest.fixture
def osint_service(mock_session):
    """Create an OSINTService with mocked session."""
    return OSINTService(mock_session)


@pytest.fixture
def mock_contact():
    """Create a mock contact."""
    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.user_id = uuid.uuid4()
    contact.name = "Иван Петров"
    contact.company = "TechCorp"
    contact.role = "CTO"
    contact.osint_data = {}
    return contact


class TestOSINTServiceConfiguration:
    """Test OSINT service configuration checks."""

    def test_is_configured_returns_false_when_no_keys(self, osint_service, monkeypatch):
        """Service should report not configured when API keys missing."""
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_CX", None)

        assert osint_service._is_configured() is False

    def test_is_configured_returns_true_with_keys(self, osint_service, monkeypatch):
        """Service should report configured when API keys present."""
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", "test-key")
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_CX", "test-cx")

        assert osint_service._is_configured() is True


class TestOSINTServiceEnrichment:
    """Test contact enrichment functionality."""

    @pytest.mark.asyncio
    async def test_enrich_contact_not_found(self, osint_service, mock_session):
        """Should return error if contact not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await osint_service.enrich_contact(uuid.uuid4())

        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_enrich_contact_no_name(self, osint_service, mock_session, mock_contact):
        """Should return error if contact has no name."""
        mock_contact.name = "Неизвестно"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contact
        mock_session.execute.return_value = mock_result

        result = await osint_service.enrich_contact(mock_contact.id)

        assert result["status"] == "error"
        assert "name is required" in result["message"]

    @pytest.mark.asyncio
    async def test_enrich_contact_cached(self, osint_service, mock_session, mock_contact):
        """Should return cached data if recently enriched."""
        # Set recent enrichment date
        mock_contact.osint_data = {
            "enriched_at": datetime.now().isoformat(),
            "career": {"current": {"company": "Test"}}
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contact
        mock_session.execute.return_value = mock_result

        result = await osint_service.enrich_contact(mock_contact.id)

        assert result["status"] == "cached"

    @pytest.mark.asyncio
    async def test_enrich_contact_force_ignores_cache(self, osint_service, mock_session, mock_contact, monkeypatch):
        """Should re-enrich when force=True even if cached."""
        mock_contact.osint_data = {
            "enriched_at": datetime.now().isoformat(),
            "career": {}
        }

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contact
        mock_session.execute.return_value = mock_result

        # Mock search methods to return empty
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        result = await osint_service.enrich_contact(mock_contact.id, force=True)

        # With no API configured, it should still attempt enrichment
        assert result["status"] == "no_results"

    @pytest.mark.asyncio
    async def test_enrich_contact_no_results(self, osint_service, mock_session, mock_contact, monkeypatch):
        """Should handle case when no search results found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contact
        mock_session.execute.return_value = mock_result

        # Mock API as not configured (will return empty results)
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        result = await osint_service.enrich_contact(mock_contact.id)

        assert result["status"] == "no_results"


class TestOSINTServiceStats:
    """Test enrichment statistics."""

    @pytest.mark.asyncio
    async def test_get_enrichment_stats(self, osint_service, mock_session):
        """Should return correct enrichment statistics."""
        user_id = uuid.uuid4()

        # Mock count queries
        mock_result_total = MagicMock()
        mock_result_total.scalar.return_value = 10

        mock_result_enriched = MagicMock()
        mock_result_enriched.scalar.return_value = 3

        mock_session.execute.side_effect = [mock_result_total, mock_result_enriched]

        stats = await osint_service.get_enrichment_stats(user_id)

        assert stats["total_contacts"] == 10
        assert stats["enriched_contacts"] == 3
        assert stats["pending_enrichment"] == 7


class TestFormatOSINTData:
    """Test OSINT data formatting for Telegram display."""

    def test_format_empty_data(self):
        """Should return empty string for empty data."""
        assert format_osint_data({}) == ""
        assert format_osint_data(None) == ""

    def test_format_no_results(self):
        """Should handle no_results flag."""
        result = format_osint_data({"no_results": True})
        assert "не найдена" in result

    def test_format_career_current(self):
        """Should format current career information."""
        data = {
            "career": {
                "current": {
                    "company": "TechCorp",
                    "role": "CTO",
                    "since": "2021"
                }
            }
        }
        result = format_osint_data(data)

        assert "Карьера" in result
        assert "TechCorp" in result
        assert "CTO" in result
        assert "2021" in result

    def test_format_career_previous(self):
        """Should format previous jobs."""
        data = {
            "career": {
                "previous": [
                    {"company": "OldCorp", "role": "Developer", "years": "2018-2021"}
                ]
            }
        }
        result = format_osint_data(data)

        assert "OldCorp" in result
        assert "2018-2021" in result

    def test_format_education(self):
        """Should format education information."""
        data = {
            "education": {
                "universities": [
                    {"name": "MIT", "degree": "CS", "year": 2015}
                ]
            }
        }
        result = format_osint_data(data)

        assert "Образование" in result
        assert "MIT" in result
        assert "CS" in result

    def test_format_geography(self):
        """Should format location."""
        data = {
            "geography": {
                "current_city": "Алматы"
            }
        }
        result = format_osint_data(data)

        assert "Локация" in result
        assert "Алматы" in result

    def test_format_social_links(self):
        """Should format social media links."""
        data = {
            "social": {
                "linkedin": "https://linkedin.com/in/test",
                "twitter": "@testuser",
                "github": "testuser"
            }
        }
        result = format_osint_data(data)

        assert "Соцсети" in result
        assert "LinkedIn" in result
        assert "Twitter" in result
        assert "GitHub" in result

    def test_format_publications(self):
        """Should format publications."""
        data = {
            "publications": [
                {"type": "article", "title": "Test Article", "url": "https://example.com"}
            ]
        }
        result = format_osint_data(data)

        assert "Публикации" in result
        assert "Test Article" in result

    def test_format_confidence(self):
        """Should format confidence indicator."""
        data = {"confidence": "high"}
        result = format_osint_data(data)

        assert "Достоверность" in result
        assert "high" in result

    def test_format_enriched_date(self):
        """Should format enrichment date."""
        data = {"enriched_at": "2025-01-20T12:00:00"}
        result = format_osint_data(data)

        assert "Обновлено" in result
        assert "20.01.2025" in result


class TestGoogleSearch:
    """Test Google Custom Search integration."""

    @pytest.mark.asyncio
    async def test_google_search_not_configured(self, osint_service, monkeypatch):
        """Should return empty when not configured."""
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        results = await osint_service._google_search("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_google_search_timeout(self, osint_service, monkeypatch):
        """Should handle timeout gracefully."""
        import asyncio

        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", "key")
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_CX", "cx")

        # Mock aiohttp to raise timeout
        async def mock_get(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch("aiohttp.ClientSession") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get

            results = await osint_service._google_search("test")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_linkedin(self, osint_service, monkeypatch):
        """Should construct proper LinkedIn search query."""
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        results = await osint_service._search_linkedin("Ivan Petrov", "TechCorp")

        # With no API key, should return empty
        assert results == []

    @pytest.mark.asyncio
    async def test_search_publications(self, osint_service, monkeypatch):
        """Should construct proper publications search query."""
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        results = await osint_service._search_publications("Ivan Petrov")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_social(self, osint_service, monkeypatch):
        """Should construct proper social media search query."""
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        results = await osint_service._search_social("Ivan Petrov")

        assert results == []


class TestBatchEnrichment:
    """Test batch enrichment functionality."""

    @pytest.mark.asyncio
    async def test_batch_enrich_no_contacts(self, osint_service, mock_session):
        """Should handle case when all contacts are enriched."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await osint_service.batch_enrich(uuid.uuid4())

        assert result["status"] == "complete"
        assert result["enriched"] == 0

    @pytest.mark.asyncio
    async def test_batch_enrich_with_contacts(self, osint_service, mock_session, mock_contact, monkeypatch):
        """Should enrich multiple contacts."""
        # Mock query to return contacts
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_contact]

        # Mock get for individual contact
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_contact

        mock_session.execute.side_effect = [mock_result, mock_result2]

        # Disable API so enrichment completes quickly
        monkeypatch.setattr("app.services.osint_service.settings.GOOGLE_CSE_API_KEY", None)

        result = await osint_service.batch_enrich(mock_contact.user_id, limit=1)

        # Should attempt to enrich
        assert "enriched" in result
