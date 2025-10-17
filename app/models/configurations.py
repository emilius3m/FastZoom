# app/models/configurations.py
"""
Modelli per configurazioni sistema, export, report finali
Include configurazioni export, relazioni finali, elenchi consegna
"""

import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, ForeignKey, 
    Integer, JSON, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, SiteMixin, UserMixin, SoftDeleteMixin


# ===== ENUMS =====

class FormatoExportEnum(str, PyEnum):
    """Formati export supportati"""
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    WORD = "word"
    ZIP = "zip"
    XML = "xml"


class TipoDestinatarioEnum(str, PyEnum):
    """Destinatari export"""
    SOPRINTENDENZA = "soprintendenza"
    UNIVERSITA = "universita"
    ENTE_RICERCA = "ente_ricerca"
    MUSEUM = "museo"
    PRIVATO = "privato"
    INTERNO = "interno"


class StatoRelazioneEnum(str, PyEnum):
    """Stati relazione finale"""
    BOZZA = "bozza"
    IN_REVISIONE = "in_revisione"
    APPROVATA = "approvata"
    CONSEGNATA = "consegnata"
    ARCHIVIATA = "archiviata"


class TipoElencoEnum(str, PyEnum):
    """Tipi elenco consegna"""
    TAVOLE = "tavole"
    FOTO = "foto"
    US = "us"
    TOMBE = "tombe"
    REPERTI = "reperti" 
    CAMPIONI = "campioni"
    CASSE = "casse"
    DOCUMENTI = "documenti"


# ===== CONFIGURAZIONI EXPORT =====

class ConfigurazioneExport(Base, SiteMixin, UserMixin):
    """
    Configurazioni per export dati verso enti esterni
    Template riutilizzabili per diverse tipologie di consegna
    """
    __tablename__ = "configurazioni_export"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== IDENTIFICAZIONE =====
    nome_configurazione = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    destinatario = Column(String(100), nullable=False)              # Enum destinatari
    ente_destinatario = Column(String(300), nullable=True)          # Nome ente specifico
    
    # ===== CONFIGURAZIONE CONTENUTI =====
    # Cosa includere nell'export
    includi_us = Column(Boolean, default=True)
    includi_usm = Column(Boolean, default=True)
    includi_tombe = Column(Boolean, default=True)
    includi_reperti = Column(Boolean, default=True)
    includi_campioni = Column(Boolean, default=True)
    includi_foto = Column(Boolean, default=True)
    includi_documenti = Column(Boolean, default=True)
    includi_tavole = Column(Boolean, default=True)
    
    # Filtri applicabili
    solo_validati = Column(Boolean, default=True)                   # Solo record validati
    data_inizio = Column(Date, nullable=True)                       # Filtro temporale
    data_fine = Column(Date, nullable=True)
    settori_inclusi = Column(JSON, default=list)                    # Lista settori
    
    # ===== FORMATO E STRUTTURA =====
    formato_principale = Column(String(20), default='pdf')          # Formato export
    formati_aggiuntivi = Column(JSON, default=list)                 # Altri formati
    
    # Template specifici
    template_copertina = Column(Text, nullable=True)                # Template copertina
    template_indice = Column(Boolean, default=True)                 # Include indice
    template_bibliografia = Column(Boolean, default=True)           # Include bibliografia
    
    # Configurazioni specifiche campi
    campi_us = Column(JSON, default=dict)                          # Campi US da includere
    campi_reperti = Column(JSON, default=dict)                     # Campi reperti da includere
    campi_personalizzati = Column(JSON, default=dict)              # Mapping campi custom
    
    # ===== METADATI CONSEGNA =====
    intestazione_ente = Column(Text, nullable=True)                # Intestazione documenti
    logo_path = Column(String(500), nullable=True)                 # Logo ente
    
    # Firme e responsabilità
    responsabile_scientifico = Column(String(200), nullable=True)
    direttore_scavo = Column(String(200), nullable=True)
    compilatore = Column(String(200), nullable=True)
    
    # ===== AUTOMAZIONE =====
    export_automatico = Column(Boolean, default=False)             # Export schedulato
    frequenza_export = Column(String(50), nullable=True)           # settimanale, mensile
    ultimo_export = Column(DateTime, nullable=True)
    prossimo_export = Column(DateTime, nullable=True)
    
    # ===== STATUS =====
    attiva = Column(Boolean, default=True)
    predefinita = Column(Boolean, default=False)                   # Config di default
    
    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="configurazioni_export")

    def __repr__(self):
        return f"<ConfigurazioneExport(nome={self.nome_configurazione}, destinatario={self.destinatario})>"
    
    def get_campi_inclusi(self) -> Dict[str, List[str]]:
        """Restituisce mapping campi inclusi per tipo"""
        return {
            'us': list(self.campi_us.keys()) if self.campi_us else [],
            'reperti': list(self.campi_reperti.keys()) if self.campi_reperti else [],
            'personalizzati': list(self.campi_personalizzati.keys()) if self.campi_personalizzati else []
        }


