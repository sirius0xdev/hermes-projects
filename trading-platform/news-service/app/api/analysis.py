"""API routes for analysis results."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db
from app.schemas.article import AnalysisResponse, AnalysisListResponse
from app.services.article_service import (
    get_analysis as _get_analysis,
    get_all_analysis as _get_all_analysis,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])


async def _get_db() -> AsyncSession:
    async for session in db.get_session():
        yield session


@router.get("/", response_model=AnalysisListResponse)
async def list_analysis(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sentiment_filter: Optional[str] = Query(None),
    min_impact: Optional[float] = Query(None, ge=0.0, le=1.0),
    session: AsyncSession = Depends(_get_db),
):
    """List all analysis results with pagination and filters."""
    items, total = await _get_all_analysis(
        db=session, page=page, page_size=page_size,
        sentiment_filter=sentiment_filter, min_impact=min_impact,
    )
    has_next = (page * page_size) < total
    has_prev = page > 1
    return AnalysisListResponse(
        items=[AnalysisResponse.model_validate(a) for a in items],
        total=total, page=page, page_size=page_size,
        has_next=has_next, has_prev=has_prev,
    )


@router.get("/{article_id}", response_model=AnalysisResponse)
async def get_analysis(
    article_id: int,
    session: AsyncSession = Depends(_get_db),
):
    """Get analysis for a specific article."""
    analysis = await _get_analysis(session, article_id)
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for article {article_id}",
        )
    return AnalysisResponse.model_validate(analysis)
