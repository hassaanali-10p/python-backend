"""Protected resource endpoints — demonstrate cross-service auth.

- /whoami        : reads identity straight from the validated token (no network).
- /profile       : fetches the full profile from the Identity Service (/me).
- /admin/summary : role-gated example (admin only).
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    CurrentClaims,
    TokenDep,
    get_http_client,
    require_role,
)
from app.core.config import get_settings
from app.services.identity import IdentityServiceError, fetch_user_profile

router = APIRouter(tags=["protected"])


@router.get("/whoami", summary="Identity from the token (validated locally)")
async def whoami(claims: CurrentClaims) -> dict:
    return {"user_id": claims["sub"], "role": claims["role"], "issuer": claims["iss"]}


@router.get("/profile", summary="Full profile fetched from the Identity Service")
async def profile(
    token: TokenDep,
    _claims: CurrentClaims,  # ensures the token is valid before we call out
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> dict:
    settings = get_settings()
    try:
        return await fetch_user_profile(http_client, settings.identity_service_url, token)
    except IdentityServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not retrieve profile: {exc}",
        )


@router.get(
    "/admin/summary",
    summary="Admin-only resource (role from token)",
    dependencies=[Depends(require_role("admin"))],
)
async def admin_summary() -> dict:
    return {"message": "Welcome, admin. This resource is role-gated by the token."}
