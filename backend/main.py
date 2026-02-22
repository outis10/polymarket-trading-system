"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware.auth import APIKeyMiddleware
from .routers import events, trading
from .services.event_manager import event_manager
from .ws.handlers import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting EventManager...")
    await event_manager.start()
    yield
    logger.info("Stopping EventManager...")
    await event_manager.stop()


app = FastAPI(title="Polymarket Monitor API", lifespan=lifespan)

# CORS — origins from env (comma-separated) or localhost defaults for dev
_cors_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:5173", "http://localhost:3000"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
)

# API Key middleware — validates X-API-Key header on all REST requests
app.add_middleware(APIKeyMiddleware)

# REST routers
app.include_router(events.router)
app.include_router(trading.router)

# WebSocket router
app.include_router(ws_router)


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
