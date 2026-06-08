"""
FastAPI application for training records Web App backend.
Run separately from Telegram bot: `uvicorn api.app:app --host 0.0.0.0 --port 8001`
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import records

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI."""
    logger.info("Starting Records API...")
    yield
    logger.info("Shutting down Records API...")


# Create FastAPI app
app = FastAPI(
    title="FitnessAI Records API",
    description="Training records backend for Telegram Web App",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for Telegram Web App
# Telegram Web App can be opened from various origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Telegram-Init-Data", "ngrok-skip-browser-warning"],
)

# Include routers
app.include_router(records.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "FitnessAI Records API",
        "version": "1.0.0",
        "docs": "/docs",
    }
