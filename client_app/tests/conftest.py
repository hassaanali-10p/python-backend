"""Test fixtures for the Client App.

Fully offline: a throwaway RSA keypair stands in for the Identity Service's
signing key, its public half is served as a mocked JWKS (via respx), and tokens
are minted locally. No Identity Service, Postgres, or network required.
"""

import json
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.core.config import get_settings
from app.main import app

# --- A signing key the tests control (mirrors Identity's private key) ---
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
KID = "test-key-1"

_jwk = json.loads(RSAAlgorithm.to_jwk(_private_key.public_key()))
_jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
JWKS = {"keys": [_jwk]}

_settings = get_settings()
JWKS_URL = _settings.jwks_url  # what the JWKSClient will fetch


def make_token(
    *,
    sub: str = "11111111-1111-1111-1111-111111111111",
    role: str = "user",
    audience: str = _settings.jwt_audience,
    issuer: str = _settings.jwt_issuer,
    token_type: str = "access",
    expired: bool = False,
    kid: str = KID,
) -> str:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(minutes=15)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": sub,
        "role": role,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "token_type": token_type,
    }
    return pyjwt.encode(claims, PRIVATE_PEM, algorithm="RS256", headers={"kid": kid})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    # Function-scoped: each test gets a fresh JWKS cache (new lifespan).
    with TestClient(app) as c:
        yield c


@pytest.fixture
def jwks_route(respx_mock):
    """Serve the test public key at the JWKS URL the client will call."""
    respx_mock.get(JWKS_URL).respond(json=JWKS)
    return respx_mock
