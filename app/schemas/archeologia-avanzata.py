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


class TipoTomba(str, Enum):
    FOSSA = "fossa"
    CAPPUCCINA = "cappuccina"
    CASSA_MURARIA = "cassa_muraria"
    SARCOFAGO = "sarcofago"
    INCINERAZIONE = "incinerazione"
    ENCHYTRISMOS = "enchytrismos"


class RitoSepolcrale(str, Enum):
    INUMAZIONE = "inumazione"
    INCINERAZIONE = "incinerazione"
    MISTO = "misto"
    NON_DETERMINABILE = "non_determinabile"


class TipoMateriale(str, Enum):
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


class TipoCampione(str, Enum):
    CARBONIO_14 = "carbonio_14"
    PALEOBOTANICO = "paleobotanico"
    ARCHEOZOOLOGICO = "archeozoologico"
    SEDIMENTO = "sedimento"
    MALTE = "malte"
    METALLI = "metalli"
    CERAMICA_ANALISI = "ceramica_analisi"


class StatoConservazione(str, Enum):
    OTTIMO = "ottimo"
    BUONO = "buono"
    DISCRETO = "discreto"
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


# ===== SCHEMI TOMBE =====

class SchedaTomba_Base(BaseModel):
    """Schema base per schede tombe"""
    numero_tomba: str = Field(..., min_length=1, max_length=20, description="Numero tomba (es: T001)")
    tipo_tomba: TipoTomba = Field(..., description="Tipologia tomba")
    rito_sepolcrale: RitoSepolcrale = Field(..., description="Rito sepolcrale")
    
    # Orientamento
    orientamento_tomba: Optional[str] = Field(None, max_length=20, description="Orientamento tomba")
    orientamento_inumato: Optional[str] = Field(None, max_length=50, description="Orientamento defunto")
    
    # Dimensioni
    lunghezza_tomba: Optional[Decimal] = Field(None, ge=0, description="Lunghezza in metri")
    larghezza_tomba: Optional[Decimal] = Field(None, ge=0, description="Larghezza in metri")
    profondita_tomba: Optional[Decimal] = Field(None, ge=0, description="Profondità in metri")
    
    # Struttura
    pareti_descrizione: Optional[str] = Field(None, max_length=1000, description="Descrizione pareti")
    fondo_descrizione: Optional[str] = Field(None, max_length=1000, description="Descrizione fondo")
    copertura_descrizione: Optional[str] = Field(None, max_length=1000, description="Descrizione copertura")
    materiali_costruzione: Optional[str] = Field(None, max_length=1000, description="Materiali costruzione")
    
    # Antropologia
    numero_individui: int = Field(1, ge=1, le=10, description="Numero individui")
    sesso: Optional[str] = Field(None, regex="^(M|F|I)$", description="M/F/I (indeterminabile)")
    eta_morte: Optional[str] = Field(None, max_length=50, description="Età alla morte")
    statura_stimata: Optional[Decimal] = Field(None, ge=0, le=300, description="Statura in cm")
    
    # Posizione corpo
    posizione_corpo: Optional[str] = Field(None, max_length=100, description="Posizione corpo")
    posizione_arti_superiori: Optional[str] = Field(None, max_length=100)
    posizione_arti_inferiori: Optional[str] = Field(None, max_length=100)
    posizione_cranio: Optional[str] = Field(None, max_length=100)
    
    # Conservazione
    conservazione_scheletro: Optional[StatoConservazione] = None
    ossa_presenti: Optional[str] = Field(None, max_length=1000, description="Lista ossa presenti")
    ossa_mancanti: Optional[str] = Field(None, max_length=1000, description="Lista ossa mancanti")
    patologie_osservate: Optional[str] = Field(None, max_length=1000)
    
    # Corredo
    presenza_corredo: bool = Field(False, description="Presenza corredo funerario")
    descrizione_corredo: Optional[str] = Field(None, max_length=2000)
    
    # Cronologia
    cronologia: Optional[str] = Field(None, max_length=200)
    periodo: Optional[str] = Field(None, max_length=100)
    fase: Optional[str] = Field(None, max_length=50)
    datazione_assoluta: Optional[str] = Field(None, max_length=100, description="Da C14 o altro")
    
    # Scavo
    data_scavo: Optional[date] = None
    responsabile_scavo: Optional[str] = Field(None, max_length=200)
    metodo_scavo: Optional[str] = Field(None, max_length=100)
    
    # Documentazione
    foto_numeri: Optional[str] = Field(None, max_length=500)
    disegni_numeri: Optional[str] = Field(None, max_length=500)
    rilievo_antropologico: bool = Field(False, description="Rilievo antropologico effettuato")
    prelievo_campioni: bool = Field(False, description="Campioni prelevati")
    
    # Interpretazione
    interpretazione: Optional[str] = Field(None, max_length=2000)
    note_tafonomiche: Optional[str] = Field(None, max_length=2000, description="Note tafonomiche")
    note_generali: Optional[str] = Field(None, max_length=2000)

    @validator('numero_tomba')
    def validate_numero_tomba(cls, v):
        """Validazione formato numero tomba"""
        if not v.upper().startswith('T'):
            v = f"T{v.zfill(3)}"
        return v.upper()


