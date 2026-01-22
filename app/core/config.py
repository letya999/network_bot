from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn, computed_field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
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

settings = Settings()
