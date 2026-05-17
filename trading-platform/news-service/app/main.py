"""FastAPI application factory with lifespan management and Kafka integration."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import db
from app.api.articles import router as articles_router
from app.api.analysis import router as analysis_router
from app.api.signals import router as signals_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: startup and shutdown."""
    # Startup
    settings = get_settings()
    logger.info(f"Starting {settings.app_name}")
    
    await db.init()
    logger.info("Database initialized")
    
    # Start periodic Kafka consumer for unprocessed articles
    # (runs in background, triggered by DB events)
    # Note: In production, this would be a separate worker process
    logger.info("News analyst service started")
    
    yield
    
    # Shutdown
    await db.close()
    logger.info("Shut down complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        description=(
            "News analyst microservice for the trading platform. "
            "Ingests articles from CNPG news database, runs NLP analysis, "
            "and exposes REST API for frontend/dashboard consumption."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routes
    prefix = settings.api_prefix
    app.include_router(articles_router, prefix=prefix)
    app.include_router(analysis_router, prefix=prefix)
    app.include_router(signals_router, prefix=prefix)
    
    # Health check
    @app.get("/health", tags=["health"])
    async def health_check():
        return {
            "status": "healthy",
            "service": settings.app_name,
            "version": "1.0.0",
        }
    
    @app.get("/health/db", tags=["health"])
    async def health_check_db(session: AsyncSession = Depends(db.get_session)):
        """Check database connectivity."""
        try:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            result.scalar()
            return {"status": "healthy", "database": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "database": str(e)}
    
    return app


# Application instance for ASGI servers
app = create_app()