# ===== RELAZIONI FINALI SCAVO =====

class RelazioneFinaleScavo(Base, SiteMixin, UserMixin, SoftDeleteMixin):
    """
    Relazioni finali di scavo
    Documenti ufficiali di chiusura attività con tutti gli allegati
    """
    __tablename__ = "relazioni_finali_scavo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey('archaeological_sites.id'), nullable=False)

    # ===== IDENTIFICAZIONE =====
    titolo = Column(String(300), nullable=False)
    sottotitolo = Column(String(300), nullable=True)
    codice_relazione = Column(String(50), nullable=False, index=True)  # REL-2024-001
    
    # ===== METADATI AMMINISTRATIVI =====
    ente_responsabile = Column(String(300), nullable=False)
    soprintendenza = Column(String(300), nullable=True)
    autorizzazione_scavo = Column(String(100), nullable=True)
    
    # Date amministrative
    data_inizio_scavo = Column(Date, nullable=False)
    data_fine_scavo = Column(Date, nullable=False)
    data_consegna = Column(Date, nullable=True)
    
    # ===== RESPONSABILITÀ =====
    direttore_scientifico = Column(String(200), nullable=False)
    direttore_scavo = Column(String(200), nullable=True)
    assistenti = Column(JSON, default=list)                         # Lista assistenti
    specialisti = Column(JSON, default=list)                        # Antropologo, geologo, etc.
    
    # ===== CONTENUTO RELAZIONE =====
    # Sezioni principali
    premessa = Column(Text, nullable=True)
    inquadramento_storico = Column(Text, nullable=True)
    inquadramento_geologico = Column(Text, nullable=True)
    metodologia = Column(Text, nullable=True)
    risultati = Column(Text, nullable=False)                        # Sezione obbligatoria
    interpretazione = Column(Text, nullable=True)
    conclusioni = Column(Text, nullable=False)                      # Sezione obbligatoria
    
    # Appendici
    cronologia = Column(Text, nullable=True)
    bibliografia = Column(Text, nullable=True)
    ringraziamenti = Column(Text, nullable=True)
    
    # ===== ALLEGATI =====
    # Riferimenti agli allegati (ID di altri record)
    elenco_us = Column(JSON, default=list)                         # ID US incluse
    elenco_tombe = Column(JSON, default=list)                      # ID Tombe incluse
    elenco_reperti = Column(JSON, default=list)                    # ID Reperti inclusi
    elenco_campioni = Column(JSON, default=list)                   # ID Campioni inclusi
    elenco_foto = Column(JSON, default=list)                       # ID Foto incluse
    elenco_tavole = Column(JSON, default=list)                     # ID Tavole incluse
    
    # ===== EXPORT E FORMATO =====
    configurazione_export_id = Column(UUID(as_uuid=True), ForeignKey('configurazioni_export.id'), nullable=True)
    formato_finale = Column(String(20), default='pdf')
    include_allegati_digitali = Column(Boolean, default=True)       # DVD, USB
    
    # Path file generati
    file_relazione_pdf = Column(String(500), nullable=True)
    file_allegati_zip = Column(String(500), nullable=True)
    file_completo_path = Column(String(500), nullable=True)
    
    # ===== STATUS E WORKFLOW =====
    stato = Column(String(20), default='bozza', nullable=False)     # Enum stati
    
    # Approvazioni
    approvata_da = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    data_approvazione = Column(DateTime, nullable=True)
    note_approvazione = Column(Text, nullable=True)
    
    # Consegna
    consegnata_a = Column(String(300), nullable=True)               # Ente consegna
    data_consegna_effettiva = Column(DateTime, nullable=True)
    ricevuta_consegna = Column(String(500), nullable=True)          # Path ricevuta
    
    # ===== VERSIONING =====
    versione = Column(String(10), default="1.0")
    note_versione = Column(Text, nullable=True)
    versione_precedente_id = Column(UUID(as_uuid=True), ForeignKey('relazioni_finali_scavo.id'), nullable=True)
    
    # ===== SISTEMA =====
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="relazioni_finali")
    configurazione_export = relationship("ConfigurazioneExport")
    approvatore = relationship("User", foreign_keys=[approvata_da])
    versione_precedente = relationship("RelazioneFinaleScavo", remote_side=[id])

    # ===== INDICI =====
    __table_args__ = (
        UniqueConstraint('site_id', 'codice_relazione', name='uq_site_relazione_codice'),
        Index('idx_relazione_site_codice', 'site_id', 'codice_relazione'),
        Index('idx_relazione_stato', 'stato'),
        Index('idx_relazione_data_consegna', 'data_consegna'),
    )

    def __repr__(self):
        return f"<RelazioneFinale(codice={self.codice_relazione}, stato={self.stato})>"
    
    @property
    def durata_scavo_giorni(self) -> int:
        """Durata scavo in giorni"""
        if self.data_inizio_scavo and self.data_fine_scavo:
            return (self.data_fine_scavo - self.data_inizio_scavo).days
        return 0
    
    def get_allegati_count(self) -> Dict[str, int]:
        """Conteggi allegati per tipo"""
        return {
            'us': len(self.elenco_us) if self.elenco_us else 0,
            'tombe': len(self.elenco_tombe) if self.elenco_tombe else 0,
            'reperti': len(self.elenco_reperti) if self.elenco_reperti else 0,
            'campioni': len(self.elenco_campioni) if self.elenco_campioni else 0,
            'foto': len(self.elenco_foto) if self.elenco_foto else 0,
            'tavole': len(self.elenco_tavole) if self.elenco_tavole else 0
        }
    
    def is_completata(self) -> bool:
        """Controlla se relazione è completata"""
        return bool(self.risultati and self.conclusioni and self.stato != 'bozza')


