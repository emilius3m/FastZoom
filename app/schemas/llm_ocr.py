# app/schemas/llm_ocr.py
"""
Pydantic schemas per validazione output LLM OCR.
Usati per validare il JSON prodotto dal VLM prima di importarlo nel DB.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator
import re


Confidence = Literal["low", "medium", "high"]


class LLMField(BaseModel):
    """Campo singolo estratto dal VLM."""
    key: str
    label: str
    value: Optional[str] = None


class LLMRelationships(BaseModel):
    """Relazioni stratigrafiche estratte da una pagina."""
    copre: List[str] = []
    coperto_da: List[str] = []
    posteriore_a: List[str] = []
    anteriore_a: List[str] = []
    taglia: List[str] = []
    tagliato_da: List[str] = []
    riempie: List[str] = []
    riempito_da: List[str] = []
    si_lega_a: List[str] = []
    uguale_a: List[str] = []
    si_appoggia_a: List[str] = []
    gli_si_appoggia: List[str] = []


class LLMPage(BaseModel):
    """Dati estratti da una singola pagina del documento."""
    page_index: Literal[0, 1]
    fields: List[LLMField] = []
    relationships: LLMRelationships = Field(default_factory=LLMRelationships)
    issues: List[str] = []


class USMapped(BaseModel):
    """
    Campi normalizzati pronti per l'import nel DB.
    Compatibili con UnitaStratigrafica(**us_data).
    """
    # Campi obbligatori
    us_code: str
    
    # Campi identificativi
    tipo: Optional[str] = None
    anno: Optional[int] = None
    ente_responsabile: Optional[str] = None
    ufficio_mic: Optional[str] = None
    identificativo_rif: Optional[str] = None
    
    # Localizzazione
    localita: Optional[str] = None
    area_struttura: Optional[str] = None
    saggio: Optional[str] = None
    ambiente_unita_funzione: Optional[str] = None
    posizione: Optional[str] = None
    settori: Optional[str] = None
    quadrati: Optional[str] = None
    quote: Optional[str] = None
    
    # Documentazione
    piante_riferimenti: Optional[str] = None
    prospetti_riferimenti: Optional[str] = None
    sezioni_riferimenti: Optional[str] = None
    fotografie: Optional[str] = None
    riferimenti_tabelle_materiali: Optional[str] = None
    
    # Caratteristiche fisiche
    definizione: Optional[str] = None
    criteri_distinzione: Optional[str] = None
    modo_formazione: Optional[str] = None
    componenti_inorganici: Optional[str] = None
    componenti_organici: Optional[str] = None
    consistenza: Optional[str] = None
    colore: Optional[str] = None
    misure: Optional[str] = None
    stato_conservazione: Optional[str] = None
    
    # Interpretazione
    descrizione: Optional[str] = None
    osservazioni: Optional[str] = None
    interpretazione: Optional[str] = None
    
    # Cronologia
    periodo: Optional[str] = None
    fase: Optional[str] = None
    attivita: Optional[str] = None
    datazione: Optional[str] = None
    elementi_datanti: Optional[str] = None
    dati_quantitativi_reperti: Optional[str] = None
    
    # Campionature
    campionature: Optional[str] = None
    flottazione: Optional[str] = None
    setacciatura: Optional[str] = None
    affidabilita_stratigrafica: Optional[str] = None
    
    # Responsabili e date
    responsabile_scientifico: Optional[str] = None
    data_rilevamento: Optional[str] = None  # YYYY-MM-DD
    responsabile_compilazione: Optional[str] = None
    data_rielaborazione: Optional[str] = None  # YYYY-MM-DD
    responsabile_rielaborazione: Optional[str] = None
    
    # Sequenza fisica (relazioni stratigrafiche)
    sequenza_fisica: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Campi extra non mappati esplicitamente
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("us_code")
    @classmethod
    def validate_us_code(cls, v: str) -> str:
        """Valida che us_code sia nel formato US + 3-4 cifre."""
        if not v:
            raise ValueError("us_code è obbligatorio")
        # Normalizza: se è solo numero, aggiungi US
        if v.isdigit():
            v = f"US{v.zfill(3)}"
        # Valida formato
        if not re.match(r"^US[M]?\d{3,4}$", v, re.IGNORECASE):
            raise ValueError(f"us_code deve essere tipo US001 o USM0001, ricevuto: {v}")
        return v.upper()

    @field_validator("data_rilevamento", "data_rielaborazione", mode="before")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """Valida e normalizza date in formato YYYY-MM-DD."""
        if not v:
            return None
        # Prova a parsare vari formati
        import re
        from datetime import datetime
        
        v = str(v).strip()
        
        # Già in formato corretto
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return v
        
        # Formato italiano DD/MM/YYYY o DD-MM-YYYY
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"]:
            try:
                dt = datetime.strptime(v, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # Se non riconosciuto, ritorna None (non blocca l'import)
        return None


class LLMUSDocument(BaseModel):
    """
    Documento completo estratto dal VLM.
    Contiene sia i dati grezzi per pagina che i campi mappati per l'import.
    """
    schema_version: Literal["fz.us.llm.v1"] = "fz.us.llm.v1"
    document_type: Literal["US"] = "US"
    filename: str
    pages: List[LLMPage]  # Normalmente 2 pagine, ma flessibile
    mapped: USMapped
    confidence: Confidence = "medium"
    global_issues: List[str] = []

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, pages: List[LLMPage]) -> List[LLMPage]:
        """Valida che ci siano almeno 1-2 pagine con indici corretti."""
        if len(pages) == 0:
            raise ValueError("Deve esserci almeno una pagina")
        if len(pages) > 2:
            raise ValueError("Massimo 2 pagine supportate")
        
        # Controlla indici
        indices = sorted([p.page_index for p in pages])
        if len(pages) == 2 and indices != [0, 1]:
            raise ValueError("pages deve contenere page_index 0 e 1")
        if len(pages) == 1 and pages[0].page_index not in [0, 1]:
            raise ValueError("page_index deve essere 0 o 1")
        
        return pages

    def to_db_dict(self, site_id: str) -> Dict[str, Any]:
        """
        Converte in dizionario pronto per UnitaStratigrafica(**data).
        
        Args:
            site_id: UUID del sito (stringa)
            
        Returns:
            Dict compatibile con il modello UnitaStratigrafica
        """
        data = self.mapped.model_dump(exclude_none=True, exclude={"extra"})
        
        # Aggiungi site_id
        data["site_id"] = site_id
        
        # Integra campi extra
        extra = self.mapped.extra or {}
        for k, v in extra.items():
            if k not in data and v is not None:
                data[k] = v
        
        # Metadata OCR
        data["_llm_source"] = self.filename
        data["_llm_confidence"] = self.confidence
        data["_llm_issues"] = self.global_issues
        
        return data


# Alias per retrocompatibilità
LLMOCRResult = LLMUSDocument
