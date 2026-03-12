from __future__ import annotations

from datetime import datetime
from enum import Enum
import unicodedata
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.utils.vocabolari_iccd import (
    CDGG_CONDIZIONE_GIURIDICA,
    CDGG_DEFAULT,
    CODICI_REGIONE,
    DENOMINAZIONI_REGIONE,
    DTM_MOTIVAZIONI_TMA_EXTENDED,
    LIVELLI_RICERCA,
    PROVINCE_PER_REGIONE,
    SIGLE_PROVINCE_VALIDE,
)


_DENOMINAZIONI_REGIONE_VALORI = set(DENOMINAZIONI_REGIONE.values())
_DTM_MOTIVAZIONI_TMA_EXTENDED_VALORI = set(DTM_MOTIVAZIONI_TMA_EXTENDED)
_CDGG_CONDIZIONE_GIURIDICA_VALORI = set(CDGG_CONDIZIONE_GIURIDICA)
_DENOMINAZIONI_REGIONE_ALIAS = {
    "Estero": "00",
    "Valle d'Aosta": "Valle d'Aosta/Vallée d'Aoste",
    "Trentino-Alto Adige": "Trentino-Alto Adige/Südtirol",
}


def _normalize_denominazione_regione(value: str, field_name: str) -> str:
    raw = (value or "").strip()
    raw = _DENOMINAZIONI_REGIONE_ALIAS.get(raw, raw)
    if raw not in _DENOMINAZIONI_REGIONE_VALORI:
        raise ValueError(f"{field_name} non valido secondo Lista Regioni ICCD")
    return raw


def _normalize_sigla_provincia(value: str, field_name: str) -> str:
    raw = (value or "").strip().upper()
    if raw not in SIGLE_PROVINCE_VALIDE:
        raise ValueError(f"{field_name} non valido secondo Lista Province ICCD")
    return raw


def _normalize_loose_text(value: str) -> str:
    raw = " ".join((value or "").strip().split())
    raw = "".join(
        c for c in unicodedata.normalize("NFD", raw)
        if unicodedata.category(c) != "Mn"
    )
    return raw.casefold()


_CDGG_CONDIZIONE_GIURIDICA_LOOKUP = {
    _normalize_loose_text(v): v for v in CDGG_CONDIZIONE_GIURIDICA
}


def _normalize_cdgg(value: str, field_name: str) -> str:
    raw = " ".join((value or "").strip().split())
    if raw in _CDGG_CONDIZIONE_GIURIDICA_VALORI:
        return raw

    normalized_key = _normalize_loose_text(raw)
    canonical = _CDGG_CONDIZIONE_GIURIDICA_LOOKUP.get(normalized_key)
    if canonical:
        return canonical

    if raw not in _CDGG_CONDIZIONE_GIURIDICA_VALORI:
        raise ValueError(f"{field_name} non valido secondo vocabolario chiuso TMA")
    return raw


class LIREnum(str, Enum):
    inventario = "I"
    precatalogo = "P"
    catalogo = "C"


class ADSPEnum(int, Enum):
    visibile = 1
    limitato = 2


class MACItem(BaseModel):
    macc: str = Field(..., max_length=100)
    macl: Optional[str] = Field(None, max_length=150)
    macd: Optional[str] = Field(None, max_length=150)
    macp: Optional[str] = Field(None, max_length=150)
    macq: int = Field(..., ge=1)
    mas: Optional[str] = Field(None, max_length=250)

    model_config = ConfigDict(extra="forbid")

    @field_validator("macc", mode="before")
    @classmethod
    def normalize_macc(cls, value: str) -> str:
        return (value or "").strip()


class FTAItem(BaseModel):
    ftax: Optional[str] = Field(None, max_length=100)
    ftap: Optional[str] = Field(None, max_length=100)
    ftan: Optional[str] = Field(None, max_length=200)
    file_path: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(extra="forbid")


