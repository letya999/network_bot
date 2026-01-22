from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
import os

# Security: Disable SQL query logging in production
# Only enable echo in development mode
is_dev_mode = os.getenv("ENV", "production").lower() in ["dev", "development", "local"]
engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=is_dev_mode,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,  # Set connection pool size
    max_overflow=20  # Allow overflow connections
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
