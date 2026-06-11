"""Service-to-service calls to the Identity Service.

Token *validation* happens locally (via JWKS); this module is only for fetching
data the token doesn't carry — the user's full profile from Identity's `/me`.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class IdentityServiceError(Exception):
    """Raised when the Identity Service is unreachable or returns an error."""


async def fetch_user_profile(
    http_client: httpx.AsyncClient, identity_url: str, bearer_token: str
) -> dict:
    """Call Identity `GET /me` with the user's token and return their profile."""
    url = f"{identity_url.rstrip('/')}/me"
    try:
        response = await http_client.get(
            url, headers={"Authorization": f"Bearer {bearer_token}"}
        )
    except httpx.RequestError as exc:
        logger.warning("identity service unreachable", extra={"error": str(exc)})
        raise IdentityServiceError("identity service unreachable") from exc

    if response.status_code == httpx.codes.OK:
        return response.json()

    # Surface auth failures faithfully; treat anything else as upstream error.
    if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        raise IdentityServiceError("identity rejected the token")
    logger.warning("identity service error", extra={"status": response.status_code})
    raise IdentityServiceError(f"identity service returned {response.status_code}")
