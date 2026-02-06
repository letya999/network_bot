from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn, computed_field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    # Security: Remove default credentials - require them to be set in .env
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "network_bot"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @computed_field
    def DATABASE_URL(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    REDIS_URL: RedisDsn = "redis://localhost:6379/0"
    
    TELEGRAM_BOT_TOKEN: str
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # OSINT & Enrichment Settings
    TAVILY_API_KEY: Optional[str] = None  # Tavily AI Search API Key

    # OSINT Rate Limits
    OSINT_DAILY_LIMIT: int = 50  # Max enrichments per user per day
    OSINT_RATE_LIMIT_WINDOW: int = 60  # Seconds between enrichment requests

    # Auto-enrichment settings
    AUTO_ENRICH_ON_CREATE: bool = True  # Auto-enrich new contacts
    OSINT_CACHE_DAYS: int = 30  # Days before re-enrichment is allowed

    # Notion Integration
    NOTION_API_KEY: Optional[str] = None
    NOTION_DATABASE_ID: Optional[str] = None

    # Google Sheets Integration
    GOOGLE_PROJ_ID: Optional[str] = None
    GOOGLE_PRIVATE_KEY_ID: Optional[str] = None
    GOOGLE_PRIVATE_KEY: Optional[str] = None
    GOOGLE_CLIENT_EMAIL: Optional[str] = None
    GOOGLE_SHEET_ID: Optional[str] = None

    # Payment: YooKassa
    YOOKASSA_SHOP_ID: Optional[str] = None
    YOOKASSA_SECRET_KEY: Optional[str] = None

    # Payment: CardPay/Unlimint
    CARDPAY_API_KEY: Optional[str] = None
    CARDPAY_MERCHANT_ID: Optional[str] = None

    # Telegram Payments (provider token from BotFather)
    TELEGRAM_PAYMENT_PROVIDER_TOKEN: Optional[str] = None

    # Subscription pricing (in RUB)
    SUBSCRIPTION_PRICE_RUB: int = 990
    SUBSCRIPTION_PRICE_STARS: int = 500

    # Admin telegram IDs (comma-separated)
    ADMIN_TELEGRAM_IDS: str = ""

    # Webhook & domain (for production)
    WEBHOOK_URL: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    APP_DOMAIN: Optional[str] = None

settings = Settings()
