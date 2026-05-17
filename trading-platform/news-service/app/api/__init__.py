"""News service routes."""

from app.api.articles import router as articles_router
from app.api.analysis import router as analysis_router
from app.api.signals import router as signals_router

__all__ = ["articles_router", "analysis_router", "signals_router"]
