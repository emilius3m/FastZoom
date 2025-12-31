# app/database/session.py
# DEPRECATED: This file now imports from the centralized engine.py
# Use app.database.engine for all new code

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

# Import all database components from the centralized engine
from app.database.engine import (
    engine,
    AsyncSessionLocal,
    async_session_maker,
    async_session_factory,
    get_async_session,
    pool_monitor
)

logger.debug("Database session module importing from centralized engine.py")

# Base dichiarativa per modelli, se non già altrove
Base = declarative_base()

# Maintain backward compatibility - re-export everything
# This ensures existing imports continue to work

# Backward compatibility alias for old imports
get_db = get_async_session

# Dependency FastAPI - imported from engine.py
