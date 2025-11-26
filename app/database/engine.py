"""
Centralized Database Engine - Single Source of Truth

This module provides the single, centralized database engine and session factory
for the entire application. All database connections should use the engine and
session factory defined here to ensure consistent WAL mode configuration and
connection pooling.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app.core.config import settings

logger = logging.getLogger(__name__)

# Optional import for pool monitor to avoid circular imports
try:
    from app.services.database_pool_monitor import initialize_pool_monitor
    POOL_MONITOR_AVAILABLE = True
except ImportError:
    POOL_MONITOR_AVAILABLE = False
    logger.warning("Database pool monitor not available due to circular import")

# Log database configuration for debugging
logger.info(f"Database URL: {settings.database_url}")
logger.info(f"Database pool configuration - Size: {settings.db_pool_size}, Max Overflow: {settings.db_max_overflow}")

# SQLite WAL mode configuration for better concurrent access
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and optimize SQLite for concurrent access"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")       # Enable WAL mode for concurrent access
    cursor.execute("PRAGMA synchronous=NORMAL")     # Better performance with WAL
    cursor.execute("PRAGMA busy_timeout=15000")     # Increased to 15 seconds for complex operations
    cursor.execute("PRAGMA foreign_keys=ON")       # Enable foreign key constraints
    cursor.execute("PRAGMA cache_size=-64000")      # 64MB cache for better performance
    cursor.execute("PRAGMA temp_store=MEMORY")      # Store temp tables in memory
    cursor.execute("PRAGMA mmap_size=268435456")    # 256MB memory-mapped I/O
    cursor.close()
    logger.info("SQLite WAL mode enabled with comprehensive optimizations (WAL, FK, cache, mmap)")

# Create the single async engine with comprehensive WAL mode configuration
engine = create_async_engine(
    settings.database_url,  # es: "sqlite+aiosqlite:///./archaeological_catalog.db"
    echo=False,
    future=True,
    # SQLite-optimized Connection Pool Configuration
    pool_size=settings.db_pool_size,               # 5 connessioni permanenti (SQLite non necesita pooling elevato)
    max_overflow=settings.db_max_overflow,         # 10 connessioni aggiuntive (totale: 15)
    pool_timeout=settings.db_pool_timeout,         # 30 secondi timeout
    pool_recycle=settings.db_pool_recycle,         # 1 ora (3600 secondi) - SQLite gestisce bene le connessioni lunghe
    pool_pre_ping=settings.db_pool_pre_ping,       # Verifica salute connessioni prima dell'uso
    # Configurazioni critiche per SQLite
    pool_reset_on_return=settings.db_pool_reset_on_return,  # Resetta stato connessione al ritorno
    connect_args={
        "check_same_thread": False,  # SQLite: permette multi-threading
        "timeout": 30,               # SQLite: timeout operazioni
    },
    # Configurazioni specifiche per SQLite
    execution_options={
        # SQLite usa default autocommit behavior
    }
)

# Create the single session factory for all application use
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Backward compatibility alias - ensures existing code continues to work
async_session_maker = AsyncSessionLocal

# Additional alias for compatibility with middleware
async_session_factory = AsyncSessionLocal

# Initialize the connection pool monitor if available
if POOL_MONITOR_AVAILABLE:
    pool_monitor = initialize_pool_monitor(engine)
    logger.info("Database connection pool monitor initialized")
else:
    pool_monitor = None
    logger.info("Database connection pool monitor skipped due to import constraints")

# Dependency FastAPI - centralized for all routes
async def get_async_session() -> AsyncSession:
    """FastAPI dependency for getting async database sessions"""
    async with AsyncSessionLocal() as session:
        yield session

# Export the main components that should be used throughout the application
__all__ = [
    'engine',                    # The single database engine
    'AsyncSessionLocal',         # The primary session factory
    'async_session_maker',       # Backward compatibility alias
    'async_session_factory',     # Additional compatibility alias
    'get_async_session',         # FastAPI dependency
    'set_sqlite_pragma',         # WAL mode event listener
    'pool_monitor',              # Connection pool monitor
]
# Backward compatibility alias - ensures existing code continues to work
async_session_maker = AsyncSessionLocal

# Additional alias for compatibility with middleware
async_session_factory = AsyncSessionLocal

# Initialize the connection pool monitor if available
if POOL_MONITOR_AVAILABLE:
    pool_monitor = initialize_pool_monitor(engine)
    logger.info("Database connection pool monitor initialized")
else:
    pool_monitor = None
    logger.info("Database connection pool monitor skipped due to import constraints")

# Dependency FastAPI - centralized for all routes
async def get_async_session() -> AsyncSession:
    """FastAPI dependency for getting async database sessions"""
    async with AsyncSessionLocal() as session:
        yield session

# Export the main components that should be used throughout the application
__all__ = [
    'engine',                    # The single database engine
    'AsyncSessionLocal',         # The primary session factory
    'async_session_maker',       # Backward compatibility alias
    'async_session_factory',     # Additional compatibility alias
    'get_async_session',         # FastAPI dependency
    'set_sqlite_pragma',         # WAL mode event listener
    'pool_monitor',              # Connection pool monitor
]