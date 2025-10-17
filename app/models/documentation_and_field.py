# app/models/documentation_and_field.py - VERSIONE CORRETTA
"""
Modelli per documentazione, gestione cantiere e configurazioni
Include: Documenti, Foto, Giornali cantiere, Form personalizzati, ICCD, Export
INCLUDE: PhotoType, MaterialType, ConservationStatus RIPRISTINATI
"""

import uuid
from datetime import datetime, date, time
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, Time, ForeignKey,
    Integer, BigInteger, JSON, Index, UniqueConstraint, Table, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, SiteMixin, UserMixin, SoftDeleteMixin
from app.models.archaeological_enums import (
    PhotoType, MaterialType, ConservationStatus,  # RIPRISTINATI!
    DocumentType, ContextType, ArtifactCategory
)


# ===== LEGACY ENUMS (mantengo per compatibilità) =====

class DocumentCategoryEnum(str, PyEnum):
    """Categorie documenti (legacy - usa DocumentType)"""
    RELAZIONE = "relazione"
    PLANIMETRIA = "planimetria"
    DISEGNO = "disegno"
    FOTO = "foto"
    AUTORIZZAZIONE = "autorizzazione"
    BIBLIOGRAFIA = "bibliografia"
    RAPPORTO = "rapporto"
    ALTRO = "altro"


class PhotoStatusEnum(str, PyEnum):
    """Stati elaborazione foto"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class TipoTavolaEnum(str, PyEnum):
    """Tipologie tavole grafiche"""
    PIANTA_GENERALE = "pianta_generale"
    PIANTA_FASE = "pianta_fase"
    SEZIONE_GENERALE = "sezione_generale"
    SEZIONE_DETTAGLIO = "sezione_dettaglio"
    PROSPETTO = "prospetto"
    RILIEVO_TOMBA = "rilievo_tomba"
    RILIEVO_STRUTTURA = "rilievo_struttura"
    MATRIX_HARRIS = "matrix_harris"
    PLANIMETRIA_REPERTI = "planimetria_reperti"


class QualificaOperatoreEnum(str, PyEnum):
    """Qualifiche operatori"""
    DIRETTORE = "direttore"
    ASSISTENTE = "assistente"
    ARCHEOLOGO = "archeologo"
    SPECIALISTA = "specialista"
    TECNICO = "tecnico"
    OPERAIO = "operaio"
    STUDENTE = "studente"


# ===== TABELLA ASSOCIATIVA GIORNALE-OPERATORI =====

giornale_operatori_association = Table(
    'giornale_operatori_associations',
    Base.metadata,
    Column('giornale_id', UUID(as_uuid=True), ForeignKey('giornali_cantiere.id'), primary_key=True),
    Column('operatore_id', UUID(as_uuid=True), ForeignKey('operatori_cantiere.id'), primary_key=True),
    Column('ore_lavorate', Float, default=8.0),
    Column('note_giornaliere', Text, nullable=True)
)


# ===== DOCUMENTI =====

class Document(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Documenti del sito archeologico
    Include relazioni, autorizzazioni, planimetrie, bibliografia
    """
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== METADATI DOCUMENTO =====
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    
    # Usa enum moderno + backward compatibility
    category = Column(String(100), nullable=False)    # DocumentType values
    doc_type = Column(String(100), nullable=True)     # pdf, word, image, etc
    
    # ===== INFO FILE =====
    filename = Column(String(500), nullable=False)
    filepath = Column(String(1000), nullable=False)
    filesize = Column(BigInteger, nullable=False)      # bytes
    mimetype = Column(String(200), nullable=True)
    
    # ===== METADATI AGGIUNTIVI =====
    tags = Column(String(500), nullable=True)         # tag separati da virgola
    doc_date = Column(DateTime, nullable=True)        # Data del documento, non upload
    author = Column(String(200), nullable=True)       # Autore documento
    is_public = Column(Boolean, default=True)
    
    # ===== VERSIONING =====
    version = Column(Integer, default=1)
    version_notes = Column(Text, nullable=True)
    
    # ===== TIMESTAMP =====
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ===== SOFT DELETE =====
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    deleter = relationship("User", foreign_keys=[deleted_by])

    def __repr__(self):
        return f"<Document(title={self.title}, category={self.category})>"
    
    @property
    def category_display(self) -> str:
        """Nome display per categoria"""
        try:
            doc_type = DocumentType(self.category)
            return doc_type.value.replace('_', ' ').title()
        except (ValueError, AttributeError):
            return self.category.replace('_', ' ').title()


