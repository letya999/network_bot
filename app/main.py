import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.api.webhooks import router as webhooks_router
from app.api.admin import router as admin_router
from app.api.webapp import router as webapp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI...")
    yield
    logger.info("Shutting down FastAPI...")


app = FastAPI(
    title="Network Bot API",
    docs_url="/docs" if not settings.APP_DOMAIN else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Include routers
app.include_router(webhooks_router)
app.include_router(admin_router)
app.include_router(webapp_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Network Bot API", "version": "2.0"}
