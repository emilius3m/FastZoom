# app/models/archeologia_avanzata.py
"""
Modelli avanzati per documentazione archeologica completa
Include Matrix Harris, Schede ICCD complete, Inventario Reperti, Campioni
Conforme alle normative italiane DM 154/2017 e linee guida Soprintendenze
"""

from datetime import date, datetime
from enum import Enum as PyEnum
from uuid import uuid4
from typing import List, Optional, Dict, Any
from decimal import Decimal

from sqlalchemy import Column, String, Text, Boolean, DateTime, Date, Integer, ForeignKey, Table, Numeric, JSON, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.database.base import Base


# ===== ENUM PER TIPOLOGIE =====
class TipoUS(str, PyEnum):
    """Tipologie Unità Stratigrafiche"""
    STRATO = "strato"
    TAGLIO = "taglio"
    RIEMPIMENTO = "riempimento"
    STRUTTURA = "struttura"
    INTERFACCIA = "interfaccia"
    DEPOSITO = "deposito"


class TipoTomba(str, PyEnum):
    """Tipologie di sepoltura"""
    FOSSA = "fossa"
    CAPPUCCINA = "cappuccina"
    CASSA_MURARIA = "cassa_muraria"
    SARCOFAGO = "sarcofago"
    INCINERAZIONE = "incinerazione"
    ENCHYTRISMOS = "enchytrismos"


class RitoSepolcrale(str, PyEnum):
    """Riti di sepoltura"""
    INUMAZIONE = "inumazione"
    INCINERAZIONE = "incinerazione"
    MISTO = "misto"
    NON_DETERMINABILE = "non_determinabile"


class TipoMateriale(str, PyEnum):
    """Categorie materiali archeologici"""
    CERAMICA = "ceramica"
    METALLO = "metallo"
    VETRO = "vetro"
    OSSO = "osso"
    PIETRA = "pietra"
    CARBONE = "carbone"
    LEGNO = "legno"
    TESSUTO = "tessuto"
    MONETA = "moneta"
    ALTRO = "altro"


class TipoCampione(str, PyEnum):
    """Tipologie di campioni scientifici"""
    CARBONIO_14 = "carbonio_14"
    PALEOBOTANICO = "paleobotanico"
    ARCHEOZOOLOGICO = "archeozoologico"
    SEDIMENTO = "sedimento"
    MALTE = "malte"
    METALLI = "metalli"
    CERAMICA_ANALISI = "ceramica_analisi"


class StatoConservazione(str, PyEnum):
    """Stati di conservazione"""
    OTTIMO = "ottimo"
    BUONO = "buono"
    DISCRETO = "discreto"
    CATTIVO = "cattivo"
    PESSIMO = "pessimo"
    FRAMMENTARIO = "frammentario"


# ===== TABELLE ASSOCIATIVE =====
matrix_harris_relations = Table(
    'matrix_harris_relations',
    Base.metadata,
    Column('id', UUID(as_uuid=True), primary_key=True, default=uuid4),
    Column('us_superiore_id', UUID(as_uuid=True), ForeignKey('unita_stratigrafiche_complete.id', ondelete='CASCADE'), nullable=False),
    Column('us_inferiore_id', UUID(as_uuid=True), ForeignKey('unita_stratigrafiche_complete.id', ondelete='CASCADE'), nullable=False),
    Column('tipo_relazione', String(50), nullable=False),  # "copre", "taglia", "riempie", etc.
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)

reperti_materiali_association = Table(
    'reperti_materiali',
    Base.metadata,
    Column('id', UUID(as_uuid=True), primary_key=True, default=uuid4),
    Column('reperto_id', UUID(as_uuid=True), ForeignKey('inventario_reperti.id', ondelete='CASCADE')),
    Column('materiale_id', UUID(as_uuid=True), ForeignKey('materiali_archeologici.id', ondelete='CASCADE')),
    Column('quantita', Integer, default=1),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)


