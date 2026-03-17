"""
Cryptographic utilities for the AI assistant.

Provides AES-256-GCM encryption/decryption, bcrypt PIN hashing,
and secure session ID generation.
"""

import base64
import hashlib
import os
import uuid

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# AES-256-GCM nonce size (96 bits is the recommended size for GCM)
_NONCE_SIZE = 12  # bytes


def _derive_key(key: str) -> bytes:
    """
    Derive a 256-bit key from an arbitrary string using SHA-256.

    This ensures a consistent 32-byte key regardless of input length.
    For production use, the caller should provide a key with sufficient
    entropy (e.g., a 32+ character random string or the output of a KDF).
    """
    return hashlib.sha256(key.encode("utf-8")).digest()


def encrypt_value(value: str, key: str) -> str:
    """
    Encrypt a string value using AES-256-GCM.

    Args:
        value: Plaintext string to encrypt.
        key: Encryption key (will be derived to 256 bits via SHA-256).

    Returns:
        Base64-encoded string containing nonce + ciphertext + tag.

    Raises:
        ValueError: If value or key is empty.
    """
    if not value:
        raise ValueError("Cannot encrypt an empty value")
    if not key:
        raise ValueError("Encryption key must not be empty")

    derived = _derive_key(key)
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(derived)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

    # Pack as nonce || ciphertext (GCM tag is appended by the library)
    packed = nonce + ciphertext
    return base64.urlsafe_b64encode(packed).decode("ascii")


def decrypt_value(encrypted: str, key: str) -> str:
    """
    Decrypt an AES-256-GCM encrypted string.

    Args:
        encrypted: Base64-encoded string from encrypt_value().
        key: Same key used for encryption.

    Returns:
        Original plaintext string.

    Raises:
        ValueError: If inputs are empty or decryption fails (wrong key / tampered data).
    """
    if not encrypted:
        raise ValueError("Cannot decrypt an empty value")
    if not key:
        raise ValueError("Decryption key must not be empty")

    derived = _derive_key(key)
    packed = base64.urlsafe_b64decode(encrypted.encode("ascii"))

    if len(packed) < _NONCE_SIZE + 16:
        raise ValueError("Encrypted data is too short (corrupted or invalid)")

    nonce = packed[:_NONCE_SIZE]
    ciphertext = packed[_NONCE_SIZE:]

    aesgcm = AESGCM(derived)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError("Decryption failed — wrong key or tampered data") from exc

    return plaintext.decode("utf-8")


def hash_pin(pin: str) -> str:
    """
    Hash a security PIN using bcrypt.

    Args:
        pin: The PIN string to hash.

    Returns:
        Bcrypt hash string (safe to store in config/database).

    Raises:
        ValueError: If PIN is empty.
    """
    if not pin:
        raise ValueError("PIN must not be empty")
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_pin(pin: str, hashed: str) -> bool:
    """
    Verify a PIN against its bcrypt hash.

    Args:
        pin: Plaintext PIN to verify.
        hashed: Bcrypt hash string from hash_pin().

    Returns:
        True if the PIN matches, False otherwise.
    """
    if not pin or not hashed:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def generate_session_id() -> str:
    """
    Generate a cryptographically random session ID using UUID4.

    Returns:
        UUID4 string (e.g., "550e8400-e29b-41d4-a716-446655440000").
    """
    return str(uuid.uuid4())
