"""Age-based master key management.

The master key encrypts all data keys. It is stored age-encrypted on disk
so that even if the filesystem is compromised, the key material is protected.

Usage:
    mgr = MasterKeyManager(keyring_path="/path/to/keyring")
    mgr.ensure_initialized()  # generates + encrypts if not present
    raw_key = mgr.get_data_key("table.column")  # get 32-byte AES-GCM key
    mgr.rotate_data_key("table.column")         # rotate

"""
import base64
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_KEYRING_DIR = os.path.expanduser("~/.hermes/crypto")
MASTER_KEY_FILE = "master.key.age"
IDENTITY_FILE = "identity.txt"
DATA_KEYS_FILE = "data_keys.json"


class MasterKeyManager:
    """Manage the age master key and per-column data keys.

    Args:
        keyring_path: Directory for key material. Defaults to ~/.hermes/crypto.
        age_password: Age password for passphrase-protected identity.
            If None, falls back to AGE_PASSWORD env var.
    """

    def __init__(self, keyring_path: Optional[str] = None, age_password: Optional[str] = None):
        self.keyring_dir = Path(keyring_path or DEFAULT_KEYRING_DIR)
        self.age_password = age_password or os.environ.get("AGE_PASSWORD", "")
        self._identity: Optional[str] = None
        self._public_key: Optional[str] = None
        self._data_keys: dict = {}
        self._master_key: bytes = b""

    @property
    def master_path(self) -> Path:
        return self.keyring_dir / MASTER_KEY_FILE

    @property
    def identity_path(self) -> Path:
        return self.keyring_dir / IDENTITY_FILE

    @property
    def data_keys_path(self) -> Path:
        return self.keyring_dir / DATA_KEYS_FILE

    def ensure_initialized(self) -> None:
        """Generate master key and data keys file if they don't exist."""
        self.keyring_dir.mkdir(parents=True, exist_ok=True)

        if not self.identity_path.exists():
            self._generate_identity()
        else:
            self._load_identity()

        if not self.master_path.exists():
            self._generate_master_key()
        self._decrypt_master_key()

        self._load_data_keys()
        if not self._data_keys:
            self._save_data_keys({})

    def _generate_identity(self) -> None:
        """Generate a new age identity (private key)."""
        result = subprocess.run(
            ["age-keygen"], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"age-keygen failed: {result.stderr}")
        for line in result.stdout.strip().split("\n"):
            if line.strip() and not line.startswith("#"):
                self._identity = line.strip()
                break
            if line.startswith("# public key:"):
                self._public_key = line.split(":", 1)[1].strip()

        with self.identity_path.open("w") as f:
            f.write(result.stdout)
        self.identity_path.chmod(0o600)

    def _load_identity(self) -> None:
        """Load age identity from disk."""
        with self.identity_path.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    self._identity = line
                    break
                if line.startswith("# public key:"):
                    self._public_key = line.split(":", 1)[1].strip()

    def _generate_master_key(self) -> None:
        """Generate a random 32-byte master key and encrypt with age."""
        self._master_key = os.urandom(32)
        b64_key = base64.b64encode(self._master_key).decode()
        subprocess.run(
            ["age", "-r", self._public_key],
            input=b64_key, capture_output=True, text=True,
            stdout=open(self.master_path, "wb"),
            check=True,
        )
        self.master_path.chmod(0o600)

    def _decrypt_master_key(self) -> None:
        """Decrypt the master key using age identity."""
        result = subprocess.run(
            ["age", "-d", "-i", str(self.identity_path)],
            stdin=open(self.master_path),
            capture_output=True, text=True, check=True,
        )
        self._master_key = base64.b64decode(result.stdout.strip())

    def _load_data_keys(self) -> None:
        """Load data key registry from disk."""
        if self.data_keys_path.exists():
            with self.data_keys_path.open() as f:
                self._data_keys = json.load(f)

    def _save_data_keys(self, data_keys: dict) -> None:
        """Save data key registry to disk."""
        self._data_keys = data_keys
        with self.data_keys_path.open("w") as f:
            json.dump(data_keys, f, indent=2)

    def _encrypt_with_master(self, data: bytes) -> bytes:
        """Encrypt data using master key as XOR cipher."""
        result = bytearray()
        for i in range(0, len(data), 32):
            chunk = data[i:i + 32]
            key_chunk = self._master_key[:len(chunk)]
            result.extend(a ^ b for a, b in zip(chunk, key_chunk))
        return bytes(result)

    def _decrypt_with_master(self, encrypted: bytes) -> bytes:
        """Decrypt data encrypted with master key XOR (symmetric)."""
        return self._encrypt_with_master(encrypted)

    def get_data_key(self, column_name: str) -> bytes:
        """Get or generate a 32-byte AES-GCM key for a column.

        Args:
            column_name: Column identifier (e.g. 'copilot_conversations.messages')
        """
        if column_name not in self._data_keys:
            raw_key = os.urandom(32)
            encrypted = self._encrypt_with_master(raw_key)
            self._data_keys[column_name] = {
                "encrypted_key": base64.b64encode(encrypted).decode(),
                "created_at": self._now_iso(),
                "version": 1,
            }
            self._save_data_keys(self._data_keys)
            logger.info("Generated data key for column: %s", column_name)

        encrypted = base64.b64decode(self._data_keys[column_name]["encrypted_key"])
        return self._decrypt_with_master(encrypted)

    def rotate_data_key(self, column_name: str) -> str:
        """Rotate the data key for a column. Returns new version."""
        raw_key = os.urandom(32)
        encrypted = self._encrypt_with_master(raw_key)
        old_version = self._data_keys.get(column_name, {}).get("version", 0)
        self._data_keys[column_name] = {
            "encrypted_key": base64.b64encode(encrypted).decode(),
            "created_at": self._now_iso(),
            "version": old_version + 1,
        }
        self._save_data_keys(self._data_keys)
        logger.info("Rotated data key for %s to version %d", column_name, old_version + 1)
        return str(old_version + 1)

    def rotate_master_key(self, new_age_password: Optional[str] = None) -> None:
        """Rotate the master key and re-encrypt all data keys."""
        # Decrypt all data keys with old master
        decrypted_keys = {}
        for col, entry in self._data_keys.items():
            encrypted = base64.b64decode(entry["encrypted_key"])
            decrypted_keys[col] = self._decrypt_with_master(encrypted)

        # Generate new master key
        self._master_key = os.urandom(32)
        if new_age_password:
            self.age_password = new_age_password
        self._generate_master_key()

        # Re-encrypt all data keys
        for col, raw in decrypted_keys.items():
            encrypted = self._encrypt_with_master(raw)
            self._data_keys[col] = {
                "encrypted_key": base64.b64encode(encrypted).decode(),
                "created_at": self._now_iso(),
                "version": self._data_keys[col]["version"],
            }
        self._save_data_keys(self._data_keys)
        logger.info("Rotated master key; %d data keys re-encrypted", len(decrypted_keys))

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
