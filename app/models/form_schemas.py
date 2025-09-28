"""Form Schema model for archaeological form builder."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.base import Base


class FormSchema(Base):
    """Form Schema model for storing custom archaeological forms."""
    
    __tablename__ = "form_schemas"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)  # artifact, structure, stratigraphy, sample
    schema_json = Column(Text, nullable=False)  # JSON string of the form schema
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign keys
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationships
    site = relationship("ArchaeologicalSite", back_populates="form_schemas")
    creator = relationship("User")
    
    def __repr__(self):
        return f"<FormSchema {self.name}>"