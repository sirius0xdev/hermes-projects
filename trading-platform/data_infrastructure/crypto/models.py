"""SQLAlchemy hybrid column for encrypted storage.

EncryptedColumn stores ciphertext in the database but exposes decrypted values
to Python code. Handles encryption/decryption transparently via column_property
and computed attributes.

"""
import base64
from typing import Any, Callable, Optional

from sqlalchemy import Column, String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

logger = __import__("logging").getLogger(__name__)


class EncryptedColumn:
    """Descriptor that encrypts on set and decrypts on get.

    Usage:
        class MyModel(Base):
            __tablename__ = "my_table"
            id = mapped_column(UUID, primary_key=True)
            _secret_encrypted = mapped_column(String, name="secret_encrypted")

            @property
            def secret(self):
                return decrypt_value(self._secret_encrypted, self._get_key())

            @secret.setter
            def secret(self, value):
                self._secret_encrypted = encrypt_value(value, self._get_key())

    Args:
        name: Database column name (stored as ciphertext base64 string)
        encrypt_fn: Function(plaintext: str, key: bytes) -> str
        decrypt_fn: Function(ciphertext: str, key: bytes) -> str
        key_column: Column name that holds the data key version for rotation
    """

    def __init__(
        self,
        name: str,
        encrypt_fn: Callable[[str, bytes], str],
        decrypt_fn: Callable[[str, bytes], str],
        key_column: Optional[str] = None,
    ):
        self.name = name
        self.encrypt_fn = encrypt_fn
        self.decrypt_fn = decrypt_fn
        self.key_column = key_column or f"{name}_version"
        self.attrs: dict = {}

    def column(self) -> Column:
        """Create the actual DB column for ciphertext."""
        return Column(String, name=self.name)

    def __get__(self, obj: Any, objtype: Any) -> Optional[str]:
        if obj is None:
            return self
        encrypted = getattr(obj, f"_{self.name}", None)
        if encrypted is None:
            return None
        key = obj._get_encryption_key(self.name)
        return self.decrypt_fn(encrypted, key)

    def __set__(self, obj: Any, value: Optional[str]) -> None:
        if value is None:
            setattr(obj, f"_{self.name}", None)
            return
        key = obj._get_encryption_key(self.name)
        encrypted = self.encrypt_fn(value, key)
        setattr(obj, f"_{self.name}", encrypted)


def encrypted_mapped_column(
    python_name: str, db_name: str
) -> Mapped[str]:
    """Helper to create a mapped column for encrypted storage.

    The column stores base64-encoded ciphertext as TEXT.
    """
    return mapped_column(String, name=db_name)
