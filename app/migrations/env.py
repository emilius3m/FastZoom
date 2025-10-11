import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ============== SEZIONE IMPORT MODELLI - CORRETTA =====================#

# Configurazione paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(BASE_DIR, "is the base directory")
load_dotenv(os.path.join(BASE_DIR, ".env"))
sys.path.append(BASE_DIR)

# IMPORT ESPLICITO DI TUTTI I MODELLI - Questo è fondamentale!
from app.database.base import Base

# 🔥 IMPORT ESPLICITO DI TUTTI I MODELLI - necessario per autogenerate
from app.models.users import User, Role, UserActivity
from app.models.user_profiles import UserProfile
from app.models.user_sites import UserSitePermission, PermissionLevel  # 🆕 NUOVO


# Se hai altri modelli, aggiungili qui:
try:
    from app.models.sites import ArchaeologicalSite
    print("SUCCESS: ArchaeologicalSite model imported")
except ImportError:
    print("WARNING: ArchaeologicalSite model not found - create it if needed")

try:
    from app.models.documentazione_grafica import TavolaGrafica, FotografiaArcheologica, MatrixHarris, ElencoConsegna
    print("SUCCESS: Documentazione grafica models imported")
except ImportError:
    print("WARNING: Documentazione grafica models not found - create them if needed")

# 🆕 AGGIUNTO: Import modelli Giornale di Cantiere
try:
    from app.models.giornale_cantiere import GiornaleCantiere, OperatoreCantiere
    print("SUCCESS: Giornale di cantiere models imported")
except ImportError:
    print("WARNING: Giornale di cantiere models not found - create them if needed")

# Verifica che tutti i modelli siano stati importati
print("Imported models:")
for cls in Base.registry._class_registry.values():
    if hasattr(cls, '__tablename__'):
        print(f"   - {cls.__tablename__} ({cls.__name__})")

# ============== FINE SEZIONE IMPORT =====================#

# this is the Alembic Config object
config = context.config

# Configura URL database
try:
    database_url = os.environ["DATABASE_URL"]
    config.set_main_option("sqlalchemy.url", database_url)
    print(f"Database URL: {database_url}")
except KeyError:
    print("DATABASE_URL not found in environment variables")
    # Fallback per sviluppo locale
    fallback_url = "sqlite:///./app.db"
    config.set_main_option("sqlalchemy.url", fallback_url)
    print(f"Using fallback URL: {fallback_url}")

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ✅ METADATA CORRETTA - include tutti i modelli importati sopra
target_metadata = Base.metadata

print(f"Tables found in metadata: {list(target_metadata.tables.keys())}")

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
        # 🆕 AGGIUNTO: Supporto per ENUM PostgreSQL
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        # 🆕 AGGIUNTO: Configurazioni avanzate per autogenerate
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
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
    print("Starting async migrations...")
    asyncio.run(run_async_migrations())

# Esecuzione
if context.is_offline_mode():
    print("Running offline migrations...")
    run_migrations_offline()
else:
    print("Running online migrations...")
    run_migrations_online()
