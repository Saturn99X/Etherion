from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import text as sa_text
from sqlalchemy import create_engine
import sqlalchemy as sa

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Allow DATABASE_URL from environment to override alembic.ini
# This ensures Alembic uses the same database as the application (e.g., Postgres in docker-compose)
import os

# ETHERION_DATABASE_URL is the app user (etherion) who OWNS the alembic_version table
# We MUST use this for migrations because:
# 1. etherion owns alembic_version table
# 2. Only owner can ALTER TABLE to disable RLS
# 3. Only owner has SELECT/INSERT permission on alembic_version
# 4. postgres user in Cloud SQL doesn't have these permissions on etherion-owned tables
_etherion_db_url = os.getenv("ETHERION_DATABASE_URL")

# Prefer ETHERION_DATABASE_URL for migrations (table owner), fall back to DATABASE_URL
_db_url = _etherion_db_url or os.getenv("DATABASE_URL")
if _db_url:
    # Escape % to avoid ConfigParser interpolation errors
    _db_url_escaped = _db_url.replace('%', '%%')
    config.set_main_option("sqlalchemy.url", _db_url_escaped)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from sqlmodel import SQLModel
# Import all models to ensure they're registered with SQLModel
from src.database.models import *
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    import sys
    
    # Log which database URL we're using
    if _etherion_db_url:
        print("Using ETHERION_DATABASE_URL (table owner) for migrations", file=sys.stderr)
    else:
        print("Using DATABASE_URL for migrations (ETHERION_DATABASE_URL not set)", file=sys.stderr)
    
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # CRITICAL: Disable RLS on alembic_version table BEFORE running migrations
    # 
    # The alembic_version table is owned by 'etherion' user. We need to:
    # 1. Disable RLS (only owner can do this)
    # 2. Run migrations (owner has full permissions)
    #
    # Since we now use ETHERION_DATABASE_URL for the entire migration,
    # the same connection can do both operations.
    
    print("Attempting to disable RLS on alembic_version...", file=sys.stderr)
    
    try:
        with connectable.connect().execution_options(isolation_level="AUTOCOMMIT") as setup_conn:
            setup_conn.execute(sa.text(
                "ALTER TABLE IF EXISTS alembic_version DISABLE ROW LEVEL SECURITY"
            ))
            print("Successfully disabled RLS on alembic_version", file=sys.stderr)
            setup_conn.execute(sa.text(
                "ALTER TABLE IF EXISTS alembic_version NO FORCE ROW LEVEL SECURITY"
            ))
            print("Successfully removed FORCE RLS on alembic_version", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not disable RLS on alembic_version: {e}", file=sys.stderr)
        # Table might not exist yet on first migration, or RLS might not be enabled

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            render_as_batch=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
