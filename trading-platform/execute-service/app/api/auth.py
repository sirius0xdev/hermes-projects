"""Wallet authentication API endpoints."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session
from app.models.auth_models import AuthNonce, WalletSession
from app.auth.service import (
    generate_nonce,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    verify_evm_signature,
    verify_solana_signature,
    construct_siwe_message,
    construct_siws_message,
    _hash_token,
)
from app.models.auth_schemas import (
    NonceRequest,
    NonceResponse,
    VerifyRequest,
    VerifyResponse,
    RefreshResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["wallet-auth"])


@router.post("/nonces", response_model=NonceResponse)
async def request_nonce(req: NonceRequest, session: AsyncSession = Depends(get_session)) -> NonceResponse:
    """Generate a one-time nonce for wallet sign-in."""
    nonce = generate_nonce()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    record = AuthNonce(
        nonce=nonce,
        wallet_address=req.wallet_address.lower(),
        chain=req.chain,
        expires_at=expires_at,
    )
    session.add(record)
    await session.commit()

    return NonceResponse(nonce=nonce, expires_at=expires_at.isoformat())


@router.post("/verify", response_model=VerifyResponse)
async def verify_signature(
    req: VerifyRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> VerifyResponse:
    """Verify wallet signature and issue JWT session tokens."""
    stmt = select(AuthNonce).where(
        AuthNonce.wallet_address == req.wallet_address.lower(),
        AuthNonce.used == False,
        AuthNonce.chain == req.chain,
    )
    result = await session.execute(stmt)
    nonce_records = result.scalars().all()

    if not nonce_records:
        raise HTTPException(status_code=400, detail="No pending nonce for this wallet")

    # Find the matching nonce by parsing the message
    message_nonce: str | None = None
    for nr in nonce_records:
        if nr.nonce in req.message and not nr.used:
            message_nonce = nr.nonce
            break

    if not message_nonce:
        raise HTTPException(status_code=400, detail="Nonce not found in message or already used")

    # Verify signature
    valid = False
    if req.chain in ("ethereum", "base"):
        valid = verify_evm_signature(req.message, req.signature, req.wallet_address)
    elif req.chain == "solana":
        valid = verify_solana_signature(req.message, req.signature, req.wallet_address)

    if not valid:
        raise HTTPException(status_code=401, detail="Signature verification failed")

    # Mark nonce as used
    for nr in nonce_records:
        if nr.nonce == message_nonce:
            nr.used = True
            break
    await session.commit()

    # Issue tokens
    jti = str(uuid.uuid4())
    access_token = create_access_token(req.wallet_address, req.chain, jti)
    refresh_token = create_refresh_token()
    refresh_hash = _hash_token(refresh_token)

    # Save refresh token in DB
    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session_record = WalletSession(
        jti=jti,
        wallet_address=req.wallet_address.lower(),
        chain=req.chain,
        scope="trading:read,trading:write",
        refresh_token_hash=refresh_hash,
        expires_at=expires_at,
    )
    session.add(session_record)
    await session.commit()

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )

    return VerifyResponse(
        access_token=access_token,
        refresh_token="",  # sent via cookie
        wallet_address=req.wallet_address,
        chain=req.chain,
        expires_in=15 * 60,  # 15 minutes
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_session(
    response: Response,
    refresh_token: str = Cookie(None),
    session: AsyncSession = Depends(get_session),
) -> RefreshResponse:
    """Refresh access token using rotation strategy."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    refresh_hash = _hash_token(refresh_token)
    stmt = select(WalletSession).where(
        WalletSession.refresh_token_hash == refresh_hash,
        WalletSession.revoked == False,
        WalletSession.expires_at > datetime.now(timezone.utc),
    )
    result = await session.execute(stmt)
    session_record = result.scalar_one_or_none()

    if not session_record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # ROTATION: revoke old refresh token
    session_record.revoked = True

    # Issue new tokens with new JTI
    new_jti = str(uuid.uuid4())
    new_access_token = create_access_token(
        session_record.wallet_address,
        session_record.chain,
        new_jti,
    )
    new_refresh_token = create_refresh_token()
    new_refresh_hash = _hash_token(new_refresh_token)

    # Create new session record
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    new_session_record = WalletSession(
        jti=new_jti,
        wallet_address=session_record.wallet_address,
        chain=session_record.chain,
        scope=session_record.scope,
        refresh_token_hash=new_refresh_hash,
        expires_at=expires_at,
    )
    session.add(new_session_record)
    await session.commit()

    # Set new refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )

    return RefreshResponse(
        access_token=new_access_token,
        refresh_token="",  # sent via cookie
        expires_in=15 * 60,
    )
