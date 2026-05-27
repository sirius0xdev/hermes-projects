"""
Rate limiting middleware for execute-service.

Uses sliding window counters backed by Redis when available,
with an in-memory fallback for development/standalone operation.

Rate limits applied per-client:
- General requests: rate_limit_requests_per_minute (default 60/min)
- Order placement: rate_limit_order_per_second (default 5/sec)
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from app.config import settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """In-memory rate limiter using sliding window counters.

    Falls back to this when Redis is unavailable. Suitable for
    single-instance deployments; not accurate under multi-pod load.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        order_per_second: int = 5,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.order_per_second = order_per_second
        # key -> list of timestamps
        self._request_windows: dict[str, list[float]] = defaultdict(list)
        self._order_windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, endpoint_type: str = "general") -> bool:
        """Check if a request is allowed under rate limits."""
        now = time.time()

        if endpoint_type == "order":
            return self._check_window(
                self._order_windows[key], now, self.order_per_second, 1.0
            )
        else:
            # Check burst (1-second window)
            if not self._check_window(
                self._request_windows[f"{key}:burst"], now, self.burst_size, 1.0
            ):
                return False
            # Check minute window
            return self._check_window(
                self._request_windows[key], now, self.requests_per_minute, 60.0
            )

    def _check_window(
        self, window: list[float], now: float, max_count: int, window_seconds: float
    ) -> bool:
        """Sliding window check. Returns True if allowed."""
        cutoff = now - window_seconds
        # Prune old entries
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= max_count:
            return False
        window.append(now)
        return True

    def get_remaining(self, key: str, endpoint_type: str = "general") -> dict:
        """Return rate limit header info."""
        now = time.time()
        if endpoint_type == "order":
            cutoff = now - 1.0
            window = self._order_windows[key]
            while window and window[0] < cutoff:
                window.pop(0)
            remaining = max(0, self.order_per_second - len(window))
            return {
                "x-ratelimit-limit": str(self.order_per_second),
                "x-ratelimit-remaining": str(remaining),
                "x-ratelimit-window": "1",
            }
        else:
            cutoff = now - 60.0
            window = self._request_windows[key]
            while window and window[0] < cutoff:
                window.pop(0)
            remaining = max(0, self.requests_per_minute - len(window))
            return {
                "x-ratelimit-limit": str(self.requests_per_minute),
                "x-ratelimit-remaining": str(remaining),
                "x-ratelimit-window": "60",
            }


