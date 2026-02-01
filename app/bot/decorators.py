"""Decorators for bot handlers."""
import functools
import logging
from typing import Callable
from telegram import Update
from telegram.ext import ContextTypes
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def with_session(handler: Callable):
    """
    Decorator to automatically provide database session to handler.

    Wraps handler functions to inject a database session as a keyword argument.
    The session is automatically committed and closed after the handler executes.

    Usage:
        @with_session
        async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
            # Use session here
            pass

    Args:
        handler: The async handler function to wrap

    Returns:
        Wrapped handler function
    """
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        async with AsyncSessionLocal() as session:
            try:
                result = await handler(update, context, *args, session=session, **kwargs)
                await session.commit()
                return result
            except Exception as e:
                try:
                    await session.rollback()
                except Exception as rollback_err:
                    logger.error(f"Error during rollback in handler {handler.__name__}: {rollback_err}")
                logger.exception(f"Error in handler {handler.__name__}: {e}")
                raise

    return wrapper