class SchedaTomba_Create(SchedaTomba_Base):
    """Schema per creazione tomba"""
    site_id: UUID = Field(..., description="ID del sito archeologico")
    us_taglio_id: Optional[UUID] = Field(None, description="ID US del taglio")
    us_riempimento_id: Optional[UUID] = Field(None, description="ID US del riempimento")


class SchedaTomba_Update(BaseModel):
    """Schema per aggiornamento tomba"""
    tipo_tomba: Optional[TipoTomba] = None
    rito_sepolcrale: Optional[RitoSepolcrale] = None
    orientamento_tomba: Optional[str] = Field(None, max_length=20)
    orientamento_inumato: Optional[str] = Field(None, max_length=50)
    sesso: Optional[str] = Field(None, regex="^(M|F|I)$")
    eta_morte: Optional[str] = Field(None, max_length=50)
    presenza_corredo: Optional[bool] = None
    interpretazione: Optional[str] = Field(None, max_length=2000)


class SchedaTomba_Out(SchedaTomba_Base):
    """Schema per output tomba"""
    id: UUID
    site_id: UUID
    us_taglio_id: Optional[UUID] = None
    us_riempimento_id: Optional[UUID] = None
    compilatore: Optional[str] = None
    data_compilazione: date
    created_at: datetime
    updated_at: Optional[datetime] = None
    version: int
    
    model_config = ConfigDict(from_attributes=True)


class TombaFilter(BaseModel):
    """Filtri per ricerca tombe"""
    tipo_tomba: Optional[TipoTomba] = None
    rito_sepolcrale: Optional[RitoSepolcrale] = None
    presenza_corredo: Optional[bool] = None
    search: Optional[str] = Field(None, max_length=100)


# ===== SCHEMI REPERTI =====

