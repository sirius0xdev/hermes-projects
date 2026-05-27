"""AES-256-GCM authenticated encryption.

Provides encrypt/decrypt primitives that store nonce+ciphertext+tag as a single
BYTEA value suitable for PostgreSQL BYTEA columns.

Ciphertext format (stored as bytes):
  [12-byte nonce][ciphertext+16-byte GCM tag]

"""
import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

NONCE_SIZE = 12  # 96-bit nonce for GCM


def encrypt_value(plaintext: str, data_key: bytes) -> str:
    """Encrypt a string value with AES-256-GCM.

    Returns base64-encoded ciphertext (nonce + ciphertext + tag).

    Args:
        plaintext: String to encrypt (UTF-8 encoded)
        data_key: 32-byte AES-256-GCM key
    """
    aesgcm = AESGCM(data_key)
    nonce = os.urandom(NONCE_SIZE)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # ct is nonce+ciphertext+tag
    return base64.b64encode(ct).decode("ascii")


def decrypt_value(b64_ciphertext: str, data_key: bytes) -> str:
    """Decrypt a base64-encoded AES-256-GCM value.

    Args:
        b64_ciphertext: Base64-encoded (nonce + ciphertext + tag)
        data_key: 32-byte AES-256-GCM key
    """
    ct = base64.b64decode(b64_ciphertext)
    # Split nonce from ciphertext+tag
    nonce = ct[:NONCE_SIZE]
    ct_only = ct[NONCE_SIZE:]
    aesgcm = AESGCM(data_key)
    plaintext_bytes = aesgcm.decrypt(nonce, ct_only, None)
    return plaintext_bytes.decode("utf-8")


def encrypt_bytes(raw: bytes, data_key: bytes) -> str:
    """Encrypt raw bytes with AES-256-GCM (for embeddings etc.).

    Returns base64-encoded ciphertext.
    """
    aesgcm = AESGCM(data_key)
    nonce = os.urandom(NONCE_SIZE)
    ct = aesgcm.encrypt(nonce, raw, None)
    return base64.b64encode(ct).decode("ascii")


def decrypt_bytes(b64_ciphertext: str, data_key: bytes) -> bytes:
    """Decrypt base64-encoded bytes."""
    ct = base64.b64decode(b64_ciphertext)
    nonce = ct[:NONCE_SIZE]
    ct_only = ct[NONCE_SIZE:]
    aesgcm = AESGCM(data_key)
    return aesgcm.decrypt(nonce, ct_only, None)


def generate_data_key() -> bytes:
    """Generate a random 32-byte AES-256-GCM key."""
    return os.urandom(32)
