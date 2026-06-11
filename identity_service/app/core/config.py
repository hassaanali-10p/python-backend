"""Application configuration, loaded from environment variables.

Settings follow the 12-factor approach: every deployment-specific value comes
from the environment, with sensible local-development defaults so the service
can boot without a .env file during development.
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
    app_name: str = "identity-service"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Database ---
    # Required: no default, so a misconfigured deployment fails loudly at
    # startup instead of silently falling back to a localhost guess. Never
    # embed connection strings/credentials in source — they come from the env.
    database_url: str

    # --- JWT / token settings ---
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "identity-service"
    jwt_audience: str = "client-app"
    # Path to a PEM-encoded RSA private key. If set and the file exists it is
    # loaded; if set and missing it is generated and persisted there. If unset,
    # an ephemeral key is generated in memory (dev only — see core/keys.py).
    jwt_private_key_path: str | None = None
    access_token_ttl_seconds: int = 15 * 60          # 15 minutes
    refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 days

    # --- Optional bootstrap admin (for demonstrating RBAC) ---
    # If both are set, an admin user is created on startup when absent.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # --- Rate limiting (brute-force protection on auth endpoints) ---
    rate_limit_enabled: bool = True
    auth_rate_limit: str = "5/minute"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read the environment only once)."""
    return Settings()
