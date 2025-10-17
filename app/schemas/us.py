# app/schemas/us.py
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

SequenzaFisica = Dict[str, List[str]]

class USBase(BaseModel):
    site_id: UUID
    us_code: str = Field(..., pattern=r"^US\d{3,4}$")
    ente_responsabile: Optional[str] = None
    anno: Optional[int] = None
    ufficio_mic: Optional[str] = None
    identificativo_rif: Optional[str] = None
    localita: Optional[str] = None
    area_struttura: Optional[str] = None
    saggio: Optional[str] = None
    ambiente_unita_funzione: Optional[str] = None
    posizione: Optional[str] = None
    settori: Optional[str] = None
    piante: Optional[str] = None
    prospetti: Optional[str] = None
    sezioni: Optional[str] = None
    definizione: Optional[str] = None
    criteri_distinzione: Optional[str] = None
    modo_formazione: Optional[str] = None
    componenti_inorganici: Optional[str] = None
    componenti_organici: Optional[str] = None
    consistenza: Optional[str] = None
    colore: Optional[str] = None
    misure: Optional[str] = None
    stato_conservazione: Optional[str] = None
    sequenza_fisica: Optional[SequenzaFisica] = None
    descrizione: Optional[str] = None
    osservazioni: Optional[str] = None
    interpretazione: Optional[str] = None
    datazione: Optional[str] = None
    periodo: Optional[str] = None
    fase: Optional[str] = None
    elementi_datanti: Optional[str] = None
    dati_quantitativi_reperti: Optional[str] = None
    campionature: Optional[Dict[str, bool]] = None
    affidabilita_stratigrafica: Optional[str] = None
    responsabile_scientifico: Optional[str] = None
    data_rilevamento: Optional[date] = None
    responsabile_compilazione: Optional[str] = None
    data_rielaborazione: Optional[date] = None
    responsabile_rielaborazione: Optional[str] = None

class USCreate(USBase):
    pass

class USUpdate(BaseModel):
    # Tutti opzionali per patch
    us_code: Optional[str] = Field(None, pattern=r"^US\d{3,4}$")
    ente_responsabile: Optional[str] = None
    anno: Optional[int] = None
    ufficio_mic: Optional[str] = None
    identificativo_rif: Optional[str] = None
    localita: Optional[str] = None
    area_struttura: Optional[str] = None
    saggio: Optional[str] = None
    ambiente_unita_funzione: Optional[str] = None
    posizione: Optional[str] = None
    settori: Optional[str] = None
    piante: Optional[str] = None
    prospetti: Optional[str] = None
    sezioni: Optional[str] = None
    definizione: Optional[str] = None
    criteri_distinzione: Optional[str] = None
    modo_formazione: Optional[str] = None
    componenti_inorganici: Optional[str] = None
    componenti_organici: Optional[str] = None
    consistenza: Optional[str] = None
    colore: Optional[str] = None
    misure: Optional[str] = None
    stato_conservazione: Optional[str] = None
    sequenza_fisica: Optional[SequenzaFisica] = None
    descrizione: Optional[str] = None
    osservazioni: Optional[str] = None
    interpretazione: Optional[str] = None
    datazione: Optional[str] = None
    periodo: Optional[str] = None
    fase: Optional[str] = None
    elementi_datanti: Optional[str] = None
    dati_quantitativi_reperti: Optional[str] = None
    campionature: Optional[Dict[str, bool]] = None
    affidabilita_stratigrafica: Optional[str] = None
    responsabile_scientifico: Optional[str] = None
    data_rilevamento: Optional[date] = None
    responsabile_compilazione: Optional[str] = None
    data_rielaborazione: Optional[date] = None
    responsabile_rielaborazione: Optional[str] = None