# ===== FOTO SISTEMA CON ENUM RIPRISTINATI =====

class Photo(Base, SiteMixin, UserMixin):
    """
    Sistema fotografico integrato con deep zoom
    INCLUDE: PhotoType enum ripristinato per classificazione
    """
    __tablename__ = "photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== INFO FILE =====
    filename = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=True)      # bytes
    
    # ===== METADATI IMMAGINE =====
    width = Column(Integer, nullable=True)             # pixel
    height = Column(Integer, nullable=True)            # pixel
    format = Column(String(10), nullable=True)         # JPEG, PNG, TIFF
    color_space = Column(String(20), nullable=True)    # RGB, CMYK
    
    # ===== METADATI FOTOGRAFICI CON ENUM RIPRISTINATO =====
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    keywords = Column(String(500), nullable=True)      # tag separati da virgola
    
    # RIPRISTINATO: PhotoType enum
    photo_type = Column(String(50), nullable=True)     # PhotoType values
    
    # Dati EXIF
    camera_make = Column(String(100), nullable=True)
    camera_model = Column(String(100), nullable=True)
    lens_info = Column(String(200), nullable=True)
    iso = Column(Integer, nullable=True)
    aperture = Column(String(20), nullable=True)       # f/2.8
    shutter_speed = Column(String(20), nullable=True)  # 1/125
    focal_length = Column(String(20), nullable=True)   # 85mm
    
    # ===== LOCALIZZAZIONE FOTO =====
    # Provenienza archeologica
    us_reference = Column(String(50), nullable=True)    # US di riferimento
    usm_reference = Column(String(50), nullable=True)   # USM di riferimento
    tomba_reference = Column(String(50), nullable=True) # Tomba di riferimento
    reperto_reference = Column(String(50), nullable=True) # Reperto di riferimento
    
    # Coordinate GPS da EXIF
    gps_lat = Column(String(50), nullable=True)
    gps_lng = Column(String(50), nullable=True)
    gps_altitude = Column(String(50), nullable=True)
    
    # ===== DEEP ZOOM INTEGRATION =====
    deepzoom_status = Column(String(20), default='none')  # none, scheduled, processing, completed, error
    deepzoom_processed_at = Column(DateTime, nullable=True)
    tile_count = Column(Integer, default=0)
    max_zoom_level = Column(Integer, default=0)
    
    # ===== GESTIONE =====
    photographer = Column(String(200), nullable=True)
    photo_date = Column(DateTime, nullable=True)        # Data scatto (da EXIF o manuale)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    is_featured = Column(Boolean, default=False)        # Foto in evidenza
    is_public = Column(Boolean, default=True)           # Visibilità pubblica
    sort_order = Column(Integer, default=0)             # Ordinamento
    
    # ===== TIMESTAMP =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="photos")
    uploader = relationship("User")

    # ===== INDICI =====
    __table_args__ = (
        Index('idx_photo_site_filename', 'site_id', 'filename'),
        Index('idx_photo_deepzoom', 'deepzoom_status'),
        Index('idx_photo_references', 'us_reference', 'usm_reference', 'tomba_reference'),
        Index('idx_photo_type', 'photo_type'),  # Nuovo indice per PhotoType
    )

    def __repr__(self):
        return f"<Photo(filename={self.filename}, site={self.site.name if self.site else 'N/A'})>"
    
    @property
    def has_coordinates(self) -> bool:
        """Controlla se ha coordinate GPS"""
        return bool(self.gps_lat and self.gps_lng)
    
    @property
    def is_deepzoom_ready(self) -> bool:
        """Controlla se deep zoom è pronto"""
        return self.deepzoom_status == 'completed'
    
    # ===== METODI PER PhotoType =====
    
    @property
    def photo_type_enum(self) -> Optional[PhotoType]:
        """Restituisce photo_type come enum"""
        if self.photo_type:
            try:
                return PhotoType(self.photo_type)
            except ValueError:
                return None
        return None
    
    @photo_type_enum.setter
    def photo_type_enum(self, value: PhotoType):
        """Imposta photo_type da enum"""
        self.photo_type = value.value if value else None
    
    @property
    def photo_type_display(self) -> str:
        """Nome visualizzabile per tipo foto"""
        from app.models.archaeological_enums import PHOTO_TYPE_DISPLAY
        photo_type_obj = self.photo_type_enum
        if photo_type_obj and photo_type_obj in PHOTO_TYPE_DISPLAY:
            return PHOTO_TYPE_DISPLAY[photo_type_obj]
        return self.photo_type.replace('_', ' ').title() if self.photo_type else 'Non specificato'
    
    def set_photo_type(self, photo_type: PhotoType):
        """Imposta tipo foto usando enum"""
        self.photo_type = photo_type.value
    
    def is_type(self, photo_type: PhotoType) -> bool:
        """Controlla se è di un tipo specifico"""
        return self.photo_type == photo_type.value


