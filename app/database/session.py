# app/database/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app.core.config import settings
from app.services.database_pool_monitor import initialize_pool_monitor
import logging

logger = logging.getLogger(__name__)

# Log database configuration for debugging
logger.info(f"Database URL: {settings.database_url}")
logger.info(f"Database pool configuration - Size: {settings.db_pool_size}, Max Overflow: {settings.db_max_overflow}")

# Base dichiarativa per modelli, se non già altrove
Base = declarative_base()

# SQLite WAL mode configuration for better concurrent access
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode for concurrent SQLite access"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")      # Enable WAL mode for concurrent access
    cursor.execute("PRAGMA synchronous=NORMAL")     # Better performance with WAL
    cursor.execute("PRAGMA busy_timeout=5000")     # 5 second lock timeout
    cursor.close()
    logger.info("SQLite WAL mode enabled with optimized settings")

# Crea engine asincrono con connection pool ottimizzato per stress test
engine = create_async_engine(
    settings.database_url,  # es: "sqlite+aiosqlite:///./archaeological_catalog.db"
    echo=False,
    future=True,
    # Connection Pool Configuration - CRITICO: Ottimizzato per 50+ richieste concorrenti
    pool_size=30,                    # Aumentato da 20 a 30 connessioni permanenti
    max_overflow=70,                # Aumentato da 30 a 70 connessioni aggiuntive (totale: 100)
    pool_timeout=60,                 # Aumentato da 30 a 60 secondi timeout
    pool_recycle=1800,               # Ridotto da 3600 a 1800 secondi (30 minuti) per evitare stale connections
    pool_pre_ping=True,              # Mantenuto: Verifica connessioni prima dell'uso
    # Aggiunte configurazioni critiche per resilienza
    pool_reset_on_return='commit',   # Resetta stato connessione al ritorno
    connect_args={
        "check_same_thread": False,  # SQLite: permette multi-threading
        "timeout": 30,                # SQLite: timeout operazioni increased to 30 seconds
        # Removed isolation_level=None to prevent AttributeError
        # SQLite will use default autocommit behavior
    },
    # Configurazioni specifiche per SQLite
    execution_options={
        # Removed isolation_level=None to prevent AttributeError
        # SQLite will use default autocommit behavior
    }
)

# Factory per sessioni asincrone
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Alias per compatibilità con middleware
async_session_factory = AsyncSessionLocal

# Inizializza il monitor del connection pool
pool_monitor = initialize_pool_monitor(engine)
logger.info("Database connection pool monitor inizializzato")

# Dependency FastAPI
async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
