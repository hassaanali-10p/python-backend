"""Security primitives: password hashing and refresh-token handling.

- Passwords are hashed with Argon2 (memory-hard) via pwdlib.
- `verify_password` is paired with `dummy_verify` so that login can spend the
  same CPU cost whether or not the user exists, defeating timing-based account
  enumeration.
- Refresh tokens are opaque, cryptographically-random strings. We never store
  the raw value — only a SHA-256 hash — so a database leak does not expose
  usable tokens. (SHA-256 is appropriate here because the input is high-entropy
  random, unlike a low-entropy password.)
"""

from __future__ import annotations

import hashlib
import secrets

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()

# Precomputed hash of a random throwaway password, used to keep login timing
# constant when the supplied email does not exist.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def dummy_verify(password: str) -> None:
    """Verify against a throwaway hash to equalize timing for unknown users."""
    _password_hash.verify(password, _DUMMY_HASH)


def generate_refresh_token() -> str:
    """Return a new opaque, URL-safe refresh token (~256 bits of entropy)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage/lookup (constant length, hex)."""
    return hashlib.sha256(token.encode()).hexdigest()
