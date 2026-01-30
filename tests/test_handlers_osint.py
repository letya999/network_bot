"""Tests for OSINT Bot Handlers."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.handlers.osint_handlers import (
    enrich_command, enrich_callback, show_osint_data,
    start_import, handle_csv_import, enrichment_stats, batch_enrich_callback
)


@pytest.fixture
def mock_contact():
    """Create a mock contact."""
    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.user_id = uuid.uuid4()
    contact.name = "Test User"
    contact.company = "TestCorp"
    contact.role = "Developer"
    contact.osint_data = {}
    return contact


@pytest.fixture
def mock_db_user():
    """Create a mock database user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.telegram_id = 12345
    return user


@pytest.fixture
def mock_osint_service():
    """Create a mock OSINT service."""
    service = MagicMock()
    service.enrich_contact = AsyncMock(return_value={
        "status": "success",
        "message": "Enriched",
        "data": {"career": {"current": {"company": "Test"}}}
    })
    service.get_enrichment_stats = AsyncMock(return_value={
        "total_contacts": 10,
        "enriched_contacts": 5,
        "pending_enrichment": 5
    })
    service.batch_enrich = AsyncMock(return_value={
        "status": "success",
        "enriched": 3,
        "errors": None
    })
    return service


@pytest.fixture(autouse=True)
def mock_rate_limit():
    """Mock rate limiter to always allow."""
    with patch("app.bot.handlers.osint_handlers.rate_limit_middleware", new_callable=AsyncMock) as mock:
        mock.return_value = True
        yield mock



class TestEnrichCommand:
    """Tests for /enrich command."""

    @pytest.mark.asyncio
    async def test_enrich_no_contact_specified(self, mock_update, mock_context, mock_async_session_local):
        """Should prompt for contact name when none specified."""
        mock_context.args = []
        mock_context.user_data = {}

        await enrich_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Кого обогатить" in call_args[0][0] or "кого" in str(call_args).lower()

    @pytest.mark.asyncio
    async def test_enrich_contact_not_found(self, mock_update, mock_context, mock_session, mock_async_session_local, mock_db_user):
        """Should show error when contact not found."""
        mock_context.args = ["NotExisting"]

        # Mock user service
        with patch("app.bot.handlers.osint_handlers.UserService") as MockUserService:
            mock_user_svc = MagicMock()
            mock_user_svc.get_or_create_user = AsyncMock(return_value=mock_db_user)
            MockUserService.return_value = mock_user_svc

            # Mock contact service - no contacts found
            with patch("app.bot.handlers.osint_handlers.ContactService") as MockContactService:
                mock_contact_svc = MagicMock()
                mock_contact_svc.find_contacts = AsyncMock(return_value=[])
                MockContactService.return_value = mock_contact_svc

                await enrich_command(mock_update, mock_context)

                mock_update.message.reply_text.assert_called()
                call_args = str(mock_update.message.reply_text.call_args)
                assert "не найден" in call_args.lower() or "not found" in call_args.lower()

    @pytest.mark.asyncio
    async def test_enrich_shows_selection_for_multiple(self, mock_update, mock_context, mock_session, mock_async_session_local, mock_db_user, mock_contact):
        """Should show selection buttons when multiple contacts match."""
        mock_context.args = ["Test"]

        # Create two contacts
        contact2 = MagicMock()
        contact2.id = uuid.uuid4()
        contact2.name = "Test User 2"
        contact2.company = "Other Corp"

        with patch("app.bot.handlers.osint_handlers.UserService") as MockUserService:
            mock_user_svc = MagicMock()
            mock_user_svc.get_or_create_user = AsyncMock(return_value=mock_db_user)
            MockUserService.return_value = mock_user_svc

            with patch("app.bot.handlers.osint_handlers.ContactService") as MockContactService:
                mock_contact_svc = MagicMock()
                mock_contact_svc.find_contacts = AsyncMock(return_value=[mock_contact, contact2])
                MockContactService.return_value = mock_contact_svc

                await enrich_command(mock_update, mock_context)

                # Should show buttons
                call_args = mock_update.message.reply_text.call_args
                assert "reply_markup" in str(call_args) or call_args[1].get("reply_markup") is not None


