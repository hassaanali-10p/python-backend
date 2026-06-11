"""Local RS256 access-token verification.

Mirrors the Identity Service's `decode_access_token`, except it verifies with the
**public** key fetched from JWKS (the Client never has the private key). No call
to the Identity Service is made on this path.
"""

from __future__ import annotations

import jwt

from app.core.config import get_settings
from app.core.jwks import JWKSClient


class TokenError(Exception):
    """Raised when an access token is missing, malformed, or invalid."""


async def verify_access_token(token: str, jwks_client: JWKSClient) -> dict:
    settings = get_settings()

    # The header tells us which key signed the token; fetch it from JWKS (cached).
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError("malformed token header") from exc

    kid = header.get("kid")
    if not kid:
        raise TokenError("missing kid")

    public_key = await jwks_client.get_key(kid)
    if public_key is None:
        raise TokenError("unknown signing key")

    try:
        claims = jwt.decode(
            token,
            public_key,
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
