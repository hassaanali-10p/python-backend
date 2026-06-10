"""Authentication and token-lifecycle logic.

Kept separate from the API layer so the rules (hashing, rotation, reuse
detection) are testable in isolation and the routers stay thin.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.jwt import create_access_token
from app.core.security import (
    dummy_verify,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)


class EmailAlreadyExistsError(Exception):
    """Raised when registering an email that is already taken."""


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token is unknown, expired, revoked, or reused."""


# --- Queries -----------------------------------------------------------------

async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


# --- Registration / authentication ------------------------------------------

async def register_user(
    session: AsyncSession, data: UserCreate, *, role: UserRole = UserRole.user
) -> User:
    if await get_user_by_email(session, data.email) is not None:
        raise EmailAlreadyExistsError(data.email)

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("user registered", extra={"user_id": str(user.id), "role": role.value})
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    """Return the user on valid credentials, else None.

    Always performs a password verification (against a dummy hash if the user
    is unknown) so response timing does not reveal whether an account exists.
    """
    user = await get_user_by_email(session, email)
    if user is None:
        dummy_verify(password)
        return None
    if not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user


# --- Refresh-token lifecycle -------------------------------------------------

async def _create_refresh_token(session: AsyncSession, user: User) -> str:
    settings = get_settings()
    raw = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    return raw


async def issue_token_pair(session: AsyncSession, user: User) -> tuple[str, int, str]:
    """Issue a fresh access + refresh token pair. Returns (access, expires_in, refresh)."""
    access_token, expires_in = create_access_token(subject=str(user.id), role=user.role.value)
    refresh_token = await _create_refresh_token(session, user)
    await session.commit()
    return access_token, expires_in, refresh_token


async def _revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str
) -> tuple[User, str, int, str]:
    """Validate + rotate a refresh token. Returns (user, access, expires_in, refresh).

    Reuse of an already-revoked token is treated as theft: every active token
    for that user is revoked and the request is rejected.
    """
    token_hash = hash_refresh_token(raw_token)
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )

    if stored is None:
        raise InvalidRefreshTokenError("unknown token")

    if stored.revoked_at is not None:
        # A revoked token being presented again indicates the token was leaked
        # and replayed after rotation. Revoke the whole family defensively.
        logger.warning("refresh token reuse detected", extra={"user_id": str(stored.user_id)})
        await _revoke_all_for_user(session, stored.user_id)
        await session.commit()
        raise InvalidRefreshTokenError("token reuse detected")

    if stored.expires_at <= datetime.now(timezone.utc):
        raise InvalidRefreshTokenError("expired token")

    user = await get_user_by_id(session, stored.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError("inactive user")

    # Rotate: revoke the presented token and issue a new pair.
    stored.revoked_at = datetime.now(timezone.utc)
    access_token, expires_in = create_access_token(subject=str(user.id), role=user.role.value)
    new_refresh = await _create_refresh_token(session, user)
    await session.commit()
    return user, access_token, expires_in, new_refresh


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> None:
    """Revoke a single refresh token (logout). Idempotent / silent if unknown."""
    token_hash = hash_refresh_token(raw_token)
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        await session.commit()
