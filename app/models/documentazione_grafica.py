# app/models/documentazione_grafica.py
"""
Modelli per gestione documentazione grafica archeologica
Include Tavole, Disegni, Matrix Harris visuale, Sistema foto avanzato
Conforme agli standard di consegna documentazione alle Soprintendenze
"""

from datetime import date, datetime
from enum import Enum as PyEnum
from uuid import uuid4
from typing import List, Optional
from decimal import Decimal

from sqlalchemy import Column, String, Text, Boolean, DateTime, Date, Integer, ForeignKey, Numeric, JSON, func

from sqlalchemy.orm import relationship

from app.database.base import Base


# ===== ENUM PER DOCUMENTAZIONE =====
class TipoTavola(str, PyEnum):
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


class ScalaTavola(str, PyEnum):
    """Scale standard per tavole"""
    SCALA_1_10 = "1:10"
    SCALA_1_20 = "1:20"
    SCALA_1_50 = "1:50"
    SCALA_1_100 = "1:100"
    SCALA_1_200 = "1:200"
    SCALA_1_500 = "1:500"
    SCALA_1_1000 = "1:1000"
    SCALA_1_2000 = "1:2000"
    SCALA_1_5000 = "1:5000"
    SCALA_1_10000 = "1:10000"


class TipoFoto(str, PyEnum):
    """Tipologie fotografiche"""
    GENERALE_CANTIERE = "generale_cantiere"
    GENERALE_AREA = "generale_area"
    DETTAGLIO_US = "dettaglio_us"
    SEZIONE_US = "sezione_us"
    TOMBA_GENERALE = "tomba_generale"
    TOMBA_DETTAGLIO = "tomba_dettaglio"
    SCHELETRO = "scheletro"
    CORREDO = "corredo"
    REPERTO = "reperto"
    STRUTTURA = "struttura"
    PARTICOLARE = "particolare"
    CAMPIONE = "campione"
    WORKING = "working"  # foto di lavoro


class FormatoFile(str, PyEnum):
    """Formati file supportati"""
    PDF = "pdf"
    DWG = "dwg"
    DXF = "dxf"
    JPG = "jpg"
    TIFF = "tiff"
    PNG = "png"
    AI = "ai"
    EPS = "eps"


# ===== MODELLO TAVOLE GRAFICHE =====
class TavolaGrafica(Base):
    """
    Modello per gestione tavole grafiche e disegni
    Include numerazione automatica, metadati, versioning
    """
    __tablename__ = "tavole_grafiche"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), index=True)
    site_id = Column(String(36), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Numerazione
    numero_tavola = Column(String(20), nullable=False, index=True)  # es: "TAV001"
    numero_progressivo = Column(Integer, nullable=False)  # auto-incrementale per sito
    
    # Classificazione
    tipo_tavola = Column(String(30), nullable=False)  # Enum TipoTavola
    titolo = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    
    # Scala e dimensioni
    scala = Column(String(10), nullable=False)  # Enum ScalaTavola
    formato_foglio = Column(String(10), nullable=True)  # A4, A3, A2, A1, A0
    
    # File
    file_path = Column(String(500), nullable=False)  # path su MinIO
    file_name = Column(String(255), nullable=False)
    file_format = Column(String(10), nullable=False)  # Enum FormatoFile
    file_size = Column(Integer, nullable=True)  # in bytes
    
    # Autori e date
    autore_rilievo = Column(String(200), nullable=True)
    autore_disegno = Column(String(200), nullable=True)
    data_rilievo = Column(Date, nullable=True)
    data_disegno = Column(Date, nullable=True)
    
    # Contenuto
    area_rappresentata = Column(String(200), nullable=True)
    us_rappresentate = Column(Text, nullable=True)  # lista US separate da virgola
    tombe_rappresentate = Column(Text, nullable=True)  # lista tombe separate da virgola
    
    # Coordinate e georeferenziazione
    coordinate_note = Column(Text, nullable=True)
    sistema_riferimento = Column(String(100), nullable=True)  # UTM, Gauss-Boaga, etc.
    
    # Stato e versioning
    versione = Column(String(10), default="1.0", nullable=False)
    stato = Column(String(20), default="bozza", nullable=False)  # bozza, definitiva, revisionata
    note_versione = Column(Text, nullable=True)
    
    # Approvazione
    approvata = Column(Boolean, default=False)
    approvata_da = Column(String(200), nullable=True)
    data_approvazione = Column(Date, nullable=True)
    
    # Consegna
    consegnata = Column(Boolean, default=False)
    data_consegna = Column(Date, nullable=True)
    destinatario = Column(String(200), nullable=True)  # Soprintendenza, etc.
    
    # Note
    note_tecniche = Column(Text, nullable=True)
    note_generali = Column(Text, nullable=True)
    
    # Metadati
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="tavole_grafiche")
    
    def __repr__(self):
        return f"<TavolaGrafica(numero='{self.numero_tavola}', tipo='{self.tipo_tavola}')>"
    
    @property
    def codice_completo(self) -> str:
        """Codice completo tavola"""
        return f"{self.site.code}-{self.numero_tavola}" if self.site else self.numero_tavola


