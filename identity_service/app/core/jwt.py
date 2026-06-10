"""Access-token encoding/decoding (RS256).

Access tokens are short-lived JWTs signed with the service's RSA private key.
The Identity Service decodes them for its own protected endpoints; the Client
app decodes them independently using the published JWKS public key.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings
from app.core.keys import get_key_pair


class TokenError(Exception):
    """Raised when an access token is missing, malformed, or invalid."""


def create_access_token(*, subject: str, role: str) -> tuple[str, int]:
    """Sign an access token for `subject`. Returns (token, expires_in_seconds)."""
    settings = get_settings()
    key_pair = get_key_pair()
    now = datetime.now(timezone.utc)
    expires_in = settings.access_token_ttl_seconds

    claims = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": subject,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }
    token = jwt.encode(
        claims,
        key_pair.private_pem,
        algorithm=settings.jwt_algorithm,
        headers={"kid": key_pair.kid},
    )
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Validate signature, issuer, audience, and expiry. Raise TokenError if invalid."""
    settings = get_settings()
    key_pair = get_key_pair()
    try:
        claims = jwt.decode(
            token,
            key_pair.public_pem,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if claims.get("token_type") != "access":
        raise TokenError("not an access token")
    return claims
