# app/schemas/giornale_cantiere.py
"""
Schemi Pydantic per il Giornale di Cantiere Archeologico
Input/Output validation per le API REST
"""

from datetime import date, datetime, time
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, validator


# ===== ENUM PER VALIDAZIONE =====
class CondizioniMeteoEnum(str, Enum):
    """Enumerazione per le condizioni meteorologiche"""
    SERENO = "sereno"
    NUVOLOSO = "nuvoloso"
    PIOGGIA = "pioggia" 
    NEVE = "neve"
    VENTO_FORTE = "vento_forte"
    NEBBIA = "nebbia"
    TEMPORALE = "temporale"


# ===== SCHEMI OPERATORE DI CANTIERE =====

class OperatoreCantiereBase(BaseModel):
    """Schema base per operatore di cantiere"""
    nome: str = Field(..., min_length=2, max_length=100, description="Nome dell'operatore")
    cognome: str = Field(..., min_length=2, max_length=100, description="Cognome dell'operatore")
    codice_fiscale: Optional[str] = Field(None, min_length=16, max_length=16, description="Codice fiscale (opzionale)")
    qualifica: str = Field(..., min_length=3, max_length=150, description="Qualifica professionale")
    specializzazione: Optional[str] = Field(None, max_length=200, description="Specializzazione specifica")
    email: Optional[str] = Field(None, max_length=320, description="Email di contatto")
    telefono: Optional[str] = Field(None, max_length=20, description="Numero di telefono")
    abilitazioni: Optional[str] = Field(None, description="Abilitazioni e certificazioni")
    is_active: bool = Field(True, description="Operatore attivo")

    @validator('codice_fiscale')
    def validate_codice_fiscale(cls, v):
        """Validazione codice fiscale italiano"""
        if v and len(v) != 16:
            raise ValueError('Il codice fiscale deve essere di 16 caratteri')
        if v and not v.isalnum():
            raise ValueError('Il codice fiscale deve contenere solo lettere e numeri')
        return v.upper() if v else v


class OperatoreCantiereCreate(OperatoreCantiereBase):
    """Schema per creazione operatore"""
    pass


class OperatoreCantiereUpdate(BaseModel):
    """Schema per aggiornamento operatore"""
    nome: Optional[str] = Field(None, min_length=2, max_length=100)
    cognome: Optional[str] = Field(None, min_length=2, max_length=100)
    codice_fiscale: Optional[str] = Field(None, min_length=16, max_length=16)
    qualifica: Optional[str] = Field(None, min_length=3, max_length=150)
    specializzazione: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=320)
    telefono: Optional[str] = Field(None, max_length=20)
    abilitazioni: Optional[str] = None
    is_active: Optional[bool] = None


class OperatoreCantiereOut(OperatoreCantiereBase):
    """Schema per output operatore"""
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# ===== SCHEMI GIORNALE DI CANTIERE =====