# ===== MODELLO FOTO AVANZATO =====
class FotografiaArcheologica(Base):
    """
    Modello per gestione sistematica delle fotografie archeologiche
    Include nomenclatura standardizzata, metadati EXIF, organizzazione per contenuto
    """
    __tablename__ = "fotografie_archeologiche"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), index=True)
    site_id = Column(String(36), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Numerazione standardizzata
    numero_foto = Column(String(20), nullable=False, unique=True, index=True)  # es: "PMP001_001"
    numero_progressivo = Column(Integer, nullable=False)  # auto-incrementale per sito
    
    # Classificazione
    tipo_foto = Column(String(30), nullable=False)  # Enum TipoFoto
    soggetto_principale = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=False)
    
    # File
    file_path = Column(String(500), nullable=False)  # path su MinIO
    file_name = Column(String(255), nullable=False)
    file_format = Column(String(10), nullable=False)
    file_size = Column(Integer, nullable=True)  # in bytes
    
    # Metadati EXIF
    camera_make = Column(String(100), nullable=True)
    camera_model = Column(String(100), nullable=True)
    lens_model = Column(String(100), nullable=True)
    focal_length = Column(String(20), nullable=True)
    aperture = Column(String(10), nullable=True)
    shutter_speed = Column(String(20), nullable=True)
    iso = Column(String(10), nullable=True)
    
    # Data e ora
    data_scatto = Column(DateTime, nullable=False)
    ora_scatto = Column(String(10), nullable=True)  # HH:MM estratto da EXIF
    
    # Localizzazione
    gps_latitude = Column(Numeric(10, 8), nullable=True)
    gps_longitude = Column(Numeric(11, 8), nullable=True)
    quota = Column(Numeric(8, 3), nullable=True)
    
    # Contesto archeologico - riferimenti a modelli esistenti
    # Nota: questi campi sono opzionali fino all'implementazione dei modelli correlati
    us_fotografata_id = Column(String(36), nullable=True)  # Riferimento a US quando disponibile
    tomba_fotografata_id = Column(String(36), nullable=True)  # Riferimento a tomba quando disponibile
    reperto_fotografato_id = Column(String(36), nullable=True)  # Riferimento a reperto quando disponibile
    
    # Tecnica fotografica
    direzione_scatto = Column(String(20), nullable=True)  # N, S, E, W, NE, etc.
    altezza_scatto = Column(Numeric(5, 2), nullable=True)  # altezza da terra in metri
    distanza_soggetto = Column(Numeric(5, 2), nullable=True)  # distanza dal soggetto in metri
    
    # Illuminazione
    tipo_illuminazione = Column(String(50), nullable=True)  # naturale, artificiale, flash, etc.
    condizioni_luce = Column(String(100), nullable=True)
    
    # Elaborazione
    post_elaborazione = Column(Boolean, default=False)
    software_elaborazione = Column(String(100), nullable=True)
    note_elaborazione = Column(Text, nullable=True)
    
    # Qualità e utilizzo
    qualita = Column(String(20), default="media", nullable=False)  # alta, media, bassa
    utilizzo_previsto = Column(String(100), nullable=True)  # documentazione, pubblicazione, etc.
    
    # Tag e keywords
    tag_liberi = Column(Text, nullable=True)  # tag separati da virgola
    parole_chiave = Column(Text, nullable=True)
    
    # Autore
    fotografo = Column(String(200), nullable=False)
    assistente = Column(String(200), nullable=True)
    
    # Pubblicazione
    pubblicabile = Column(Boolean, default=True)
    diritti_utilizzo = Column(String(200), nullable=True)
    copyright = Column(String(200), nullable=True)
    
    # Note
    note_tecniche = Column(Text, nullable=True)
    note_contenuto = Column(Text, nullable=True)
    
    # Sistema
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="fotografie_archeologiche")
    # Nota: relazioni con US, tombe e reperti da implementare quando disponibili i modelli correlati
    
    def __repr__(self):
        return f"<FotografiaArcheologica(numero='{self.numero_foto}', tipo='{self.tipo_foto}')>"
    
    @property
    def nome_file_standard(self) -> str:
        """Nome file secondo nomenclatura standard"""
        return f"{self.site.code}_{self.numero_progressivo:04d}" if self.site else f"NOSITE_{self.numero_progressivo:04d}"