# ===== ELENCHI CONSEGNA =====
# ElencoConsegna è importato da documentazione_grafica per evitare duplicazione
from app.models.documentazione_grafica import ElencoConsegna  # noqa: F401


# ===== TEMPLATE ELENCHI =====

TEMPLATE_ELENCHI = {
    'tavole': {
        'nome': 'Elenco Tavole Grafiche',
        'campi': ['numero_tavola', 'tipo', 'titolo', 'scala', 'formato', 'autore', 'data'],
        'descrizione': 'Elenco completo delle tavole grafiche prodotte'
    },
    'foto': {
        'nome': 'Elenco Fotografico', 
        'campi': ['numero_foto', 'descrizione', 'soggetto', 'data_scatto', 'fotografo', 'formato'],
        'descrizione': 'Catalogo fotografico completo'
    },
    'us': {
        'nome': 'Elenco Unità Stratigrafiche',
        'campi': ['us_code', 'definizione', 'datazione', 'periodo', 'stato_conservazione', 'interpretazione'],
        'descrizione': 'Elenco completo delle US documentate'
    },
    'tombe': {
        'nome': 'Elenco Sepolture',
        'campi': ['numero_tomba', 'tipo_tomba', 'orientamento', 'sesso', 'eta', 'corredo', 'datazione'],
        'descrizione': 'Catalogo delle sepolture indagate'
    },
    'reperti': {
        'nome': 'Inventario Reperti',
        'campi': ['numero_inventario', 'categoria', 'materiale', 'descrizione', 'provenienza', 'datazione', 'stato_conservazione'],
        'descrizione': 'Inventario completo dei materiali archeologici'
    },
    'campioni': {
        'nome': 'Elenco Campioni Scientifici',
        'campi': ['numero_campione', 'tipo_campione', 'provenienza', 'data_prelievo', 'laboratorio', 'risultati'],
        'descrizione': 'Registro dei campioni per analisi scientifiche'
    }
}


# ===== HELPER FUNCTIONS =====

def genera_elenco_automatico(site_id: uuid.UUID, tipo_elenco: str, user_id: uuid.UUID) -> Optional[ElencoConsegna]:
    """
    Genera automaticamente elenco per tipo specificato
    Questa funzione sarebbe implementata nel service layer
    """
    pass

def esporta_elenco_pdf(elenco: ElencoConsegna, template_path: str) -> str:
    """
    Esporta elenco in PDF utilizzando template
    Restituisce path del file generato
    """
    pass

def valida_configurazione_export(config: ConfigurazioneExport) -> Dict[str, Any]:
    """
    Valida configurazione export e restituisce eventuali errori
    """
    errori = []
    
    if not config.nome_configurazione:
        errori.append("Nome configurazione obbligatorio")
    
    if not config.destinatario:
        errori.append("Destinatario obbligatorio")
    
    # Valida che almeno un tipo contenuto sia selezionato
    contenuti_selezionati = [
        config.includi_us, config.includi_usm, config.includi_tombe,
        config.includi_reperti, config.includi_campioni, config.includi_foto,
        config.includi_documenti, config.includi_tavole
    ]
    
    if not any(contenuti_selezionati):
        errori.append("Selezionare almeno un tipo di contenuto da includere")
    
    return {
        'valida': len(errori) == 0,
        'errori': errori
    }