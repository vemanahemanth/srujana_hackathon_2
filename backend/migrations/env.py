"""FragilityShield — Alembic Migration Environment (Sprint 4).

Separates migration privileges from runtime privileges:
1. Prefers MIGRATION_DATABASE_URL (e.g. for `fragility_migrator` with DDL privileges).
2. Falls back to DATABASE_URL if MIGRATION_DATABASE_URL is not set.
3. Automatically adapts postgresql:// to postgresql+psycopg2:// for SQLAlchemy.
4. Masks database credentials in all log statements.
5. Preserves PostgreSQL Row-Level Security (RLS) policies and grants.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

logger = logging.getLogger("alembic.env")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

target_metadata = None


def mask_url(url: str) -> str:
    """Mask password credentials in database connection string."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.password:
            netloc = f"{parsed.username or ''}:***@{parsed.hostname or ''}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return url
    except Exception:
        return "<masked_url>"


def get_migration_database_url() -> str:
    """Resolve database URL for migrations, prioritizing MIGRATION_DATABASE_URL."""
    # 1. Check dedicated migration connection string
    db_url = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not db_url:
        # 2. Fall back to application DATABASE_URL
        db_url = os.environ.get("DATABASE_URL", "").strip()

    if not db_url:
        db_url = config.get_main_option("sqlalchemy.url") or ""

    if not db_url:
        raise RuntimeError(
            "FAIL-CLOSED: No database URL provided for migrations. "
            "Set MIGRATION_DATABASE_URL or DATABASE_URL environment variable."
        )

    # Ensure postgresql:// uses psycopg2 driver under SQLAlchemy
    if db_url.startswith("postgresql://"):
        db_url = "postgresql+psycopg2://" + db_url[len("postgresql://"):]

    masked = mask_url(db_url)
    logger.info("Alembic targeting database: %s", masked)
    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_migration_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_migration_database_url()
    
    # Inject resolved URL into configuration dictionary
    configuration = config.get_section(config.config_ini_section, {}) or {}
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
