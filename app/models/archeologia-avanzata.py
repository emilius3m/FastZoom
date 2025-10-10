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

from sqlalchemy import Column, String, Text, Boolean, DateTime, Date, Integer, ForeignKey, Table, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import func

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
    Column('us_superiore_id', UUID(as_uuid=True), ForeignKey('unita_stratigrafiche.id', ondelete='CASCADE'), nullable=False),
    Column('us_inferiore_id', UUID(as_uuid=True), ForeignKey('unita_stratigrafiche.id', ondelete='CASCADE'), nullable=False),
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
class UnitaStratigrafica(Base):
    """
    Modello per Unità Stratigrafiche complete con standard ICCD
    Include tutti i campi necessari per schede US definitive
    """
    __tablename__ = "unita_stratigrafiche"
    
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
    site = relationship("ArchaeologicalSite", back_populates="unita_stratigrafiche")
    
    # Relazioni stratigrafiche (Matrix Harris)
    us_superiori = relationship(
        "UnitaStratigrafica",
        secondary=matrix_harris_relations,
        primaryjoin=id==matrix_harris_relations.c.us_inferiore_id,
        secondaryjoin=id==matrix_harris_relations.c.us_superiore_id,
        back_populates="us_inferiori"
    )
    
    us_inferiori = relationship(
        "UnitaStratigrafica",
        secondary=matrix_harris_relations,
        primaryjoin=id==matrix_harris_relations.c.us_superiore_id,
        secondaryjoin=id==matrix_harris_relations.c.us_inferiore_id,
        back_populates="us_superiori"
    )
    
    # Relazione con reperti trovati in questa US
    reperti = relationship("InventarioReperto", back_populates="unita_stratigrafica")
    
    # Relazione con campioni prelevati
    campioni = relationship("CampioneScientifico", back_populates="unita_stratigrafica")
    
    def __repr__(self):
        return f"<UnitaStratigrafica(numero='{self.numero_us}', tipo='{self.tipo_us}')>"
    
    @property
    def codice_completo(self) -> str:
        """Restituisce codice completo US"""
        return f"{self.site.code}-{self.numero_us}" if self.site else self.numero_us


# ===== MODELLO TOMBE/SEPOLTURE =====
class SchedaTomba(Base):
    """
    Modello per schede di tomba/sepoltura complete
    Conforme agli standard ICCD per documentazione sepolture
    """
    __tablename__ = "schede_tombe"
    
    # Identificativi
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    numero_tomba = Column(String(20), nullable=False, index=True)  # es: "T001"
    us_taglio_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche.id"), nullable=True)
    us_riempimento_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche.id"), nullable=True)
    
    # Tipologia sepoltura
    tipo_tomba = Column(String(30), nullable=False)  # Enum TipoTomba
    rito_sepolcrale = Column(String(30), nullable=False)  # Enum RitoSepolcrale
    orientamento_tomba = Column(String(20), nullable=True)  # N-S, E-W, etc.
    orientamento_inumato = Column(String(50), nullable=True)  # "testa a N, piedi a S"
    
    # Dimensioni tomba
    lunghezza_tomba = Column(Numeric(6, 2), nullable=True)
    larghezza_tomba = Column(Numeric(6, 2), nullable=True)
    profondita_tomba = Column(Numeric(6, 2), nullable=True)
    
    # Struttura tomba
    pareti_descrizione = Column(Text, nullable=True)
    fondo_descrizione = Column(Text, nullable=True)
    copertura_descrizione = Column(Text, nullable=True)
    materiali_costruzione = Column(Text, nullable=True)
    
    # Dati antropologici
    numero_individui = Column(Integer, default=1, nullable=False)
    sesso = Column(String(20), nullable=True)  # M, F, I (indeterminabile)
    eta_morte = Column(String(50), nullable=True)  # "adulto", "20-30 anni", etc.
    statura_stimata = Column(Numeric(5, 2), nullable=True)  # in cm
    
    # Posizione scheletro
    posizione_corpo = Column(String(100), nullable=True)  # supino, prono, etc.
    posizione_arti_superiori = Column(String(100), nullable=True)
    posizione_arti_inferiori = Column(String(100), nullable=True)
    posizione_cranio = Column(String(100), nullable=True)
    
    # Stato conservazione
    conservazione_scheletro = Column(String(20), nullable=True)  # Enum StatoConservazione
    ossa_presenti = Column(Text, nullable=True)  # lista dettagliata
    ossa_mancanti = Column(Text, nullable=True)
    patologie_osservate = Column(Text, nullable=True)
    
    # Corredo funerario
    presenza_corredo = Column(Boolean, default=False)
    descrizione_corredo = Column(Text, nullable=True)
    
    # Cronologia
    cronologia = Column(String(200), nullable=True)
    periodo = Column(String(100), nullable=True)
    fase = Column(String(50), nullable=True)
    datazione_assoluta = Column(String(100), nullable=True)  # da C14 o altro
    
    # Scavo
    data_scavo = Column(Date, nullable=True)
    responsabile_scavo = Column(String(200), nullable=True)
    metodo_scavo = Column(String(100), nullable=True)
    
    # Documentazione
    foto_numeri = Column(Text, nullable=True)
    disegni_numeri = Column(Text, nullable=True)
    rilievo_antropologico = Column(Boolean, default=False)
    prelievo_campioni = Column(Boolean, default=False)
    
    # Interpretazione
    interpretazione = Column(Text, nullable=True)
    note_tafonomiche = Column(Text, nullable=True)
    note_generali = Column(Text, nullable=True)
    
    # Metadati
    compilatore = Column(String(200), nullable=True)
    data_compilazione = Column(Date, nullable=False, default=date.today)
    antropologo = Column(String(200), nullable=True)  # responsabile analisi antropologica
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    version = Column(Integer, default=1, nullable=False)
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="schede_tombe")
    us_taglio = relationship("UnitaStratigrafica", foreign_keys=[us_taglio_id])
    us_riempimento = relationship("UnitaStratigrafica", foreign_keys=[us_riempimento_id])
    
    # Corredo funerario
    reperti_corredo = relationship("InventarioReperto", back_populates="tomba")
    
    def __repr__(self):
        return f"<SchedaTomba(numero='{self.numero_tomba}', tipo='{self.tipo_tomba}')>"