# ===== MODELLO UNITÀ STRATIGRAFICHE COMPLETE =====
class UnitaStratigraficaCompleta(Base):
    """
    Modello per Unità Stratigrafiche complete con standard ICCD
    Include tutti i campi necessari per schede US definitive
    """
    __tablename__ = "unita_stratigrafiche_complete"
    
    # Identificativi
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    numero_us = Column(String(20), nullable=False, index=True)  # es: "US001"
    
    # Informazioni base
    tipo_us = Column(String(20), nullable=False)  # Enum TipoUS
    denominazione = Column(String(200), nullable=True)
    descrizione = Column(Text, nullable=False)
    
    # Dati stratigrafici
    formazione = Column(String(100), nullable=True)  # naturale, artificiale
    consistenza = Column(String(100), nullable=True)  # compatto, friabile, etc.
    colore_munsell = Column(String(20), nullable=True)  # Codice Munsell
    colore_descrizione = Column(String(100), nullable=True)
    
    # Dimensioni e posizione
    lunghezza_max = Column(Numeric(8, 2), nullable=True)  # in metri
    larghezza_max = Column(Numeric(8, 2), nullable=True)
    spessore_max = Column(Numeric(8, 2), nullable=True)
    spessore_min = Column(Numeric(8, 2), nullable=True)
    quota_superiore = Column(Numeric(8, 3), nullable=True)  # quota assoluta
    quota_inferiore = Column(Numeric(8, 3), nullable=True)
    
    # Composizione
    componenti_principali = Column(Text, nullable=True)
    componenti_secondari = Column(Text, nullable=True)
    inclusi = Column(Text, nullable=True)
    
    # Interpretazione
    interpretazione = Column(Text, nullable=True)
    cronologia = Column(String(200), nullable=True)
    periodo = Column(String(100), nullable=True)
    fase = Column(String(50), nullable=True)
    
    # Scavo
    data_scavo = Column(Date, nullable=True)
    metodo_scavo = Column(String(100), nullable=True)
    responsabile_scavo = Column(String(200), nullable=True)
    
    # Stato conservazione
    stato_conservazione = Column(String(20), nullable=True)  # Enum StatoConservazione
    agenti_degrado = Column(Text, nullable=True)
    
    # Documentazione
    foto_numeri = Column(Text, nullable=True)  # Lista numeri foto
    disegni_numeri = Column(Text, nullable=True)  # Lista numeri disegni
    campioni_prelevati = Column(Boolean, default=False)
    
    # Note
    note_generali = Column(Text, nullable=True)
    note_tecniche = Column(Text, nullable=True)
    
    # Metadati
    compilatore = Column(String(200), nullable=True)
    data_compilazione = Column(Date, nullable=False, default=date.today)
    revisore = Column(String(200), nullable=True)
    data_revisione = Column(Date, nullable=True)
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    version = Column(Integer, default=1, nullable=False)
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="unita_stratigrafiche_complete")
    
    # Relazioni stratigrafiche (Matrix Harris)
    us_superiori = relationship(
        "UnitaStratigraficaCompleta",
        secondary=matrix_harris_relations,
        primaryjoin=id==matrix_harris_relations.c.us_inferiore_id,
        secondaryjoin=id==matrix_harris_relations.c.us_superiore_id,
        back_populates="us_inferiori"
    )
    
    us_inferiori = relationship(
        "UnitaStratigraficaCompleta",
        secondary=matrix_harris_relations,
        primaryjoin=id==matrix_harris_relations.c.us_superiore_id,
        secondaryjoin=id==matrix_harris_relations.c.us_inferiore_id,
        back_populates="us_superiori"
    )
    
    # Relazione con reperti trovati in questa US
    reperti = relationship("InventarioReperto",
                           foreign_keys="InventarioReperto.unita_stratigrafica_completa_id",
                           back_populates="unita_stratigrafica_completa")
    
    # Relazione con campioni prelevati
    campioni = relationship("CampioneScientifico",
                           foreign_keys="CampioneScientifico.unita_stratigrafica_completa_id",
                           back_populates="unita_stratigrafica_completa")
    
    def __repr__(self):
        return f"<UnitaStratigraficaCompleta(numero='{self.numero_us}', tipo='{self.tipo_us}')>"
    
    @property
    def codice_completo(self) -> str:
        """Restituisce codice completo US"""
        return f"{self.site.code}-{self.numero_us}" if self.site else self.numero_us


# ===== MODELLO TOMBE/SEPOLTURE =====
# SchedaTomba è importata da archaeological_records per evitare duplicazione
from app.models.archaeological_records import SchedaTomba  # noqa: F401

# ===== MODELLO INVENTARIO REPERTI =====
# InventarioReperto è importato da archaeological_records per evitare duplicazione
from app.models.archaeological_records import InventarioReperto  # noqa: F401

# ===== MODELLO MATERIALI ARCHEOLOGICI =====
class MaterialeArcheologico(Base):
    """
    Modello per tipologie di materiali archeologici
    Database di riferimento per classificazione
    """
    __tablename__ = "materiali_archeologici"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Classificazione
    categoria = Column(String(30), nullable=False)  # Enum TipoMateriale
    sottocategoria = Column(String(100), nullable=True)
    tipo = Column(String(100), nullable=False)
    sottotipo = Column(String(100), nullable=True)
    
    # Descrizione
    nome_comune = Column(String(200), nullable=False)
    nome_scientifico = Column(String(200), nullable=True)
    descrizione = Column(Text, nullable=True)
    
    # Caratteristiche
    caratteristiche_tipiche = Column(Text, nullable=True)
    cronologia_tipo = Column(String(200), nullable=True)
    
    # Bibliografia di riferimento
    bibliografia_tipo = Column(Text, nullable=True)
    
    # Metadati
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ===== RELAZIONI =====
    reperti = relationship(
        "InventarioReperto",
        secondary=reperti_materiali_association,
        back_populates="materiali"
    )
    
    def __repr__(self):
        return f"<MaterialeArcheologico(nome='{self.nome_comune}', categoria='{self.categoria}')>"

# ===== MODELLO CAMPIONI SCIENTIFICI =====
# CampioneScientifico è importato da archaeological_records per evitare duplicazione
from app.models.archaeological_records import CampioneScientifico  # noqa: F401


# ===== AGGIORNAMENTI PER ARCHAEOLOGICALSITE =====
"""
AGGIUNGERE QUESTE RELAZIONI in app/models/sites.py nella classe ArchaeologicalSite:

# Relazioni con moduli avanzati
unita_stratigrafiche = relationship("UnitaStratigrafica", back_populates="site", cascade="all, delete-orphan")
schede_tombe = relationship("SchedaTomba", back_populates="site", cascade="all, delete-orphan")
inventario_reperti = relationship("InventarioReperto", back_populates="site", cascade="all, delete-orphan")
campioni_scientifici = relationship("CampioneScientifico", back_populates="site", cascade="all, delete-orphan")
"""