# ===== RESTO DEL FILE INVARIATO =====
# (Mantengo tutto il resto uguale per brevità...)

class TavolaGrafica(Base, SiteMixin, UserMixin):
    """Gestione tavole grafiche e disegni archeologici"""
    __tablename__ = "tavole_grafiche"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id', ondelete='CASCADE'), nullable=False)

    # Numero e classificazione
    numero_tavola = Column(String(20), nullable=False, index=True)
    numero_progressivo = Column(Integer, nullable=False)
    tipo_tavola = Column(String(30), nullable=False)
    titolo = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    
    # Metadati tecnici
    scala = Column(String(20), nullable=True)
    formato = Column(String(10), nullable=True)
    software_utilizzato = Column(String(100), nullable=True)
    
    # File
    filepath = Column(String(500), nullable=True)
    formato_file = Column(String(10), nullable=True)
    filesize = Column(BigInteger, nullable=True)
    
    # Versioning
    versione = Column(String(10), default="1.0")
    note_versione = Column(Text, nullable=True)
    data_ultima_modifica = Column(DateTime, default=datetime.utcnow)
    
    # Responsabilità
    autore = Column(String(200), nullable=True)
    revisore = Column(String(200), nullable=True)
    approvato_da = Column(String(200), nullable=True)
    data_approvazione = Column(DateTime, nullable=True)
    
    # Status
    stato = Column(String(20), default='bozza')
    pubblicato = Column(Boolean, default=False)
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relazioni
    site = relationship("ArchaeologicalSite", back_populates="tavole_grafiche")

    def __repr__(self):
        return f"<TavolaGrafica(numero={self.numero_tavola}, tipo={self.tipo_tavola})>"


class MatrixHarris(Base, SiteMixin, UserMixin):
    """Matrix Harris digitale per sequenze stratigrafiche"""
    __tablename__ = "matrix_harris"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id', ondelete='CASCADE'), nullable=False)

    nome_matrix = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    area_riferimento = Column(String(100), nullable=True)
    
    us_incluse = Column(JSON, default=list)
    usm_incluse = Column(JSON, default=list)
    relazioni = Column(JSON, default=dict)
    
    layout_dati = Column(JSON, default=dict)
    configurazione_display = Column(JSON, default=dict)
    
    versione = Column(String(10), default="1.0")
    note_versione = Column(Text, nullable=True)
    
    validata = Column(Boolean, default=False)
    validata_da = Column(String(200), nullable=True)
    data_validazione = Column(DateTime, nullable=True)
    
    ultimo_export = Column(DateTime, nullable=True)
    formati_export = Column(JSON, default=list)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    site = relationship("ArchaeologicalSite", back_populates="matrix_harris")

    def __repr__(self):
        return f"<MatrixHarris(nome={self.nome_matrix}, versione={self.versione})>"


# ===== OPERATORI E GIORNALI CANTIERE (invariati) =====

class OperatoreCantiere(Base, SiteMixin):
    """Anagrafica operatori di cantiere"""
    __tablename__ = "operatori_cantiere"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    nome = Column(String(100), nullable=False)
    cognome = Column(String(100), nullable=False)
    codice_fiscale = Column(String(16), nullable=True, index=True)
    
    qualifica = Column(String(50), nullable=False)
    specializzazioni = Column(JSON, default=list)
    anni_esperienza = Column(Integer, nullable=True)
    
    telefono = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    indirizzo = Column(Text, nullable=True)
    
    data_assunzione = Column(Date, nullable=True)
    contratto = Column(String(100), nullable=True)
    retribuzione_giornaliera = Column(Float, nullable=True)
    
    attivo = Column(Boolean, default=True)
    note = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    site = relationship("ArchaeologicalSite", back_populates="operatori_cantiere")
    giornali = relationship(
        "GiornaleCantiere", 
        secondary=giornale_operatori_association,
        back_populates="operatori"
    )

    def __repr__(self):
        return f"<OperatoreCantiere(nome={self.nome} {self.cognome}, qualifica={self.qualifica})>"
    
    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.cognome}"


