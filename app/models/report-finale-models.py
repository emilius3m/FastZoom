# app/models/report_finale.py
"""
Modello per generazione automatica relazione finale di scavo
Include tutti i componenti richiesti dalle Soprintendenze italiane
Conforme a DM 154/2017 e linee guida regionali
"""

from datetime import date, datetime
from enum import Enum as PyEnum
from uuid import uuid4
from typing import List, Optional, Dict, Any

from sqlalchemy import Column, String, Text, Boolean, DateTime, Date, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import func

from app.database.base import Base


# ===== ENUM PER REPORT =====
class TipoReport(str, PyEnum):
    """Tipologie di report archeologici"""
    RELAZIONE_PRELIMINARE = "relazione_preliminare"
    RELAZIONE_FINALE = "relazione_finale" 
    RELAZIONE_SCIENTIFICA = "relazione_scientifica"
    SCHEDA_INTERVENTO = "scheda_intervento"
    NOTA_CONSEGNA = "nota_consegna"


class StatoReport(str, PyEnum):
    """Stati del report"""
    BOZZA = "bozza"
    IN_REVISIONE = "in_revisione"
    COMPLETATO = "completato"
    CONSEGNATO = "consegnato"
    APPROVATO = "approvato"


class FormatoOutput(str, PyEnum):
    """Formati di output del report"""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    LATEX = "latex"


