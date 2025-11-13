# app/models/cantiere.py
"""
Modello per la gestione dei Cantieri (Work Sites) all'interno di un Sito Archeologico
Un sito può avere più cantieri contemporanei, e ogni giornale è associato a un cantiere specifico.
"""

from datetime import datetime, date
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, Date, Boolean, ForeignKey, Integer, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Cantiere(Base):
    """
    Modello per un Cantiere (Work Site) all'interno di un Sito Archeologico
    
    Rappresenta un'area di lavoro specifica all'interno di un sito archeologico,
    dove possono essere registrati giornali di cantiere.
    """
    __tablename__ = "cantieri"
    
    # Primary key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), index=True)
    
    # Foreign key to ArchaeologicalSite
    site_id = Column(
        String(36),
        ForeignKey("archaeological_sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Informazioni base del cantiere
    nome = Column(String(200), nullable=False, index=True)
    codice = Column(String(50), nullable=True, index=True)  # Codice identificativo cantiere
    descrizione = Column(Text, nullable=True)
    
    # Campi per il giornale dei lavori
    # Ente o soggetto committente (es: 'PARCO ARCHEOLOGICO DI SEPINO')
    committente = Column(String(200), nullable=True)
    
    # Impresa che esegue i lavori (es: 'De Maioribus srl')
    impresa_esecutrice = Column(String(200), nullable=True)
    
    # Nome e qualifica del Direttore dei Lavori
    direttore_lavori = Column(String(200), nullable=True)
    
    # Responsabile Unico del Procedimento (RUP)
    responsabile_procedimento = Column(String(200), nullable=True)
    
    # Descrizione completa dell'oggetto dell'appalto
    oggetto_appalto = Column(Text, nullable=True)
    
    # Campi opzionali
    # Codice Unico di Progetto
    codice_cup = Column(String(50), nullable=True)
    
    # Codice Identificativo Gara
    codice_cig = Column(String(50), nullable=True)
    
    # Importo complessivo dei lavori
    importo_lavori = Column(Numeric(15, 2), nullable=True)
    
    # Informazioni temporali
    data_inizio_prevista = Column(Date, nullable=True)
    data_fine_prevista = Column(Date, nullable=True)
    data_inizio_effettiva = Column(Date, nullable=True)
    data_fine_effettiva = Column(Date, nullable=True)
    
    # Stato del cantiere
    stato = Column(String(20), nullable=False, default="pianificato", index=True)
    # Stati possibili: pianificato, in_corso, sospeso, completato, annullato
    
    # Informazioni geografiche/localizzazione specifica del cantiere
    area_descrizione = Column(Text, nullable=True)  # Descrizione dell'area specifica
    coordinate_lat = Column(String(50), nullable=True)
    coordinate_lon = Column(String(50), nullable=True)
    quota = Column(String(20), nullable=True)  # Quota altimetrica
    
    # Metadati
    responsabile_cantiere = Column(String(200), nullable=True)  # Nome responsabile cantiere
    tipologia_intervento = Column(String(100), nullable=True)  # Tipo di intervento
    priorita = Column(Integer, nullable=False, default=3)  # Priorità (1-5)
    
    # Timestamp
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Soft delete
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime, nullable=True)
    
    # Relationships
    site = relationship("ArchaeologicalSite", back_populates="cantieri")
    # Relazione con i giornali di cantiere
    giornali_cantiere = relationship("GiornaleCantiere", back_populates="cantiere", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Cantiere(id={self.id}, nome='{self.nome}', sito_id={self.site_id})>"
    
    @property
    def nome_completo(self):
        """Restituisce il nome completo del cantiere con codice se presente"""
        if self.codice:
            return f"{self.nome} ({self.codice})"
        return self.nome
    
    @property
    def durata_giorni(self):
        """Calcola la durata in giorni del cantiere se completato"""
        if self.data_inizio_effettiva and self.data_fine_effettiva:
            return (self.data_fine_effettiva - self.data_inizio_effettiva).days + 1
        return None
    
    @property
    def e_in_corso(self):
        """Verifica se il cantiere è attualmente in corso"""
        today = date.today()
        if self.data_inizio_effettiva and self.data_fine_effettiva:
            return self.data_inizio_effettiva <= today <= self.data_fine_effettiva
        return False
    
    @property
    def stato_formattato(self):
        """Restituisce lo stato formattato per la visualizzazione"""
        stati = {
            "pianificato": "Pianificato",
            "in_corso": "In Corso", 
            "sospeso": "Sospeso",
            "completato": "Completato",
            "annullato": "Annullato"
        }
        return stati.get(self.stato, self.stato.title())
    
    def to_dict(self):
        """Converte il modello in dizionario per serializzazione JSON"""
        return {
            "id": str(self.id),
            "site_id": str(self.site_id),
            "nome": self.nome,
            "codice": self.codice,
            "descrizione": self.descrizione,
            # Campi per il giornale dei lavori
            "committente": self.committente,
            "impresa_esecutrice": self.impresa_esecutrice,
            "direttore_lavori": self.direttore_lavori,
            "responsabile_procedimento": self.responsabile_procedimento,
            "oggetto_appalto": self.oggetto_appalto,
            # Campi opzionali
            "codice_cup": self.codice_cup,
            "codice_cig": self.codice_cig,
            "importo_lavori": float(self.importo_lavori) if self.importo_lavori else None,
            # Campi temporali
            "data_inizio_prevista": self.data_inizio_prevista.isoformat() if self.data_inizio_prevista else None,
            "data_fine_prevista": self.data_fine_prevista.isoformat() if self.data_fine_prevista else None,
            "data_inizio_effettiva": self.data_inizio_effettiva.isoformat() if self.data_inizio_effettiva else None,
            "data_fine_effettiva": self.data_fine_effettiva.isoformat() if self.data_fine_effettiva else None,
            "stato": self.stato,
            "stato_formattato": self.stato_formattato,
            # Campi geografici
            "area_descrizione": self.area_descrizione,
            "coordinate_lat": self.coordinate_lat,
            "coordinate_lon": self.coordinate_lon,
            "quota": self.quota,
            # Metadati
            "responsabile_cantiere": self.responsabile_cantiere,
            "tipologia_intervento": self.tipologia_intervento,
            "priorita": self.priorita,
            # Proprietà calcolate
            "nome_completo": self.nome_completo,
            "durata_giorni": self.durata_giorni,
            "e_in_corso": self.e_in_corso,
            # Timestamp
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active
        }