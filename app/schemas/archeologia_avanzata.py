# app/schemas/archeologia_avanzata.py
"""
Schemi Pydantic per Archeologia Avanzata
Validazione input/output per US, Tombe, Reperti, Campioni
"""

from datetime import date, datetime, time
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, validator


# ===== ENUM PER VALIDAZIONE =====
class TipoUS(str, Enum):
    STRATO = "strato"
    TAGLIO = "taglio"  
    RIEMPIMENTO = "riempimento"
    STRUTTURA = "struttura"
    INTERFACCIA = "interfaccia"
    DEPOSITO = "deposito"


    CATTIVO = "cattivo"
    PESSIMO = "pessimo"
    FRAMMENTARIO = "frammentario"


# ===== SCHEMI UNITÀ STRATIGRAFICHE =====

class UnitaStratigrafica_Base(BaseModel):
    """Schema base per Unità Stratigrafiche"""
    numero_us: str = Field(..., min_length=1, max_length=20, description="Numero US (es: US001)")
    tipo_us: TipoUS = Field(..., description="Tipologia US")
    denominazione: Optional[str] = Field(None, max_length=200, description="Denominazione US")
    descrizione: str = Field(..., min_length=10, max_length=2000, description="Descrizione dettagliata")
    
    # Dati stratigrafici
    formazione: Optional[str] = Field(None, max_length=100, description="Naturale/artificiale")
    consistenza: Optional[str] = Field(None, max_length=100, description="Consistenza deposito")
    colore_munsell: Optional[str] = Field(None, max_length=20, description="Codice colore Munsell")
    colore_descrizione: Optional[str] = Field(None, max_length=100, description="Descrizione colore")
    
    # Dimensioni
    lunghezza_max: Optional[Decimal] = Field(None, ge=0, description="Lunghezza massima in metri")
    larghezza_max: Optional[Decimal] = Field(None, ge=0, description="Larghezza massima in metri")  
    spessore_max: Optional[Decimal] = Field(None, ge=0, description="Spessore massimo in metri")
    spessore_min: Optional[Decimal] = Field(None, ge=0, description="Spessore minimo in metri")
    quota_superiore: Optional[Decimal] = Field(None, description="Quota superiore assoluta")
    quota_inferiore: Optional[Decimal] = Field(None, description="Quota inferiore assoluta")
    
    # Composizione
    componenti_principali: Optional[str] = Field(None, max_length=1000, description="Componenti principali")
    componenti_secondari: Optional[str] = Field(None, max_length=1000, description="Componenti secondari")
    inclusi: Optional[str] = Field(None, max_length=1000, description="Inclusi nel deposito")
    
    # Interpretazione
    interpretazione: Optional[str] = Field(None, max_length=2000, description="Interpretazione funzionale")
    cronologia: Optional[str] = Field(None, max_length=200, description="Cronologia")
    periodo: Optional[str] = Field(None, max_length=100, description="Periodo culturale")
    fase: Optional[str] = Field(None, max_length=50, description="Fase di scavo")
    
    # Scavo
    data_scavo: Optional[date] = Field(None, description="Data di scavo")
    metodo_scavo: Optional[str] = Field(None, max_length=100, description="Metodologia scavo")
    responsabile_scavo: Optional[str] = Field(None, max_length=200, description="Responsabile scavo")
    
    # Documentazione
    foto_numeri: Optional[str] = Field(None, max_length=500, description="Numeri foto")
    disegni_numeri: Optional[str] = Field(None, max_length=500, description="Numeri disegni")
    campioni_prelevati: bool = Field(False, description="Campioni prelevati")
    
    # Note
    note_generali: Optional[str] = Field(None, max_length=2000, description="Note generali")
    note_tecniche: Optional[str] = Field(None, max_length=2000, description="Note tecniche")

    @validator('numero_us')
    def validate_numero_us(cls, v):
        """Validazione formato numero US"""
        if not v.upper().startswith('US'):
            v = f"US{v.zfill(3)}"
        return v.upper()


class UnitaStratigrafica_Create(UnitaStratigrafica_Base):
    """Schema per creazione US"""
    site_id: UUID = Field(..., description="ID del sito archeologico")


class UnitaStratigrafica_Update(BaseModel):
    """Schema per aggiornamento US"""
    denominazione: Optional[str] = Field(None, max_length=200)
    descrizione: Optional[str] = Field(None, min_length=10, max_length=2000)
    formazione: Optional[str] = Field(None, max_length=100)
    consistenza: Optional[str] = Field(None, max_length=100)
    colore_munsell: Optional[str] = Field(None, max_length=20)
    colore_descrizione: Optional[str] = Field(None, max_length=100)
    lunghezza_max: Optional[Decimal] = Field(None, ge=0)
    larghezza_max: Optional[Decimal] = Field(None, ge=0)
    spessore_max: Optional[Decimal] = Field(None, ge=0)
    spessore_min: Optional[Decimal] = Field(None, ge=0)
    quota_superiore: Optional[Decimal] = None
    quota_inferiore: Optional[Decimal] = None
    interpretazione: Optional[str] = Field(None, max_length=2000)
    cronologia: Optional[str] = Field(None, max_length=200)
    periodo: Optional[str] = Field(None, max_length=100)
    fase: Optional[str] = Field(None, max_length=50)


class UnitaStratigrafica_Out(UnitaStratigrafica_Base):
    """Schema per output US"""
    id: UUID
    site_id: UUID
    compilatore: Optional[str] = None
    data_compilazione: date
    created_at: datetime
    updated_at: Optional[datetime] = None
    version: int
    
    model_config = ConfigDict(from_attributes=True)


# ===== SCHEMI FILTRI =====

class USFilter(BaseModel):
    """Filtri per ricerca US"""
    tipo_us: Optional[TipoUS] = None
    fase: Optional[str] = None
    periodo: Optional[str] = None
    data_scavo_da: Optional[date] = None
    data_scavo_a: Optional[date] = None
    search: Optional[str] = Field(None, max_length=100, description="Ricerca testuale")

