# app/models/documentation_and_field.py
"""
Modelli per documentazione, gestione cantiere e configurazioni
Include: Documenti, Foto, Giornali cantiere, Form personalizzati, ICCD, Export
"""

import uuid
from datetime import datetime, date, time
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, Time, ForeignKey,
    Integer, BigInteger, JSON, Index, UniqueConstraint, Table, Numeric
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, SiteMixin, UserMixin, SoftDeleteMixin


# ===== ENUMS =====

class DocumentCategoryEnum(str, PyEnum):
    """Categorie documenti"""
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
    Column('ore_lavorate', Numeric(4, 2), default=8.0),
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
    category = Column(String(100), nullable=False)    # Enum categorie
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


# ===== FOTO SISTEMA =====

class Photo(Base, SiteMixin, UserMixin):
    """
    Sistema fotografico integrato con deep zoom
    Riutilizza sistema MinIO esistente di FastZoom
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
    
    # ===== METADATI FOTOGRAFICI =====
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    keywords = Column(String(500), nullable=True)      # tag separati da virgola
    
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


# ===== TAVOLE GRAFICHE =====

class TavolaGrafica(Base, SiteMixin, UserMixin):
    """
    Gestione tavole grafiche e disegni archeologici
    Include numerazione automatica, metadati, versioning
    """
    __tablename__ = "tavole_grafiche"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id', ondelete='CASCADE'), nullable=False)

    # ===== NUMERAZIONE =====
    numero_tavola = Column(String(20), nullable=False, index=True)  # TAV001
    numero_progressivo = Column(Integer, nullable=False)            # auto-incrementale per sito
    
    # ===== CLASSIFICAZIONE =====
    tipo_tavola = Column(String(30), nullable=False)               # Enum TipoTavola
    titolo = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    
    # ===== METADATI TECNICI =====
    scala = Column(String(20), nullable=True)                      # 1:50, 1:100
    formato = Column(String(10), nullable=True)                    # A4, A3, A1
    software_utilizzato = Column(String(100), nullable=True)       # AutoCAD, QGIS
    
    # ===== FILE =====
    filepath = Column(String(500), nullable=True)                  # Path file originale
    formato_file = Column(String(10), nullable=True)               # PDF, DWG, JPG
    filesize = Column(BigInteger, nullable=True)
    
    # ===== VERSIONING =====
    versione = Column(String(10), default="1.0")
    note_versione = Column(Text, nullable=True)
    data_ultima_modifica = Column(DateTime, default=datetime.utcnow)
    
    # ===== RESPONSABILITÀ =====
    autore = Column(String(200), nullable=True)                    # Disegnatore
    revisore = Column(String(200), nullable=True)                  # Revisore
    approvato_da = Column(String(200), nullable=True)              # Responsabile approvazione
    data_approvazione = Column(DateTime, nullable=True)
    
    # ===== STATUS =====
    stato = Column(String(20), default='bozza')                    # bozza, revisione, approvato, archiviato
    pubblicato = Column(Boolean, default=False)
    
    # ===== SISTEMA =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="tavole_grafiche")

    def __repr__(self):
        return f"<TavolaGrafica(numero={self.numero_tavola}, tipo={self.tipo_tavola})>"


# ===== MATRIX HARRIS =====

class MatrixHarris(Base, SiteMixin, UserMixin):
    """
    Matrix Harris digitale per sequenze stratigrafiche
    Include relazioni US/USM, versioning, export
    """
    __tablename__ = "matrix_harris"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id', ondelete='CASCADE'), nullable=False)

    # ===== IDENTIFICAZIONE =====
    nome_matrix = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    area_riferimento = Column(String(100), nullable=True)          # Settore, Area, etc.
    
    # ===== DATI MATRIX =====
    us_incluse = Column(JSON, default=list)                        # Lista codici US
    usm_incluse = Column(JSON, default=list)                       # Lista codici USM
    relazioni = Column(JSON, default=dict)                         # Relazioni stratigrafiche complete
    
    # ===== LAYOUT GRAFICO =====
    layout_dati = Column(JSON, default=dict)                       # Coordinate nodi, stile, etc.
    configurazione_display = Column(JSON, default=dict)            # Colori, font, etc.
    
    # ===== VERSIONING =====
    versione = Column(String(10), default="1.0")
    note_versione = Column(Text, nullable=True)
    
    # ===== VALIDAZIONE =====
    validata = Column(Boolean, default=False)
    validata_da = Column(String(200), nullable=True)
    data_validazione = Column(DateTime, nullable=True)
    
    # ===== EXPORT =====
    ultimo_export = Column(DateTime, nullable=True)
    formati_export = Column(JSON, default=list)                    # PDF, SVG, GraphML
    
    # ===== SISTEMA =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="matrix_harris")

    def __repr__(self):
        return f"<MatrixHarris(nome={self.nome_matrix}, versione={self.versione})>"


# ===== OPERATORI CANTIERE =====

class OperatoreCantiere(Base, SiteMixin):
    """
    Anagrafica operatori di cantiere
    Include qualifiche, competenze, presenze
    """
    __tablename__ = "operatori_cantiere"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== ANAGRAFICA =====
    nome = Column(String(100), nullable=False)
    cognome = Column(String(100), nullable=False)
    codice_fiscale = Column(String(16), nullable=True, index=True)
    
    # ===== QUALIFICA PROFESSIONALE =====
    qualifica = Column(String(50), nullable=False)                 # Enum qualifiche
    specializzazioni = Column(JSON, default=list)                  # Lista specializzazioni
    anni_esperienza = Column(Integer, nullable=True)
    
    # ===== CONTATTI =====
    telefono = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    indirizzo = Column(Text, nullable=True)
    
    # ===== DATI LAVORATIVI =====
    data_assunzione = Column(Date, nullable=True)
    contratto = Column(String(100), nullable=True)                 # Tempo determinato/indeterminato
    retribuzione_giornaliera = Column(Numeric(8, 2), nullable=True)
    
    # ===== STATUS =====
    attivo = Column(Boolean, default=True)
    note = Column(Text, nullable=True)
    
    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== RELAZIONI =====
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


# ===== GIORNALE CANTIERE =====

class GiornaleCantiere(Base, SiteMixin, UserMixin):
    """
    Giornale giornaliero di cantiere archeologico
    Include condizioni meteo, lavori, personale, US elaborate
    """
    __tablename__ = "giornali_cantiere"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== DATA E IDENTIFICAZIONE =====
    data = Column(Date, nullable=False, index=True)
    numero_giornata = Column(Integer, nullable=True)               # Giorno progressivo scavo
    responsabile_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    # ===== ORARI =====
    ora_inizio = Column(Time, default=time(8, 0))
    ora_fine = Column(Time, default=time(17, 0))
    pausa_pranzo = Column(Integer, default=60)                     # minuti
    
    # ===== CONDIZIONI METEO =====
    meteo = Column(String(50), nullable=True)                      # sereno, nuvoloso, pioggia
    temperatura = Column(String(20), nullable=True)                # 15-22°C
    vento = Column(String(50), nullable=True)                      # assente, leggero, forte
    umidita = Column(String(20), nullable=True)                    # alta, media, bassa
    
    # ===== LAVORI ESEGUITI =====
    descrizione_lavori = Column(Text, nullable=False)              # Descrizione dettagliata
    settori_interessati = Column(String(200), nullable=True)       # A1, B2, C3
    us_elaborate = Column(String(500), nullable=True)              # Lista US separate da virgola
    usm_elaborate = Column(String(500), nullable=True)             # Lista USM separate da virgola
    
    # ===== ATTREZZATURE E MATERIALI =====
    attrezzatura_utilizzata = Column(Text, nullable=True)          # Lista attrezzature
    materiali_consumati = Column(Text, nullable=True)              # Sacchetti, etichette, etc.
    
    # ===== RITROVAMENTI =====
    reperti_rinvenuti = Column(Text, nullable=True)                # Descrizione reperti
    strutture_individuate = Column(Text, nullable=True)            # Nuove strutture
    campionature = Column(Text, nullable=True)                     # Campioni prelevati
    
    # ===== PROBLEMI E OSSERVAZIONI =====
    problemi_riscontrati = Column(Text, nullable=True)             # Problemi tecnici/logistici
    osservazioni = Column(Text, nullable=True)                     # Note generali
    
    # ===== SICUREZZA =====
    incidenti = Column(Text, nullable=True)                        # Eventuali incidenti
    misure_sicurezza = Column(Text, nullable=True)                 # Misure applicate
    
    # ===== VISITATORI =====
    visitatori = Column(Text, nullable=True)                       # Visitatori del giorno
    
    # ===== VALIDAZIONE =====
    validato = Column(Boolean, default=False)
    validato_da = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    data_validazione = Column(DateTime, nullable=True)
    
    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="giornali_cantiere")
    responsabile = relationship("User", foreign_keys=[responsabile_id], back_populates="giornali_cantiere")
    validatore = relationship("User", foreign_keys=[validato_da])
    
    # Operatori presenti (many-to-many)
    operatori = relationship(
        "OperatoreCantiere", 
        secondary=giornale_operatori_association,
        back_populates="giornali"
    )

    # ===== INDICI =====
    __table_args__ = (
        UniqueConstraint('site_id', 'data', name='uq_site_giornale_data'),
        Index('idx_giornale_site_data', 'site_id', 'data'),
        Index('idx_giornale_validato', 'validato'),
    )

    def __repr__(self):
        return f"<GiornaleCantiere(site={self.site.name if self.site else 'N/A'}, data={self.data})>"
    
    @property 
    def durata_lavoro(self) -> str:
        """Calcola durata lavoro in ore"""
        if self.ora_inizio and self.ora_fine:
            start = datetime.combine(self.data, self.ora_inizio)
            end = datetime.combine(self.data, self.ora_fine)
            if end < start:
                end += timedelta(days=1)
            duration = end - start - timedelta(minutes=self.pausa_pranzo or 0)
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        return "N/A"
    
    def get_us_list(self) -> List[str]:
        """Restituisce lista delle US elaborate come array"""
        if self.us_elaborate:
            return [us.strip() for us in self.us_elaborate.split(',') if us.strip()]
        return []
    
    def get_usm_list(self) -> List[str]:
        """Restituisce lista delle USM elaborate come array"""
        if self.usm_elaborate:
            return [usm.strip() for usm in self.usm_elaborate.split(',') if usm.strip()]
        return []


# ===== FORM PERSONALIZZATI =====

class FormSchema(Base, SiteMixin, UserMixin):
    """
    Form personalizzati per siti archeologici
    Builder di schede personalizzate per diversi tipi di reperti/strutture
    """
    __tablename__ = "form_schemas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== DEFINIZIONE FORM =====
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)                  # artifact, structure, stratigraphy, sample
    schema_json = Column(Text, nullable=False)                     # JSON string of the form schema
    
    # ===== STATUS =====
    is_active = Column(Boolean, default=True)
    
    # ===== SISTEMA =====
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="form_schemas")
    creator = relationship("User", back_populates="created_forms")

    def __repr__(self):
        return f"<FormSchema({self.name})>"


# ===== ICCD RECORDS =====

class ICCDBaseRecord(Base, SiteMixin, UserMixin):
    """
    Modello base per schede ICCD con supporto gerarchico
    Include SI, CA, MA, SAS, RA, NU, TMA, AT
    """
    __tablename__ = "iccd_base_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== IDENTIFICAZIONE NCT =====
    nct_region = Column(String(2), nullable=False)                 # IT, FR, etc.
    nct_number = Column(String(10), nullable=False)                # Numero progressivo
    nct_suffix = Column(String(5), nullable=True)                  # Suffisso alfabetico
    
    # ===== METADATI SCHEDA =====
    schema_type = Column(String(5), nullable=False)                # SI, CA, MA, SAS, RA, NU, TMA, AT
    schema_version = Column(String(10), default="3.00")
    level = Column(String(1), nullable=False, default='C')         # P, C, A
    
    # ===== RELAZIONI GERARCHICHE =====
    parent_id = Column(UUID(as_uuid=True), ForeignKey('iccd_base_records.id'), nullable=True)
    
    # ===== DATI ICCD =====
    iccd_data = Column(JSON, nullable=False)                       # Tutti i campi ICCD strutturati
    
    # ===== GESTIONE =====
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String(20), default='draft')                   # draft, validated, published
    
    # ===== SISTEMA =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ===== RELAZIONI =====
    parent = relationship("ICCDBaseRecord", remote_side=[id])
    children = relationship("ICCDBaseRecord", back_populates="parent")
    site = relationship("ArchaeologicalSite", back_populates="iccd_records")
    creator = relationship("User")

    # ===== INDICI E VINCOLI =====
    __table_args__ = (
        Index('idx_nct_complete', 'nct_region', 'nct_number', 'nct_suffix'),
        Index('idx_schema_site', 'schema_type', 'site_id'),
        Index('idx_hierarchy', 'parent_id', 'schema_type'),
        UniqueConstraint('nct_region', 'nct_number', 'nct_suffix', name='uq_nct_complete'),
    )

    def get_nct(self) -> str:
        """Restituisce il codice NCT completo"""
        suffix = self.nct_suffix or ""
        return f"{self.nct_region}{self.nct_number}{suffix}"
    
    def get_object_name(self) -> str:
        """Estrae il nome dell'oggetto dai dati ICCD"""
        try:
            return self.iccd_data.get('OG', {}).get('OGT', {}).get('OGTD', 'Oggetto sconosciuto')
        except (AttributeError, KeyError):
            return "Oggetto sconosciuto"

    def __repr__(self):
        return f"<ICCDRecord(nct={self.get_nct()}, type={self.schema_type})>"