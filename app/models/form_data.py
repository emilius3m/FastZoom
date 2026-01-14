from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database.db import Base
from app.models.base import SiteMixin, UserMixin

class FormData(Base, SiteMixin, UserMixin):
    """Dati compilati dai form personalizzati"""
    __tablename__ = "form_data"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String(36), ForeignKey('archaeological_sites.id'), nullable=False)
    schema_id = Column(String(36), ForeignKey('form_schemas.id'), nullable=False)
    
    # JSON field for flexible data storage
    data = Column(JSON, nullable=False)
    
    submitted_by = Column(String(36), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    site = relationship("ArchaeologicalSite")
    schema = relationship("FormSchema", backref="submissions")
    submitter = relationship("User", foreign_keys=[submitted_by])

    def __repr__(self):
        return f"<FormData({self.id} for schema {self.schema_id})>"
