"""
Document Model
File: app/models/documents.py
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database.base import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # Metadata
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)  # relazioni, documentazione, planimetrie, etc.
    doc_type = Column(String(100), nullable=True)  # pdf, word, image, etc.

    # File info
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(200), nullable=True)

    # Additional info
    tags = Column(String(500), nullable=True)
    doc_date = Column(DateTime, nullable=True)  # Data del documento, non upload
    author = Column(String(200), nullable=True)
    is_public = Column(Boolean, default=True)

    # Versioning
    version = Column(Integer, default=1)
    version_notes = Column(Text, nullable=True)

    # Timestamps
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Soft delete
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    site = relationship("ArchaeologicalSite", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by])
