from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print("Starting up...")
    yield
    # Shutdown actions
    print("Shutting down...")

app = FastAPI(title="Network Bot", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Hello from Network Bot API"}