class TestEnrichCallback:
    """Tests for enrich callback handler."""

    @pytest.mark.asyncio
    async def test_enrich_callback_success(self, mock_update, mock_context, mock_async_session_local, mock_contact, mock_db_user):
        """Should show success message after enrichment."""
        mock_update.callback_query.data = f"enrich_{mock_contact.id}"

        with patch("app.bot.handlers.osint_handlers.UserService") as MockUserService:
            mock_user_svc = MagicMock()
            mock_user_svc.get_or_create_user = AsyncMock(return_value=mock_db_user)
            MockUserService.return_value = mock_user_svc

            with patch("app.bot.handlers.osint_handlers.OSINTService") as MockOSINT:
                mock_osint = MagicMock()
                mock_osint.enrich_contact = AsyncMock(return_value={
                    "status": "success",
                    "data": {"career": {"current": {"company": "Test"}}}
                })
                MockOSINT.return_value = mock_osint

                # Mock session.get to return contact
                mock_async_session_local.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_contact)
                mock_contact.user_id = mock_db_user.id

                await enrich_callback(mock_update, mock_context)

                mock_update.callback_query.answer.assert_called()


class TestShowOSINTData:
    """Tests for /osint command."""

    @pytest.mark.asyncio
    async def test_show_osint_no_data(self, mock_update, mock_context, mock_async_session_local, mock_db_user, mock_contact):
        """Should offer to enrich when no OSINT data."""
        mock_context.args = ["Test"]
        mock_contact.osint_data = None

        with patch("app.bot.handlers.osint_handlers.UserService") as MockUserService:
            mock_user_svc = MagicMock()
            mock_user_svc.get_or_create_user = AsyncMock(return_value=mock_db_user)
            MockUserService.return_value = mock_user_svc

            with patch("app.bot.handlers.osint_handlers.ContactService") as MockContactService:
                mock_contact_svc = MagicMock()
                mock_contact_svc.find_contacts = AsyncMock(return_value=[mock_contact])
                MockContactService.return_value = mock_contact_svc

                await show_osint_data(mock_update, mock_context)

                call_args = mock_update.message.reply_text.call_args
                # Should offer enrichment button
                assert "reply_markup" in str(call_args) or call_args[1].get("reply_markup") is not None


class TestImportCommand:
    """Tests for /import command."""

    @pytest.mark.asyncio
    async def test_start_import(self, mock_update, mock_context):
        """Should show import instructions."""
        result = await start_import(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = str(mock_update.message.reply_text.call_args)
        assert "LinkedIn" in call_args
        # Should return conversation state
        from app.bot.osint_handlers import WAITING_FOR_CSV
        assert result == WAITING_FOR_CSV


class TestEnrichmentStats:
    """Tests for /enrich_stats command."""

    @pytest.mark.asyncio
    async def test_enrichment_stats_display(self, mock_update, mock_context, mock_async_session_local, mock_db_user, mock_osint_service):
        """Should display enrichment statistics."""
        with patch("app.bot.handlers.osint_handlers.UserService") as MockUserService:
            mock_user_svc = MagicMock()
            mock_user_svc.get_or_create_user = AsyncMock(return_value=mock_db_user)
            MockUserService.return_value = mock_user_svc

            with patch("app.bot.handlers.osint_handlers.OSINTService") as MockOSINT:
                MockOSINT.return_value = mock_osint_service

                await enrichment_stats(mock_update, mock_context)

                mock_update.message.reply_text.assert_called()
                call_args = str(mock_update.message.reply_text.call_args)
                # Should show stats
                assert "Статистика" in call_args or "10" in call_args


class TestBatchEnrichCallback:
    """Tests for batch enrichment callback."""

    @pytest.mark.asyncio
    async def test_batch_enrich_callback(self, mock_update, mock_context, mock_async_session_local, mock_db_user, mock_osint_service):
        """Should trigger batch enrichment."""
        mock_update.callback_query.data = "batch_enrich"

        with patch("app.bot.handlers.osint_handlers.UserService") as MockUserService:
            mock_user_svc = MagicMock()
            mock_user_svc.get_or_create_user = AsyncMock(return_value=mock_db_user)
            MockUserService.return_value = mock_user_svc

            with patch("app.bot.handlers.osint_handlers.OSINTService") as MockOSINT:
                MockOSINT.return_value = mock_osint_service

                await batch_enrich_callback(mock_update, mock_context)

                mock_update.callback_query.answer.assert_called()
                mock_update.callback_query.edit_message_text.assert_called()
