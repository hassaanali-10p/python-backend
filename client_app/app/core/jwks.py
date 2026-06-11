"""JWKS client: fetches the Identity Service's public keys and caches them.

The whole point is to verify tokens *locally*. We fetch the key set once, cache
each key by its `kid`, and reuse it for every subsequent request. We only go back
to the network on a **cache miss** — i.e. a token signed with a `kid` we haven't
seen yet (which is exactly what happens after the Identity Service rotates keys).

A lock guards the refresh so that a burst of requests with a new `kid` triggers a
single fetch, not one per request.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)


class JWKSClient:
    def __init__(self, jwks_url: str, http_client: httpx.AsyncClient) -> None:
        self._url = jwks_url
        self._http = http_client
        self._keys: dict[str, object] = {}
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> object | None:
        """Return the public key for `kid`, refetching once on a cache miss."""
        key = self._keys.get(kid)
        if key is not None:
            return key

        async with self._lock:
            # Another coroutine may have refreshed while we waited for the lock.
            if kid in self._keys:
                return self._keys[kid]
            await self._refresh()

        return self._keys.get(kid)

    async def _refresh(self) -> None:
        logger.info("fetching JWKS", extra={"url": self._url})
        response = await self._http.get(self._url)
        response.raise_for_status()
        jwks = response.json()
        # Build a usable public key object per kid from each JWK entry.
        self._keys = {
            jwk["kid"]: RSAAlgorithm.from_jwk(json.dumps(jwk))
            for jwk in jwks.get("keys", [])
            if "kid" in jwk
        }
        logger.info("JWKS cached", extra={"kids": list(self._keys)})
