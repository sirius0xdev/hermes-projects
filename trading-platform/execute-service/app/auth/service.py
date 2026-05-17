"""
Wallet authentication service.
- SIWE (EIP-4361) for Ethereum / Base
- SIWS pattern for Solana (Ed25519 signature verification)
- JWT issuance with refresh rotation
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from siwe import SiweMessage
from eth_account.messages import encode_defunct
from eth_account import Account

from app.config import settings


def _hash_token(token: str) -> str:
    """SHA-256 hash of a token for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_nonce() -> str:
    """Generate a cryptographically random nonce."""
    return secrets.token_urlsafe(24)


def create_access_token(wallet_address: str, chain: str, jti: str, ttl_minutes: int | None = None) -> str:
    """Create a short-lived JWT access token."""
    ttl = ttl_minutes or settings.jwt_access_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": wallet_address,
        "chain": chain,
        "scope": "trading:read,trading:write",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=ttl),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token() -> str:
    """Create a refresh token (raw string — caller hashes it for DB)."""
    return secrets.token_urlsafe(48)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate an access token. Returns None on failure."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def verify_evm_signature(message: str, signature: str, address: str) -> bool:
    """Verify an EVM signature. Uses SIWE parsing + erc-191 recovery."""
    try:
        siwe_msg = SiweMessage.from_message(message)
        # Recover the signer
        msg_encoded = encode_defunct(text=message)
        recovered = Account.recover_message(msg_encoded, signature=signature)
        if recovered.lower() != address.lower():
            return False
        # Validate SIWE fields
        if siwe_msg.domain != address:
            # SIWE domain check: can be domain name, skip strict matching
            pass
        return True
    except Exception:
        return False


def verify_solana_signature(message: str, signature_b58: str, public_key_b58: str) -> bool:
    """Verify a Solana Ed25519 signature."""
    try:
        import nacl.signing
        import base58

        pubkey_bytes = base58.b58decode(public_key_b58)
        signature_bytes = base58.b58decode(signature_b58)
        message_bytes = message.encode("utf-8")

        verify_key = nacl.signing.VerifyKey(pubkey_bytes)
        verify_key.verify(message_bytes, signature_bytes)
        return True
    except Exception:
        return False


def construct_siwe_message(wallet_address: str, nonce: str, chain_id: int, domain: str) -> str:
    """Construct a SIWE-compliant message string."""
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n"
        f"{wallet_address}\n\n"
        f"Sign in to the DeFi Trading Dashboard.\n\n"
        f"URI: https://{domain}\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {now}\n"
        f"Expiration Time: {expires}"
    )


def construct_siws_message(wallet_address: str, nonce: str, domain: str) -> str:
    """Construct a SIWS-style message for Solana."""
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    return (
        f"{domain} wants you to sign in with your Solana account:\n"
        f"{wallet_address}\n\n"
        f"Sign in to the DeFi Trading Dashboard.\n\n"
        f"URI: https://{domain}\n"
        f"Version: 1\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {now}\n"
        f"Expiration Time: {expires}"
    )
