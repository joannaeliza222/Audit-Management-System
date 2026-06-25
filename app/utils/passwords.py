"""
Password hashing/verification utilities.

Goals:
- Use modern, memory-hard hashing (Argon2id) for new/updated passwords.
- Maintain backwards compatibility with existing Werkzeug PBKDF2 hashes.
- Avoid logging secrets or sensitive tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash, VerificationError
from werkzeug.security import check_password_hash as werkzeug_check
from werkzeug.security import generate_password_hash as werkzeug_hash


# Reasonable defaults for 8GB RAM environments (server-side).
# You can tune via deployment if needed, but keep within safe bounds.
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    needs_rehash: bool = False


def hash_password(password: str) -> str:
    """
    Hash password using Argon2id.
    """
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> VerifyResult:
    """
    Verify password against stored hash.

    Supports:
    - Argon2id hashes (preferred)
    - Werkzeug PBKDF2 hashes (legacy) and marks them for rehash
    """
    if not stored_hash or not password:
        return VerifyResult(False, False)

    # Argon2 hashes start with "$argon2"
    if stored_hash.startswith("$argon2"):
        try:
            ok = _ph.verify(stored_hash, password)
            if not ok:
                return VerifyResult(False, False)
            return VerifyResult(True, _ph.check_needs_rehash(stored_hash))
        except (VerifyMismatchError, InvalidHash, VerificationError):
            return VerifyResult(False, False)

    # Legacy Werkzeug PBKDF2 (pbkdf2:sha256:...)
    try:
        ok = werkzeug_check(stored_hash, password)
        return VerifyResult(ok, ok)  # if ok, we want to upgrade to Argon2
    except Exception:
        return VerifyResult(False, False)


def hash_password_legacy(password: str) -> str:
    """
    Legacy hash for controlled compatibility scenarios.
    Not used by default.
    """
    return werkzeug_hash(password)

