"""
Application configuration — reads from environment variables / .env file.

DATABASE_URL is the single authoritative PostgreSQL connection string.
Render provides it in postgresql:// format.
The application derives both sync (psycopg2) and async (asyncpg) URLs from it.
"""
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from functools import lru_cache
import re


class Settings(BaseSettings):
    # ── Database (single authoritative source) ────────────────────────────────
    # Render supplies a standard postgresql:// URL via DATABASE_URL.
    # DATABASE_URL_SYNC is accepted as an alias for backwards compatibility.
    # Both psycopg2 and asyncpg URLs are derived from this one value.
    database_url: str = Field(
        default="postgresql://waterford:waterford_dev@localhost:5432/waterford_si",
        alias="DATABASE_URL",
    )
    database_url_sync_override: str = Field(default="", alias="DATABASE_URL_SYNC")

    # Derived — see model_validator below
    database_url_sync: str = ""         # psycopg2 DSN (postgresql:// format)
    database_url_async: str = ""        # asyncpg URL (postgresql+asyncpg://)

    database_url_test: str = Field(
        default='postgresql+asyncpg://waterford:waterford_dev@localhost:5433/waterford_si_test',
        alias='DATABASE_URL_TEST',
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Clerk Auth ────────────────────────────────────────────────────────────
    clerk_secret_key: str = Field(default="")
    clerk_publishable_key: str = Field(default="")
    clerk_jwks_url: str = Field(default="")

    # ── Redis / Celery (optional — not required for current functionality) ────
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = Field(default="development")
    app_secret_key: str = Field(default="change_this_in_production")  # MUST override in production
    # ALLOWED_ORIGINS: plain Render-style string — NOT a list field.
    # Pydantic-Settings JSON-parses list fields from env; we avoid that
    # by reading as str, then splitting in the @property below.
    # Single:   ALLOWED_ORIGINS=https://waterford-si-frontend.onrender.com
    # Multiple: ALLOWED_ORIGINS=https://a.example.com,https://b.example.com
    allowed_origins_raw: str = Field(
        default="http://localhost:5173",
        alias="ALLOWED_ORIGINS",
    )
    log_level: str = Field(default="info")

    @model_validator(mode="after")
    def derive_db_urls(self) -> "Settings":
        """
        Derive sync and async database URLs from the single DATABASE_URL.

        If DATABASE_URL_SYNC is explicitly set, it takes precedence for sync
        (legacy support for psycopg2 host= DSN format).
        """
        # Choose base URL
        base = self.database_url_sync_override or self.database_url

        # Normalise: convert psycopg2 host= DSN → postgresql:// URL
        if base.startswith("host="):
            parts = dict(tok.split("=", 1) for tok in base.split() if "=" in tok)
            base = "postgresql://{user}:{password}@{host}:{port}/{dbname}".format(
                user=parts.get("user", "waterford"),
                password=parts.get("password", ""),
                host=parts.get("host", "localhost"),
                port=parts.get("port", "5432"),
                dbname=parts.get("dbname", "waterford_si"),
            )

        # Strip asyncpg prefix if present
        base_clean = re.sub(r"^postgresql\+asyncpg://", "postgresql://", base)

        # Sync URL: psycopg2-compatible (standard postgresql://)
        self.database_url_sync = base_clean

        # Async URL: asyncpg-compatible
        self.database_url_async = re.sub(
            r"^postgresql://", "postgresql+asyncpg://", base_clean
        )

        # Also update database_url so the async engine in database.py has the right URL
        self.database_url = self.database_url_async

        return self

    @property
    def allowed_origins(self) -> list[str]:
        """
        Parse comma-separated ALLOWED_ORIGINS into a list.
        Accepts Render-style plain strings: https://a.example.com,https://b.example.com
        Never requires JSON encoding. Trims whitespace. Ignores empty entries.
        Rejects wildcard '*' in production — raises ValueError at startup.
        """
        raw = self.allowed_origins_raw or "http://localhost:5173"
        origins = [o.strip() for o in raw.split(",") if o.strip()] or ["http://localhost:5173"]
        if self.app_env in ("production", "staging"):
            if any(o == "*" for o in origins):
                raise ValueError(
                    "Wildcard CORS origin '*' is not permitted in production. "
                    "Set ALLOWED_ORIGINS to your specific frontend URL(s), e.g. "
                    "https://waterford-si-frontend.onrender.com"
                )
        return origins

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        populate_by_name = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — reads env once per process."""
    return Settings()


settings = get_settings()
