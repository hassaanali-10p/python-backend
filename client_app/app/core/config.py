"""Application configuration, loaded from environment variables.

The client application is stateless: it has no database of its own. It trusts
the Identity Service for authentication (validating RS256 tokens against the
published JWKS) and calls it over HTTP for user information.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "client-app"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Identity Service (auth provider) ---
    identity_service_url: str = "http://localhost:8001"
    jwks_path: str = "/.well-known/jwks.json"

    # --- Token validation (must match what the Identity Service issues) ---
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "identity-service"
    jwt_audience: str = "client-app"

    # --- Outbound HTTP (external APIs, inter-service calls) ---
    http_timeout_seconds: float = 5.0

    # --- Task A (analytics) ---
    # Upper bound on the range end, so an enormous request can't tie up CPU
    # (a simple DoS guard). The segmented sieve keeps memory flat regardless.
    analytics_max_end: int = 100_000_000

    @property
    def jwks_url(self) -> str:
        return f"{self.identity_service_url.rstrip('/')}{self.jwks_path}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read the environment only once)."""
    return Settings()
