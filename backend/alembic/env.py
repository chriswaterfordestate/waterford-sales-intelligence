"""Alembic environment — synchronous psycopg2 connection for multi-statement SQL migrations."""
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context
import os, sys, re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # SQL-file migrations, no autogenerate


def _sync_url() -> str:
    """
    Return a psycopg2-compatible sync URL for Alembic.

    Priority:
    1. DATABASE_URL env var (standard postgresql:// URL from Render or local)
    2. DATABASE_URL_SYNC env var (psycopg2 DSN or postgresql:// URL)
    3. alembic.ini sqlalchemy.url
    4. Hard-coded dev fallback (dev/test only)

    asyncpg URLs are converted to psycopg2 URLs because Alembic runs multi-statement
    SQL blocks that asyncpg cannot handle in prepared-statement mode.
    """
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_URL_SYNC")
        or config.get_main_option("sqlalchemy.url", "")
    )
    if not url:
        if os.getenv("APP_ENV") in ("production", "staging"):
            raise RuntimeError("DATABASE_URL or DATABASE_URL_SYNC must be set in production")
        url = "postgresql://waterford:waterford_dev@localhost:5432/waterford_si"

    # Convert asyncpg URL → psycopg2 URL
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    # Convert psycopg2 DSN format → URL if needed
    if url.startswith("host="):
        parts = dict(tok.split("=", 1) for tok in url.split() if "=" in tok)
        url = "postgresql://{user}:{password}@{host}:{port}/{dbname}".format(
            user=parts.get("user", "waterford"),
            password=parts.get("password", "waterford_dev"),
            host=parts.get("host", "localhost"),
            port=parts.get("port", "5432"),
            dbname=parts.get("dbname", "waterford_si"),
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Use psycopg2 (sync) — required for multi-statement SQL in migration files
    engine = create_engine(
        _sync_url(),
        poolclass=pool.NullPool,
        # Execute each migration file as a single text block
        # psycopg2 supports multi-statement SQL; asyncpg does not
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