class InventarioReperto_Base(BaseModel):
    """Schema base per inventario reperti"""
    numero_inventario: str = Field(..., min_length=1, max_length=50, description="Numero inventario univoco")
    numero_cassa: Optional[str] = Field(None, max_length=20, description="Numero cassa")
    numero_sacco: Optional[str] = Field(None, max_length=20, description="Numero sacco")
    
    # Classificazione
    categoria_materiale: TipoMateriale = Field(..., description="Categoria materiale")
    classe: Optional[str] = Field(None, max_length=100, description="Classe tipologica")
    tipo: Optional[str] = Field(None, max_length=100, description="Tipo")
    forma: Optional[str] = Field(None, max_length=100, description="Forma")
    
    # Descrizione
    descrizione_breve: str = Field(..., min_length=5, max_length=500, description="Descrizione sintetica")
    descrizione_dettagliata: Optional[str] = Field(None, max_length=2000)
    
    # Caratteristiche fisiche
    altezza: Optional[Decimal] = Field(None, ge=0, description="Altezza in cm")
    larghezza: Optional[Decimal] = Field(None, ge=0, description="Larghezza in cm")
    lunghezza: Optional[Decimal] = Field(None, ge=0, description="Lunghezza in cm")
    diametro: Optional[Decimal] = Field(None, ge=0, description="Diametro in cm")
    spessore: Optional[Decimal] = Field(None, ge=0, description="Spessore in cm")
    peso: Optional[Decimal] = Field(None, ge=0, description="Peso in grammi")
    
    # Quantità e conservazione
    numero_frammenti: int = Field(1, ge=1, description="Numero frammenti")
    percentuale_conservato: Optional[int] = Field(None, ge=0, le=100, description="% conservato")
    stato_conservazione: StatoConservazione = Field(..., description="Stato conservazione")
    agenti_degrado: Optional[str] = Field(None, max_length=1000)
    interventi_restauro: Optional[str] = Field(None, max_length=1000)
    
    # Cronologia
    cronologia: Optional[str] = Field(None, max_length=200)
    periodo: Optional[str] = Field(None, max_length=100)
    datazione_proposta: Optional[str] = Field(None, max_length=100)
    
    # Significatività
    rilevanza_scientifica: Optional[str] = Field(None, regex="^(alta|media|bassa)$")
    note_interpretative: Optional[str] = Field(None, max_length=2000)
    
    # Documentazione
    foto_numeri: Optional[str] = Field(None, max_length=500)
    disegni_numeri: Optional[str] = Field(None, max_length=500)
    bibliografia: Optional[str] = Field(None, max_length=1000)
    
    # Posizione deposito
    settore_deposito: Optional[str] = Field(None, max_length=50)
    scaffale: Optional[str] = Field(None, max_length=20)
    posizione: Optional[str] = Field(None, max_length=50)


class InventarioReperto_Create(InventarioReperto_Base):
    """Schema per creazione reperto"""
    site_id: UUID = Field(..., description="ID del sito archeologico")
    unita_stratigrafica_id: Optional[UUID] = Field(None, description="ID US di provenienza")
    tomba_id: Optional[UUID] = Field(None, description="ID tomba di provenienza")


class InventarioReperto_Update(BaseModel):
    """Schema per aggiornamento reperto"""
    categoria_materiale: Optional[TipoMateriale] = None
    classe: Optional[str] = Field(None, max_length=100)
    tipo: Optional[str] = Field(None, max_length=100)
    descrizione_breve: Optional[str] = Field(None, min_length=5, max_length=500)
    stato_conservazione: Optional[StatoConservazione] = None
    rilevanza_scientifica: Optional[str] = Field(None, regex="^(alta|media|bassa)$")
    posizione: Optional[str] = Field(None, max_length=50)


class InventarioReperto_Out(InventarioReperto_Base):
    """Schema per output reperto"""
    id: UUID
    site_id: UUID
    unita_stratigrafica_id: Optional[UUID] = None
    tomba_id: Optional[UUID] = None
    catalogatore: Optional[str] = None
    data_catalogazione: date
    created_at: datetime
    updated_at: Optional[datetime] = None
    version: int
    
    model_config = ConfigDict(from_attributes=True)


class RepertoFilter(BaseModel):
    """Filtri per ricerca reperti"""
    categoria_materiale: Optional[TipoMateriale] = None
    stato_conservazione: Optional[StatoConservazione] = None
    numero_cassa: Optional[str] = None
    rilevanza_scientifica: Optional[str] = Field(None, regex="^(alta|media|bassa)$")
    search: Optional[str] = Field(None, max_length=100)


# ===== SCHEMI CAMPIONI =====

