# app/models/us_enhanced.py
"""
Modelli US/USM aggiornati con gestione file (sezioni, fotografie)
Integrazione con il sistema MinIO/Photo esistente di FastZoom
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from uuid import uuid4, UUID

from sqlalchemy import (
    Column, String, Text, Enum, Date, DateTime, Boolean, ForeignKey, 
    Numeric, Integer, Table
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ===== TABELLE ASSOCIATIVE PER FILE =====

# US - File associazioni (many-to-many)
us_files_association = Table(
    'us_files_associations',
    Base.metadata,
    Column('us_id', PG_UUID(as_uuid=True), ForeignKey('unita_stratigrafiche.id'), primary_key=True),
    Column('file_id', PG_UUID(as_uuid=True), ForeignKey('us_files.id'), primary_key=True),
    Column('file_type', String(50), nullable=False),  # 'sezione', 'fotografia', 'pianta', 'prospetto'
    Column('created_at', DateTime, default=datetime.utcnow),
    Column('ordine', Integer, default=0)  # Per ordinamento file dello stesso tipo
)

# USM - File associazioni  
usm_files_association = Table(
    'usm_files_associations',
    Base.metadata,
    Column('usm_id', PG_UUID(as_uuid=True), ForeignKey('unita_stratigrafiche_murarie.id'), primary_key=True),
    Column('file_id', PG_UUID(as_uuid=True), ForeignKey('us_files.id'), primary_key=True),
    Column('file_type', String(50), nullable=False),
    Column('created_at', DateTime, default=datetime.utcnow),
    Column('ordine', Integer, default=0)
)

# ===== MODELLO FILES US/USM =====

class USFile(Base):
    """File associati a US/USM (sezioni, fotografie, piante, prospetti)"""
    __tablename__ = 'us_files'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id = Column(PG_UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)
    
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
    uploaded_by = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    is_published = Column(Boolean, default=False)
    is_validated = Column(Boolean, default=False)
    validated_by = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'))
    validated_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relazioni
    site = relationship("ArchaeologicalSite", backref="us_files")
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

# ===== MODELLI US/USM AGGIORNATI =====

class UnitaStratigrafica(Base):
    """US con gestione file integrata"""
    __tablename__ = "unita_stratigrafiche"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id = Column(PG_UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== CAMPI ESISTENTI (dal modello precedente) =====
    us_code = Column(String(16), nullable=False, index=True)
    ente_responsabile = Column(String(200))
    anno = Column(Integer)
    ufficio_mic = Column(String(200))
    identificativo_rif = Column(String(200))
    localita = Column(String(200))
    area_struttura = Column(String(200))
    saggio = Column(String(100))
    ambiente_unita_funzione = Column(String(200))
    posizione = Column(String(200))
    settori = Column(String(200))
    
    # ===== CAMPI DOCUMENTAZIONE (AGGIORNATI) =====
    # Questi campi ora supportano riferimenti ai file
    piante_riferimenti = Column(Text)  # "TAV. 8, TAV. 12" - riferimenti testuali 
    prospetti_riferimenti = Column(Text)  # "TAV. 15-16" - riferimenti testuali
    sezioni_riferimenti = Column(Text)  # "TAV. 38-39" - riferimenti testuali
    
    # ===== RESTO CAMPI INVARIATO =====
    definizione = Column(Text)
    criteri_distinzione = Column(Text)
    modo_formazione = Column(Text)
    componenti_inorganici = Column(Text)
    componenti_organici = Column(Text)
    consistenza = Column(String(50))
    colore = Column(String(50))
    misure = Column(String(100))
    stato_conservazione = Column(Text)
    
    sequenza_fisica = Column(
        JSONB,
        default=lambda: {
            "uguale_a": [], "si_lega_a": [], "gli_si_appoggia": [], "si_appoggia_a": [],
            "coperto_da": [], "copre": [], "tagliato_da": [], "taglia": [],
            "riempito_da": [], "riempie": []
        },
        nullable=False,
    )
    
    descrizione = Column(Text)
    osservazioni = Column(Text)
    interpretazione = Column(Text)
    datazione = Column(String(200))
    periodo = Column(String(100))
    fase = Column(String(100))
    elementi_datanti = Column(Text)
    dati_quantitativi_reperti = Column(Text)
    
    campionature = Column(
        JSONB, default=lambda: {"flottazione": False, "setacciatura": False}, nullable=False
    )
    
    affidabilita_stratigrafica = Column(String(50))
    responsabile_scientifico = Column(String(200))
    data_rilevamento = Column(Date)
    responsabile_compilazione = Column(String(200))
    data_rielaborazione = Column(Date)
    responsabile_rielaborazione = Column(String(200))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ===== RELAZIONI FILE =====
    files = relationship(
        "USFile", 
        secondary=us_files_association,
        backref="unita_stratigrafiche",
        order_by="us_files_association.c.ordine"
    )
    
    site = relationship("ArchaeologicalSite", backref="unita_stratigrafiche")
    
    # ===== METODI HELPER FILE =====
    
    def get_files_by_type(self, file_type: str) -> List[USFile]:
        """Ottieni file di un tipo specifico"""
        return [f for f in self.files 
                if any(assoc.file_type == file_type 
                      for assoc in f.unita_stratigrafiche_associations 
                      if assoc.us_id == self.id)]
    
    def get_piante(self) -> List[USFile]:
        """Ottieni file piante"""
        return self.get_files_by_type('pianta')
    
    def get_sezioni(self) -> List[USFile]:
        """Ottieni file sezioni"""
        return self.get_files_by_type('sezione')
    
    def get_prospetti(self) -> List[USFile]:
        """Ottieni file prospetti"""
        return self.get_files_by_type('prospetto')
    
    def get_fotografie(self) -> List[USFile]:
        """Ottieni fotografie"""
        return self.get_files_by_type('fotografia')
    
    def get_documenti(self) -> List[USFile]:
        """Ottieni documenti (PDF, etc.)"""
        return self.get_files_by_type('documento')
    
    def add_file(self, us_file: USFile, file_type: str, ordine: int = 0):
        """Aggiungi file con tipo e ordinamento"""
        # Questa logica sarà gestita dal service layer
        pass
    
    def get_files_summary(self) -> dict:
        """Riassunto file per UI"""
        files_by_type = {}
        for file_obj in self.files:
            # Logic per contare file per tipo
            pass
        
        return {
            'piante': len(self.get_piante()),
            'sezioni': len(self.get_sezioni()),
            'prospetti': len(self.get_prospetti()),
            'fotografie': len(self.get_fotografie()),
            'documenti': len(self.get_documenti()),
            'total': len(self.files)
        }


class UnitaStratigraficaMuraria(Base):
    """USM con gestione file integrata - struttura simile a US"""
    __tablename__ = "unita_stratigrafiche_murarie"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id = Column(PG_UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== CAMPI ESISTENTI USM =====
    usm_code = Column(String(16), nullable=False, index=True)
    ente_responsabile = Column(String(200))
    anno = Column(Integer)
    ufficio_mic = Column(String(200))
    identificativo_rif = Column(String(200))
    localita = Column(String(200))
    area_struttura = Column(String(200))
    saggio = Column(String(100))
    ambiente_unita_funzione = Column(String(200))
    posizione = Column(String(200))
    settori = Column(String(200))
    
    # ===== CAMPI DOCUMENTAZIONE USM =====
    piante_riferimenti = Column(Text)
    prospetti_riferimenti = Column(Text)
    sezioni_riferimenti = Column(Text)
    
    # ===== RESTO CAMPI USM =====
    misure = Column(String(100))
    superficie_analizzata = Column(Numeric(10, 2))
    definizione = Column(Text)
    tecnica_costruttiva = Column(String(200))
    sezione_muraria_visibile = Column(Boolean)
    sezione_muraria_tipo = Column(String(200))
    sezione_muraria_spessore = Column(String(50))
    funzione_statica = Column(String(200))
    modulo = Column(String(200))
    criteri_distinzione = Column(Text)
    provenienza_materiali = Column(Text)
    orientamento = Column(String(100))
    uso_primario = Column(String(200))
    riutilizzo = Column(String(200))
    stato_conservazione = Column(Text)
    
    materiali_laterizi = Column(JSONB, default=dict)
    materiali_elementi_litici = Column(JSONB, default=dict)
    materiali_altro = Column(Text)
    legante = Column(JSONB, default=dict)
    legante_altro = Column(Text)
    finiture_elementi_particolari = Column(Text)
    
    sequenza_fisica = Column(
        JSONB,
        default=lambda: {
            "uguale_a": [], "si_lega_a": [], "gli_si_appoggia": [], "si_appoggia_a": [],
            "coperto_da": [], "copre": [], "tagliato_da": [], "taglia": [],
            "riempito_da": [], "riempie": []
        },
        nullable=False,
    )
    
    descrizione = Column(Text)
    osservazioni = Column(Text)
    interpretazione = Column(Text)
    datazione = Column(String(200))
    periodo = Column(String(100))
    fase = Column(String(100))
    elementi_datanti = Column(Text)
    
    campionature = Column(
        JSONB, default=lambda: {
            "elementi_litici": False, "laterizi": False, "malta": False
        }, nullable=False
    )
    
    affidabilita_stratigrafica = Column(String(50))
    responsabile_scientifico = Column(String(200))
    data_rilevamento = Column(Date)
    responsabile_compilazione = Column(String(200))
    data_rielaborazione = Column(Date)
    responsabile_rielaborazione = Column(String(200))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ===== RELAZIONI FILE USM =====
    files = relationship(
        "USFile", 
        secondary=usm_files_association,
        backref="unita_stratigrafiche_murarie",
        order_by="usm_files_association.c.ordine"
    )
    
    site = relationship("ArchaeologicalSite", backref="unita_stratigrafiche_murarie")
    
    # ===== METODI HELPER FILE USM (stessi di US) =====
    
    def get_files_by_type(self, file_type: str) -> List[USFile]:
        return [f for f in self.files 
                if any(assoc.file_type == file_type 
                      for assoc in f.unita_stratigrafiche_murarie_associations 
                      if assoc.usm_id == self.id)]
    
    def get_piante(self) -> List[USFile]:
        return self.get_files_by_type('pianta')
    
    def get_sezioni(self) -> List[USFile]:
        return self.get_files_by_type('sezione')
    
    def get_prospetti(self) -> List[USFile]:
        return self.get_files_by_type('prospetto')
    
    def get_fotografie(self) -> List[USFile]:
        return self.get_files_by_type('fotografia')
    
    def get_documenti(self) -> List[USFile]:
        return self.get_files_by_type('documento')
    
    def get_files_summary(self) -> dict:
        return {
            'piante': len(self.get_piante()),
            'sezioni': len(self.get_sezioni()),
            'prospetti': len(self.get_prospetti()),
            'fotografie': len(self.get_fotografie()),
            'documenti': len(self.get_documenti()),
            'total': len(self.files)
        }