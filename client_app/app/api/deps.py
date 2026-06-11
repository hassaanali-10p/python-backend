"""Shared API dependencies for the Client App.

Authentication is done by validating the RS256 token locally against the cached
JWKS public key — no per-request call to the Identity Service. Authorization uses
the `role` claim carried inside the token, so it needs no lookup either.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.jwks import JWKSClient
from app.core.security import TokenError, verify_access_token

# auto_error=False so we can return 401 (not FastAPI's default 403) when the
# Authorization header is missing.
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_jwks_client(request: Request) -> JWKSClient:
    return request.app.state.jwks_client


async def get_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _UNAUTHENTICATED
    return credentials.credentials


TokenDep = Annotated[str, Depends(get_token)]


async def get_current_claims(
    token: TokenDep,
    jwks_client: Annotated[JWKSClient, Depends(get_jwks_client)],
) -> dict:
    try:
        return await verify_access_token(token, jwks_client)
    except TokenError:
        raise _UNAUTHENTICATED


CurrentClaims = Annotated[dict, Depends(get_current_claims)]


def require_role(*roles: str):
    """Dependency factory enforcing that the token's role is one of `roles`."""

    async def checker(claims: CurrentClaims) -> dict:
        if claims.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return claims

    return checker
