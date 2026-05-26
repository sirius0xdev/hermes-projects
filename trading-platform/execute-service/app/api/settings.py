"""Settings API — allows dashboard to set API keys at runtime without K8s secrets.

Keys are stored in the service_config DB table and applied on next executor init.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.config_models import ServiceConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Schemas ──────────────────────────────────────────────────────────

# All known config keys and whether they're secrets (values hidden on read)
CONFIG_KEYS: dict[str, bool] = {
    "jwt_secret_key": True,
    "db_password": True,
    "hyperliquid_private_key": True,
    "hyperliquid_wallet_address": False,
    "hyperliquid_testnet": False,
    "solana_private_key_base58": True,
    "solana_rpc_url": False,
}


class ConfigUpdateRequest(BaseModel):
    jwt_secret_key: str | None = None
    db_password: str | None = None
    hyperliquid_private_key: str | None = None
    hyperliquid_wallet_address: str | None = None
    hyperliquid_testnet: bool | None = None
    solana_private_key_base58: str | None = None
    solana_rpc_url: str | None = None


class ConfigStatusResponse(BaseModel):
    configured: dict[str, bool]  # key -> whether it has been set


# ── Helpers ───────────────────────────────────────────────────────────


async def _get_config(session: AsyncSession, key: str) -> str | None:
    """Get a single config value from the DB."""
    result = await session.execute(
        select(ServiceConfig).where(ServiceConfig.key == key)
    )
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _set_config(session: AsyncSession, key: str, value: str) -> None:
    """Upsert a config value in the DB."""
    result = await session.execute(
        select(ServiceConfig).where(ServiceConfig.key == key)
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(ServiceConfig(key=key, value=value))


def _mask(val: str | None, is_secret: bool) -> str:
    """Mask secret values for display."""
    if not val:
        return ""
    if is_secret and len(val) > 8:
        return val[:4] + "****" + val[-4:]
    return val


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("", response_model=ConfigStatusResponse)
async def get_config_status(session: AsyncSession = Depends(get_session)) -> ConfigStatusResponse:
    """Return which config keys are set (values masked for secrets)."""
    configured: dict[str, bool] = {}
    for key, is_secret in CONFIG_KEYS.items():
        val = await _get_config(session, key)
        configured[key] = val is not None and val != ""
    return ConfigStatusResponse(configured=configured)


@router.post("", response_model=ConfigStatusResponse)
async def update_config(
    req: ConfigUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> ConfigStatusResponse:
    """Update config keys. Only provided keys are changed."""
    updates = req.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key not in CONFIG_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown config key: {key}")
        if isinstance(value, bool):
            await _set_config(session, key, "true" if value else "false")
        else:
            await _set_config(session, key, str(value))
        logger.info("Config updated: %s (masked=%s)", key, CONFIG_KEYS.get(key, True))

    await session.commit()

    # Return updated status
    configured: dict[str, bool] = {}
    for key, is_secret in CONFIG_KEYS.items():
        val = await _get_config(session, key)
        configured[key] = val is not None and val != ""
    return ConfigStatusResponse(configured=configured)