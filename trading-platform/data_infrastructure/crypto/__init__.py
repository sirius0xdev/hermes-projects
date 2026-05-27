"""Column-level encryption for sensitive AI data at rest.

Uses AES-256-GCM (authenticated encryption) with age-encrypted key material
on disk. Each sensitive column gets its own independent data key.

Architecture:
  - Master key: 32-byte random key, stored age-encrypted on disk
  - Data keys: 32-byte AES-GCM keys, encrypted with master key (XChaCha20-Poly1305)
  - Per-column keys: each encrypted column has a unique data key
  - Ciphertext stored in DB as base64-encoded BYTEA (nonce + ciphertext + tag)

Dependencies:
  - cryptography (PyPI) — AES-GCM encryption
  - age CLI — master key file encryption/decryption

"""
from data_infrastructure.crypto.keys import MasterKeyManager
from data_infrastructure.crypto.aead import encrypt_value, decrypt_value
from data_infrastructure.crypto.models import EncryptedColumn

__all__ = [
    "MasterKeyManager",
    "encrypt_value",
    "decrypt_value",
    "EncryptedColumn",
]
