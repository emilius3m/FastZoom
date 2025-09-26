# app/database/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# Base dichiarativa per modelli, se non già altrove
Base = declarative_base()

# Crea engine asincrono
engine = create_async_engine(
    settings.database_url,  # es: "sqlite+aiosqlite:///./archaeological_catalog.db"
    echo=False,
    future=True,
)

# Factory per sessioni asincrone
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Dependency FastAPI
async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
