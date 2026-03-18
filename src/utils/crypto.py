"""AES-256-GCM encryption, bcrypt PIN hashing, session ID generation."""

import base64
import hashlib
import os
import uuid

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12  # 96-bit GCM nonce


def _derive_key(key: str) -> bytes:
    return hashlib.sha256(key.encode("utf-8")).digest()


def encrypt_value(value: str, key: str) -> str:
    if not value:
        raise ValueError("Cannot encrypt an empty value")
    if not key:
        raise ValueError("Encryption key must not be empty")

    derived = _derive_key(key)
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(derived)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

    packed = nonce + ciphertext
    return base64.urlsafe_b64encode(packed).decode("ascii")


def decrypt_value(encrypted: str, key: str) -> str:
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
    if not pin:
        raise ValueError("PIN must not be empty")
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_pin(pin: str, hashed: str) -> bool:
    if not pin or not hashed:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def generate_session_id() -> str:
    return str(uuid.uuid4())