class CampioneScientifico_Base(BaseModel):
    """Schema base per campioni scientifici"""
    numero_campione: str = Field(..., min_length=1, max_length=50, description="Numero campione univoco")
    tipo_campione: TipoCampione = Field(..., description="Tipologia campione")
    
    # Prelievo
    data_prelievo: date = Field(..., description="Data prelievo")
    metodo_prelievo: Optional[str] = Field(None, max_length=200)
    strumenti_utilizzati: Optional[str] = Field(None, max_length=200)
    
    # Descrizione
    descrizione: str = Field(..., min_length=10, max_length=2000, description="Descrizione campione")
    peso_campione: Optional[Decimal] = Field(None, ge=0, description="Peso in grammi")
    volume_campione: Optional[Decimal] = Field(None, ge=0, description="Volume in ml")
    
    # Conservazione
    modalita_conservazione: Optional[str] = Field(None, max_length=100)
    contenitore: Optional[str] = Field(None, max_length=100)
    posizione_deposito: Optional[str] = Field(None, max_length=100)
    
    # Analisi
    laboratorio_analisi: Optional[str] = Field(None, max_length=200)
    data_invio: Optional[date] = None
    data_risultati: Optional[date] = None
    codice_laboratorio: Optional[str] = Field(None, max_length=100)
    
    # Risultati
    interpretazione_risultati: Optional[str] = Field(None, max_length=2000)
    data_calibrata: Optional[str] = Field(None, max_length=100, description="Per C14")
    sigma: Optional[str] = Field(None, max_length=50, description="Per C14")
    
    # Note
    note_prelievo: Optional[str] = Field(None, max_length=2000)
    note_analisi: Optional[str] = Field(None, max_length=2000)


class CampioneScientifico_Create(CampioneScientifico_Base):
    """Schema per creazione campione"""
    site_id: UUID = Field(..., description="ID del sito archeologico")
    unita_stratigrafica_id: Optional[UUID] = Field(None, description="ID US di prelievo")
    tomba_id: Optional[UUID] = Field(None, description="ID tomba di prelievo")


class CampioneScientifico_Update(BaseModel):
    """Schema per aggiornamento campione"""
    tipo_campione: Optional[TipoCampione] = None
    descrizione: Optional[str] = Field(None, min_length=10, max_length=2000)
    laboratorio_analisi: Optional[str] = Field(None, max_length=200)
    data_invio: Optional[date] = None
    data_risultati: Optional[date] = None
    interpretazione_risultati: Optional[str] = Field(None, max_length=2000)


class CampioneScientifico_Out(CampioneScientifico_Base):
    """Schema per output campione"""
    id: UUID
    site_id: UUID
    unita_stratigrafica_id: Optional[UUID] = None
    tomba_id: Optional[UUID] = None
    responsabile_prelievo: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class CampioneFilter(BaseModel):
    """Filtri per ricerca campioni"""
    tipo_campione: Optional[TipoCampione] = None
    data_prelievo_da: Optional[date] = None
    data_prelievo_a: Optional[date] = None
    laboratorio_analisi: Optional[str] = None
    search: Optional[str] = Field(None, max_length=100)


# ===== SCHEMI MATERIALI ARCHEOLOGICI =====

class MaterialeArcheologico_Create(BaseModel):
    """Schema per creazione materiale tipologico"""
    categoria: TipoMateriale = Field(..., description="Categoria materiale")
    sottocategoria: Optional[str] = Field(None, max_length=100)
    tipo: str = Field(..., min_length=1, max_length=100, description="Tipo")
    sottotipo: Optional[str] = Field(None, max_length=100)
    nome_comune: str = Field(..., min_length=1, max_length=200, description="Nome comune")
    nome_scientifico: Optional[str] = Field(None, max_length=200)
    descrizione: Optional[str] = Field(None, max_length=2000)
    caratteristiche_tipiche: Optional[str] = Field(None, max_length=2000)
    cronologia_tipo: Optional[str] = Field(None, max_length=200)
    bibliografia_tipo: Optional[str] = Field(None, max_length=2000)


class MaterialeArcheologico_Out(MaterialeArcheologico_Create):
    """Schema per output materiale"""
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)