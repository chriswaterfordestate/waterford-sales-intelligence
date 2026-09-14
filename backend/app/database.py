"""
Database connection layer using SQLAlchemy async engine.
All database access goes through the AsyncSession dependency.

Design notes:
- Uses asyncpg for PostgreSQL — significantly faster than psycopg2 for I/O-bound queries
- Session-per-request pattern via FastAPI dependency injection
- Separate test engine for test database (port 5433)
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def _to_asyncpg_url(url: str) -> str:
    """Normalise any PostgreSQL URL to asyncpg format."""
    import re
    # Strip psycopg2 DSN → postgresql:// first
    if url.startswith("host="):
        parts = dict(tok.split("=", 1) for tok in url.split() if "=" in tok)
        url = "postgresql://{user}:{password}@{host}:{port}/{dbname}".format(
            user=parts.get("user", ""), password=parts.get("password", ""),
            host=parts.get("host", "localhost"), port=parts.get("port", "5432"),
            dbname=parts.get("dbname", ""),
        )
    # Convert postgresql:// → postgresql+asyncpg://
    return re.sub(r"^postgresql://", "postgresql+asyncpg://", url)


def create_engine(url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given URL.
    The URL is normalised to asyncpg format.
    This function MUST use the supplied URL, not settings.database_url_async,
    so test and production engines are genuinely isolated.
    """
    return create_async_engine(
        _to_asyncpg_url(url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # Reconnect if connection dropped
        echo=settings.app_env == "development",  # Log SQL in dev only
    )


# Production engine
engine = create_engine(settings.database_url)

# Test engine — used in tests via override
test_engine = create_engine(settings.database_url_test)

# Session factories
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

TestAsyncSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an async session per request.
    Session is committed on success, rolled back on exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_test_db() -> AsyncGenerator[AsyncSession, None]:
    """Test database session — used in pytest fixtures."""
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context():
    """Context manager version — for use outside FastAPI request cycle (e.g. Celery tasks)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Synchronous psycopg2 connection (used by Sprint 3 API routes) ─────────────
# The async SQLAlchemy engine is the primary connection layer,
# but the import engine and Sprint 3 routes use synchronous psycopg2
# for simplicity and direct compatibility with the import engine's db_ops module.

import psycopg2
from psycopg2.extras import register_uuid
import os, sys

def get_db_conn():
    """Return a synchronous psycopg2 connection for API routes."""
    # Use the canonical sync URL derived from DATABASE_URL in settings
    from app.config import settings as _settings
    dsn = _settings.database_url_sync
    if not dsn:
        raise RuntimeError(
            "database_url_sync is empty — set DATABASE_URL or DATABASE_URL_SYNC environment variable"
        )
    conn = psycopg2.connect(dsn)
    register_uuid()
    return conn