class GiornaleCantiereBase(BaseModel):
    """Schema base per giornale di cantiere"""
    data: date = Field(..., description="Data del giorno lavorativo")
    ora_inizio: Optional[time] = Field(None, description="Ora inizio lavori")
    ora_fine: Optional[time] = Field(None, description="Ora fine lavori")
    
    # Condizioni operative
    condizioni_meteo: CondizioniMeteoEnum = Field(..., description="Condizioni meteorologiche")
    temperatura: Optional[int] = Field(None, ge=-30, le=50, description="Temperatura in gradi Celsius")
    note_meteo: Optional[str] = Field(None, max_length=500, description="Note aggiuntive sulle condizioni meteo")
    
    # Descrizione attività
    descrizione_lavori: str = Field(..., min_length=10, max_length=2000, description="Descrizione dettagliata dei lavori svolti")
    modalita_lavorazioni: Optional[str] = Field(None, max_length=1000, description="Modalità e metodologie di lavorazione")
    attrezzatura_utilizzata: Optional[str] = Field(None, max_length=1000, description="Attrezzatura e strumenti utilizzati")
    mezzi_utilizzati: Optional[str] = Field(None, max_length=500, description="Mezzi meccanici utilizzati")
    
    # Documentazione archeologica
    us_elaborate: Optional[str] = Field(None, max_length=500, description="Unità Stratigrafiche elaborate (es: US001, US002)")
    usm_elaborate: Optional[str] = Field(None, max_length=500, description="Unità Stratigrafiche Murarie elaborate")
    usr_elaborate: Optional[str] = Field(None, max_length=500, description="Unità Stratigrafiche di Rivestimento elaborate")
    materiali_rinvenuti: Optional[str] = Field(None, max_length=1000, description="Materiali archeologici rinvenuti")
    documentazione_prodotta: Optional[str] = Field(None, max_length=1000, description="Documentazione grafica e fotografica prodotta")
    
    # Sopralluoghi e disposizioni
    sopralluoghi: Optional[str] = Field(None, max_length=1000, description="Sopralluoghi e visite ricevute")
    disposizioni_rup: Optional[str] = Field(None, max_length=1000, description="Disposizioni del RUP")
    disposizioni_direttore: Optional[str] = Field(None, max_length=1000, description="Disposizioni del Direttore Lavori/Scientifico")
    
    # Eventi e problemi
    contestazioni: Optional[str] = Field(None, max_length=1000, description="Eventuali contestazioni")
    sospensioni: Optional[str] = Field(None, max_length=1000, description="Sospensioni e motivazioni")
    incidenti: Optional[str] = Field(None, max_length=1000, description="Incidenti o problemi riscontrati")
    forniture: Optional[str] = Field(None, max_length=500, description="Forniture e materiali consegnati")

    @validator('ora_fine')
    def validate_ora_fine(cls, v, values):
        """Valida che ora_fine sia successiva a ora_inizio"""
        if v and 'ora_inizio' in values and values['ora_inizio']:
            if v <= values['ora_inizio']:
                raise ValueError('Ora fine deve essere successiva a ora inizio')
        return v


class GiornaleCantiereCreate(GiornaleCantiereBase):
    """Schema per creazione giornale di cantiere"""
    site_id: UUID = Field(..., description="ID del sito archeologico")
    operatori_ids: List[UUID] = Field(default_factory=list, description="Lista ID degli operatori presenti")


class GiornaleCantiereUpdate(BaseModel):
    """Schema per aggiornamento giornale di cantiere"""
    data: Optional[date] = None
    ora_inizio: Optional[time] = None
    ora_fine: Optional[time] = None
    condizioni_meteo: Optional[CondizioniMeteoEnum] = None
    temperatura: Optional[int] = Field(None, ge=-30, le=50)
    note_meteo: Optional[str] = Field(None, max_length=500)
    descrizione_lavori: Optional[str] = Field(None, min_length=10, max_length=2000)
    modalita_lavorazioni: Optional[str] = Field(None, max_length=1000)
    attrezzatura_utilizzata: Optional[str] = Field(None, max_length=1000)
    mezzi_utilizzati: Optional[str] = Field(None, max_length=500)
    us_elaborate: Optional[str] = Field(None, max_length=500)
    usm_elaborate: Optional[str] = Field(None, max_length=500)
    usr_elaborate: Optional[str] = Field(None, max_length=500)
    materiali_rinvenuti: Optional[str] = Field(None, max_length=1000)
    documentazione_prodotta: Optional[str] = Field(None, max_length=1000)
    sopralluoghi: Optional[str] = Field(None, max_length=1000)
    disposizioni_rup: Optional[str] = Field(None, max_length=1000)
    disposizioni_direttore: Optional[str] = Field(None, max_length=1000)
    contestazioni: Optional[str] = Field(None, max_length=1000)
    sospensioni: Optional[str] = Field(None, max_length=1000)
    incidenti: Optional[str] = Field(None, max_length=1000)
    forniture: Optional[str] = Field(None, max_length=500)
    operatori_ids: Optional[List[UUID]] = None


