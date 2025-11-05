# app/models/archaeological_records.py
"""
Modelli per record archeologici: Tombe, Reperti, Campioni Scientifici
Include gestione completa sepolture, inventario manufatti, campionature C14/analisi
"""

import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any
from decimal import Decimal

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, ForeignKey,
    Integer, Numeric, JSON, Index, UniqueConstraint, Float, UUID
)

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, SiteMixin, UserMixin, SoftDeleteMixin


# ===== ENUMS =====

class TipoTombaEnum(str, PyEnum):
    """Tipologie tombe"""
    INUMAZIONE = "inumazione"
    CREMAZIONE = "cremazione" 
    CENOTAFIO = "cenotafio"
    DEPOSIZIONE = "deposizione"
    RIDUZIONE = "riduzione"
    MISTA = "mista"


class OrientamentoEnum(str, PyEnum):
    """Orientamento scheletro"""
    N_S = "n-s"
    S_N = "s-n"
    E_O = "e-o" 
    O_E = "o-e"
    NE_SO = "ne-so"
    NO_SE = "no-se"
    SE_NO = "se-no"
    SO_NE = "so-ne"


class ConservazioneEnum(str, PyEnum):
    """Stato conservazione"""
    OTTIMO = "ottimo"
    BUONO = "buono"
    DISCRETO = "discreto"
    MEDIOCRE = "mediocre"
    CATTIVO = "cattivo"
    PESSIMO = "pessimo"


class TipoCampioneEnum(str, PyEnum):
    """Tipi campione scientifico"""
    CARBONIO = "carbonio"           # C14
    POLLINE = "polline"             # Palinologia
    CARBONE = "carbone"             # Antracologia
    OSSO = "osso"                   # Analisi isotopiche
    CERAMICA = "ceramica"           # TL, archeomagnetismo
    TERRA = "terra"                 # Sedimentologia
    MALTA = "malta"                 # Analisi malte
    LEGNO = "legno"                 # Dendrocronologia
    METALLO = "metallo"             # Analisi composizione
    VETRO = "vetro"                 # Analisi composizione
    ALTRO = "altro"


class MaterialeEnum(str, PyEnum):
    """Materiali reperti"""
    CERAMICA = "ceramica"
    BRONZO = "bronzo"
    FERRO = "ferro"
    ARGENTO = "argento"
    ORO = "oro"
    PIOMBO = "piombo"
    VETRO = "vetro"
    OSSO = "osso"
    CORNO = "corno"
    AMBRA = "ambra"
    PIETRA = "pietra"
    MARMO = "marmo"
    LEGNO = "legno"
    TESSUTO = "tessuto"
    CUOIO = "cuoio"
    PASTA_VITREA = "pasta_vitrea"
    ALTRO = "altro"


# ===== SCHEDE TOMBE =====

