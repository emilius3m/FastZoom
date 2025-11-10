from sqlalchemy import Column, String, Text, Boolean, DateTime, func, Integer, Float, ForeignKey, UUID
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship, mapped_column, Mapped
from uuid import uuid4
from datetime import datetime
from typing import Optional
from app.database.base import Base

class ArchaeologicalPlan(Base):
    """Modello per piante archeologiche - ogni sito può avere multiple piante"""
    __tablename__ = "archaeological_plans"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Relazione con sito
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    
    # Informazioni base pianta
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_type: Mapped[str] = mapped_column(String(100), nullable=False)  # "general", "detail", "section", etc.
    
    # File pianta
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)  # Path to plan image
    image_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Sistema coordinate
    coordinate_system: Mapped[str] = mapped_column(String(100), default="archaeological_grid")
    origin_x: Mapped[float] = mapped_column(Float, default=0.0)  # Punto datum X
    origin_y: Mapped[float] = mapped_column(Float, default=0.0)  # Punto datum Y
    scale_factor: Mapped[float] = mapped_column(Float, default=1.0)  # Scala 1:scale_factor
    
    # Bounds della pianta (coordinate archeologiche)
    bounds_north: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_south: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_east: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bounds_west: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Dimensioni immagine in pixel
    image_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Metadati
    survey_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    surveyor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    drawing_scale: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "1:100", "1:50", etc.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Configurazione griglia
    grid_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Stato
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)  # Pianta principale del sito
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    created_by: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Relazioni
    site = relationship("ArchaeologicalSite", back_populates="plans")
    excavation_units = relationship("ExcavationUnit", back_populates="plan", cascade="all, delete-orphan")
    archaeological_data = relationship("ArchaeologicalData", back_populates="plan", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ArchaeologicalPlan(name='{self.name}', site='{self.site_id}')>"
    
    def get_grid_config(self):
        """Restituisce configurazione griglia con defaults"""
        default_config = {
            "unit_size": 5,
            "major_grid_size": 20,
            "show_labels": True,
            "show_major_grid": True,
            "show_minor_grid": True,
            "label_format": "letter_number"  # A1, B2, etc.
        }
        
        if self.grid_config:
            default_config.update(self.grid_config)
        
        return default_config
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": str(self.id),
            "site_id": str(self.site_id),
            "name": self.name,
            "description": self.description,
            "plan_type": self.plan_type,
            "image_path": self.image_path,
            "image_filename": self.image_filename,
            "coordinate_system": self.coordinate_system,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "scale_factor": self.scale_factor,
            "bounds": {
                "north": self.bounds_north,
                "south": self.bounds_south,
                "east": self.bounds_east,
                "west": self.bounds_west
            },
            "image_dimensions": {
                "width": self.image_width,
                "height": self.image_height
            },
            "grid_config": self.get_grid_config(),
            "is_active": self.is_active,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ExcavationUnit(Base):
    """Modello per unità di scavo archeologiche"""
    __tablename__ = "excavation_units"
    
    # Chiave primaria (ID formato archeologico es. "A5-23")
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    
    # Relazioni
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_plans.id"), nullable=False)
    
    # Coordinate archeologiche
    coordinates_x: Mapped[float] = mapped_column(Float, nullable=False)
    coordinates_y: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Dimensioni unità
    size_x: Mapped[float] = mapped_column(Float, default=5.0)  # Larghezza in metri
    size_y: Mapped[float] = mapped_column(Float, default=5.0)  # Lunghezza in metri
    
    # Stato scavo
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned, in_progress, completed, suspended
    current_depth: Mapped[float] = mapped_column(Float, default=0.0)  # Profondità attuale di scavo
    max_depth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Profondità massima prevista
    
    # Informazioni archeologiche
    stratigraphic_sequence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Sequenza stratigrafica
    finds_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Riassunto reperti
    
    # Gestione
    supervisor: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    team_members: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Lista membri team
    priority: Mapped[int] = mapped_column(Integer, default=1)  # Priorità di scavo (1=alta, 5=bassa)
    
    # Note e osservazioni
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    soil_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preservation_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Date
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_excavation_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Metadati
    excavation_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # "manual", "mechanical", etc.
    documentation_level: Mapped[str] = mapped_column(String(20), default="standard")  # "basic", "standard", "detailed"
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relazioni
    site = relationship("ArchaeologicalSite")
    plan = relationship("ArchaeologicalPlan", back_populates="excavation_units")
    archaeological_data = relationship("ArchaeologicalData", back_populates="excavation_unit", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ExcavationUnit(id='{self.id}', status='{self.status}')>"
    
    def get_status_color(self):
        """Restituisce colore per visualizzazione stato"""
        status_colors = {
            'planned': '#94a3b8',     # Gray
            'in_progress': '#f59e0b', # Orange
            'completed': '#10b981',   # Green
            'suspended': '#ef4444'    # Red
        }
        return status_colors.get(self.status, '#94a3b8')
    
    def get_status_display(self):
        """Restituisce nome display per stato"""
        status_display = {
            'planned': 'Pianificata',
            'in_progress': 'In Corso',
            'completed': 'Completata',
            'suspended': 'Sospesa'
        }
        return status_display.get(self.status, 'Sconosciuto')
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": self.id,
            "site_id": str(self.site_id),
            "plan_id": str(self.plan_id),
            "coordinates": {
                "x": self.coordinates_x,
                "y": self.coordinates_y
            },
            "size": {
                "x": self.size_x,
                "y": self.size_y
            },
            "status": self.status,
            "status_display": self.get_status_display(),
            "status_color": self.get_status_color(),
            "current_depth": self.current_depth,
            "max_depth": self.max_depth,
            "supervisor": self.supervisor,
            "team_members": self.team_members or [],
            "priority": self.priority,
            "notes": self.notes,
            "soil_description": self.soil_description,
            "preservation_conditions": self.preservation_conditions,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "completion_date": self.completion_date.isoformat() if self.completion_date else None,
            "last_excavation_date": self.last_excavation_date.isoformat() if self.last_excavation_date else None,
            "excavation_method": self.excavation_method,
            "documentation_level": self.documentation_level,
            "stratigraphic_sequence": self.stratigraphic_sequence or [],
            "finds_summary": self.finds_summary or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ArchaeologicalData(Base):
    """Modello per dati archeologici georeferenziati raccolti sulla pianta"""
    __tablename__ = "archaeological_data"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Relazioni
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_plans.id"), nullable=False)
    excavation_unit_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("excavation_units.id"), nullable=True)
    module_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("form_schemas.id"), nullable=False)
    
    # Coordinate del punto
    coordinates_x: Mapped[float] = mapped_column(Float, nullable=False)
    coordinates_y: Mapped[float] = mapped_column(Float, nullable=False)
    elevation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Quota altimetrica
    
    # Dati raccolti (JSON schemas-based)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Metadati raccolta
    collection_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    collector_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    collection_method: Mapped[str] = mapped_column(String(50), default="digital")  # "digital", "manual", "gps"
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Precisione in cm
    
    # Validazione
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_by: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relazioni
    site = relationship("ArchaeologicalSite")
    plan = relationship("ArchaeologicalPlan", back_populates="archaeological_data")
    excavation_unit = relationship("ExcavationUnit", back_populates="archaeological_data")
    module = relationship("FormSchema")
    collector = relationship("User", foreign_keys=[collector_id])
    validator = relationship("User", foreign_keys=[validated_by])
    
    def __repr__(self):
        return f"<ArchaeologicalData(id='{self.id}', plan='{self.plan_id}')>"
    
    def to_dict(self):
        """Conversione a dizionario per API"""
        return {
            "id": str(self.id),
            "site_id": str(self.site_id),
            "plan_id": str(self.plan_id),
            "excavation_unit_id": self.excavation_unit_id,
            "module_id": str(self.module_id),
            "coordinates": {
                "x": self.coordinates_x,
                "y": self.coordinates_y,
                "elevation": self.elevation
            },
            "data": self.data,
            "collection_date": self.collection_date.isoformat() if self.collection_date else None,
            "collector_id": str(self.collector_id),
            "collection_method": self.collection_method,
            "accuracy": self.accuracy,
            "is_validated": self.is_validated,
            "validated_by": str(self.validated_by) if self.validated_by else None,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "validation_notes": self.validation_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }