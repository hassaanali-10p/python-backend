"""Client Application entrypoint.

Application 2 of the assessment: a resource server that uses the Identity
Service as its authentication provider. It validates issued tokens locally
(via the Identity Service's JWKS) and hosts the Analytics (Task A) and Data
Aggregation (Task B) services.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "client-app starting",
        extra={
            "environment": settings.environment,
            "identity_service_url": settings.identity_service_url,
        },
    )
    yield
    logger.info("client-app shutting down")


app = FastAPI(
    title="Client Application",
    description="Resource server: token-protected endpoints, analytics, data aggregation.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