class RedisRateLimiter:
    """Redis-backed rate limiter using INCR + TTL for sliding windows."""

    def __init__(
        self,
        redis_url: str,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        order_per_second: int = 5,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.order_per_second = order_per_second
        self._redis_url = redis_url
        self._redis = None
        self._fallback = InMemoryRateLimiter(
            requests_per_minute=requests_per_minute,
            burst_size=burst_size,
            order_per_second=order_per_second,
        )

    async def initialize(self) -> None:
        """Initialize Redis connection. Falls back to in-memory on failure."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=1,
            )
            await self._redis.ping()
            logger.info("Redis rate limiter connected")
        except Exception:
            logger.warning(
                "Redis unavailable for rate limiting — using in-memory fallback"
            )
            self._redis = None

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def is_allowed(
        self, key: str, endpoint_type: str = "general"
    ) -> bool:
        """Check rate limit. Falls back to in-memory if Redis fails."""
        if self._redis is None:
            return self._fallback.is_allowed(key, endpoint_type)

        try:
            if endpoint_type == "order":
                return await self._check_redis_rate(
                    f"rl:order:{key}", self.order_per_second, 1
                )
            else:
                # Burst check
                if not await self._check_redis_rate(
                    f"rl:burst:{key}", self.burst_size, 1
                ):
                    return False
                return await self._check_redis_rate(
                    f"rl:minute:{key}", self.requests_per_minute, 60
                )
        except Exception:
            # Fallback to in-memory on Redis error
            logger.warning("Redis rate limit check failed, using fallback")
            return self._fallback.is_allowed(key, endpoint_type)

    async def _check_redis_rate(
        self, key: str, max_count: int, window_seconds: int
    ) -> bool:
        """Atomic INCR + TTL rate check."""
        assert self._redis is not None
        current = await self._redis.incr(key)
        if current == 1:
            await self._redis.expire(key, window_seconds)
        return current <= max_count

    async def get_remaining(
        self, key: str, endpoint_type: str = "general"
    ) -> dict:
        """Return rate limit header info."""
        if self._redis is None:
            return self._fallback.get_remaining(key, endpoint_type)

        try:
            if endpoint_type == "order":
                current = await self._redis.get(f"rl:order:{key}")
                remaining = max(0, self.order_per_second - int(current or 0))
                return {
                    "x-ratelimit-limit": str(self.order_per_second),
                    "x-ratelimit-remaining": str(remaining),
                    "x-ratelimit-window": "1",
                }
            else:
                current = await self._redis.get(f"rl:minute:{key}")
                remaining = max(0, self.requests_per_minute - int(current or 0))
                return {
                    "x-ratelimit-limit": str(self.requests_per_minute),
                    "x-ratelimit-remaining": str(remaining),
                    "x-ratelimit-window": "60",
                }
        except Exception:
            return self._fallback.get_remaining(key, endpoint_type)


def _extract_client_key(request: Request) -> str:
    """Extract rate limit key from request: prefer wallet from JWT, fallback to IP."""
    # Try JWT wallet address
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        from app.auth.service import decode_access_token
        try:
            token = authorization.split(" ", 1)[1]
            payload = decode_access_token(token)
            if payload:
                return f"wallet:{payload.get('sub', 'unknown')}"
        except Exception:
            pass

    # Fallback to IP (supports Cloudflare CF-Connecting-IP header)
    ip = (
        request.headers.get("x-forwarded-for", "")
        or request.headers.get("cf-connecting-ip", "")
        or request.client.host
        if request.client
        else "unknown"
    )
    return f"ip:{ip}"


def _is_order_endpoint(path: str, method: str) -> bool:
    """Check if the request targets an order-placement endpoint."""
    return method == "POST" and "/trades/place" in path


# --- Module-level singleton ---
_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter | RedisRateLimiter:
    """Get the rate limiter singleton (lazy init)."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter(
            requests_per_minute=settings.rate_limit_requests_per_minute,
            burst_size=settings.rate_limit_burst_size,
            order_per_second=settings.rate_limit_order_per_second,
        )
    return _rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware.

    Applies per-client rate limits based on wallet address (from JWT)
    or IP address as fallback.

    Endpoints exempt from rate limiting:
    - /health/* (liveness/readiness probes)
    - /docs, /openapi.json (API documentation)
    - /auth/* (login/signature endpoints)
    """

    EXEMPT_PATHS = ["/health", "/docs", "/openapi.json", "/auth"]

    def __init__(self, app) -> None:
        super().__init__(app)
        self._limiter = get_rate_limiter()

    async def dispatch(
        self, request: StarletteRequest, call_next: Callable[[StarletteRequest], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        # Check if exempt
        path = request.scope.get("path", "")
        for exempt in self.EXEMPT_PATHS:
            if path == exempt or path.startswith(exempt + "/"):
                return await call_next(request)

        # Skip if rate limiting disabled
        if not settings.rate_limit_enabled:
            return await call_next(request)

        client_key = _extract_client_key(request)
        endpoint_type = "order" if _is_order_endpoint(path, request.method) else "general"

        allowed = self._limiter.is_allowed(
            client_key, endpoint_type
        ) if hasattr(self._limiter, "is_allowed") and not hasattr(self._limiter, "_redis") else None

        # Handle async Redis limiter
        if isinstance(self._limiter, RedisRateLimiter):
            allowed = await self._limiter.is_allowed(client_key, endpoint_type)
        else:
            allowed = self._limiter.is_allowed(client_key, endpoint_type)

        if not allowed:
            headers = {}
            if isinstance(self._limiter, RedisRateLimiter):
                headers = await self._limiter.get_remaining(client_key, endpoint_type)
            else:
                headers = self._limiter.get_remaining(client_key, endpoint_type)

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after": 1,
                },
                headers=headers,
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        if isinstance(self._limiter, RedisRateLimiter):
            headers = await self._limiter.get_remaining(client_key, endpoint_type)
        else:
            headers = self._limiter.get_remaining(client_key, endpoint_type)

        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value

        return response