class LAItem(BaseModel):
    tcl: Optional[str] = Field(None, max_length=100)
    prvs: Optional[str] = Field(None, max_length=50)
    prvr: Optional[str] = Field(None, max_length=50)
    prvp: Optional[str] = Field(None, max_length=3)
    prvc: Optional[str] = Field(None, max_length=50)
    prcu: Optional[str] = Field(None, max_length=250)

    model_config = ConfigDict(extra="forbid")

    @field_validator("prvr")
    @classmethod
    def validate_prvr(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return _normalize_denominazione_regione(value, "PRVR")

    @field_validator("prvp")
    @classmethod
    def validate_prvp(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return _normalize_sigla_provincia(value, "PRVP")

    @model_validator(mode="after")
    def validate_prvr_prvp_consistency(self) -> "LAItem":
        if not self.prvr or not self.prvp:
            return self
        expected = PROVINCE_PER_REGIONE.get(self.prvr)
        if expected and self.prvp not in expected:
            raise ValueError("PRVP non coerente con PRVR secondo Lista Province ICCD")
        return self


class SchedaTMABase(BaseModel):
    # CD
    tsk: str = Field(default="TMA", max_length=4)
    lir: LIREnum = LIREnum.inventario
    nctr: str = Field(..., min_length=2, max_length=2)
    nctn: str = Field(..., max_length=8)
    esc: str = Field(..., max_length=25)
    ecp: str = Field(..., max_length=25)

    # OG
    ogtd: str = Field(..., max_length=100)
    ogtm: str = Field(..., max_length=250)

    # LC - PVC
    pvcs: str = Field(default="ITALIA", max_length=50)
    pvcr: str = Field(..., max_length=50)
    pvcp: str = Field(..., max_length=3)
    pvcc: str = Field(..., max_length=50)

    # LDC
    ldct: Optional[str] = Field(None, max_length=100)
    ldcn: Optional[str] = Field(None, max_length=250)
    ldcu: Optional[str] = Field(None, max_length=250)
    ldcs: Optional[str] = Field(None, max_length=500)

    # LA
    altre_localizzazioni: List[LAItem] = Field(default_factory=list)

    # RE / DSC
    scan: Optional[str] = Field(None, max_length=200)
    dscf: Optional[str] = Field(None, max_length=200)
    dsca: Optional[str] = Field(None, max_length=200)
    dsct: Optional[str] = Field(None, max_length=100)
    dscm: Optional[str] = Field(None, max_length=100)
    dscd: Optional[str] = Field(None, max_length=4)
    dscu: Optional[str] = Field(None, max_length=50)
    dscn: Optional[str] = Field(None, max_length=250)

    # DT
    dtzg: str = Field(..., max_length=50)
    dtm: List[str] = Field(..., min_length=1)

    # DA
    nsc: Optional[str] = Field(None, max_length=4000)

    # MA
    materiali: List[MACItem] = Field(..., min_length=1)

    # TU
    cdgg: str = Field(default=CDGG_DEFAULT, max_length=120)

    # DO
    fotografie: List[FTAItem] = Field(default_factory=list)

    # AD
    adsp: ADSPEnum = ADSPEnum.limitato
    adsm: Optional[str] = Field(None, max_length=70)

    # CM
    cmpd: str = Field(..., min_length=4, max_length=4)
    cmpn: List[str] = Field(..., min_length=1)
    fur: List[str] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_validator("tsk", mode="before")
    @classmethod
    def force_tsk(cls, _value: str) -> str:
        return "TMA"

    @field_validator("lir", mode="before")
    @classmethod
    def force_lir(cls, _value) -> str:
        # TMA-3.00_INV_01 supporta il livello Inventario (I) come valore operativo.
        # Manteniamo il vocabolario completo in LIVELLI_RICERCA per riuso cross-scheda.
        _ = LIVELLI_RICERCA
        return LIREnum.inventario.value

    @field_validator("pvcs", mode="before")
    @classmethod
    def normalize_pvcs(cls, value: Optional[str]) -> str:
        normalized = (value or "ITALIA").strip()
        return normalized or "ITALIA"

    @field_validator("nctn", mode="before")
    @classmethod
    def normalize_nctn(cls, value: str) -> str:
        raw = str(value or "").strip()
        if not raw.isdigit():
            raise ValueError("NCTN deve contenere solo cifre")
        if len(raw) > 8:
            raise ValueError("NCTN deve essere al massimo di 8 cifre")
        return raw.zfill(8)

    @field_validator("nctr")
    @classmethod
    def validate_nctr(cls, value: str) -> str:
        raw = (value or "").strip()
        if not raw.isdigit() or len(raw) != 2:
            raise ValueError("NCTR deve essere composto da 2 cifre")
        if raw not in CODICI_REGIONE:
            raise ValueError("NCTR non valido secondo codifica ICCD/ISTAT")
        return raw

    @field_validator("pvcr")
    @classmethod
    def validate_pvcr(cls, value: str) -> str:
        return _normalize_denominazione_regione(value, "PVCR")

    @field_validator("pvcp")
    @classmethod
    def validate_pvcp(cls, value: str) -> str:
        return _normalize_sigla_provincia(value, "PVCP")

    @model_validator(mode="after")
    def validate_pvcr_pvcp_consistency(self) -> "SchedaTMABase":
        expected = PROVINCE_PER_REGIONE.get(self.pvcr)
        if expected and self.pvcp not in expected:
            raise ValueError("PVCP non coerente con PVCR secondo Lista Province ICCD")
        return self

    @field_validator("dscd")
    @classmethod
    def validate_dscd(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        raw = value.strip()
        if not raw.isdigit() or len(raw) != 4:
            raise ValueError("DSCD deve essere un anno a 4 cifre")
        return raw

    @field_validator("cmpd")
    @classmethod
    def validate_cmpd(cls, value: str) -> str:
        raw = (value or "").strip()
        if not raw.isdigit() or len(raw) != 4:
            raise ValueError("CMPD deve essere un anno a 4 cifre")

        year = int(raw)
        current_year = datetime.now().year
        if year < 1900 or year > current_year:
            raise ValueError(f"CMPD deve essere tra 1900 e {current_year}")

        return raw

    @field_validator("dtm")
    @classmethod
    def normalize_dtm(cls, values: List[str]) -> List[str]:
        normalized = [v.strip() for v in values if v and v.strip()]
        if not normalized:
            # Backward compatibility: existing historical records may have empty arrays.
            if cls.__name__ == "SchedaTMARead":
                return []
            raise ValueError("DTM richiede almeno una motivazione")

        invalid = [v for v in normalized if v not in _DTM_MOTIVAZIONI_TMA_EXTENDED_VALORI]
        if invalid:
            raise ValueError(
                "DTM contiene valori non ammessi dal vocabolario chiuso TMA: "
                + ", ".join(invalid)
            )
        return normalized

    @field_validator("cdgg")
    @classmethod
    def validate_cdgg(cls, value: str) -> str:
        return _normalize_cdgg(value, "CDGG")

    @field_validator("cmpn", "fur")
    @classmethod
    def validate_name_list(cls, values: List[str]) -> List[str]:
        normalized = [v.strip() for v in values if v and v.strip()]
        if not normalized:
            # Backward compatibility: allow empty arrays only for read serialization.
            if cls.__name__ == "SchedaTMARead":
                return []
            raise ValueError("La lista non può essere vuota")
        return normalized

    @model_validator(mode="after")
    def normalize_adsp(self) -> "SchedaTMABase":
        if self.adsp is None:
            self.adsp = ADSPEnum.limitato
        return self

    @property
    def nct(self) -> str:
        return f"{self.nctr}{self.nctn}"

    @property
    def ogtm_materiali_warning(self) -> Optional[str]:
        """Warning non bloccante: OGTM dovrebbe riflettere le categorie in MACC."""
        if not self.ogtm or not self.materiali:
            return None

        ogtm_lower = self.ogtm.lower()
        missing = [m.macc for m in self.materiali if m.macc and m.macc.lower() not in ogtm_lower]
        if missing:
            return f"OGTM non include alcune categorie materiali: {', '.join(missing)}"
        return None


class SchedaTMACreate(SchedaTMABase):
    pass


class SchedaTMAUpdate(BaseModel):
    # CD
    tsk: Optional[str] = Field(default=None, max_length=4)
    lir: Optional[LIREnum] = None
    nctr: Optional[str] = Field(default=None, min_length=2, max_length=2)
    nctn: Optional[str] = Field(default=None, max_length=8)
    esc: Optional[str] = Field(default=None, max_length=25)
    ecp: Optional[str] = Field(default=None, max_length=25)

    # OG
    ogtd: Optional[str] = Field(default=None, max_length=100)
    ogtm: Optional[str] = Field(default=None, max_length=250)

    # LC - PVC
    pvcs: Optional[str] = Field(default=None, max_length=50)
    pvcr: Optional[str] = Field(default=None, max_length=50)
    pvcp: Optional[str] = Field(default=None, max_length=3)
    pvcc: Optional[str] = Field(default=None, max_length=50)

    # LDC
    ldct: Optional[str] = Field(None, max_length=100)
    ldcn: Optional[str] = Field(None, max_length=250)
    ldcu: Optional[str] = Field(None, max_length=250)
    ldcs: Optional[str] = Field(None, max_length=500)

    # LA
    altre_localizzazioni: Optional[List[LAItem]] = None

    # RE / DSC
    scan: Optional[str] = Field(None, max_length=200)
    dscf: Optional[str] = Field(None, max_length=200)
    dsca: Optional[str] = Field(None, max_length=200)
    dsct: Optional[str] = Field(None, max_length=100)
    dscm: Optional[str] = Field(None, max_length=100)
    dscd: Optional[str] = Field(None, max_length=4)
    dscu: Optional[str] = Field(None, max_length=50)
    dscn: Optional[str] = Field(None, max_length=250)

    # DT
    dtzg: Optional[str] = Field(None, max_length=50)
    dtm: Optional[List[str]] = None

    # DA
    nsc: Optional[str] = Field(None, max_length=4000)

    # MA
    materiali: Optional[List[MACItem]] = None

    # TU
    cdgg: Optional[str] = Field(None, max_length=120)

    # DO
    fotografie: Optional[List[FTAItem]] = None

    # AD
    adsp: Optional[ADSPEnum] = None
    adsm: Optional[str] = Field(None, max_length=70)

    # CM
    cmpd: Optional[str] = Field(None, min_length=4, max_length=4)
    cmpn: Optional[List[str]] = None
    fur: Optional[List[str]] = None

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_validator("pvcr")
    @classmethod
    def validate_pvcr(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        return _normalize_denominazione_regione(value, "PVCR")

    @field_validator("pvcp")
    @classmethod
    def validate_pvcp(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        return _normalize_sigla_provincia(value, "PVCP")

    @field_validator("dtm")
    @classmethod
    def validate_dtm(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        if values is None:
            return values
        normalized = [v.strip() for v in values if v and v.strip()]
        invalid = [v for v in normalized if v not in _DTM_MOTIVAZIONI_TMA_EXTENDED_VALORI]
        if invalid:
            raise ValueError(
                "DTM contiene valori non ammessi dal vocabolario chiuso TMA: "
                + ", ".join(invalid)
            )
        return normalized

    @field_validator("cdgg")
    @classmethod
    def validate_cdgg(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        return _normalize_cdgg(value, "CDGG")


class MACItemRead(MACItem):
    id: int
    ordine: int

    model_config = ConfigDict(from_attributes=True)


class FTAItemRead(FTAItem):
    id: int
    ordine: int

    model_config = ConfigDict(from_attributes=True)


class SchedaTMARead(SchedaTMABase):
    id: str
    site_id: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    materiali: List[MACItemRead] = Field(default_factory=list)
    fotografie: List[FTAItemRead] = Field(default_factory=list)
    dtm: List[str] = Field(default_factory=list)
    cmpn: List[str] = Field(default_factory=list)
    fur: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# Backward-compatible aliases used by existing imports/routes.
TMACreate = SchedaTMACreate
TMAUpdate = SchedaTMAUpdate
TMAOut = SchedaTMARead