class USOut(USBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class USMBase(BaseModel):
    site_id: UUID
    usm_code: str = Field(..., pattern=r"^USM\d{3,4}$")
    ente_responsabile: Optional[str] = None
    anno: Optional[int] = None
    ufficio_mic: Optional[str] = None
    identificativo_rif: Optional[str] = None
    localita: Optional[str] = None
    area_struttura: Optional[str] = None
    saggio: Optional[str] = None
    ambiente_unita_funzione: Optional[str] = None
    posizione: Optional[str] = None
    settori: Optional[str] = None
    piante: Optional[str] = None
    prospetti: Optional[str] = None
    sezioni: Optional[str] = None
    misure: Optional[str] = None
    superficie_analizzata: Optional[float] = None
    definizione: Optional[str] = None
    tecnica_costruttiva: Optional[str] = None
    sezione_muraria_visibile: Optional[bool] = None
    sezione_muraria_tipo: Optional[str] = None
    sezione_muraria_spessore: Optional[str] = None
    funzione_statica: Optional[str] = None
    modulo: Optional[str] = None
    criteri_distinzione: Optional[str] = None
    provenienza_materiali: Optional[str] = None
    orientamento: Optional[str] = None
    uso_primario: Optional[str] = None
    riutilizzo: Optional[str] = None
    stato_conservazione: Optional[str] = None
    materiali_laterizi: Optional[Dict[str, Any]] = None
    materiali_elementi_litici: Optional[Dict[str, Any]] = None
    materiali_altro: Optional[str] = None
    legante: Optional[Dict[str, Any]] = None
    legante_altro: Optional[str] = None
    finiture_elementi_particolari: Optional[str] = None
    sequenza_fisica: Optional[SequenzaFisica] = None
    descrizione: Optional[str] = None
    osservazioni: Optional[str] = None
    interpretazione: Optional[str] = None
    datazione: Optional[str] = None
    periodo: Optional[str] = None
    fase: Optional[str] = None
    elementi_datanti: Optional[str] = None
    campionature: Optional[Dict[str, bool]] = None
    affidabilita_stratigrafica: Optional[str] = None
    responsabile_scientifico: Optional[str] = None
    data_rilevamento: Optional[date] = None
    responsabile_compilazione: Optional[str] = None
    data_rielaborazione: Optional[date] = None
    responsabile_rielaborazione: Optional[str] = None

class USMCreate(USMBase):
    pass

class USMUpdate(BaseModel):
    # Tutti i campi opzionali per permettere update parziali
    usm_code: Optional[str] = Field(None, pattern=r"^USM\d{3,4}$")
    ente_responsabile: Optional[str] = None
    anno: Optional[int] = None
    ufficio_mic: Optional[str] = None
    identificativo_rif: Optional[str] = None
    localita: Optional[str] = None
    area_struttura: Optional[str] = None
    saggio: Optional[str] = None
    ambiente_unita_funzione: Optional[str] = None
    posizione: Optional[str] = None
    settori: Optional[str] = None
    piante: Optional[str] = None
    prospetti: Optional[str] = None
    sezioni: Optional[str] = None
    misure: Optional[str] = None
    superficie_analizzata: Optional[float] = None
    definizione: Optional[str] = None
    tecnica_costruttiva: Optional[str] = None
    sezione_muraria_visibile: Optional[bool] = None
    sezione_muraria_tipo: Optional[str] = None
    sezione_muraria_spessore: Optional[str] = None
    funzione_statica: Optional[str] = None
    modulo: Optional[str] = None
    criteri_distinzione: Optional[str] = None
    provenienza_materiali: Optional[str] = None
    orientamento: Optional[str] = None
    uso_primario: Optional[str] = None
    riutilizzo: Optional[str] = None
    stato_conservazione: Optional[str] = None
    materiali_laterizi: Optional[Dict[str, Any]] = None
    materiali_elementi_litici: Optional[Dict[str, Any]] = None
    materiali_altro: Optional[str] = None
    legante: Optional[Dict[str, Any]] = None
    legante_altro: Optional[str] = None
    finiture_elementi_particolari: Optional[str] = None
    sequenza_fisica: Optional[SequenzaFisica] = None
    descrizione: Optional[str] = None
    osservazioni: Optional[str] = None
    interpretazione: Optional[str] = None
    datazione: Optional[str] = None
    periodo: Optional[str] = None
    fase: Optional[str] = None
    elementi_datanti: Optional[str] = None
    campionature: Optional[Dict[str, bool]] = None
    affidabilita_stratigrafica: Optional[str] = None
    responsabile_scientifico: Optional[str] = None
    data_rilevamento: Optional[date] = None
    responsabile_compilazione: Optional[str] = None
    data_rielaborazione: Optional[date] = None
    responsabile_rielaborazione: Optional[str] = None

class USMOut(USMBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