class GiornaleCantiereOut(GiornaleCantiereBase):
    """Schema per output giornale di cantiere"""
    id: UUID
    site_id: UUID
    responsabile_id: UUID
    responsabile_nome: Optional[str] = None
    validato: bool
    data_validazione: Optional[datetime] = None
    version: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Relazioni
    operatori: List[OperatoreCantiereOut] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)
    
    @property
    def durata_lavori_computed(self) -> Optional[str]:
        """Calcola durata lavori come proprietà computata"""
        if self.ora_inizio and self.ora_fine:
            from datetime import datetime, timedelta
            start = datetime.combine(self.data, self.ora_inizio)
            end = datetime.combine(self.data, self.ora_fine)
            
            if end > start:
                duration = end - start
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        return None


# ===== SCHEMI PER FILTRI E RICERCA =====

class GiornaleCantiereFilter(BaseModel):
    """Schema per filtri di ricerca sui giornali di cantiere"""
    data_inizio: Optional[date] = Field(None, description="Filtra da questa data (inclusa)")
    data_fine: Optional[date] = Field(None, description="Filtra fino a questa data (inclusa)")
    condizioni_meteo: Optional[CondizioniMeteoEnum] = Field(None, description="Filtra per condizioni meteo")
    responsabile_id: Optional[UUID] = Field(None, description="Filtra per responsabile")
    validato: Optional[bool] = Field(None, description="Filtra per stato validazione")


# ===== SCHEMI PER STATISTICHE =====

class GiornaleStatistiche(BaseModel):
    """Schema per statistiche sui giornali di cantiere"""
    site_id: UUID
    total_giornali: int = Field(..., description="Totale giornali nel sito")
    validated_giornali: int = Field(..., description="Giornali validati")
    pending_validation: int = Field(..., description="Giornali in attesa di validazione")
    last_entry_date: Optional[date] = Field(None, description="Data dell'ultimo giornale")
    validation_percentage: float = Field(..., description="Percentuale di validazione")


# ===== SCHEMI PER BULK OPERATIONS =====

class GiornaleBulkValidation(BaseModel):
    """Schema per validazione multipla di giornali"""
    giornale_ids: List[UUID] = Field(..., min_items=1, description="Lista ID giornali da validare")
    
    @validator('giornale_ids')
    def validate_unique_ids(cls, v):
        """Verifica che gli ID siano unici"""
        if len(v) != len(set(v)):
            raise ValueError('Gli ID dei giornali devono essere unici')
        return v


# ===== SCHEMI PER EXPORT/REPORT =====

class GiornaleExportFilter(BaseModel):
    """Schema per filtri export giornali"""
    site_id: UUID = Field(..., description="ID sito archeologico")
    data_inizio: Optional[date] = None
    data_fine: Optional[date] = None
    formato: str = Field("pdf", pattern="^(pdf|excel|csv)$", description="Formato export")
    include_allegati: bool = Field(False, description="Includi riferimenti agli allegati")


# ===== SCHEMI PER UPLOAD ALLEGATI =====

class AllegatoInfo(BaseModel):
    """Schema per informazioni allegato"""
    filename: str
    content_type: str
    size: int
    path: str
    
    
class AllegatoResponse(BaseModel):
    """Schema per risposta upload allegato"""
    giornale_id: UUID
    allegati_caricati: List[AllegatoInfo]
    total_allegati: int


# ===== SCHEMI PER VALIDAZIONI AVANZATE =====

class GiornaleValidationResult(BaseModel):
    """Schema per risultato validazione giornale"""
    giornale_id: UUID
    is_valid: bool
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    required_fields_missing: List[str] = Field(default_factory=list)


# ===== SCHEMI RESPONSE PERSONALIZZATI =====

class GiornaleResponse(BaseModel):
    """Schema response generico per operazioni sui giornali"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)


class PaginatedGiornaleResponse(BaseModel):
    """Schema per risposta paginata"""
    items: List[GiornaleCantiereOut]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_prev: bool