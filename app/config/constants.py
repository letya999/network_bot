"""
Application Constants

This module contains all magic strings and numbers used throughout the application.
Centralizing constants makes the codebase more maintainable and easier to update.
"""

# ============================================================================
# Contact Constants
# ============================================================================

UNKNOWN_CONTACT_NAME = "Неизвестно"
UNKNOWN_VALUE = "Не указано"

# ============================================================================
# Timing Constants (in seconds)
# ============================================================================

# Contact merge timeout - contacts created within this window can be merged
CONTACT_MERGE_TIMEOUT_SECONDS = 300  # 5 minutes

# Rate limiting
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_REQUESTS_PER_MINUTE = 20
MAX_VOICE_REQUESTS_PER_MINUTE = 5

# Rate limiter cleanup
RATE_LIMITER_CLEANUP_INTERVAL_HOURS = 24
RATE_LIMITER_INACTIVE_USER_THRESHOLD_HOURS = 24

# ============================================================================
# Search Constants
# ============================================================================

MAX_SEARCH_QUERY_LENGTH = 100
MIN_SEARCH_QUERY_LENGTH = 1
DEFAULT_SEARCH_RESULTS_LIMIT = 10

# ============================================================================
# AI/Gemini Constants
# ============================================================================

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-exp"
GEMINI_FALLBACK_MODEL = "gemini-1.5-flash"

# Semantic search - limit contacts loaded into memory
MAX_SEMANTIC_SEARCH_CONTACTS = 50

# ============================================================================
# OSINT/Enrichment Constants
# ============================================================================

# Days before re-enriching a contact
OSINT_ENRICHMENT_DELAY_DAYS = 30

# Batch enrichment settings
BATCH_ENRICHMENT_RATE_LIMIT = 5  # concurrent requests
BATCH_ENRICHMENT_DELAY_SECONDS = 1  # delay between batches

# Tavily search settings
TAVILY_MAX_RESULTS = 5
TAVILY_SEARCH_DEPTH = "advanced"  # "basic" or "advanced"
TAVILY_TIMEOUT_SECONDS = 20

# ============================================================================
# Export Constants
# ============================================================================

EXPORT_FORMATS = ['csv', 'json', 'vcard']
MAX_EXPORT_CONTACTS = 1000

# ============================================================================
# Scheduler Constants
# ============================================================================

# Retry settings for failed jobs
SCHEDULER_MAX_RETRIES = 3
SCHEDULER_RETRY_DELAY_BASE_MINUTES = 1  # Exponential backoff: 1, 2, 4 minutes

# ============================================================================
# Telegram Bot Constants
# ============================================================================

# Message limits
MAX_TELEGRAM_MESSAGE_LENGTH = 4096
MAX_TELEGRAM_CAPTION_LENGTH = 1024

# Callback data limits
MAX_CALLBACK_DATA_LENGTH = 64

# ============================================================================
# Database Constants
# ============================================================================

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ============================================================================
# File Processing Constants
# ============================================================================

# Voice message processing
MAX_VOICE_FILE_SIZE_MB = 20
VOICE_FILE_FORMATS = ['.ogg', '.mp3', '.wav', '.m4a']

# Document processing
MAX_DOCUMENT_SIZE_MB = 20
ALLOWED_DOCUMENT_FORMATS = ['.pdf', '.doc', '.docx', '.txt']

# ============================================================================
# Validation Constants
# ============================================================================

# Contact field lengths (should match database schema)
MAX_NAME_LENGTH = 255
MAX_COMPANY_LENGTH = 255
MAX_ROLE_LENGTH = 255
MAX_PHONE_LENGTH = 50
MAX_EMAIL_LENGTH = 255
MAX_TELEGRAM_USERNAME_LENGTH = 100
MAX_LINKEDIN_URL_LENGTH = 500

# ============================================================================
# Feature Flags
# ============================================================================

ENABLE_AUTO_ENRICHMENT = True
ENABLE_SEMANTIC_SEARCH = True
ENABLE_NOTION_SYNC = True
ENABLE_SHEETS_SYNC = True

# ============================================================================
# Marketplace & Sharing Constants
# ============================================================================

MAX_SHARES_PER_USER = 100
DEFAULT_SHARE_VISIBILITY = "public"
SUBSCRIPTION_GRACE_PERIOD_DAYS = 3
SUBSCRIPTION_RENEWAL_REMINDER_DAYS = 3
PAYMENT_TIMEOUT_MINUTES = 30
MIN_CONTACT_PRICE_RUB = 0
MAX_CONTACT_PRICE_RUB = 100000
