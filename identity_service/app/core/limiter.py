"""Shared rate limiter (brute-force protection for auth endpoints).

In-memory, keyed by client IP — simple and sufficient for a single instance.
A multi-instance deployment would point slowapi at a shared store (e.g. Redis).
Disabled in tests via `RATE_LIMIT_ENABLED=false`.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=get_settings().rate_limit_enabled,
)
