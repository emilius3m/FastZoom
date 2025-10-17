# app/models/sites.py
"""
Modelli per siti archeologici e configurazioni geografiche
Include gestione coordinate, metadati, e relazioni con tutti gli altri moduli
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional, Dict, Any

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, JSON, Float, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from decimal import Decimal

from app.models.base import Base, TimestampMixin, UserMixin, SoftDeleteMixin


class SiteStatusEnum(str, PyEnum):
    """Stati del sito archeologico"""
    PLANNED = "planned"  # In programmazione
    ACTIVE = "active"  # Scavo attivo
    SUSPENDED = "suspended"  # Sospeso
    COMPLETED = "completed"  # Completato
    ARCHIVED = "archived"  # Archiviato


class SiteTypeEnum(str, PyEnum):
    """Tipologie sito"""
    NECROPOLI = "necropoli"
    ABITATO = "abitato"
    VILLA = "villa"
    TEMPIO = "tempio"
    FORTIFICAZIONE = "fortificazione"
    INDUSTRIAL = "industrial"
    UNDERWATER = "underwater"
    CAVE = "cave"
    OTHER = "other"


class ResearchStatusEnum(str, PyEnum):
    """Status ricerca archeologica"""
    SURVEY = "survey"  # Ricognizione
    EXCAVATION = "excavation"  # Scavo
    STUDY = "study"  # Studio
    PUBLICATION = "publication"  # Pubblicazione
    MONITORING = "monitoring"  # Monitoraggio


class ArchaeologicalSite(Base, UserMixin, SoftDeleteMixin):
    """
    Modello principale per siti archeologici
    Centro del sistema multi-tenant - ogni contenuto appartiene a un sito
    """
    __tablename__ = "archaeological_sites"

    # Chiave primaria
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # === IDENTIFICAZIONE SITO ===
    name = Column(String(200), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # Codice univoco sito
    alternative_names = Column(JSON, default=list)  # Nomi alternativi/storici

    description = Column(Text, nullable=True)
    short_description = Column(String(500), nullable=True)  # Per preview/cards

    # === CLASSIFICAZIONE ARCHEOLOGICA ===
    site_type = Column(String(50), default=SiteTypeEnum.OTHER, nullable=False)
    historical_period = Column(String(200), nullable=True)  # Es: "Romano Imperiale", "Medievale"
    chronology_start = Column(String(100), nullable=True)  # Es: "I sec. a.C."
    chronology_end = Column(String(100), nullable=True)  # Es: "III sec. d.C."
    cultural_attribution = Column(String(200), nullable=True)  # Cultura archeologica

    # === LOCALIZZAZIONE GEOGRAFICA ===
    # Coordinate GPS (WGS84)
    coordinates_lat = Column(String(20), nullable=True, index=True)  # Latitudine
    coordinates_lng = Column(String(20), nullable=True, index=True)  # Longitudine
    coordinates_precision = Column(Float, nullable=True)  # Precisione in metri
    elevation = Column(Float, nullable=True)  # Quota s.l.m.

    # Localizzazione amministrativa
    country = Column(String(100), default="Italia", nullable=False)
    region = Column(String(100), nullable=True)  # Regione
    province = Column(String(100), nullable=True)  # Provincia/Città Metropolitana
    municipality = Column(String(100), nullable=True)  # Comune
    locality = Column(String(200), nullable=True)  # Località/frazione
    address = Column(String(300), nullable=True)  # Indirizzo specifico

    # Riferimenti catastali
    cadastral_sheet = Column(String(50), nullable=True)  # Foglio catastale
    cadastral_parcels = Column(JSON, default=list)  # Particelle catastali

    # === STATUS E GESTIONE ===
    status = Column(String(20), default=SiteStatusEnum.PLANNED, nullable=False, index=True)
    research_status = Column(String(20), default=ResearchStatusEnum.SURVEY, nullable=False)

    # Date principali
    discovery_date = Column(DateTime, nullable=True)  # Data scoperta
    excavation_start = Column(DateTime, nullable=True)  # Inizio scavi
    excavation_end = Column(DateTime, nullable=True)  # Fine scavi

    # === DATI SCIENTIFICI ===
    research_project = Column(String(300), nullable=True)  # Progetto di ricerca
    funding_source = Column(String(300), nullable=True)  # Finanziamento
    excavation_method = Column(String(200), nullable=True)  # Metodologia scavo

    # Bibliografia e riferimenti
    bibliography = Column(JSON, default=list)  # Lista pubblicazioni
    external_references = Column(JSON, default=dict)  # Link esterni, ID altri DB

    # === AUTORIZZAZIONI AMMINISTRATIVE ===
    authorization_number = Column(String(100), nullable=True)  # N. autorizzazione MiC
    authorization_date = Column(DateTime, nullable=True)  # Data autorizzazione
    superintendency = Column(String(300), nullable=True)  # Soprintendenza competente

    # === CONFIGURAZIONI TECNICHE ===
    # Configurazioni display e export
    default_coordinate_system = Column(String(50), default="WGS84", nullable=False)
    default_measurement_unit = Column(String(10), default="m", nullable=False)
    site_grid_system = Column(JSON, default=dict)  # Sistema griglia sito

    # Metadati per sistema
    is_public = Column(Boolean, default=False)  # Visibilità pubblica
    is_template = Column(Boolean, default=False)  # Sito template per copia
    storage_quota_mb = Column(Integer, default=10240)  # Quota storage (10GB default)

    # === TIMESTAMP E UTENTI ===
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # === RELAZIONI ===
    # Utenti e permessi
    creator = relationship("User",
                         primaryjoin="ArchaeologicalSite.created_by == User.id",
                         back_populates="created_sites")
    user_permissions = relationship("UserSitePermission", back_populates="site", cascade="all, delete-orphan")

    # === CONTENUTI ARCHEOLOGICI ===
    # Unità stratigrafiche (US/USM)
    unita_stratigrafiche = relationship("UnitaStratigrafica", back_populates="site", cascade="all, delete-orphan")
    unita_stratigrafiche_murarie = relationship("UnitaStratigraficaMuraria", back_populates="site",
                                                cascade="all, delete-orphan")

    # Tombe e sepolture
    schede_tombe = relationship("SchedaTomba", back_populates="site", cascade="all, delete-orphan")

    # Inventario reperti
    inventario_reperti = relationship("InventarioReperto", back_populates="site", cascade="all, delete-orphan")

    # Campioni scientifici
    campioni_scientifici = relationship("CampioneScientifico", back_populates="site", cascade="all, delete-orphan")

    # === DOCUMENTAZIONE ===
    # File e foto
    photos = relationship("Photo", back_populates="site", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="site", cascade="all, delete-orphan")
    us_files = relationship("USFile", back_populates="site", cascade="all, delete-orphan")

    # Documentazione grafica
    tavole_grafiche = relationship("TavolaGrafica", back_populates="site", cascade="all, delete-orphan")
    matrix_harris = relationship("MatrixHarris", back_populates="site", cascade="all, delete-orphan")
    elenchi_consegna = relationship("ElencoConsegna", back_populates="site", cascade="all, delete-orphan")

    # === GESTIONE CANTIERE ===
    # Giornali di cantiere e operatori
    giornali_cantiere = relationship("GiornaleCantiere", back_populates="site", cascade="all, delete-orphan")
    operatori_cantiere = relationship("OperatoreCantiere", back_populates="site", cascade="all, delete-orphan")

    # === CONFIGURAZIONI E STANDARD ===
    # Form personalizzati e ICCD
    form_schemas = relationship("FormSchema", back_populates="site", cascade="all, delete-orphan")
    iccd_records = relationship("ICCDBaseRecord", back_populates="site", cascade="all, delete-orphan")

    # Configurazioni export e report
    configurazioni_export = relationship("ConfigurazioneExport", back_populates="site", cascade="all, delete-orphan")
    relazioni_finali = relationship("RelazioneFinaleScavo", back_populates="site", cascade="all, delete-orphan")

    # === MAPPE E GIS ===
    geographic_maps = relationship("GeographicMap", back_populates="site", cascade="all, delete-orphan")

    # Indici per performance
    __table_args__ = (
        Index('idx_site_coords', 'coordinates_lat', 'coordinates_lng'),
        Index('idx_site_location', 'region', 'municipality'),
        Index('idx_site_status', 'status', 'research_status'),
        Index('idx_site_period', 'historical_period'),
    )

    def __repr__(self):
        return f"<ArchaeologicalSite(code={self.code}, name={self.name})>"

    def __str__(self):
        return f"{self.name} ({self.code})"

    # === METODI HELPER ===

    @property
    def display_location(self) -> str:
        """Localizzazione per display UI"""
        parts = [self.municipality, self.province, self.region]
        return ", ".join(p for p in parts if p)

    @property
    def coordinates(self) -> Optional[Dict[str, float]]:
        """Coordinate GPS come dizionario"""
        if self.coordinates_lat and self.coordinates_lng:
            try:
                return {
                    'lat': float(self.coordinates_lat),
                    'lng': float(self.coordinates_lng),
                    'precision': self.coordinates_precision
                }
            except (ValueError, TypeError):
                return None
        return None

    @property
    def is_active_excavation(self) -> bool:
        """Controlla se scavo è attivo"""
        return self.status == SiteStatusEnum.ACTIVE

    @property
    def excavation_duration_days(self) -> Optional[int]:
        """Durata scavo in giorni"""
        if self.excavation_start and self.excavation_end:
            return (self.excavation_end.date() - self.excavation_start.date()).days
        return None

    def get_total_us_count(self) -> int:
        """Conta totale US + USM"""
        return len(self.unita_stratigrafiche) + len(self.unita_stratigrafiche_murarie)

    def get_storage_usage_mb(self) -> float:
        """Calcola uso storage in MB (approssimato)"""
        # Calcolo semplificato basato su file photos/documents
        total_size = 0
        for photo in self.photos:
            if hasattr(photo, 'file_size') and photo.file_size:
                total_size += photo.file_size
        for doc in self.documents:
            if hasattr(doc, 'filesize') and doc.filesize:
                total_size += doc.filesize
        return total_size / (1024 * 1024)  # Convert to MB

    def get_storage_usage_percentage(self) -> float:
        """Percentuale uso storage"""
        if not self.storage_quota_mb:
            return 0.0
        usage_mb = self.get_storage_usage_mb()
        return min((usage_mb / self.storage_quota_mb) * 100, 100.0)

    def has_coordinates(self) -> bool:
        """Controlla se ha coordinate GPS valide"""
        return bool(self.coordinates_lat and self.coordinates_lng)

    def add_alternative_name(self, name: str):
        """Aggiunge nome alternativo"""
        names = self.alternative_names or []
        if name not in names:
            names.append(name)
            self.alternative_names = names

    def get_bibliography_list(self) -> List[str]:
        """Lista bibliografia come stringhe"""
        return self.bibliography or []

    def add_bibliography_entry(self, entry: str):
        """Aggiunge voce bibliografica"""
        biblio = self.bibliography or []
        if entry not in biblio:
            biblio.append(entry)
            self.bibliography = biblio

    def get_site_summary(self) -> Dict[str, Any]:
        """Riassunto sito per dashboard"""
        return {
            'name': self.name,
            'code': self.code,
            'status': self.status,
            'location': self.display_location,
            'period': self.historical_period,
            'us_count': self.get_total_us_count(),
            'tomb_count': len(self.schede_tombe),
            'artifact_count': len(self.inventario_reperti),
            'photo_count': len(self.photos),
            'storage_usage_pct': self.get_storage_usage_percentage(),
            'has_coordinates': self.has_coordinates(),
            'created_at': self.created_at,
            'last_activity': self.updated_at
        }


# GeographicMap è importata da app.models.geographic_maps per evitare duplicazione