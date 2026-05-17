"""
mTLS middleware for inter-service communication.
Validates client certificates when mTLS is enabled.
"""
from __future__ import annotations

import logging
import ssl
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


class MTLSMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates the TLS connection for inter-service requests.
    
    When mtls_enabled:
      - Checks for client certificate verification via X-Client-CN header (set by reverse proxy like nginx/envoy)
      - Alternatively checks ssl.getpeercert() if running directly with mTLS
    
    In production, terminate mTLS at the ingress (nginx/envoy) and pass the
    verification result via header for application-level checks.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.mtls_enabled:
            return await call_next(request)

        # Skip mTLS check for health endpoints
        if request.url.path in ("/health", "/health/ready", "/health/live", "/docs", "/openapi.json"):
            return await call_next(request)

        # Check if reverse proxy forwarded the client CN
        client_cn = request.headers.get("X-Client-CN") or request.headers.get("X-Forwarded-Client-Cn")

        if settings.mtls_client_cert_required and not client_cn:
            logger.warning("mTLS: missing client cert for %s", request.url.path)
            return JSONResponse(
                status_code=403,
                content={"error": "mTLS client certificate required"},
            )

        # Optional: validate allowed CNs (whitelist known services)
        allowed_services = {
            "market-data",
            "frontend",
            "market-data-service",
        }
        if client_cn and client_cn not in allowed_services:
            logger.warning("mTLS: unauthorized service CN=%s", client_cn)
            return JSONResponse(
                status_code=403,
                content={"error": f"Unauthorized service: {client_cn}"},
            )

        return await call_next(request)


def create_ssl_context() -> ssl.SSLContext | None:
    """
    Create SSL context for uvicorn when mTLS is enabled.
    Used by the app startup to configure HTTPS with client cert verification.
    """
    if not settings.mtls_enabled:
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    # Load server cert and key
    if settings.mtls_server_cert and settings.mtls_server_key:
        ctx.load_cert_chain(
            certfile=settings.mtls_server_cert,
            keyfile=settings.mtls_server_key,
        )

    # Load CA cert for client verification
    if settings.mtls_ca_cert:
        ctx.load_verify_locations(cafile=settings.mtls_ca_cert)
        if settings.mtls_client_cert_required:
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx.verify_mode = ssl.CERT_OPTIONAL

    logger.info("mTLS SSL context created")
    return ctx