class SchedaTomba(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Schede tombe complete con antropologia e corredi
    Conforme a standard di documentazione sepolture
    """
    __tablename__ = "schede_tombe"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== IDENTIFICAZIONE =====
    numero_tomba = Column(String(20), nullable=False, index=True)  # T001, T002
    numero_individuo = Column(String(20), nullable=True)          # Se multiple sepolture
    denominazione = Column(String(100), nullable=True)            # Nome locale/storico
    
    # ===== LOCALIZZAZIONE =====
    settore = Column(String(50), nullable=True)     # A, B, C...
    quadrato = Column(String(50), nullable=True)    # A1, B2...
    us_riferimento = Column(String(20), nullable=True)  # US di taglio/riempimento
    
    # Coordinate relative (griglia scavo)
    coord_x = Column(Numeric(8, 3), nullable=True)
    coord_y = Column(Numeric(8, 3), nullable=True)
    quota_superiore = Column(Numeric(8, 3), nullable=True)  # m s.l.m.
    quota_inferiore = Column(Numeric(8, 3), nullable=True)
    
    # ===== TIPOLOGIA E STRUTTURA =====
    tipo_tomba = Column(String(20), default=TipoTombaEnum.INUMAZIONE, nullable=False)
    tipo_deposizione = Column(String(100), nullable=True)  # Primaria, secondaria
    struttura_tomba = Column(Text, nullable=True)          # Fossa, cassa, anfora...
    copertura = Column(String(200), nullable=True)         # Tegole, lastre, etc.
    segnacoli = Column(String(200), nullable=True)         # Stele, cippi, etc.
    
    # ===== DATI ANTROPOLOGICI =====
    sesso = Column(String(20), nullable=True)              # M, F, I (indeterminato)
    eta_stimata = Column(String(50), nullable=True)        # 20-30 anni, infantile...
    statura_stimata = Column(String(50), nullable=True)    # 165-170 cm
    
    # Orientamento e posizione
    orientamento_scheletro = Column(String(10), nullable=True)  # N-S, E-O...
    posizione_braccia = Column(String(100), nullable=True)      # Lungo il corpo, incrociate
    posizione_gambe = Column(String(100), nullable=True)        # Estese, flesse
    posizione_cranio = Column(String(100), nullable=True)       # Supino, destro, sinistro
    
    # ===== CONSERVAZIONE =====
    stato_conservazione = Column(String(20), default=ConservazioneEnum.DISCRETO, nullable=False)
    conservazione_dettagli = Column(Text, nullable=True)    # Descrizione stato ossa
    patologie = Column(Text, nullable=True)                 # Patologie rilevate
    traumi = Column(Text, nullable=True)                    # Traumi ante/post mortem
    
    # ===== CORREDO FUNERARIO =====
    presenza_corredo = Column(Boolean, default=False)
    corredo_posizione = Column(Text, nullable=True)         # Localizzazione oggetti
    corredo_descrizione = Column(Text, nullable=True)       # Descrizione generale
    
    # ===== ANALISI E CAMPIONATURE =====
    campionature_effettuate = Column(JSON, default=list)   # Tipi campioni prelevati
    analisi_antropologiche = Column(Text, nullable=True)    # Risultati analisi
    analisi_paleopatologiche = Column(Text, nullable=True)  # Risultati paleopatologia
    
    # ===== DATAZIONE =====
    datazione_relativa = Column(String(200), nullable=True)  # I-II sec. d.C.
    datazione_assoluta = Column(String(200), nullable=True)  # C14, dendro...
    periodo_culturale = Column(String(100), nullable=True)   # Romano, Medievale
    fase = Column(String(50), nullable=True)                 # Fase I, II...
    
    # ===== DOCUMENTAZIONE =====
    foto_generali = Column(JSON, default=list)              # ID foto generali
    foto_dettaglio = Column(JSON, default=list)             # ID foto dettaglio
    rilievi_grafici = Column(JSON, default=list)            # ID disegni/rilievi
    
    # ===== SCAVO E RESPONSABILITÀ =====
    data_scavo = Column(Date, nullable=True)
    responsabile_scavo = Column(String(200), nullable=True)
    metodo_scavo = Column(Text, nullable=True)              # Metodologia utilizzata
    note_scavo = Column(Text, nullable=True)                # Osservazioni scavo
    
    # ===== INTERPRETAZIONE =====
    interpretazione = Column(Text, nullable=True)           # Interpretazione generale
    osservazioni = Column(Text, nullable=True)              # Note aggiuntive
    anomalie = Column(Text, nullable=True)                  # Anomalie riscontrate
    
    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="schede_tombe")
    
    # Corredo (reperti associati)
    reperti_corredo = relationship(
        "InventarioReperto", 
        back_populates="tomba",
        foreign_keys="InventarioReperto.tomba_id"
    )
    
    # Campioni scientifici
    campioni = relationship("CampioneScientifico", back_populates="tomba")
    
    # Indici
    __table_args__ = (
        UniqueConstraint('site_id', 'numero_tomba', name='uq_site_tomba'),
        Index('idx_tomba_site_numero', 'site_id', 'numero_tomba'),
        Index('idx_tomba_tipo', 'tipo_tomba'),
        Index('idx_tomba_periodo', 'periodo_culturale'),
    )
    
    def __repr__(self):
        return f"<Tomba(numero={self.numero_tomba}, sito={self.site.name if self.site else 'N/A'})>"
    
    def get_corredo_count(self) -> int:
        """Conta oggetti corredo"""
        return len(self.reperti_corredo)
    
    def has_complete_anthropology(self) -> bool:
        """Controlla se ha dati antropologici completi"""
        return bool(self.sesso and self.eta_stimata and self.orientamento_scheletro)


# ===== INVENTARIO REPERTI =====

class InventarioReperto(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Inventario reperti con catalogazione completa
    Include provenienza stratigrafica e associazioni
    """
    __tablename__ = "inventario_reperti"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== IDENTIFICAZIONE =====
    numero_inventario = Column(String(50), nullable=False, index=True)  # INV001, REP2024-001
    sigla_sito = Column(String(20), nullable=True)                      # Sigla sito
    numero_catalogo = Column(String(50), nullable=True)                 # Numero catalogo museo
    
    # ===== PROVENIENZA =====
    # Provenienza stratigrafica
    unita_stratigrafica_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche.id"), nullable=True)
    unita_stratigrafica_completa_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche_complete.id"), nullable=True)
    tomba_id = Column(UUID(as_uuid=True), ForeignKey("schede_tombe.id"), nullable=True)
    
    # Localizzazione
    settore = Column(String(50), nullable=True)
    quadrato = Column(String(50), nullable=True)
    coord_x = Column(Numeric(8, 3), nullable=True)
    coord_y = Column(Numeric(8, 3), nullable=True)
    quota = Column(Numeric(8, 3), nullable=True)
    
    # ===== CLASSIFICAZIONE =====
    categoria = Column(String(100), nullable=False)         # Ceramica, Metalli, etc.
    sottocategoria = Column(String(100), nullable=True)     # Vascolare, Ornamenti, etc.
    classe = Column(String(100), nullable=True)             # Sigillata, Comune, etc.
    tipo = Column(String(100), nullable=True)               # Coppa, Anello, etc.
    forma = Column(String(100), nullable=True)              # Forma specifica
    
    # ===== CARATTERISTICHE FISICHE =====
    materiale = Column(String(50), nullable=False)          # Enum materiali
    colore = Column(String(100), nullable=True)             # Colore Munsell o descrittivo
    dimensioni = Column(String(200), nullable=True)         # L x W x H in cm
    peso = Column(Numeric(8, 2), nullable=True)             # grammi
    spessore = Column(Numeric(6, 2), nullable=True)         # mm
    diametro = Column(Numeric(8, 2), nullable=True)         # cm
    
    # ===== STATO DI CONSERVAZIONE =====
    stato_conservazione = Column(String(20), default=ConservazioneEnum.DISCRETO, nullable=False)
    completezza = Column(String(100), nullable=True)        # Integro, frammentario, %
    restauri = Column(Text, nullable=True)                  # Interventi di restauro
    
    # ===== DESCRIZIONE =====
    descrizione = Column(Text, nullable=False)              # Descrizione completa
    decorazioni = Column(Text, nullable=True)               # Decorazioni presenti
    iscrizioni = Column(Text, nullable=True)                # Testi, marchi, bolli
    confronti = Column(Text, nullable=True)                 # Confronti tipologici
    
    # ===== DATAZIONE =====
    datazione = Column(String(200), nullable=True)          # Cronologia
    periodo = Column(String(100), nullable=True)            # Periodo culturale
    fase = Column(String(50), nullable=True)                # Fase sito
    
    # ===== DOCUMENTAZIONE =====
    foto_ids = Column(JSON, default=list)                   # ID foto
    disegno_ids = Column(JSON, default=list)                # ID disegni
    bibliografia = Column(Text, nullable=True)              # Riferimenti bibliografici
    
    # ===== ANALISI =====
    analisi_effettuate = Column(JSON, default=list)         # Tipi analisi
    risultati_analisi = Column(Text, nullable=True)         # Risultati
    
    # ===== GESTIONE COLLEZIONE =====
    ubicazione_attuale = Column(String(200), nullable=True)  # Magazzino, museo, etc.
    numero_cassa = Column(String(50), nullable=True)        # Contenitore
    esposto = Column(Boolean, default=False)                # In esposizione
    prestiti = Column(JSON, default=list)                   # Storico prestiti
    
    # ===== VALUTAZIONE =====
    importanza_scientifica = Column(String(50), nullable=True)  # Alta, media, bassa
    valore_economico = Column(String(50), nullable=True)       # Stima valore
    note_conservazione = Column(Text, nullable=True)           # Note conservatore
    
    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="inventario_reperti")
    unita_stratigrafica = relationship("UnitaStratigrafica", back_populates="reperti")
    unita_stratigrafica_completa = relationship("UnitaStratigraficaCompleta", back_populates="reperti")
    tomba = relationship("SchedaTomba", back_populates="reperti_corredo", foreign_keys=[tomba_id])
    
    # Campioni associati
    campioni = relationship("CampioneScientifico", back_populates="reperto")
    
    # Materiali (many-to-many con MaterialeArcheologico)
    materiali = relationship(
        "MaterialeArcheologico",
        secondary="reperti_materiali",
        back_populates="reperti"
    )
    
    # Indici
    __table_args__ = (
        UniqueConstraint('site_id', 'numero_inventario', name='uq_site_inventario'),
        Index('idx_reperto_site_numero', 'site_id', 'numero_inventario'),
        Index('idx_reperto_categoria', 'categoria', 'materiale'),
        Index('idx_reperto_datazione', 'periodo', 'datazione'),
        Index('idx_reperto_provenienza', 'unita_stratigrafica_id', 'unita_stratigrafica_completa_id', 'tomba_id'),
    )
    
    def __repr__(self):
        return f"<Reperto(inventario={self.numero_inventario}, categoria={self.categoria})>"
    
    def get_provenienza_text(self) -> str:
        """Testo provenienza per display"""
        if self.tomba_id and self.tomba:
            return f"Tomba {self.tomba.numero_tomba}"
        elif self.unita_stratigrafica_completa_id and self.unita_stratigrafica_completa:
            return f"US {self.unita_stratigrafica_completa.numero_us}"
        elif self.unita_stratigrafica_id and self.unita_stratigrafica:
            return f"US {self.unita_stratigrafica.us_code}"
        elif self.settore:
            return f"Settore {self.settore}"
        return "Provenienza non specificata"