# ===== MODELLO INVENTARIO REPERTI =====
class InventarioReperto(Base):
    """
    Modello per inventario completo dei reperti
    Include numerazione, descrizione, stato, posizione
    """
    __tablename__ = "inventario_reperti"
    
    # Identificativi
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Numerazione reperto
    numero_inventario = Column(String(50), nullable=False, unique=True, index=True)  # es: "PMP-001-R001"
    numero_cassa = Column(String(20), nullable=True, index=True)  # es: "C001"
    numero_sacco = Column(String(20), nullable=True)  # es: "S001"
    
    # Provenienza
    unita_stratigrafica_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche.id"), nullable=True)
    tomba_id = Column(UUID(as_uuid=True), ForeignKey("schede_tombe.id"), nullable=True)
    
    # Posizione nel deposito
    settore_deposito = Column(String(50), nullable=True)
    scaffale = Column(String(20), nullable=True)
    posizione = Column(String(50), nullable=True)
    
    # Classificazione
    categoria_materiale = Column(String(30), nullable=False)  # Enum TipoMateriale
    classe = Column(String(100), nullable=True)  # ceramica fine, grossolana, etc.
    tipo = Column(String(100), nullable=True)  # coppa, anfora, etc.
    forma = Column(String(100), nullable=True)
    
    # Descrizione
    descrizione_breve = Column(String(500), nullable=False)
    descrizione_dettagliata = Column(Text, nullable=True)
    
    # Caratteristiche fisiche
    altezza = Column(Numeric(8, 2), nullable=True)  # in cm
    larghezza = Column(Numeric(8, 2), nullable=True)
    lunghezza = Column(Numeric(8, 2), nullable=True)
    diametro = Column(Numeric(8, 2), nullable=True)
    spessore = Column(Numeric(6, 2), nullable=True)
    peso = Column(Numeric(8, 2), nullable=True)  # in grammi
    
    # Quantità
    numero_frammenti = Column(Integer, default=1, nullable=False)
    percentuale_conservato = Column(Integer, nullable=True)  # 0-100%
    
    # Stato conservazione
    stato_conservazione = Column(String(20), nullable=False)  # Enum StatoConservazione
    agenti_degrado = Column(Text, nullable=True)
    interventi_restauro = Column(Text, nullable=True)
    
    # Cronologia
    cronologia = Column(String(200), nullable=True)
    periodo = Column(String(100), nullable=True)
    datazione_proposta = Column(String(100), nullable=True)
    
    # Significatività
    rilevanza_scientifica = Column(String(20), nullable=True)  # alta, media, bassa
    note_interpretative = Column(Text, nullable=True)
    
    # Documentazione
    foto_numeri = Column(Text, nullable=True)
    disegni_numeri = Column(Text, nullable=True)
    bibliografia = Column(Text, nullable=True)
    
    # Analisi
    analisi_effettuate = Column(Text, nullable=True)
    campionature = Column(Text, nullable=True)
    
    # Pubblicazione
    pubblicato = Column(Boolean, default=False)
    riferimenti_bibliografici = Column(Text, nullable=True)
    
    # Metadati
    catalogatore = Column(String(200), nullable=True)
    data_catalogazione = Column(Date, nullable=False, default=date.today)
    revisore = Column(String(200), nullable=True)
    data_revisione = Column(Date, nullable=True)
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    version = Column(Integer, default=1, nullable=False)
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="inventario_reperti")
    unita_stratigrafica = relationship("UnitaStratigrafica", back_populates="reperti")
    tomba = relationship("SchedaTomba", back_populates="reperti_corredo")
    
    # Materiali costituenti (many-to-many)
    materiali = relationship(
        "MaterialeArcheologico",
        secondary=reperti_materiali_association,
        back_populates="reperti"
    )
    
    def __repr__(self):
        return f"<InventarioReperto(numero='{self.numero_inventario}', categoria='{self.categoria_materiale}')>"


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
class CampioneScientifico(Base):
    """
    Modello per campioni scientifici (C14, archeobotanici, etc.)
    Include tracking delle analisi e risultati
    """
    __tablename__ = "campioni_scientifici"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Identificativi
    numero_campione = Column(String(50), nullable=False, unique=True, index=True)  # es: "PMP-001-C14-001"
    tipo_campione = Column(String(30), nullable=False)  # Enum TipoCampione
    
    # Provenienza
    unita_stratigrafica_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche.id"), nullable=True)
    tomba_id = Column(UUID(as_uuid=True), ForeignKey("schede_tombe.id"), nullable=True)
    
    # Prelievo
    data_prelievo = Column(Date, nullable=False)
    responsabile_prelievo = Column(String(200), nullable=False)
    metodo_prelievo = Column(String(200), nullable=True)
    strumenti_utilizzati = Column(String(200), nullable=True)
    
    # Descrizione campione
    descrizione = Column(Text, nullable=False)
    peso_campione = Column(Numeric(8, 3), nullable=True)  # in grammi
    volume_campione = Column(Numeric(8, 3), nullable=True)  # in ml
    
    # Conservazione
    modalita_conservazione = Column(String(100), nullable=True)  # refrigerato, secco, etc.
    contenitore = Column(String(100), nullable=True)
    posizione_deposito = Column(String(100), nullable=True)
    
    # Analisi
    laboratorio_analisi = Column(String(200), nullable=True)
    data_invio = Column(Date, nullable=True)
    data_risultati = Column(Date, nullable=True)
    codice_laboratorio = Column(String(100), nullable=True)
    
    # Risultati
    risultati_analisi = Column(JSON, nullable=True)  # JSON con risultati strutturati
    interpretazione_risultati = Column(Text, nullable=True)
    data_calibrata = Column(String(100), nullable=True)  # per C14
    sigma = Column(String(50), nullable=True)  # per C14
    
    # Pubblicazione
    pubblicato = Column(Boolean, default=False)
    riferimenti_pubblicazione = Column(Text, nullable=True)
    
    # Note
    note_prelievo = Column(Text, nullable=True)
    note_analisi = Column(Text, nullable=True)
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="campioni_scientifici")
    unita_stratigrafica = relationship("UnitaStratigrafica", back_populates="campioni")
    tomba = relationship("SchedaTomba")
    
    def __repr__(self):
        return f"<CampioneScientifico(numero='{self.numero_campione}', tipo='{self.tipo_campione}')>"


# ===== AGGIORNAMENTI PER ARCHAEOLOGICALSITE =====
"""
AGGIUNGERE QUESTE RELAZIONI in app/models/sites.py nella classe ArchaeologicalSite:

# Relazioni con moduli avanzati
unita_stratigrafiche = relationship("UnitaStratigrafica", back_populates="site", cascade="all, delete-orphan")
schede_tombe = relationship("SchedaTomba", back_populates="site", cascade="all, delete-orphan")
inventario_reperti = relationship("InventarioReperto", back_populates="site", cascade="all, delete-orphan")
campioni_scientifici = relationship("CampioneScientifico", back_populates="site", cascade="all, delete-orphan")
"""