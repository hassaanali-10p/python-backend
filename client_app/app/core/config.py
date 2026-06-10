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

    # --- Outbound HTTP (external APIs, inter-service calls) ---
    http_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read the environment only once)."""
    return Settings()
