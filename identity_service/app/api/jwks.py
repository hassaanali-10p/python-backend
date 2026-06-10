"""JWKS endpoint.

Publishes the RSA public key(s) so that the Client app (and any other resource
server) can verify RS256 access tokens locally, without calling this service on
every request.
"""

from fastapi import APIRouter

from app.core.keys import get_key_pair

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json", summary="JSON Web Key Set (public keys)")
async def jwks() -> dict:
    return get_key_pair().jwks()
