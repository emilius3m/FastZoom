# app/models/giornale_cantiere.py
"""
Modelli per il Giornale di Cantiere Archeologico
Conforme alle normative italiane per la documentazione di scavo
"""

from datetime import date, datetime
from enum import Enum as PyEnum
from uuid import uuid4
from typing import List

from sqlalchemy import Column, String, Text, Boolean, DateTime, Date, Time, Integer, ForeignKey, Table, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


# ===== ENUM PER CONDIZIONI METEO =====
class CondizioniMeteoEnum(PyEnum):
    """Enumerazione per le condizioni meteorologiche"""
    SERENO = "sereno"
    NUVOLOSO = "nuvoloso" 
    PIOGGIA = "pioggia"
    NEVE = "neve"
    VENTO_FORTE = "vento_forte"
    NEBBIA = "nebbia"
    TEMPORALE = "temporale"


# ===== TABELLA ASSOCIATIVA GIORNALE-OPERATORI =====
giornale_operatori_association = Table(
    'giornale_operatori',
    Base.metadata,
    Column('id', UUID(as_uuid=True), primary_key=True, default=uuid4),
    Column('giornale_id', UUID(as_uuid=True), ForeignKey('giornali_cantiere.id', ondelete='CASCADE'), nullable=False),
    Column('operatore_id', UUID(as_uuid=True), ForeignKey('operatori_cantiere.id', ondelete='CASCADE'), nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)


# ===== MODELLO OPERATORE DI CANTIERE =====
class OperatoreCantiere(Base):
    """
    Modello per gli operatori che lavorano nel cantiere archeologico
    Include archeologo, tecnici, operai specializzati, ecc.
    """
    __tablename__ = "operatori_cantiere"
    
    # Chiave primaria UUID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Informazioni anagrafiche
    nome = Column(String(100), nullable=False, index=True)
    cognome = Column(String(100), nullable=False, index=True)
    codice_fiscale = Column(String(16), nullable=True, unique=True)  # Opzionale per privacy
    
    # Qualifica e ruolo professionale
    qualifica = Column(String(150), nullable=False, index=True)
    # Es: "Archeologo", "Operaio specializzato", "Tecnico del rilievo",
    #     "Responsabile di cantiere", "Restauratore", "Topografo", etc.
    
    ruolo = Column(String(100), nullable=True, index=True)
    # Es: "responsabile_scavo", "assistente", "operatore", "specialista", "tecnico"
    
    # Specializzazione
    specializzazione = Column(String(200), nullable=True)
    # Es: "Ceramica romana", "Rilievo fotogrammetrico", "Epoca medievale"
    
    # Contatti
    email = Column(String(320), nullable=True, index=True)
    telefono = Column(String(20), nullable=True)
    
    # Abilitazioni e certificazioni
    abilitazioni = Column(Text, nullable=True)  # JSON o testo libero
    
    # Note aggiuntive
    note = Column(Text, nullable=True)
    
    # Stato e statistiche
    is_active = Column(Boolean, default=True, nullable=False)
    ore_totali = Column(Integer, default=0, nullable=False)  # Ore totali lavorate
    
    # Timestamp automatici
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ===== RELAZIONI =====
    # Relazione many-to-many con giornali di cantiere
    giornali = relationship(
        "GiornaleCantiere", 
        secondary=giornale_operatori_association, 
        back_populates="operatori"
    )
    
    def __repr__(self):
        return f"<OperatoreCantiere(nome='{self.nome}', cognome='{self.cognome}', qualifica='{self.qualifica}')>"
    
    def __str__(self):
        return f"{self.nome} {self.cognome} ({self.qualifica})"
    
    @property
    def nome_completo(self) -> str:
        """Restituisce nome e cognome completi"""
        return f"{self.nome} {self.cognome}"
    


# ===== MODELLO GIORNALE DI CANTIERE =====
class GiornaleCantiere(Base):
    """
    Modello per il Giornale di Cantiere Archeologico
    Conforme alle normative italiane per la documentazione di scavo
    """
    __tablename__ = "giornali_cantiere"
    
    # Chiave primaria UUID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Riferimento al sito archeologico
    site_id = Column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), nullable=False)
    
    # ===== INFORMAZIONI TEMPORALI =====
    data = Column(Date, nullable=False, index=True)
    ora_inizio = Column(Time, nullable=True)
    ora_fine = Column(Time, nullable=True)
    
    # ===== CONDIZIONI OPERATIVE =====
    condizioni_meteo = Column(String(20), nullable=False)  # Enum CondizioniMeteoEnum
    temperatura = Column(Integer, nullable=True)  # Gradi Celsius
    temperatura_min = Column(Integer, nullable=True)  # Gradi Celsius minima
    temperatura_max = Column(Integer, nullable=True)  # Gradi Celsius massima
    note_meteo = Column(Text, nullable=True)
    compilatore = Column(String(200), nullable=True)  # Nome del compilatore del giornale
    
    # ===== DESCRIZIONE ATTIVITÀ =====
    descrizione_lavori = Column(Text, nullable=False)
    modalita_lavorazioni = Column(Text, nullable=True)
    
    # Attrezzatura e mezzi utilizzati
    attrezzatura_utilizzata = Column(Text, nullable=True)
    mezzi_utilizzati = Column(Text, nullable=True)  # Es: "Escavatore, Pala meccanica"
    
    # ===== DOCUMENTAZIONE ARCHEOLOGICA PRODOTTA =====
    # Riferimenti alle Unità Stratigrafiche elaborate
    us_elaborate = Column(Text, nullable=True)  # Lista separata da virgole: "US001, US002, US003"
    usm_elaborate = Column(Text, nullable=True)  # Unità Stratigrafiche Murarie
    usr_elaborate = Column(Text, nullable=True)  # Unità Stratigrafiche di Rivestimento
    
    # Materiali rinvenuti
    materiali_rinvenuti = Column(Text, nullable=True)
    # Es: "Ceramica romana (frr. 15), Monete (n.3), Ossa animali"
    
    # Documentazione grafica e fotografica prodotta
    documentazione_prodotta = Column(Text, nullable=True)
    # Es: "Pianta US001 1:20, Sezioni A-A' e B-B', Foto nn. 150-175"
    
    # ===== SOPRALLUOGHI E VISITE =====
    sopralluoghi = Column(Text, nullable=True)
    # Es: "Sopralluogo Soprintendenza ore 10:30 - Dott.ssa Rossi"
    
    # ===== DISPOSIZIONI E ORDINI DI SERVIZIO =====
    disposizioni_rup = Column(Text, nullable=True)  # Responsabile Unico del Procedimento
    disposizioni_direttore = Column(Text, nullable=True)  # Direttore dei Lavori / Direttore Scientifico
    
    # ===== EVENTI PARTICOLARI =====
    contestazioni = Column(Text, nullable=True)
    sospensioni = Column(Text, nullable=True)  # Motivi di sospensione e ripresa
    incidenti = Column(Text, nullable=True)  # Eventuali incidenti o problemi
    note_generali = Column(Text, nullable=True)  # Note generali sul giornale
    problematiche = Column(Text, nullable=True)  # Problematiche riscontrate
    
    # ===== FORNITURE E MATERIALI =====
    forniture = Column(Text, nullable=True)  # Materiali consegnati in cantiere
    
    # ===== VALIDAZIONE E RESPONSABILITÀ =====
    responsabile_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    responsabile_nome = Column(String(200), nullable=True)  # Nome leggibile per report
    
    # Firma digitale e validazione
    validato = Column(Boolean, default=False, nullable=False)
    data_validazione = Column(DateTime(timezone=True), nullable=True)
    firma_digitale_hash = Column(String(500), nullable=True)  # Hash della firma digitale
    
    # ===== ALLEGATI E DOCUMENTAZIONE =====
    # Path degli allegati su MinIO storage
    allegati_paths = Column(Text, nullable=True)  # JSON array di path
    
    # ===== METADATI DI SISTEMA =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Versioning per modifiche
    version = Column(Integer, default=1, nullable=False)
    
    # ===== RELAZIONI =====
    # Relazione con il sito archeologico
    site = relationship("ArchaeologicalSite", back_populates="giornali_cantiere")
    
    # Relazione con l'utente responsabile
    responsabile = relationship("User", foreign_keys=[responsabile_id])
    
    # Relazione many-to-many con operatori
    operatori = relationship(
        "OperatoreCantiere", 
        secondary=giornale_operatori_association, 
        back_populates="giornali"
    )
    
    def __repr__(self):
        return f"<GiornaleCantiere(site='{self.site.name if self.site else 'N/A'}', data='{self.data}')>"
    
    def __str__(self):
        site_name = self.site.name if self.site else "N/A"
        return f"Giornale {site_name} - {self.data.strftime('%d/%m/%Y') if self.data else 'N/A'}"
    
    # ===== METODI UTILITY =====
    @property
    def durata_lavori(self) -> str:
        """Calcola la durata dei lavori se ora_inizio e ora_fine sono disponibili"""
        if self.ora_inizio and self.ora_fine:
            # Converte time in datetime per il calcolo
            from datetime import datetime, timedelta
            start = datetime.combine(self.data, self.ora_inizio)
            end = datetime.combine(self.data, self.ora_fine)
            
            if end > start:
                duration = end - start
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        return "N/A"
    
    def get_operatori_by_qualifica(self, qualifica: str) -> List["OperatoreCantiere"]:
        """Restituisce operatori filtrati per qualifica"""
        return [op for op in self.operatori if qualifica.lower() in op.qualifica.lower()]
    
    def is_modificabile(self) -> bool:
        """Controlla se il giornale può essere ancora modificato"""
        return not self.validato
    
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
    
    def set_us_list(self, us_list: List[str]) -> None:
        """Imposta la lista delle US elaborate come stringa separata da virgole"""
        self.us_elaborate = ', '.join(us_list) if us_list else None
    
    def set_usm_list(self, usm_list: List[str]) -> None:
        """Imposta la lista delle USM elaborate come stringa separata da virgole"""
        self.usm_elaborate = ', '.join(usm_list) if usm_list else None
    
    def get_apparecchiature_list(self) -> List[str]:
        """Restituisce lista delle apparecchiature utilizzate come array"""
        if self.attrezzatura_utilizzata:
            return [app.strip() for app in self.attrezzatura_utilizzata.split(',') if app.strip()]
        return []
    
    def set_apparecchiature_list(self, apparecchiature_list: List[str]) -> None:
        """Imposta la lista delle apparecchiature utilizzate come stringa separata da virgole"""
        self.attrezzatura_utilizzata = ', '.join(apparecchiature_list) if apparecchiature_list else None


# ===== AGGIORNAMENTO DEL MODELLO ARCHAEOLOGICALSITE =====
# Questo codice va aggiunto al file app/models/sites.py nella classe ArchaeologicalSite:

"""
AGGIUNGI QUESTA RELAZIONE IN app/models/sites.py:

# Relazione con i giornali di cantiere
giornali_cantiere = relationship("GiornaleCantiere", back_populates="site", cascade="all, delete-orphan")
"""


# ===== FUNZIONI UTILITY PER INIT_MODELS =====
def init_giornale_cantiere_models():
    """
    Funzione per inizializzare i modelli del giornale di cantiere
    Da aggiungere alla funzione init_models() in app/database/base.py
    """
    # Import per assicurarsi che i modelli siano registrati
    from app.models.giornale_cantiere import GiornaleCantiere, OperatoreCantiere  # noqa: F401