class GiornaleCantiere(Base, SiteMixin, UserMixin):
    """Giornale giornaliero di cantiere archeologico"""
    __tablename__ = "giornali_cantiere"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # Data e identificazione
    data = Column(Date, nullable=False, index=True)
    numero_giornata = Column(Integer, nullable=True)
    responsabile_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    # Orari
    ora_inizio = Column(Time, default=time(8, 0))
    ora_fine = Column(Time, default=time(17, 0))
    pausa_pranzo = Column(Integer, default=60)  # minuti
    
    # Condizioni meteo
    meteo = Column(String(50), nullable=True)
    temperatura = Column(String(20), nullable=True)
    vento = Column(String(50), nullable=True)
    umidita = Column(String(20), nullable=True)
    
    # Lavori eseguiti
    descrizione_lavori = Column(Text, nullable=False)
    settori_interessati = Column(String(200), nullable=True)
    us_elaborate = Column(String(500), nullable=True)
    usm_elaborate = Column(String(500), nullable=True)
    
    # Attrezzature e materiali
    attrezzatura_utilizzata = Column(Text, nullable=True)
    materiali_consumati = Column(Text, nullable=True)
    
    # Ritrovamenti
    reperti_rinvenuti = Column(Text, nullable=True)
    strutture_individuate = Column(Text, nullable=True)
    campionature = Column(Text, nullable=True)
    
    # Problemi e osservazioni
    problemi_riscontrati = Column(Text, nullable=True)
    osservazioni = Column(Text, nullable=True)
    
    # Sicurezza
    incidenti = Column(Text, nullable=True)
    misure_sicurezza = Column(Text, nullable=True)
    
    # Visitatori
    visitatori = Column(Text, nullable=True)
    
    # Validazione
    validato = Column(Boolean, default=False)
    validato_da = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    data_validazione = Column(DateTime, nullable=True)
    
    # Sistema
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relazioni
    site = relationship("ArchaeologicalSite", back_populates="giornali_cantiere")
    responsabile = relationship("User", foreign_keys=[responsabile_id], back_populates="giornali_cantiere")
    validatore = relationship("User", foreign_keys=[validato_da])
    
    operatori = relationship(
        "OperatoreCantiere", 
        secondary=giornale_operatori_association,
        back_populates="giornali"
    )

    __table_args__ = (
        UniqueConstraint('site_id', 'data', name='uq_site_giornale_data'),
        Index('idx_giornale_site_data', 'site_id', 'data'),
        Index('idx_giornale_validato', 'validato'),
    )

    def __repr__(self):
        return f"<GiornaleCantiere(site={self.site.name if self.site else 'N/A'}, data={self.data})>"


# ===== FORM E ICCD (invariati) =====

class FormSchema(Base, SiteMixin, UserMixin):
    """Form personalizzati per siti archeologici"""
    __tablename__ = "form_schemas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)
    schema_json = Column(Text, nullable=False)
    
    is_active = Column(Boolean, default=True)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    site = relationship("ArchaeologicalSite", back_populates="form_schemas")
    creator = relationship("User", back_populates="created_forms")

    def __repr__(self):
        return f"<FormSchema({self.name})>"


# ICCDBaseRecord è importata da app.models.iccd_records per evitare duplicazione


# ===== HELPER FUNCTIONS PER ENUM USAGE =====

def create_photo_with_type(site_id: uuid.UUID, filename: str, photo_type: PhotoType, **kwargs) -> Photo:
    """Helper per creare Photo con PhotoType enum"""
    photo = Photo(
        site_id=site_id,
        filename=filename,
        photo_type=photo_type.value,
        **kwargs
    )
    return photo

def filter_photos_by_type(photos: List[Photo], photo_type: PhotoType) -> List[Photo]:
    """Filtra foto per tipo usando enum"""
    return [p for p in photos if p.photo_type == photo_type.value]

def get_photos_by_types(photos: List[Photo], photo_types: List[PhotoType]) -> Dict[PhotoType, List[Photo]]:
    """Raggruppa foto per tipo"""
    result = {}
    for photo_type in photo_types:
        result[photo_type] = filter_photos_by_type(photos, photo_type)
    return result