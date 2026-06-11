"""Security-focused checks: password storage, token claims, JWKS."""

import asyncio

import asyncpg
import jwt as pyjwt

from app.core.jwt import decode_access_token
from tests.conftest import TEST_DATABASE_URL, access_token, register, unique_email


async def _fetch_hashed_password(email: str) -> str | None:
    conn = await asyncpg.connect(TEST_DATABASE_URL.replace("+asyncpg", ""))
    try:
        return await conn.fetchval("SELECT hashed_password FROM users WHERE email=$1", email)
    finally:
        await conn.close()


def test_password_is_stored_hashed_not_plaintext(client):
    email = unique_email()
    register(client, email, "supersecret1")
    stored = asyncio.run(_fetch_hashed_password(email))
    assert stored is not None
    assert stored != "supersecret1"          # never store plaintext
    assert stored.startswith("$argon2")       # Argon2 hash


def test_access_token_has_expected_claims(client):
    email = unique_email()
    register(client, email)
    token = access_token(client, email)

    claims = decode_access_token(token)  # verifies signature, iss, aud, exp
    assert claims["iss"] == "identity-service"
    assert claims["aud"] == "client-app"
    assert claims["role"] == "user"
    assert claims["token_type"] == "access"
    assert claims["sub"]  # the user id


def test_jwks_publishes_rsa_key_matching_token_kid(client):
    jwks = client.get("/.well-known/jwks.json").json()
    assert len(jwks["keys"]) >= 1
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["n"] and key["e"]

    # The kid published in JWKS must match the kid in an issued token's header.
    email = unique_email()
    register(client, email)
    token = access_token(client, email)
    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == key["kid"]
