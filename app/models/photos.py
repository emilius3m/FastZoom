# app/models/photos.py - MODELLO FOTO ARCHEOLOGICHE SPECIALIZZATO

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import uuid4, UUID
import json
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseSQLModel

class MaterialType(PyEnum):
    """Tipologie di materiali archeologici"""
    CERAMIC = "ceramica"
    BRONZE = "bronzo"
    IRON = "ferro"
    STONE = "pietra"
    MARBLE = "marmo"
    GLASS = "vetro"
    BONE = "osso"
    WOOD = "legno"
    GOLD = "oro"
    SILVER = "argento"
    LEAD = "piombo"
    TERRACOTTA = "terracotta"
    STUCCO = "stucco"
    MOSAIC = "mosaico"
    FABRIC = "tessuto"
    LEATHER = "cuoio"
    OTHER = "altro"

class ConservationStatus(PyEnum):
    """Stati di conservazione"""
    EXCELLENT = "eccellente"
    GOOD = "buono"
    FAIR = "discreto"
    POOR = "cattivo"
    FRAGMENTARY = "frammentario"
    RESTORED = "restaurato"
    LOST = "perduto"

class PhotoType(PyEnum):
    """Tipologie di fotografie archeologiche"""
    GENERAL_VIEW = "vista_generale"
    DETAIL = "dettaglio"
    SECTION = "sezione"
    DRAWING_OVERLAY = "disegno_sovrapposto"
    BEFORE_RESTORATION = "pre_restauro"
    AFTER_RESTORATION = "post_restauro"
    EXCAVATION_PROGRESS = "avanzamento_scavo"
    STRATIGRAPHY = "stratigrafia"
    FIND_CONTEXT = "contesto_rinvenimento"
    LABORATORY = "laboratorio"
    ARCHIVE = "archivio"

