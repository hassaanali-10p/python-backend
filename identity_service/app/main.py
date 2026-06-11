"""Identity Service entrypoint.

Application 1 of the assessment: the authentication provider. Issues and signs
JWTs (RS256) and exposes a JWKS endpoint that Application 2 uses to validate
those tokens locally.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.jwks import router as jwks_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.user import UserRole
from app.schemas.user import UserCreate
from app.services import auth as auth_service

settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


async def _bootstrap_admin() -> None:
    """Create the configured admin user on startup if it does not yet exist."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    async with SessionLocal() as session:
        existing = await auth_service.get_user_by_email(session, settings.bootstrap_admin_email)
        if existing is not None:
            return
        await auth_service.register_user(
            session,
            UserCreate(
                email=settings.bootstrap_admin_email,
                password=settings.bootstrap_admin_password,
            ),
            role=UserRole.admin,
        )
        logger.info("bootstrap admin created", extra={"email": settings.bootstrap_admin_email})


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("identity-service starting", extra={"environment": settings.environment})
    await _bootstrap_admin()
    yield
    logger.info("identity-service shutting down")


app = FastAPI(
    title="Identity Service",
    description="Authentication provider: registration, login, JWT issuance, RBAC.",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting (brute-force protection); auth endpoints opt in via @limiter.limit.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    """Set a small set of safe HTTP response headers on every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.include_router(health_router)
app.include_router(jwks_router)
app.include_router(auth_router)
app.include_router(users_router)
