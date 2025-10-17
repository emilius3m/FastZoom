"""
Modelli Database per Foto e Metadati
"""

from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Photo(Base):
    """Modello foto con metadati archeologici"""
    __tablename__ = "photos"

    # PK
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # File info
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)  # bytes
    mime_type = Column(String(100))

    # Dimensioni immagine
    width = Column(Integer)
    height = Column(Integer)

    # Metadati EXIF (JSON)
    exif_data = Column(JSONB, default={})

    # Metadati archeologici (conforme a schemas JSON)
    metadata = Column(JSONB, default={})

    # Relazioni
    site_id = Column(UUID(as_uuid=True), ForeignKey('sites.id'), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Status
    visibility = Column(String(20), default='team')  # public, team, private
    featured = Column(Boolean, default=False)
    is_processed = Column(Boolean, default=False)

    # Deep Zoom
    has_deep_zoom = Column(Boolean, default=False)
    deep_zoom_path = Column(String(500))

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    site = relationship("Site", back_populates="photos")
    uploader = relationship("User")

    def __repr__(self):
        return f"<Photo {self.filename}>"


class PhotoMetadataHistory(Base):
    """Storico modifiche metadati foto"""
    __tablename__ = "photo_metadata_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    photo_id = Column(UUID(as_uuid=True), ForeignKey('photos.id'), nullable=False)

    # Dati storici
    metadata_snapshot = Column(JSONB, nullable=False)

    # Chi ha modificato
    modified_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow)

    # Tipo modifica
    change_type = Column(String(50))  # create, update, bulk_update
    change_description = Column(Text)

    def __repr__(self):
        return f"<PhotoMetadataHistory {self.photo_id} - {self.modified_at}>"