# ===== MODELLO RELAZIONE FINALE =====
class RelazioneFinaleScavo(Base):
    """
    Modello per la relazione finale di scavo archeologico
    Include tutti i componenti standard richiesti dalle Soprintendenze
    """
    __tablename__ = "relazioni_finali"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Identificativi
    numero_relazione = Column(String(50), nullable=False, unique=True, index=True)
    titolo = Column(String(500), nullable=False)
    sottotitolo = Column(String(500), nullable=True)
    
    # Tipologia e stato
    tipo_report = Column(String(30), nullable=False, default="relazione_finale")  # Enum TipoReport
    stato = Column(String(20), nullable=False, default="bozza")  # Enum StatoReport
    
    # ===== SEZIONI STANDARD RELAZIONE =====
    
    # 1. DATI AMMINISTRATIVI
    ente_committente = Column(String(200), nullable=True)
    ditta_esecutrice = Column(String(200), nullable=True)
    direttore_scientifico = Column(String(200), nullable=False)
    responsabile_procedimento = Column(String(200), nullable=True)
    
    # Autorizzazioni
    decreto_autorizzazione = Column(String(200), nullable=True)
    data_decreto = Column(Date, nullable=True)
    soprintendenza_competente = Column(String(200), nullable=True)
    funzionario_competente = Column(String(200), nullable=True)
    
    # Date intervento
    data_inizio_scavo = Column(Date, nullable=False)
    data_fine_scavo = Column(Date, nullable=False)
    durata_giorni = Column(Integer, nullable=True)
    
    # 2. INQUADRAMENTO GEOGRAFICO E TOPOGRAFICO
    localizzazione = Column(Text, nullable=False)
    coordinate_geografiche = Column(String(100), nullable=True)
    cartografia_riferimento = Column(String(200), nullable=True)
    vincoli_presenti = Column(Text, nullable=True)
    
    # 3. INQUADRAMENTO GEOLOGICO E GEOMORFOLOGICO
    geologia_area = Column(Text, nullable=True)
    geomorfologia = Column(Text, nullable=True)
    idrografia = Column(Text, nullable=True)
    
    # 4. INQUADRAMENTO STORICO-ARCHEOLOGICO
    storia_ricerche = Column(Text, nullable=True)
    bibliografia_pregressa = Column(Text, nullable=True)
    notizie_storiche = Column(Text, nullable=True)
    
    # 5. METODOLOGIA DI SCAVO
    metodologia_adottata = Column(Text, nullable=False)
    criteri_documentazione = Column(Text, nullable=True)
    campionature_effettuate = Column(Text, nullable=True)
    
    # 6. SEQUENZA STRATIGRAFICA
    descrizione_stratigrafia = Column(Text, nullable=False)
    interpretazione_fasi = Column(Text, nullable=True)
    cronologia_relativa = Column(Text, nullable=True)
    
    # 7. STRUTTURE E CONTESTI
    descrizione_strutture = Column(Text, nullable=True)
    descrizione_sepolture = Column(Text, nullable=True)
    descrizione_depositi = Column(Text, nullable=True)
    
    # 8. MATERIALI ARCHEOLOGICI
    sintesi_materiali = Column(Text, nullable=True)
    analisi_ceramica = Column(Text, nullable=True)
    analisi_metalli = Column(Text, nullable=True)
    altri_materiali = Column(Text, nullable=True)
    
    # 9. ANALISI SCIENTIFICHE
    campioni_analizzati = Column(Text, nullable=True)
    risultati_c14 = Column(Text, nullable=True)
    risultati_archeobotanica = Column(Text, nullable=True)
    risultati_archeozoologia = Column(Text, nullable=True)
    altre_analisi = Column(Text, nullable=True)
    
    # 10. INTERPRETAZIONE E CRONOLOGIA
    interpretazione_generale = Column(Text, nullable=False)
    cronologia_assoluta = Column(Text, nullable=True)
    periodi_frequentazione = Column(Text, nullable=True)
    
    # 11. CONSIDERAZIONI CONCLUSIVE
    conclusioni = Column(Text, nullable=False)
    prospettive_ricerca = Column(Text, nullable=True)
    raccomandazioni_conservazione = Column(Text, nullable=True)
    
    # 12. BIBLIOGRAFIA
    bibliografia = Column(Text, nullable=True)
    
    # ===== ELENCHI AUTOMATICI =====
    # Questi vengono generati automaticamente dai dati del database
    elenco_us_auto = Column(Boolean, default=True)
    elenco_tombe_auto = Column(Boolean, default=True)
    elenco_reperti_auto = Column(Boolean, default=True)
    elenco_campioni_auto = Column(Boolean, default=True)
    elenco_foto_auto = Column(Boolean, default=True)
    elenco_tavole_auto = Column(Boolean, default=True)
    
    # ===== CONFIGURAZIONE OUTPUT =====
    formato_output = Column(String(10), default="pdf", nullable=False)  # Enum FormatoOutput
    template_utilizzato = Column(String(100), nullable=True)
    stile_bibliografico = Column(String(50), default="chicago", nullable=True)
    
    # Include allegati
    include_matrix_harris = Column(Boolean, default=True)
    include_tavole = Column(Boolean, default=True)
    include_foto_significative = Column(Boolean, default=True)
    include_schede_us = Column(Boolean, default=False)
    include_schede_tombe = Column(Boolean, default=False)
    
    # ===== GENERAZIONE E EXPORT =====
    file_generato_path = Column(String(500), nullable=True)
    data_generazione = Column(DateTime, nullable=True)
    dimensione_file = Column(Integer, nullable=True)  # in bytes
    
    # Statistiche automatiche
    numero_us_totali = Column(Integer, nullable=True)
    numero_tombe_totali = Column(Integer, nullable=True)
    numero_reperti_totali = Column(Integer, nullable=True)
    numero_foto_totali = Column(Integer, nullable=True)
    numero_tavole_totali = Column(Integer, nullable=True)
    
    # ===== REVISIONI E APPROVAZIONI =====
    storia_revisioni = Column(JSON, nullable=True)  # Lista di revisioni con date e autori
    
    # Approvazione scientifica
    approvato_da = Column(String(200), nullable=True)
    data_approvazione = Column(Date, nullable=True)
    note_approvazione = Column(Text, nullable=True)
    
    # Consegna
    consegnato_a = Column(String(200), nullable=True)  # Soprintendenza
    data_consegna = Column(Date, nullable=True)
    modalita_consegna = Column(String(100), nullable=True)  # PEC, raccomandata, etc.
    ricevuta_consegna = Column(String(500), nullable=True)  # path ricevuta
    
    # ===== METADATI AUTORI =====
    autore_principale = Column(String(200), nullable=False)
    coautori = Column(Text, nullable=True)  # lista separata da virgole
    collaboratori = Column(Text, nullable=True)
    
    # Compilazione
    compilatore = Column(String(200), nullable=False)
    data_compilazione = Column(Date, nullable=False, default=date.today)
    
    # Revisione
    revisore = Column(String(200), nullable=True)
    data_revisione = Column(Date, nullable=True)
    
    # ===== SISTEMA =====
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="relazioni_finali")
    
    def __repr__(self):
        return f"<RelazioneFinaleSca vo(numero='{self.numero_relazione}', stato='{self.stato}')>"
    
    # ===== METODI UTILITY =====
    @property
    def is_completabile(self) -> bool:
        """Verifica se la relazione ha tutti i dati necessari per essere completata"""
        required_fields = [
            self.titolo,
            self.direttore_scientifico,
            self.data_inizio_scavo,
            self.data_fine_scavo,
            self.localizzazione,
            self.metodologia_adottata,
            self.descrizione_stratigrafia,
            self.interpretazione_generale,
            self.conclusioni
        ]
        return all(field for field in required_fields)
    
    def get_durata_scavo(self) -> int:
        """Calcola automaticamente la durata in giorni"""
        if self.data_inizio_scavo and self.data_fine_scavo:
            return (self.data_fine_scavo - self.data_inizio_scavo).days + 1
        return 0


