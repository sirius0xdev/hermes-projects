"""API routes for market signal summaries and ticker tracking."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db
from app.schemas.article import SignalSummary
from app.services.article_service import get_signal_summary as _get_summary

router = APIRouter(prefix="/signals", tags=["signals"])


async def _get_db() -> AsyncSession:
    async for session in db.get_session():
        yield session


@router.get("/summary", response_model=SignalSummary)
async def get_market_signal_summary(
    hours: int = Query(24, ge=1, le=720, description="Timeframe in hours"),
    session: AsyncSession = Depends(_get_db),
):
    """Get aggregated market signal summary for the dashboard.
    
    Returns sentiment distribution, top mentioned tickers,
    top market signals, and high-impact article count.
    """
    return await _get_summary(session, hours=hours)
