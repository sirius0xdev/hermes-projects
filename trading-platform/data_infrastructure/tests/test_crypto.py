"""Tests for AES-256-GCM encryption primitives."""
import os
import pytest
from data_infrastructure.crypto.aead import (
    encrypt_value,
    decrypt_value,
    encrypt_bytes,
    decrypt_bytes,
    generate_data_key,
)


@pytest.fixture
def data_key():
    return generate_data_key()


class TestAESSymmetric:
    def test_encrypt_decrypt_string(self, data_key):
        original = "This is a sensitive message about trading strategy."
        encrypted = encrypt_value(original, data_key)
        decrypted = decrypt_value(encrypted, data_key)
        assert decrypted == original

    def test_encrypt_decrypt_empty_string(self, data_key):
        original = ""
        encrypted = encrypt_value(original, data_key)
        decrypted = decrypt_value(encrypted, data_key)
        assert decrypted == original

    def test_encrypt_decrypt_long_string(self, data_key):
        original = "A" * 10000  # 10KB string
        encrypted = encrypt_value(original, data_key)
        decrypted = decrypt_value(encrypted, data_key)
        assert decrypted == original

    def test_encrypt_decrypt_unicode(self, data_key):
        original = "策略加密测试 \u2764\ufe0f trading \u03b1\u03b2\u03b3"
        encrypted = encrypt_value(original, data_key)
        decrypted = decrypt_value(encrypted, data_key)
        assert decrypted == original

    def test_different_ciphertext_same_plaintext(self, data_key):
        """Different nonces should produce different ciphertext even for same input."""
        original = "same message"
        ct1 = encrypt_value(original, data_key)
        ct2 = encrypt_value(original, data_key)
        assert ct1 != ct2
        assert decrypt_value(ct1, data_key) == original
        assert decrypt_value(ct2, data_key) == original

    def test_wrong_key_fails(self, data_key):
        """Decrypting with wrong key should raise an exception."""
        original = "secret message"
        encrypted = encrypt_value(original, data_key)
        wrong_key = generate_data_key()
        with pytest.raises(Exception):
            decrypt_value(encrypted, wrong_key)


class TestBytesEncryption:
    def test_encrypt_decrypt_bytes(self, data_key):
        original = b'\x00\x01\x02\xff\xfe\xfd' * 100
        encrypted = encrypt_bytes(original, data_key)
        decrypted = decrypt_bytes(encrypted, data_key)
        assert decrypted == original

    def test_encrypt_embedding_vector(self, data_key):
        """Test with realistic embedding vector size (1536 floats * 4 bytes)."""
        import struct
        floats = [0.1 * i for i in range(1536)]
        raw = struct.pack(f'{len(floats)}f', *floats)
        encrypted = encrypt_bytes(raw, data_key)
        decrypted = decrypt_bytes(encrypted, data_key)
        assert decrypted == raw

    def test_different_ciphertext_bytes(self, data_key):
        original = b'\xde\xad\xbe\xef'
        ct1 = encrypt_bytes(original, data_key)
        ct2 = encrypt_bytes(original, data_key)
        assert ct1 != ct2


class TestKeyGeneration:
    def test_generate_32_byte_key(self):
        key = generate_data_key()
        assert len(key) == 32

    def test_keys_are_unique(self):
        keys = [generate_data_key() for _ in range(10)]
        assert len(set(keys)) == 10