class Photo(BaseSQLModel):
    """Modello per fotografie archeologiche con metadati specializzati"""
    
    __tablename__ = "photos"
    
    # ===== FILE INFORMATION =====
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Image properties
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dpi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    color_profile: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Thumbnail
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # ===== METADATI FOTOGRAFICI STANDARD =====
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    photo_type: Mapped[Optional[PhotoType]] = mapped_column(nullable=True)
    
    # Informazioni fotografo e data scatto
    photographer: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    photo_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    camera_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lens: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # ===== METADATI ARCHEOLOGICI SPECIFICI =====
    
    # Identificazione reperto
    inventory_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    old_inventory_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    catalog_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Contesto di scavo
    excavation_area: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stratigraphic_unit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    grid_square: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    depth_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # in metri
    
    # Informazioni rinvenimento
    find_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finder: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    excavation_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Caratteristiche oggetto
    material: Mapped[Optional[MaterialType]] = mapped_column(nullable=True)
    material_details: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    object_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    object_function: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Dimensioni oggetto (in cm)
    length_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diameter_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_grams: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Cronologia
    chronology_period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chronology_culture: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dating_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Anno
    dating_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # Anno
    dating_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Conservazione
    conservation_status: Mapped[Optional[ConservationStatus]] = mapped_column(nullable=True)
    conservation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    restoration_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Bibliografia e riferimenti
    bibliography: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comparative_references: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_links: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    
    # Metadati tecnici (EXIF, IPTC)
    exif_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    iptc_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    # Copyright e licenze
    copyright_holder: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    license_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    usage_rights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Qualità e validazione
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Deep Zoom / Tiles status
    has_deep_zoom: Mapped[bool] = mapped_column(Boolean, default=False)
    deep_zoom_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 'processing', 'completed', 'failed', 'scheduled'
    deep_zoom_levels: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deep_zoom_tile_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deep_zoom_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # ===== RELAZIONI =====
    site_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("archaeological_sites.id"), 
        nullable=False,
        index=True
    )
    
    uploaded_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=False,
        index=True
    )
    
    site: Mapped["ArchaeologicalSite"] = relationship(
        "ArchaeologicalSite",
        back_populates="photos"
    )
    
    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by])

    validator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[validated_by])
    
    # Storico modifiche
    modifications: Mapped[List["PhotoModification"]] = relationship(
        "PhotoModification",
        back_populates="photo",
        cascade="all, delete-orphan"
    )
    
    # ===== INDICI =====
    __table_args__ = (
        Index("idx_photo_site", "site_id"),
        Index("idx_photo_uploader", "uploaded_by"),
        Index("idx_photo_inventory", "inventory_number"),
        Index("idx_photo_material", "material"),
        Index("idx_photo_find_date", "find_date"),
        Index("idx_photo_area", "excavation_area"),
        Index("idx_photo_unit", "stratigraphic_unit"),
        Index("idx_photo_period", "chronology_period"),
        Index("idx_photo_validated", "is_validated"),
        Index("idx_photo_published", "is_published"),
        Index("idx_photo_type", "photo_type"),
        Index("idx_photo_created", "created"),
    )
    
    def __repr__(self):
        return f"<Photo(filename={self.filename!r}, inventory={self.inventory_number!r})>"
    
    # ===== PROPERTIES =====
    
    @property
    def thumbnail_url(self) -> str:
        if self.thumbnail_path:
            from app.core.config import get_settings
            settings = get_settings()
            return f"{settings.minio_url}/{settings.minio_bucket}/{self.thumbnail_path}"
        return f"/photos/{self.id}/thumbnail"

    @property
    def full_url(self) -> str:
        return f"/photos/{self.id}/full"
    
    @property
    def download_url(self) -> str:
        return f"/photos/{self.id}/download"
    
    @property
    def file_size_mb(self) -> float:
        return round(self.file_size / (1024 * 1024), 2)
    
    @property
    def resolution(self) -> Optional[str]:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None
    
    @property
    def dimensions_display(self) -> Optional[str]:
        """Dimensioni oggetto per display"""
        dims = []
        if self.length_cm:
            dims.append(f"L: {self.length_cm}cm")
        if self.width_cm:
            dims.append(f"l: {self.width_cm}cm")
        if self.height_cm:
            dims.append(f"h: {self.height_cm}cm")
        if self.diameter_cm:
            dims.append(f"⌀: {self.diameter_cm}cm")
        
        return " × ".join(dims) if dims else None
    
    @property
    def dating_display(self) -> Optional[str]:
        """Datazione per display"""
        if self.dating_from and self.dating_to:
            if self.dating_from == self.dating_to:
                return f"{self.dating_from} d.C."
            else:
                return f"{self.dating_from}-{self.dating_to} d.C."
        elif self.dating_from:
            return f"dal {self.dating_from} d.C."
        elif self.dating_to:
            return f"fino al {self.dating_to} d.C."
        elif self.chronology_period:
            return self.chronology_period
        return None
    
    # ===== METODI JSON =====
    
    def get_keywords_list(self) -> List[str]:
        if self.keywords:
            try:
                return json.loads(self.keywords)
            except (json.JSONDecodeError, TypeError):
                return self.keywords.split(',') if isinstance(self.keywords, str) else []
        return []
    
    def set_keywords_list(self, keywords: List[str]):
        self.keywords = json.dumps(keywords) if keywords else None
    
    def get_external_links_list(self) -> List[Dict[str, str]]:
        if self.external_links:
            try:
                return json.loads(self.external_links)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def set_external_links_list(self, links: List[Dict[str, str]]):
        self.external_links = json.dumps(links) if links else None
    
    def get_exif_data(self) -> Dict[str, Any]:
        if self.exif_data:
            try:
                return json.loads(self.exif_data)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_exif_data(self, exif: Dict[str, Any]):
        self.exif_data = json.dumps(exif) if exif else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Photo object to dictionary for JSON serialization"""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "color_profile": self.color_profile,
            "thumbnail_path": self.thumbnail_path,
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "photo_type": self.photo_type.value if self.photo_type else None,
            "photographer": self.photographer,
            "photo_date": self.photo_date.isoformat() if self.photo_date else None,
            "camera_model": self.camera_model,
            "lens": self.lens,
            "inventory_number": self.inventory_number,
            "old_inventory_number": self.old_inventory_number,
            "catalog_number": self.catalog_number,
            "excavation_area": self.excavation_area,
            "stratigraphic_unit": self.stratigraphic_unit,
            "grid_square": self.grid_square,
            "depth_level": self.depth_level,
            "find_date": self.find_date.isoformat() if self.find_date else None,
            "finder": self.finder,
            "excavation_campaign": self.excavation_campaign,
            "material": self.material.value if self.material else None,
            "material_details": self.material_details,
            "object_type": self.object_type,
            "object_function": self.object_function,
            "length_cm": self.length_cm,
            "width_cm": self.width_cm,
            "height_cm": self.height_cm,
            "diameter_cm": self.diameter_cm,
            "weight_grams": self.weight_grams,
            "chronology_period": self.chronology_period,
            "chronology_culture": self.chronology_culture,
            "dating_from": self.dating_from,
            "dating_to": self.dating_to,
            "dating_notes": self.dating_notes,
            "conservation_status": self.conservation_status.value if self.conservation_status else None,
            "conservation_notes": self.conservation_notes,
            "restoration_history": self.restoration_history,
            "bibliography": self.bibliography,
            "comparative_references": self.comparative_references,
            "external_links": self.external_links,
            "exif_data": self.exif_data,
            "iptc_data": self.iptc_data,
            "copyright_holder": self.copyright_holder,
            "license_type": self.license_type,
            "usage_rights": self.usage_rights,
            "is_published": self.is_published,
            "is_validated": self.is_validated,
            "validation_notes": self.validation_notes,
            "validated_by": str(self.validated_by) if self.validated_by else None,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "site_id": str(self.site_id),
            "uploaded_by": str(self.uploaded_by),
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
            # Computed properties
            "thumbnail_url": self.thumbnail_url,
            "full_url": self.full_url,
            "download_url": self.download_url,
            "file_size_mb": self.file_size_mb,
            "resolution": self.resolution,
            "dimensions_display": self.dimensions_display,
            "dating_display": self.dating_display,
            # Deep zoom fields
            "has_deep_zoom": self.has_deep_zoom,
            "deep_zoom_status": self.deep_zoom_status,
            "deep_zoom_levels": self.deep_zoom_levels,
            "deep_zoom_tile_count": self.deep_zoom_tile_count,
            "deep_zoom_processed_at": self.deep_zoom_processed_at.isoformat() if self.deep_zoom_processed_at else None,
        }


class PhotoModification(BaseSQLModel):
    """Storico modifiche foto per audit trail"""
    
    __tablename__ = "photo_modifications"
    
    photo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("photos.id"),
        nullable=False,
        index=True
    )
    
    modified_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False
    )
    
    modification_type: Mapped[str] = mapped_column(String(100), nullable=False)  # CREATE, UPDATE, DELETE, VALIDATE
    field_changed: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relazioni
    photo: Mapped["Photo"] = relationship("Photo", back_populates="modifications")
    modifier: Mapped["User"] = relationship("User")
    
    # Indici
    __table_args__ = (
        Index("idx_modification_photo", "photo_id"),
        Index("idx_modification_user", "modified_by"),
        Index("idx_modification_date", "created"),
        Index("idx_modification_type", "modification_type"),
    )
    
    def __repr__(self):
        return f"<PhotoModification(photo={self.photo_id!r}, type={self.modification_type!r})>"
