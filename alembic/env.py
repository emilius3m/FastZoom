import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Setup BASE_DIR e sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)

# Carica .env per DATABASE_URL
try:
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    print(f"BASE_DIR: {BASE_DIR}")
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")

# Import Base e init_models
try:
    from app.database.base import Base, init_models
    # Inizializza modelli per popolare Base.metadata
    init_models()
    print("Models initialized successfully")
except ImportError as e:
    print(f"Error importing models: {e}")
    # Fallback se init_models non esiste
    from app.database.base import Base
    # Import esplicito dei modelli
    try:
        import app.models.users  # noqa: F401
        import app.models.sites  # noqa: F401
        import app.models.user_sites  # noqa: F401
        print("Models imported explicitly")
    except ImportError:
        print("Warning: Could not import some models")

# Alembic Config object
config = context.config

# Configura DATABASE_URL con fallback
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
    print(f"Database URL set from environment: {database_url}")
else:
    # Usa sqlalchemy.url da alembic.ini se DATABASE_URL non è disponibile
    database_url = config.get_main_option("sqlalchemy.url")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment or alembic.ini")
    print(f"Database URL from alembic.ini: {database_url}")

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata per autogenerate
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
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
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    """Configure context and run migrations on a connection."""
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """Create async engine and associate connection with context."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    
    await connectable.dispose()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
