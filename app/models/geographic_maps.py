# app/models/geographic_maps.py - Modelli per mappe geografiche con salvataggio server

from sqlalchemy import Column, String, Text, Boolean, DateTime, func, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship, mapped_column, Mapped
from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.database.base import Base

class GeographicMap(Base):
    """Modello per mappe geografiche salvate - ogni sito può avere multiple mappe"""
    __tablename__ = "geographic_maps"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Relazione con sito
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    
    # Informazioni base mappa
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Bounds geografici (coordinate lat/lng)
    bounds_north: Mapped[float] = mapped_column(Float, nullable=False)
    bounds_south: Mapped[float] = mapped_column(Float, nullable=False)
    bounds_east: Mapped[float] = mapped_column(Float, nullable=False)
    bounds_west: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Centro mappa
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    default_zoom: Mapped[int] = mapped_column(Integer, default=15)
    
    # Configurazione mappa
    map_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Stato
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # Mappa di default del sito
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relazioni
    site = relationship("ArchaeologicalSite", back_populates="geographic_maps")
    geojson_layers = relationship("GeographicMapLayer", back_populates="map", cascade="all, delete-orphan")
    manual_markers = relationship("GeographicMapMarker", back_populates="map", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<GeographicMap(name='{self.name}', site='{self.site_id}')>"
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": str(self.id),
            "site_id": str(self.site_id),
            "name": self.name,
            "description": self.description,
            "bounds": {
                "north": self.bounds_north,
                "south": self.bounds_south,
                "east": self.bounds_east,
                "west": self.bounds_west
            },
            "center": {
                "lat": self.center_lat,
                "lng": self.center_lng
            },
            "default_zoom": self.default_zoom,
            "map_config": self.map_config or {},
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "layers_count": len(self.geojson_layers) if self.geojson_layers else 0,
            "markers_count": len(self.manual_markers) if self.manual_markers else 0
        }


class GeographicMapLayer(Base):
    """Layer GeoJSON salvati per le mappe geografiche"""
    __tablename__ = "geographic_map_layers"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Relazioni
    map_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("geographic_maps.id"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    
    # Informazioni layer
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    layer_type: Mapped[str] = mapped_column(String(100), default="geojson")  # geojson, kml, etc.
    
    # Dati GeoJSON
    geojson_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    features_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Stile e visualizzazione
    style_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Bounds del layer
    bounds_north: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_south: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_east: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_west: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relazioni
    map = relationship("GeographicMap", back_populates="geojson_layers")
    site = relationship("ArchaeologicalSite")
    
    def __repr__(self):
        return f"<GeographicMapLayer(name='{self.name}', map='{self.map_id}')>"
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": str(self.id),
            "map_id": str(self.map_id),
            "site_id": str(self.site_id),
            "name": self.name,
            "description": self.description,
            "layer_type": self.layer_type,
            "geojson_data": self.geojson_data,
            "features_count": self.features_count,
            "style_config": self.style_config or {},
            "is_visible": self.is_visible,
            "display_order": self.display_order,
            "bounds": {
                "north": self.bounds_north,
                "south": self.bounds_south,
                "east": self.bounds_east,
                "west": self.bounds_west
            } if self.bounds_north else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class GeographicMapMarker(Base):
    """Marker manuali aggiunti alle mappe geografiche"""
    __tablename__ = "geographic_map_markers"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Relazioni
    map_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("geographic_maps.id"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    
    # Posizione
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Informazioni marker
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    marker_type: Mapped[str] = mapped_column(String(100), default="generic")
    icon: Mapped[str] = mapped_column(String(10), default="📍")
    color: Mapped[str] = mapped_column(String(20), default="#007bff")
    
    # Metadati aggiuntivi
    marker_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relazioni
    map = relationship("GeographicMap", back_populates="manual_markers")
    site = relationship("ArchaeologicalSite")
    photo_associations = relationship("GeographicMapMarkerPhoto", back_populates="marker", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<GeographicMapMarker(title='{self.title}', lat='{self.latitude}', lng='{self.longitude}')>"
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": str(self.id),
            "map_id": str(self.map_id),
            "site_id": str(self.site_id),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "title": self.title,
            "description": self.description,
            "marker_type": self.marker_type,
            "icon": self.icon,
            "color": self.color,
            "metadata": self.marker_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "photos_count": len(self.photo_associations) if self.photo_associations else 0,
            "photos": [assoc.photo.to_dict() for assoc in self.photo_associations] if self.photo_associations else []
        }


class GeographicMapMarkerPhoto(Base):
    """Associazione tra marker geografici e foto"""
    __tablename__ = "geographic_map_marker_photos"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Relazioni
    marker_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("geographic_map_markers.id"), nullable=False)
    photo_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("photos.id"), nullable=False)
    
    # Metadati associazione
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)  # Foto principale del marker
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relazioni
    marker = relationship("GeographicMapMarker", back_populates="photo_associations")
    photo = relationship("Photo")
    
    def __repr__(self):
        return f"<GeographicMapMarkerPhoto(marker='{self.marker_id}', photo='{self.photo_id}')>"
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": str(self.id),
            "marker_id": str(self.marker_id),
            "photo_id": str(self.photo_id),
            "description": self.description,
            "display_order": self.display_order,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "photo": self.photo.to_dict() if self.photo else None
        }