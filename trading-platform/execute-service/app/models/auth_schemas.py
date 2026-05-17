"""Pydantic schemas for wallet auth API requests/responses."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class NonceRequest(BaseModel):
    wallet_address: str = Field(..., min_length=1, max_length=64)
    chain: Literal["ethereum", "base", "solana"]


class NonceResponse(BaseModel):
    nonce: str
    expires_at: str


class VerifyRequest(BaseModel):
    chain: Literal["ethereum", "base", "solana"]
    wallet_address: str = Field(..., min_length=1, max_length=64)
    message: str
    signature: str
    chain_id: int | None = None


class VerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    wallet_address: str
    chain: str
    expires_in: int


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class SessionInfo(BaseModel):
    wallet_address: str
    chain: str
    scope: str
    jti: str
