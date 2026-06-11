"""Test fixtures for the Identity Service.

These are integration tests against a **real Postgres** (the app is async +
Postgres-specific — tz-aware timestamps, a native enum — which SQLite would not
faithfully reproduce). The test database is created automatically; you only need
a running Postgres reachable via `TEST_DATABASE_URL`, supplied through the
environment (a gitignored `.env.test` locally, or CI). See `.env.test.example`.
"""

import asyncio
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Configure the environment BEFORE importing the app (settings read it on import).
# The test database URL is not hardcoded: it comes from the environment, loaded
# from a gitignored `.env.test` locally (see `.env.test.example`) or injected by
# CI. No fallback — fail fast if absent, like the app's required `database_url`.
load_dotenv(Path(__file__).resolve().parent.parent / ".env.test")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# example.com is reserved for testing (RFC 2606); .local is rejected by email-validator.
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
# Generated per run — never a hardcoded secret literal.
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", secrets.token_urlsafe(16))
os.environ.pop("JWT_PRIVATE_KEY_PATH", None)  # ephemeral key for the test run

import asyncpg  # noqa: E402
import jwt as pyjwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.keys import get_key_pair  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401  (registers models on Base.metadata)
from app.main import app  # noqa: E402

ADMIN_EMAIL = os.environ["BOOTSTRAP_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["BOOTSTRAP_ADMIN_PASSWORD"]


async def _bootstrap_database() -> None:
    # Create the test database if it doesn't exist (connect to the maintenance db).
    sys_dsn = TEST_DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[1]
    conn = await asyncpg.connect(sys_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    # Fresh schema for the test session.
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database():
    asyncio.run(_bootstrap_database())
    yield


@pytest.fixture(scope="session")
def client(_database):
    # One TestClient for the session: lifespan runs once (seeds the bootstrap
    # admin) and the app's async engine pool binds to a single event loop.
    with TestClient(app) as c:
        yield c


# --- Helpers -----------------------------------------------------------------

def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def register(client: TestClient, email: str, password: str = "supersecret1"):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client: TestClient, email: str, password: str = "supersecret1"):
    return client.post("/auth/login", data={"username": email, "password": password})


def access_token(client: TestClient, email: str, password: str = "supersecret1") -> str:
    return login(client, email, password).json()["access_token"]


def make_expired_token(sub: str = "00000000-0000-0000-0000-000000000000") -> str:
    """An otherwise-valid access token signed by the app's key, but expired."""
    settings = get_settings()
    kp = get_key_pair()
    now = datetime.now(timezone.utc)
    claims = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": sub,
        "role": "user",
        "iat": now - timedelta(hours=1),
        "nbf": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=30),
        "jti": "expired",
        "token_type": "access",
    }
    return pyjwt.encode(claims, kp.private_pem, algorithm="RS256", headers={"kid": kp.kid})
