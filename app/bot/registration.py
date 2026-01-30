"""Handler registration utilities for modular bot architecture."""
import logging
from telegram.ext import Application

logger = logging.getLogger(__name__)


def register_all_handlers(app: Application):
    """
    Register all bot handlers in a modular fashion.

    This function imports and calls register_handlers() from each handler module,
    implementing a clean separation of concerns and making the codebase more maintainable.

    Args:
        app: Telegram Application instance
    """
    # Import handler registration functions
    from app.bot.handlers import info_handlers

    # Register handlers from each module
    logger.info("Registering info handlers...")
    info_handlers.register_handlers(app)

    # Additional handler modules can be registered here following the same pattern:
    # from app.bot.handlers import profile_handlers, contact_handlers, osint_handlers, etc.
    # profile_handlers.register_handlers(app)
    # contact_handlers.register_handlers(app)
    # osint_handlers.register_handlers(app)

    logger.info("All handlers registered successfully")