# ===== CAMPIONI SCIENTIFICI =====

class CampioneScientifico(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Campioni per analisi scientifiche
    Include C14, palinologia, antracologia, analisi isotopiche, etc.
    """
    __tablename__ = "campioni_scientifici"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)

    # ===== IDENTIFICAZIONE =====
    numero_campione = Column(String(50), nullable=False, index=True)  # CAMP001, C14-001
    tipo_campione = Column(String(30), nullable=False)               # Enum tipi
    descrizione_campione = Column(String(200), nullable=False)       # Carbone di quercia, osso lungo...
    
    # ===== PROVENIENZA =====
    unita_stratigrafica_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche.id"), nullable=True)
    unita_stratigrafica_completa_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche_complete.id"), nullable=True)
    unita_stratigrafica_muraria_id = Column(UUID(as_uuid=True), ForeignKey("unita_stratigrafiche_murarie.id"), nullable=True)
    tomba_id = Column(UUID(as_uuid=True), ForeignKey("schede_tombe.id"), nullable=True)
    reperto_id = Column(UUID(as_uuid=True), ForeignKey("inventario_reperti.id"), nullable=True)
    
    # Localizzazione specifica
    settore = Column(String(50), nullable=True)
    quadrato = Column(String(50), nullable=True)
    coord_x = Column(Numeric(8, 3), nullable=True)
    coord_y = Column(Numeric(8, 3), nullable=True)
    quota = Column(Numeric(8, 3), nullable=True)
    
    # ===== PRELIEVO =====
    data_prelievo = Column(Date, nullable=False)
    responsabile_prelievo = Column(String(200), nullable=False)
    metodo_prelievo = Column(String(200), nullable=True)      # Sterile, bulk, setacciatura...
    strumenti_utilizzati = Column(String(200), nullable=True) # Spatola, pinzette, etc.
    
    # ===== DESCRIZIONE CAMPIONE =====
    descrizione = Column(Text, nullable=False)                # Descrizione dettagliata
    peso_campione = Column(Numeric(8, 3), nullable=True)      # in grammi
    volume_campione = Column(Numeric(8, 3), nullable=True)    # in ml
    
    # ===== CONSERVAZIONE =====
    modalita_conservazione = Column(String(100), nullable=True)  # refrigerato, secco, etc.
    contenitore = Column(String(100), nullable=True)            # bustina, provetta, etc.
    posizione_deposito = Column(String(100), nullable=True)     # freezer n.1, scaffale A
    
    # ===== ANALISI =====
    laboratorio_analisi = Column(String(200), nullable=True)    # Nome laboratorio
    data_invio = Column(Date, nullable=True)                    # Data spedizione
    data_risultati = Column(Date, nullable=True)                # Data ricezione risultati
    codice_laboratorio = Column(String(100), nullable=True)     # Codice lab
    
    # ===== RISULTATI =====
    risultati_analisi = Column(JSON, nullable=True)             # JSON con risultati strutturati
    interpretazione_risultati = Column(Text, nullable=True)     # Interpretazione
    data_calibrata = Column(String(100), nullable=True)         # per C14
    sigma = Column(String(50), nullable=True)                   # per C14
    
    # ===== PUBBLICAZIONE =====
    pubblicato = Column(Boolean, default=False)
    riferimenti_pubblicazione = Column(Text, nullable=True)
    
    # ===== NOTE =====
    note_prelievo = Column(Text, nullable=True)
    note_analisi = Column(Text, nullable=True)
    
    # ===== SISTEMA =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="campioni_scientifici")
    unita_stratigrafica = relationship("UnitaStratigrafica", back_populates="campioni")
    unita_stratigrafica_completa = relationship("UnitaStratigraficaCompleta", back_populates="campioni")
    unita_stratigrafica_muraria = relationship("UnitaStratigraficaMuraria", back_populates="campioni")
    tomba = relationship("SchedaTomba", back_populates="campioni")
    reperto = relationship("InventarioReperto", back_populates="campioni")
    
    # Indici
    __table_args__ = (
        UniqueConstraint('site_id', 'numero_campione', name='uq_site_campione'),
        Index('idx_campione_site_numero', 'site_id', 'numero_campione'),
        Index('idx_campione_tipo', 'tipo_campione'),
        Index('idx_campione_data', 'data_prelievo'),
    )
    
    def __repr__(self):
        return f"<CampioneScientifico(numero={self.numero_campione}, tipo={self.tipo_campione})>"
    
    def get_provenienza_text(self) -> str:
        """Testo provenienza completo"""
        sources = []
        if self.unita_stratigrafica_completa:
            sources.append(f"US {self.unita_stratigrafica_completa.numero_us}")
        if self.unita_stratigrafica:
            sources.append(f"US {self.unita_stratigrafica.us_code}")
        if self.unita_stratigrafica_muraria:
            sources.append(f"USM {self.unita_stratigrafica_muraria.usm_code}")
        if self.tomba:
            sources.append(f"Tomba {self.tomba.numero_tomba}")
        if self.reperto:
            sources.append(f"Reperto {self.reperto.numero_inventario}")
        
        return " - ".join(sources) if sources else "Provenienza non specificata"
    
    def has_results(self) -> bool:
        """Controlla se ha risultati analisi"""
        return bool(self.risultati_analisi or self.interpretazione_risultati)