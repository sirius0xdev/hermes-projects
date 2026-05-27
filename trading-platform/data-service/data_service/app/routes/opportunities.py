"""Opportunity scanner routes — REST + SSE endpoints."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException

from data_service.app.kafka.topics import KafkaTopics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["opportunities"])


def _get_opportunity_scanner():
    """Access the global opportunity scanner from main module."""
    import data_service.app.main as main_module
    scanner = getattr(main_module, "_opportunity_scanner", None)
    if not scanner:
        raise HTTPException(status_code=503, detail="Opportunity scanner not initialized")
    return scanner


@router.get("/opportunities")
async def get_opportunities():
    """Get current active opportunities."""
    scanner = _get_opportunity_scanner()
    opps = scanner.latest_opportunities
    return [opp.model_dump(mode="json") for opp in opps]


@router.get("/opportunities/stream")
async def stream_opportunities():
    """SSE stream — pushes new opportunities in real-time.

    Clients connect and receive a JSON-encoded OpportunityEvent
    each time the scanner detects something above the threshold.
    """
    from sse_starlette.sse import EventSourceResponse

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        scanner = _get_opportunity_scanner()

        # Send initial opportunities
        for opp in scanner.latest_opportunities:
            yield {
                "event": "opportunity",
                "data": json.dumps(opp.model_dump(mode="json")),
            }

        # Then stream new ones
        last_count = len(scanner.latest_opportunities)
        while True:
            await __import__("asyncio").sleep(5)
            current = scanner.latest_opportunities
            # New opportunities appear at the front
            new = current[:len(current) - last_count] if len(current) > last_count else []
            if new:
                for opp in new:
                    yield {
                        "event": "opportunity",
                        "data": json.dumps(opp.model_dump(mode="json")),
                    }
                last_count = len(current)

    return EventSourceResponse(event_generator())


@router.get("/yields")
async def get_yields():
    """Get latest Solana yield data."""
    import data_service.app.main as main_module
    scanner = getattr(main_module, "_opportunity_scanner", None)
    if not scanner:
        raise HTTPException(status_code=503, detail="Opportunity scanner not initialized")

    cache = scanner._yield_scanner.latest_cache
    result: dict[str, Any] = {}
    for protocol, assets in cache.items():
        result[protocol] = {}
        for asset, snap in assets.items():
            result[protocol][asset] = {
                "supply_apy": snap.supply_apy,
                "borrow_apy": snap.borrow_apy,
                "utilization": snap.utilization,
                "timestamp": snap.timestamp.isoformat(),
            }
    return result


@router.get("/funding")
async def get_funding_rates():
    """Get latest Hyperliquid funding rates."""
    import data_service.app.main as main_module
    scanner = getattr(main_module, "_opportunity_scanner", None)
    if not scanner:
        raise HTTPException(status_code=503, detail="Opportunity scanner not initialized")

    cache = scanner._funding_scanner.latest_cache
    result: dict[str, Any] = {}
    for symbol, fr in cache.items():
        result[symbol] = {
            "funding_rate": fr.funding_rate,
            "funding_rate_annual": fr.funding_rate_annual,
            "mark_price": fr.mark_price,
            "index_price": fr.index_price,
            "open_interest": fr.open_interest,
            "timestamp": fr.timestamp.isoformat(),
        }
    return result
