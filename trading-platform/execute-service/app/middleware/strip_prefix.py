"""ASGI middleware to strip a Gateway API path prefix from incoming requests.

Usage in main.py:
    from app.middleware.strip_prefix import StripPrefixMiddleware
    app.add_middleware(StripPrefixMiddleware, prefix="/api/execute")

This lets Gateway API route /api/execute/* to the service while the
service's routes remain at /* (e.g. /trades, /health).
"""
from __future__ import annotations

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class StripPrefixMiddleware(BaseHTTPMiddleware):
    """Strip a configured prefix from request paths before they reach route handlers."""

    def __init__(self, app, prefix: str = "") -> None:
        super().__init__(app)
        self.prefix = prefix.rstrip("/")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.scope.get("path", "")
        if self.prefix and path.startswith(self.prefix):
            stripped = path[len(self.prefix):] or "/"
            request.scope["path"] = stripped
            logger.debug("Stripped prefix %s: %s -> %s", self.prefix, path, stripped)
        return await call_next(request)