# ===== MODELLO TEMPLATE RELAZIONE =====
class TemplateRelazione(Base):
    """
    Modello per template personalizzabili delle relazioni
    Permette di creare template specifici per diverse Soprintendenze
    """
    __tablename__ = "template_relazioni"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Identificativi
    nome_template = Column(String(200), nullable=False, unique=True)
    descrizione = Column(Text, nullable=True)
    
    # Destinazione
    soprintendenza_destinataria = Column(String(200), nullable=True)
    regione = Column(String(100), nullable=True)
    tipo_scavo_applicabile = Column(String(100), nullable=True)  # urbano, rurale, emergenza, etc.
    
    # Struttura template
    sezioni_obbligatorie = Column(JSON, nullable=False)  # Lista sezioni da includere
    sezioni_opzionali = Column(JSON, nullable=True)
    ordine_sezioni = Column(JSON, nullable=False)  # Ordine di presentazione
    
    # Configurazione
    formato_default = Column(String(10), default="pdf")
    stile_bibliografico = Column(String(50), default="chicago")
    include_frontespizio = Column(Boolean, default=True)
    include_indice = Column(Boolean, default=True)
    include_elenchi = Column(Boolean, default=True)
    
    # Template LaTeX/HTML
    template_content = Column(Text, nullable=True)  # Template Jinja2
    css_style = Column(Text, nullable=True)  # Stili CSS personalizzati
    
    # Metadati
    creatore = Column(String(200), nullable=False)
    data_creazione = Column(Date, nullable=False, default=date.today)
    versione = Column(String(10), default="1.0")
    
    # Utilizzo
    utilizzato_count = Column(Integer, default=0)
    ultima_utilizzato = Column(DateTime, nullable=True)
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<TemplateRelazione(nome='{self.nome_template}', versione='{self.versione}')>"


# ===== MODELLO CONFIGURAZIONE ESPORT =====
class ConfigurazioneExport(Base):
    """
    Modello per configurazioni di export personalizzate
    Permette di salvare impostazioni per diversi tipi di consegna
    """
    __tablename__ = "configurazioni_export"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # Identificativi
    nome_configurazione = Column(String(200), nullable=False)
    descrizione = Column(Text, nullable=True)
    
    # Destinazione
    destinatario = Column(String(200), nullable=False)  # Soprintendenza, ente, etc.
    tipo_consegna = Column(String(50), nullable=False)  # finale, preliminare, scientifica
    
    # Configurazione contenuti
    include_relazione = Column(Boolean, default=True)
    include_giornale_cantiere = Column(Boolean, default=True)
    include_schede_us = Column(Boolean, default=True)
    include_schede_tombe = Column(Boolean, default=True)
    include_inventario_reperti = Column(Boolean, default=True)
    include_matrix_harris = Column(Boolean, default=True)
    include_tavole_tutte = Column(Boolean, default=True)
    include_foto_tutte = Column(Boolean, default=False)
    include_foto_significative = Column(Boolean, default=True)
    include_elenchi = Column(Boolean, default=True)
    
    # Formati di output
    formato_relazione = Column(String(10), default="pdf")
    formato_schede = Column(String(10), default="pdf")
    formato_elenchi = Column(String(10), default="excel")
    formato_matrix = Column(String(10), default="pdf")
    
    # Organizzazione file
    struttura_cartelle = Column(JSON, nullable=True)  # Struttura directory export
    nomenclatura_file = Column(JSON, nullable=True)  # Schema nomi file
    
    # Compressione
    crea_archivio = Column(Boolean, default=True)
    formato_archivio = Column(String(10), default="zip")  # zip, rar, 7z
    
    # Metadati
    creatore = Column(String(200), nullable=False)
    data_creazione = Column(Date, nullable=False, default=date.today)
    utilizzato_count = Column(Integer, default=0)
    
    # Sistema
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ===== RELAZIONI =====
    site = relationship("ArchaeologicalSite", back_populates="configurazioni_export")
    
    def __repr__(self):
        return f"<ConfigurazioneExport(nome='{self.nome_configurazione}', destinatario='{self.destinatario}')>"


# ===== AGGIORNAMENTI PER ARCHAEOLOGICALSITE =====
"""
AGGIUNGERE QUESTE RELAZIONI in app/models/sites.py nella classe ArchaeologicalSite:

# Relazioni con report finale
relazioni_finali = relationship("RelazioneFinaleSca vo", back_populates="site", cascade="all, delete-orphan")
configurazioni_export = relationship("ConfigurazioneExport", back_populates="site", cascade="all, delete-orphan")
"""