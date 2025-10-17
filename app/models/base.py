# app/models/base.py
"""
Modelli base per FastZoom Archaeological System
Include Base SQLAlchemy e BaseSQLModel con timestamp automatici
"""

import uuid
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import DateTime, Column, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import func

# Base SQLAlchemy
Base = declarative_base()


class BaseSQLModel(Base):
    """
    Abstract base class per tutti i modelli con campi comuni:
    - ID UUID primario
    - Timestamp created/updated automatici
    """
    __abstract__ = True

    # ID primario UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Timestamp automatici
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id})>"


class TimestampMixin:
    """Mixin per aggiungere timestamp a modelli esistenti"""
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteMixin:
    """Mixin per modelli associati a un sito archeologico"""
    site_id = Column(UUID(as_uuid=True), nullable=False, index=True)


class UserMixin:
    """Mixin per modelli che richiedono tracciamento utente"""
    created_by = Column(UUID(as_uuid=True), nullable=False)
    updated_by = Column(UUID(as_uuid=True), nullable=True)


class SoftDeleteMixin:
    """Mixin per soft delete"""
    is_deleted = Column('is_deleted', default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)