"""
Rate limiting middleware for Telegram bot to prevent abuse.
"""
import time
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Tuple
from telegram import Update
from telegram.ext import ContextTypes
from app.config.constants import (
    MAX_REQUESTS_PER_MINUTE,
    MAX_VOICE_REQUESTS_PER_MINUTE,
    RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMITER_INACTIVE_USER_THRESHOLD_HOURS
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple rate limiter to prevent bot abuse.
    Tracks requests per user and enforces limits.
    """

    def __init__(
        self,
        max_requests: int = 10,
        time_window: int = 60,
        voice_max_requests: int = 5,
        voice_time_window: int = 60,
        cleanup_interval_hours: int = 24
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in time window
            time_window: Time window in seconds
            voice_max_requests: Maximum voice messages allowed
            voice_time_window: Time window for voice messages in seconds
            cleanup_interval_hours: Hours between cleanup of inactive users
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.voice_max_requests = voice_max_requests
        self.voice_time_window = voice_time_window
        self.cleanup_interval_hours = cleanup_interval_hours

        # Storage: user_id -> list of timestamps
        self.request_history: Dict[int, list] = defaultdict(list)
        self.voice_history: Dict[int, list] = defaultdict(list)
        
        # Cleanup task
        self._cleanup_task = None

    def _clean_old_requests(self, user_id: int, current_time: float, is_voice: bool = False):
        """Remove expired requests from history."""
        history = self.voice_history if is_voice else self.request_history
        window = self.voice_time_window if is_voice else self.time_window

        history[user_id] = [
            timestamp for timestamp in history[user_id]
            if current_time - timestamp < window
        ]

    def cleanup_inactive_users(self) -> int:
        """
        Remove users with no activity for 24+ hours to prevent memory leak.
        
        Returns:
            Number of users removed
        """
        current_time = time.time()
        inactive_threshold = RATE_LIMITER_INACTIVE_USER_THRESHOLD_HOURS * 3600  # Convert to seconds
        
        # Find inactive users in request history
        inactive_users = set()
        for user_id, timestamps in list(self.request_history.items()):
            if timestamps:
                last_activity = max(timestamps)
                if current_time - last_activity > inactive_threshold:
                    inactive_users.add(user_id)
        
        # Also check voice history
        for user_id, timestamps in list(self.voice_history.items()):
            if timestamps:
                last_activity = max(timestamps)
                if current_time - last_activity > inactive_threshold:
                    inactive_users.add(user_id)
        
        # Remove inactive users
        for user_id in inactive_users:
            self.request_history.pop(user_id, None)
            self.voice_history.pop(user_id, None)
        
        if inactive_users:
            logger.info(f"Cleaned up {len(inactive_users)} inactive users from rate limiter")
        
        return len(inactive_users)

    async def _periodic_cleanup(self):
        """Periodic cleanup task that runs every cleanup_interval_hours."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_hours * 3600)
                self.cleanup_inactive_users()
            except asyncio.CancelledError:
                logger.info("Rate limiter cleanup task cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in rate limiter cleanup: {e}")

    def start_cleanup_task(self):
        """Start the periodic cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info(f"Started rate limiter cleanup task (interval: {self.cleanup_interval_hours}h)")

    def stop_cleanup_task(self):
        """Stop the periodic cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Stopped rate limiter cleanup task")

    def check_rate_limit(self, user_id: int, is_voice: bool = False) -> Tuple[bool, int]:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: Telegram user ID
            is_voice: Whether this is a voice message request

        Returns:
            Tuple of (is_allowed, seconds_until_reset)
        """
        current_time = time.time()
        self._clean_old_requests(user_id, current_time, is_voice)

        history = self.voice_history if is_voice else self.request_history
        max_req = self.voice_max_requests if is_voice else self.max_requests

        if len(history[user_id]) >= max_req:
            # Calculate time until oldest request expires
            oldest_request = min(history[user_id])
            window = self.voice_time_window if is_voice else self.time_window
            seconds_until_reset = int(window - (current_time - oldest_request)) + 1
            return False, seconds_until_reset

        # Add current request to history
        history[user_id].append(current_time)
        return True, 0


# Global rate limiter instance
rate_limiter = RateLimiter(
    max_requests=MAX_REQUESTS_PER_MINUTE,
    time_window=RATE_LIMIT_WINDOW_SECONDS,
    voice_max_requests=MAX_VOICE_REQUESTS_PER_MINUTE,
    voice_time_window=RATE_LIMIT_WINDOW_SECONDS
)


async def rate_limit_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Rate limiting middleware for bot handlers.
    Returns True if request should be processed, False if rate limited.
    """
    if not update.effective_user:
        return True

    user_id = update.effective_user.id
    is_voice = bool(update.message and update.message.voice)

    allowed, wait_time = rate_limiter.check_rate_limit(user_id, is_voice)

    if not allowed:
        logger.warning(f"Rate limit exceeded for user {user_id}. Wait time: {wait_time}s")
        if update.message:
            await update.message.reply_text(
                f"⚠️ Слишком много запросов. Пожалуйста, подождите {wait_time} секунд."
            )
        return False

    return True
