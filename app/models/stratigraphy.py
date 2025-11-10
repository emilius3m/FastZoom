# app/models/stratigraphy.py
"""
Modelli per Unità Stratigrafiche (US) e Unità Stratigrafiche Murarie (USM)
Include gestione file integrata, Matrix Harris, standard MiC 2021
Basato su schede US-3.doc e USM template allegati
"""

import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, ForeignKey,
    Integer, Numeric, Table, Index, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base, SiteMixin, UserMixin, SoftDeleteMixin


# ===== TABELLE ASSOCIATIVE PER FILE =====

# US - File associazioni (many-to-many)
us_files_association = Table(
    'us_files_associations',
    Base.metadata,
    Column('us_id', String(36), ForeignKey('unita_stratigrafiche.id'), primary_key=True),
    Column('file_id', String(36), ForeignKey('us_files.id'), primary_key=True),
    Column('file_type', String(50), nullable=False),  # 'sezione', 'fotografia', 'pianta', 'prospetto'
    Column('created_at', DateTime, default=datetime.utcnow),
    Column('ordine', Integer, default=0)  # Per ordinamento file dello stesso tipo
)

# USM - File associazioni
usm_files_association = Table(
    'usm_files_associations',
    Base.metadata,
    Column('usm_id', String(36), ForeignKey('unita_stratigrafiche_murarie.id'), primary_key=True),
    Column('file_id', String(36), ForeignKey('us_files.id'), primary_key=True),
    Column('file_type', String(50), nullable=False),
    Column('created_at', DateTime, default=datetime.utcnow),
    Column('ordine', Integer, default=0)
)


# ===== ENUMS PER US/USM =====

class ConsistenzaEnum(str, PyEnum):
    """Consistenza unità stratigrafiche"""
    COMPATTA = "compatta"
    MEDIA = "media"
    FRIABILE = "friabile"
    MOLTO_FRIABILE = "molto_friabile"
    SCIOLTA = "sciolta"


class AffidabilitaEnum(str, PyEnum):
    """Affidabilità stratigrafica"""
    ALTA = "alta"
    MEDIA = "media"
    BASSA = "bassa"


class TecnicaCostruttiva(str, PyEnum):
    """Tecniche costruttive USM"""
    OPUS_QUADRATUM = "opus_quadratum"
    OPUS_INCERTUM = "opus_incertum"
    OPUS_RETICULATUM = "opus_reticulatum"
    OPUS_MIXTUM = "opus_mixtum"
    OPUS_TESTACEUM = "opus_testaceum"
    OPUS_SPICATUM = "opus_spicatum"
    PARAMENTO_ESTERNO = "paramento_esterno"
    PARAMENTO_INTERNO = "paramento_interno"


# ===== MODELLO FILES US/USM =====

