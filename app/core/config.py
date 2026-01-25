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

    # OSINT & Enrichment Settings
    TAVILY_API_KEY: Optional[str] = None  # Tavily AI Search API Key

    # OSINT Rate Limits
    OSINT_DAILY_LIMIT: int = 50  # Max enrichments per user per day
    OSINT_RATE_LIMIT_WINDOW: int = 60  # Seconds between enrichment requests

    # Auto-enrichment settings
    AUTO_ENRICH_ON_CREATE: bool = True  # Auto-enrich new contacts
    OSINT_CACHE_DAYS: int = 30  # Days before re-enrichment is allowed

settings = Settings()
