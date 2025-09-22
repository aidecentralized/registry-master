"""FastAPI application entry point for the Global Registry Master service."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, public
from app.api.dependencies import init_repository, shutdown_repository, init_kafka_services, shutdown_kafka_services
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Global Registry Master",
    description="API for agent discovery and resolution",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public.router)
app.include_router(admin.router)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialise resources when the application starts."""
    settings = get_settings()
    try:
        init_repository(settings)
        init_kafka_services(settings)
        logger.info("Registry service started successfully")
    except RuntimeError as exc:  # pylint: disable=broad-except
        logger.error("Failed to connect to database during startup: %s", exc)
        raise RuntimeError("Database connection failed") from exc


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Release resources during application shutdown."""
    shutdown_kafka_services()
    shutdown_repository()
    logger.info("Registry service shutdown complete")


__all__ = ["app"]