class USFile(Base, SiteMixin, UserMixin):
    """File associati a US/USM (sezioni, fotografie, piante, prospetti)"""
    __tablename__ = 'us_files'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String(36), ForeignKey('archaeological_sites.id'), nullable=False)
    
    # Info file
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)  # Path MinIO o locale
    filesize = Column(Integer, nullable=False)
    mimetype = Column(String(100), nullable=False)
    
    # Metadati specifici US/USM
    file_category = Column(String(50), nullable=False)  # 'disegno', 'fotografia', 'documento'
    title = Column(String(200))
    description = Column(Text)
    
    # Info disegno tecnico
    scale_ratio = Column(String(50))  # 1:50, 1:100, etc.
    drawing_type = Column(String(50))  # 'pianta', 'sezione', 'prospetto'
    tavola_number = Column(String(50))  # TAV. 8, TAV. 38-39
    
    # Info fotografia
    photo_date = Column(Date)
    photographer = Column(String(200))
    camera_info = Column(String(200))
    
    # Metadati tecnici
    width = Column(Integer)  # Pixel o mm per disegni
    height = Column(Integer)
    dpi = Column(Integer)
    
    # Integrazione con sistema MinIO FastZoom
    is_deepzoom_enabled = Column(Boolean, default=False)
    deepzoom_status = Column(String(20), default='none')  # none, scheduled, processing, completed
    thumbnail_path = Column(String(500))
    
    # Gestione
    uploaded_by = Column(String(36), ForeignKey('users.id'), nullable=False)
    is_published = Column(Boolean, default=False)
    is_validated = Column(Boolean, default=False)
    validated_by = Column(String(36), ForeignKey('users.id'))
    validated_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relazioni
    site = relationship("ArchaeologicalSite", back_populates="us_files")
    uploaded_by_user = relationship("User", foreign_keys=[uploaded_by])
    validated_by_user = relationship("User", foreign_keys=[validated_by])
    
    def to_dict(self):
        """Conversione dict per API"""
        return {
            'id': str(self.id),
            'filename': self.filename,
            'original_filename': self.original_filename,
            'filesize': self.filesize,
            'mimetype': self.mimetype,
            'file_category': self.file_category,
            'title': self.title,
            'description': self.description,
            'scale_ratio': self.scale_ratio,
            'drawing_type': self.drawing_type,
            'tavola_number': self.tavola_number,
            'photo_date': self.photo_date.isoformat() if self.photo_date else None,
            'photographer': self.photographer,
            'width': self.width,
            'height': self.height,
            'is_deepzoom_enabled': self.is_deepzoom_enabled,
            'thumbnail_url': f"/api/us-files/{self.id}/thumbnail" if self.thumbnail_path else None,
            'download_url': f"/api/us-files/{self.id}/download",
            'view_url': f"/api/us-files/{self.id}/view",
            'is_published': self.is_published,
            'is_validated': self.is_validated,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


# ===== MODELLO US (UNITÀ STRATIGRAFICHE) =====

class UnitaStratigrafica(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Unità Stratigrafiche (US) - Standard MiC 2021
    Replica ESATTA della struttura scheda US-3.doc allegata
    """
    __tablename__ = "unita_stratigrafiche"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String(36), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== INTESTAZIONE E IDENTIFICAZIONE =====
    us_code = Column(String(16), nullable=False, index=True)  # US003
    ente_responsabile = Column(String(200))  # PARCO ARCHEOLOGICO DI SEPINO
    anno = Column(Integer)  # 2023
    ufficio_mic = Column(String(200))  # Ufficio MiC Competente
    identificativo_rif = Column(String(200))  # TERME P. BOJANO
    
    # ===== LOCALIZZAZIONE =====
    localita = Column(String(200))  # SEPINO (CB), ALTILIA
    area_struttura = Column(String(200))  # TERME PORTA BOJANO
    saggio = Column(String(100))  # Saggio scavo
    ambiente_unita_funzione = Column(String(200))  # TUTTA L'AREA
    posizione = Column(String(200))  # Posizione specifica
    settori = Column(String(200))  # A1, A2, B1...
    
    # ===== DOCUMENTAZIONE (CON RIFERIMENTI E FILE) =====
    # Riferimenti testuali (come nella scheda originale)
    piante_riferimenti = Column(Text)  # "TAV. 8" - riferimenti testuali 
    prospetti_riferimenti = Column(Text)  # "TAV. 15-16" 
    sezioni_riferimenti = Column(Text)  # "TAV. 38-39"
    
    # ===== DEFINIZIONE E CARATTERIZZAZIONE =====
    definizione = Column(Text)  # Accumulo di terreno argilloso
    criteri_distinzione = Column(Text)  # Composizione, colore, consistenza
    modo_formazione = Column(Text)  # Artificiale intenzionale
    
    # ===== COMPONENTI E PROPRIETÀ FISICHE =====
    componenti_inorganici = Column(Text)  # Elementi fittili, elementi lapidei
    componenti_organici = Column(Text)  # Apparati radicali, frammenti ossei
    consistenza = Column(String(50))  # compatta (Enum)
    colore = Column(String(50))  # Marrone scuro
    misure = Column(String(100))  # 8x3,20 m
    stato_conservazione = Column(Text)  # OTTIMO
    
    # ===== SEQUENZA FISICA (Matrix Harris) =====
    sequenza_fisica = Column(
        JSON,
        default=lambda: {
            "uguale_a": [], 
            "si_lega_a": [], 
            "gli_si_appoggia": [], 
            "si_appoggia_a": [],
            "coperto_da": [],  # 1
            "copre": [],  # 4, 8, 23, 25, 29, 79, 81, 225, 174(usm), 175(usm)
            "tagliato_da": [], 
            "taglia": [],
            "riempito_da": [], 
            "riempie": []
        },
        nullable=False,
    )
    
    # ===== DESCRIZIONE E INTERPRETAZIONE =====
    descrizione = Column(Text)  # Descrizione completa
    osservazioni = Column(Text)  # Note aggiuntive
    interpretazione = Column(Text)  # Interpretazione archeologica
    
    # ===== DATAZIONE E REPERTI =====
    datazione = Column(String(200))  # I sec. a.C. - I sec. d.C.
    periodo = Column(String(100))  # Romano imperiale
    fase = Column(String(100))  # Fase 2, III
    elementi_datanti = Column(Text)  # Monete, ceramica sigillata
    dati_quantitativi_reperti = Column(Text)  # Frr. ceramici: 150, ossa: 20
    
    # ===== CAMPIONATURE =====
    campionature = Column(
        JSON, 
        default=lambda: {
            "flottazione": False, 
            "setacciatura": False
        }, 
        nullable=False
    )
    
    # ===== AFFIDABILITÀ E RESPONSABILITÀ =====
    affidabilita_stratigrafica = Column(String(50))  # Alta/Media/Bassa
    responsabile_scientifico = Column(String(200))
    data_rilevamento = Column(Date)
    responsabile_compilazione = Column(String(200))
    data_rielaborazione = Column(Date)
    responsabile_rielaborazione = Column(String(200))

    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="unita_stratigrafiche")
    
    # Relazioni file
    files = relationship(
        "USFile",
        secondary=us_files_association,
        backref="unita_stratigrafiche",
        order_by=us_files_association.c.ordine
    )
    
    # Campioni e reperti associati
    campioni = relationship("CampioneScientifico", back_populates="unita_stratigrafica")
    reperti = relationship("InventarioReperto", back_populates="unita_stratigrafica") 
    
    # Indici per performance e integrità
    __table_args__ = (
        UniqueConstraint('site_id', 'us_code', name='uq_site_us_code'),
        Index('idx_us_site_code', 'site_id', 'us_code'),
        Index('idx_us_periodo', 'periodo'),
        Index('idx_us_datazione', 'datazione'),
    )
    
    def __repr__(self):
        return f"<US(code={self.us_code}, site={self.site.name if self.site else 'N/A'})>"
    
    # ===== METODI HELPER FILE =====
    
    def get_files_by_type(self, file_type: str) -> List['USFile']:
        """Ottieni file di un tipo specifico"""
        return [f for f in self.files 
                if any(assoc.file_type == file_type 
                      for assoc in f.unita_stratigrafiche_associations 
                      if assoc.us_id == self.id)]
    
    def get_piante(self) -> List['USFile']:
        """Ottieni file piante"""
        return self.get_files_by_type('pianta')
    
    def get_sezioni(self) -> List['USFile']:
        """Ottieni file sezioni"""
        return self.get_files_by_type('sezione')
    
    def get_prospetti(self) -> List['USFile']:
        """Ottieni file prospetti"""
        return self.get_files_by_type('prospetto')
    
    def get_fotografie(self) -> List['USFile']:
        """Ottieni fotografie"""
        return self.get_files_by_type('fotografia')
    
    def get_documenti(self) -> List['USFile']:
        """Ottieni documenti (PDF, etc.)"""
        return self.get_files_by_type('documento')
    
    def get_files_summary(self) -> Dict[str, Any]:
        """Riassunto file per UI"""
        return {
            'piante': len(self.get_piante()),
            'sezioni': len(self.get_sezioni()),
            'prospetti': len(self.get_prospetti()),
            'fotografie': len(self.get_fotografie()),
            'documenti': len(self.get_documenti()),
            'total': len(self.files)
        }
    
    # ===== METODI HELPER MATRIX HARRIS =====
    
    def get_relationships_summary(self) -> Dict[str, List[str]]:
        """Riassunto relazioni stratigrafiche"""
        if not self.sequenza_fisica:
            return {}
        return {k: v for k, v in self.sequenza_fisica.items() if v}
    
    def add_relationship(self, rel_type: str, target_us: str):
        """Aggiungi relazione stratigrafica"""
        if rel_type not in self.sequenza_fisica:
            return False
        
        if target_us not in self.sequenza_fisica[rel_type]:
            self.sequenza_fisica[rel_type].append(target_us)
            return True
        return False
    
    def remove_relationship(self, rel_type: str, target_us: str):
        """Rimuovi relazione stratigrafica"""
        if rel_type in self.sequenza_fisica and target_us in self.sequenza_fisica[rel_type]:
            self.sequenza_fisica[rel_type].remove(target_us)
            return True
        return False


# ===== MODELLO USM (UNITÀ STRATIGRAFICHE MURARIE) =====

class UnitaStratigraficaMuraria(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Unità Stratigrafiche Murarie (USM) - Standard MiC 2021
    Basato su template USM ufficiale con sezioni specifiche per strutture murarie
    """
    __tablename__ = "unita_stratigrafiche_murarie"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String(36), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== INTESTAZIONE E IDENTIFICAZIONE =====
    usm_code = Column(String(16), nullable=False, index=True)  # USM001
    ente_responsabile = Column(String(200))
    anno = Column(Integer)
    ufficio_mic = Column(String(200))
    identificativo_rif = Column(String(200))
    
    # ===== LOCALIZZAZIONE =====
    localita = Column(String(200))
    area_struttura = Column(String(200))
    saggio = Column(String(100))
    ambiente_unita_funzione = Column(String(200))
    posizione = Column(String(200))
    settori = Column(String(200))
    
    # ===== DOCUMENTAZIONE =====
    piante_riferimenti = Column(Text)
    prospetti_riferimenti = Column(Text)
    sezioni_riferimenti = Column(Text)
    
    # ===== MISURE E DEFINIZIONE =====
    misure = Column(String(100))  # 5.2x0.6x2.8 m
    superficie_analizzata = Column(Numeric(10, 2))  # m²
    definizione = Column(Text)  # Muro, fondazione, pavimento...
    
    # ===== TECNICA COSTRUTTIVA E STRUTTURA =====
    tecnica_costruttiva = Column(String(200))  # Paramento esterno/interno, opus...
    sezione_muraria_visibile = Column(Boolean, default=False)
    sezione_muraria_tipo = Column(String(200))  # A sacco, piena...
    sezione_muraria_spessore = Column(String(50))  # 60 cm
    funzione_statica = Column(String(200))  # Portante, non portante, contrafforte...
    modulo = Column(String(200))  # Dimensioni modulo mattoni
    criteri_distinzione = Column(Text)
    provenienza_materiali = Column(Text)  # Cava, reimpiego...
    orientamento = Column(String(100))  # N-S, E-O...
    uso_primario = Column(String(200))  # Funzione originaria
    riutilizzo = Column(String(200))  # Uso secondario, spoliazione...
    stato_conservazione = Column(Text)
    
    # ===== MATERIALI LATERIZI =====
    materiali_laterizi = Column(JSON, default=dict)  # {"tipo": [...], "consistenza": [...]}
    
    # ===== MATERIALI - ELEMENTI LITICI =====
    materiali_elementi_litici = Column(JSON, default=dict)  # {"litotipi": [...], "lavorazione": [...]}
    materiali_altro = Column(Text)  # Altri materiali
    
    # ===== LEGANTE E FINITURE =====
    legante = Column(JSON, default=dict)  # {"tipo": "...", "consistenza": "..."}
    legante_altro = Column(Text)
    finiture_elementi_particolari = Column(Text)  # Intonaco, decorazioni, iscrizioni...
    
    # ===== SEQUENZA FISICA (Matrix Harris) =====
    sequenza_fisica = Column(
        JSON,
        default=lambda: {
            "uguale_a": [], "si_lega_a": [], "gli_si_appoggia": [], "si_appoggia_a": [],
            "coperto_da": [], "copre": [], "tagliato_da": [], "taglia": [],
            "riempito_da": [], "riempie": []
        },
        nullable=False,
    )
    
    # ===== DESCRIZIONE E INTERPRETAZIONE =====
    descrizione = Column(Text)
    osservazioni = Column(Text)
    interpretazione = Column(Text)
    
    # ===== DATAZIONE =====
    datazione = Column(String(200))
    periodo = Column(String(100))
    fase = Column(String(100))
    elementi_datanti = Column(Text)
    
    # ===== CAMPIONATURE =====
    campionature = Column(
        JSON, 
        default=lambda: {
            "elementi_litici": False, 
            "laterizi": False, 
            "malta": False
        }, 
        nullable=False
    )
    
    # ===== AFFIDABILITÀ E RESPONSABILITÀ =====
    affidabilita_stratigrafica = Column(String(50))
    responsabile_scientifico = Column(String(200))
    data_rilevamento = Column(Date)
    responsabile_compilazione = Column(String(200))
    data_rielaborazione = Column(Date)
    responsabile_rielaborazione = Column(String(200))

    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="unita_stratigrafiche_murarie")
    
    # Relazioni file
    files = relationship(
        "USFile",
        secondary=usm_files_association,
        backref="unita_stratigrafiche_murarie",
        order_by=usm_files_association.c.ordine
    )
    
    # Campioni associati
    campioni = relationship("CampioneScientifico", back_populates="unita_stratigrafica_muraria")
    
    # Indici
    __table_args__ = (
        UniqueConstraint('site_id', 'usm_code', name='uq_site_usm_code'),
        Index('idx_usm_site_code', 'site_id', 'usm_code'),
        Index('idx_usm_tecnica', 'tecnica_costruttiva'),
    )
    
    def __repr__(self):
        return f"<USM(code={self.usm_code}, site={self.site.name if self.site else 'N/A'})>"
    
    # ===== METODI HELPER (stessi di US) =====
    
    def get_files_by_type(self, file_type: str) -> List['USFile']:
        return [f for f in self.files 
                if any(assoc.file_type == file_type 
                      for assoc in f.unita_stratigrafiche_murarie_associations 
                      if assoc.usm_id == self.id)]
    
    def get_piante(self) -> List['USFile']:
        return self.get_files_by_type('pianta')
    
    def get_sezioni(self) -> List['USFile']:
        return self.get_files_by_type('sezione')
    
    def get_prospetti(self) -> List['USFile']:
        return self.get_files_by_type('prospetto')
    
    def get_fotografie(self) -> List['USFile']:
        return self.get_files_by_type('fotografia')
    
    def get_documenti(self) -> List['USFile']:
        return self.get_files_by_type('documento')
    
    def get_files_summary(self) -> Dict[str, Any]:
        return {
            'piante': len(self.get_piante()),
            'sezioni': len(self.get_sezioni()),
            'prospetti': len(self.get_prospetti()),
            'fotografie': len(self.get_fotografie()),
            'documenti': len(self.get_documenti()),
            'total': len(self.files)
        }
    
    # ===== METODI SPECIFICI USM =====
    
    def get_materiali_summary(self) -> Dict[str, Any]:
        """Riassunto materiali USM"""
        laterizi = self.materiali_laterizi or {}
        litici = self.materiali_elementi_litici or {}
        legante = self.legante or {}
        
        return {
            'laterizi_tipi': laterizi.get('tipo', []),
            'laterizi_consistenza': laterizi.get('consistenza', []),
            'litici_litotipi': litici.get('litotipi', []),
            'litici_lavorazione': litici.get('lavorazione', []),
            'legante_tipo': legante.get('tipo', ''),
            'legante_consistenza': legante.get('consistenza', ''),
            'has_materiali_altro': bool(self.materiali_altro)
        }
    
    def has_sezione_muraria(self) -> bool:
        """Controlla se ha sezione muraria documentata"""
        return self.sezione_muraria_visibile and bool(self.sezione_muraria_tipo)