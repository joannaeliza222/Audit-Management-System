"""
Security utilities
- CSRF integration helpers
- Session cookie settings and enforcement helpers
- Rate limiting integration hooks (e.g., decorators for login)
- Export sanitization (e.g., excel_safe)
- Encryption helpers for document storage
"""

import os
from cryptography.fernet import Fernet


def generate_encryption_key():
    """Generate a new encryption key for document storage"""
    return Fernet.generate_key().decode()


def encrypt_data(data: bytes, key: str) -> bytes:
    """Encrypt data using Fernet symmetric encryption"""
    f = Fernet(key.encode())
    return f.encrypt(data)


def decrypt_data(encrypted_data: bytes, key: str) -> bytes:
    """Decrypt data using Fernet symmetric encryption"""
    f = Fernet(key.encode())
    return f.decrypt(encrypted_data)


def excel_safe(value):
    s = "" if value is None else str(value)
    if s.startswith(("=", "+", "-", "@")):
        return "'" + s
    return s
