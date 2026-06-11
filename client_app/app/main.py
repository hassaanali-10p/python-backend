"""Client Application entrypoint.

Application 2 of the assessment: a resource server that uses the Identity
Service as its authentication provider. It validates issued tokens locally
(via the Identity Service's JWKS) and hosts the Analytics (Task A) and Data
Aggregation (Task B) services.
"""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response

from app.api.aggregation import router as aggregation_router
from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.protected import router as protected_router
from app.core.config import get_settings
from app.core.jwks import JWKSClient
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "client-app starting",
        extra={
            "environment": settings.environment,
            "identity_service_url": settings.identity_service_url,
        },
    )
    # A single shared HTTP client gives connection pooling across JWKS fetches
    # and service-to-service calls (matters for Task B's concurrent fan-out too).
    # A descriptive User-Agent is required by some public APIs (e.g. GitHub);
    # follow_redirects keeps us tolerant of upstreams that 301.
    # follow_redirects=False: the upstreams we call return 200 directly, and not
    # following redirects avoids an SSRF vector (a crafted redirect to an internal
    # address). A descriptive User-Agent is required by some APIs (e.g. GitHub).
    app.state.http_client = httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        follow_redirects=False,
        headers={"User-Agent": "company-snapshot/1.0 (FastAPI assessment)"},
    )
    app.state.jwks_client = JWKSClient(settings.jwks_url, app.state.http_client)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        logger.info("client-app shutting down")


app = FastAPI(
    title="Client Application",
    description="Resource server: token-protected endpoints, analytics, data aggregation.",
    version="0.1.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    """Set a small set of safe HTTP response headers on every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.include_router(health_router)
app.include_router(protected_router)
app.include_router(analytics_router)
app.include_router(aggregation_router)