# ===== MODELLO MATRIX HARRIS AVANZATA =====
class MatrixHarris(Base):
    """
    Modello per Matrix Harris completa
    Include diagramma stratigrafico, fasi, periodi, export grafico
    """
    __tablename__ = "matrix_harris"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), index=True)
    site_id = Column(String(36), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Identificativi
    nome_matrix = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    
    # Area di riferimento
    area = Column(String(100), nullable=True)
    settore = Column(String(50), nullable=True)
    
    # Configurazione visuale
    layout_config = Column(JSON, nullable=True)  # Configurazione posizionamento nodi
    stile_grafico = Column(JSON, nullable=True)  # Colori, forme, dimensioni
    
    # Fasi cronologiche
    fasi_cronologiche = Column(JSON, nullable=True)  # Lista fasi con relative US
    periodi_culturali = Column(JSON, nullable=True)  # Lista periodi archeologici
    
    # Interpretazione
    interpretazione_generale = Column(Text, nullable=True)
    sequenza_attivita = Column(Text, nullable=True)
    
    # Export
    immagine_path = Column(String(500), nullable=True)  # path immagine generata
    pdf_path = Column(String(500), nullable=True)  # path PDF generato
    ultima_generazione = Column(DateTime, nullable=True)
    
    # Validazione
    validata = Column(Boolean, default=False)
    validata_da = Column(String(200), nullable=True)
    data_validazione = Column(Date, nullable=True)
    note_validazione = Column(Text, nullable=True)
    
    # Versioning
    versione = Column(String(10), default="1.0", nullable=False)
    note_versione = Column(Text, nullable=True)
    
    # Autori
    compilatore = Column(String(200), nullable=False)
    revisore = Column(String(200), nullable=True)
    data_compilazione = Column(Date, nullable=False, default=date.today)
    data_revisione = Column(Date, nullable=True)
    
    # Sistema
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="matrix_harris")
    
    def __repr__(self):
        return f"<MatrixHarris(nome='{self.nome_matrix}', versione='{self.versione}')>"


# ===== MODELLO ELENCHI CONSEGNA =====
class ElencoConsegna(Base):
    """
    Modello per elenchi di consegna documentazione
    Include tutti gli elenchi richiesti dalle Soprintendenze
    """
    __tablename__ = "elenchi_consegna"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), index=True)
    site_id = Column(String(36), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Tipo elenco
    tipo_elenco = Column(String(50), nullable=False)  # tavole, foto, us, tombe, reperti, campioni, casse
    titolo = Column(String(200), nullable=False)
    
    # Contenuto elenco (JSON strutturato)
    contenuto = Column(JSON, nullable=False)
    
    # Generazione automatica
    generato_automaticamente = Column(Boolean, default=True)
    data_generazione = Column(DateTime, nullable=False, default=datetime.now)
    
    # Export
    formato_export = Column(String(20), nullable=True)  # pdf, excel, csv
    file_path = Column(String(500), nullable=True)
    
    # Metadati
    compilatore = Column(String(200), nullable=False)
    note = Column(Text, nullable=True)
    
    # Sistema
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="elenchi_consegna")
    
    def __repr__(self):
        return f"<ElencoConsegna(tipo='{self.tipo_elenco}', sito='{self.site.name if self.site else 'N/A'})>"
