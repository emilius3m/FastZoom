"""Base repository class for database operations."""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, and_, or_
from sqlalchemy.orm import joinedload, selectinload
from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository class with common database operations."""
    
    def __init__(self, db_session: AsyncSession, model: Type[ModelType]):
        """
        Initialize repository with database session and model.
        
        Args:
            db_session: Async database session
            model: SQLAlchemy model class
        """
        self.db_session = db_session
        self.model = model

    async def get(self, id: UUID) -> Optional[ModelType]:
        """Get a record by ID."""
        # Convert UUID to string for SQLite compatibility (models use String(36) for ID)
        id_str = str(id) if isinstance(id, UUID) else id
        query = select(self.model).where(self.model.id == id_str)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None
    ) -> List[ModelType]:
        """Get multiple records with pagination and filtering."""
        query = select(self.model)
        
        if filters:
            conditions = []
            for key, value in filters.items():
                if hasattr(self.model, key):
                    if isinstance(value, list):
                        conditions.append(getattr(self.model, key).in_(value))
                    else:
                        conditions.append(getattr(self.model, key) == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        if order_by and hasattr(self.model, order_by):
            query = query.order_by(getattr(self.model, order_by))
        
        query = query.offset(skip).limit(limit)
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def create(self, obj_in: Dict[str, Any]) -> ModelType:
        """Create a new record."""
        db_obj = self.model(**obj_in)
        self.db_session.add(db_obj)
        await self.db_session.flush()  # Flush to get ID without committing
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: Union[Dict[str, Any], ModelType]) -> ModelType:
        """Update an existing record."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.__dict__
        
        # Remove SQLAlchemy internal attributes
        update_data = {k: v for k, v in update_data.items() 
                      if not k.startswith('_') and k != 'id'}
        
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        await self.db_session.flush()
        return db_obj

    async def remove(self, id: UUID) -> ModelType:
        """Remove a record by ID."""
        obj = await self.get(id)
        if obj:
            await self.db_session.delete(obj)
            await self.db_session.flush()
        return obj

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with optional filtering."""
        from sqlalchemy import func

        query = select(func.count(self.model.id))

        if filters:
            conditions = []
            for key, value in filters.items():
                if hasattr(self.model, key):
                    if isinstance(value, list):
                        conditions.append(getattr(self.model, key).in_(value))
                    else:
                        conditions.append(getattr(self.model, key) == value)
            if conditions:
                query = query.where(and_(*conditions))

        result = await self.db_session.execute(query)
        return result.scalar_one()