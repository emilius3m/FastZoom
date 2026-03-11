from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TMAMaterialItem(BaseModel):
    macc: str = Field(..., min_length=1, max_length=100)
    macq: str = Field(..., min_length=1, max_length=100)
    macl: Optional[str] = Field(default=None, max_length=100)
    macd: Optional[str] = Field(default=None, max_length=100)
    macp: Optional[str] = Field(default=None, max_length=100)
    mas: Optional[str] = Field(default=None, max_length=250)


class TMALDCCollocazione(BaseModel):
    ldct: Optional[str] = Field(default=None, max_length=100)
    ldcn: Optional[str] = Field(default=None, max_length=200)
    ldcu: Optional[str] = Field(default=None, max_length=200)
    ldcs: Optional[str] = Field(default=None, max_length=250)


class TMAProvenienzaItem(BaseModel):
    tcl: Optional[str] = Field(default=None, max_length=100)
    prvs: Optional[str] = Field(default=None, max_length=50)
    prvr: Optional[str] = Field(default=None, max_length=50)
    prvp: Optional[str] = Field(default=None, max_length=3)
    prvc: Optional[str] = Field(default=None, max_length=50)
    prcu: Optional[str] = Field(default=None, max_length=200)


class TMADatiScavo(BaseModel):
    scan: Optional[str] = Field(default=None, max_length=200)
    dscf: Optional[str] = Field(default=None, max_length=200)
    dsca: Optional[str] = Field(default=None, max_length=200)
    dsct: Optional[str] = Field(default=None, max_length=100)
    dscm: Optional[str] = Field(default=None, max_length=100)
    dscd: Optional[str] = Field(default=None, max_length=4)
    dscu: Optional[str] = Field(default=None, max_length=50)
    dscn: Optional[str] = Field(default=None, max_length=250)


class TMAFotoRiferimento(BaseModel):
    ftax: Optional[str] = Field(default=None, max_length=100)
    ftap: Optional[str] = Field(default=None, max_length=100)
    ftan: Optional[str] = Field(default=None, max_length=200)


class TMAEntitaMultimediale(BaseModel):
    ftap: Optional[str] = Field(default=None, max_length=100)
    ftan: Optional[str] = Field(default=None, max_length=200)
    mmto: Optional[str] = Field(default=None, max_length=300)


class TMABase(BaseModel):
    site_id: UUID

    # CD
    tsk: str = Field(default="TMA", min_length=3, max_length=4)
    lir: str = Field(default="I", min_length=1, max_length=5)
    nctr: str = Field(..., pattern=r"^\d{2}$")
    nctn: str = Field(..., pattern=r"^\d{8}$")
    esc: str = Field(..., min_length=1, max_length=25)
    ecp: str = Field(..., min_length=1, max_length=25)

    # OG
    ogtd: str = Field(..., min_length=1, max_length=100)
    ogtm: str = Field(..., min_length=1, max_length=250)

    # LC
    pvcs: str = Field(..., min_length=1, max_length=50)
    pvcr: str = Field(..., min_length=1, max_length=25)
    pvcp: str = Field(..., min_length=1, max_length=3)
    pvcc: str = Field(..., min_length=1, max_length=50)

    # DT
    dtzg: str = Field(..., min_length=1, max_length=50)
    dtm: List[str] = Field(default_factory=list, min_length=1)

    # MA
    macc: str = Field(..., min_length=1, max_length=100)
    macq: str = Field(..., min_length=1, max_length=100)
    ma_items: List[TMAMaterialItem] = Field(default_factory=list)

    # TU
    cdgg: str = Field(..., min_length=1, max_length=50)

    # AD
    adsp: str = Field(default="2", min_length=1, max_length=1)
    adsm: str = Field(..., min_length=1, max_length=70)

    # CM
    cmpd: str = Field(..., pattern=r"^\d{4}$")
    cmpn: List[str] = Field(default_factory=list, min_length=1)
    fur: List[str] = Field(default_factory=list, min_length=1)

    # Extra sections from extended TMA output example
    ldc: Optional[TMALDCCollocazione] = None
    provenienze: List[TMAProvenienzaItem] = Field(default_factory=list)
    scavo: Optional[TMADatiScavo] = None
    nsc: Optional[str] = Field(default=None, max_length=5000)
    fta: List[TMAFotoRiferimento] = Field(default_factory=list)
    entita_multimediali: List[TMAEntitaMultimediale] = Field(default_factory=list)

    notes: Optional[str] = None

    @field_validator("adsp")
    @classmethod
    def validate_adsp(cls, value: str) -> str:
        if value not in {"1", "2"}:
            raise ValueError("ADSP deve essere '1' o '2'")
        return value


class TMACreate(TMABase):
    pass


class TMAUpdate(BaseModel):
    # CD
    tsk: Optional[str] = Field(default=None, min_length=3, max_length=4)
    lir: Optional[str] = Field(default=None, min_length=1, max_length=5)
    nctr: Optional[str] = Field(default=None, pattern=r"^\d{2}$")
    nctn: Optional[str] = Field(default=None, pattern=r"^\d{8}$")
    esc: Optional[str] = Field(default=None, min_length=1, max_length=25)
    ecp: Optional[str] = Field(default=None, min_length=1, max_length=25)

    # OG
    ogtd: Optional[str] = Field(default=None, min_length=1, max_length=100)
    ogtm: Optional[str] = Field(default=None, min_length=1, max_length=250)

    # LC
    pvcs: Optional[str] = Field(default=None, min_length=1, max_length=50)
    pvcr: Optional[str] = Field(default=None, min_length=1, max_length=25)
    pvcp: Optional[str] = Field(default=None, min_length=1, max_length=3)
    pvcc: Optional[str] = Field(default=None, min_length=1, max_length=50)

    # DT
    dtzg: Optional[str] = Field(default=None, min_length=1, max_length=50)
    dtm: Optional[List[str]] = None

    # MA
    macc: Optional[str] = Field(default=None, min_length=1, max_length=100)
    macq: Optional[str] = Field(default=None, min_length=1, max_length=100)
    ma_items: Optional[List[TMAMaterialItem]] = None

    # TU
    cdgg: Optional[str] = Field(default=None, min_length=1, max_length=50)

    # AD
    adsp: Optional[str] = Field(default=None, min_length=1, max_length=1)
    adsm: Optional[str] = Field(default=None, min_length=1, max_length=70)

    # CM
    cmpd: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    cmpn: Optional[List[str]] = None
    fur: Optional[List[str]] = None

    # Extra sections from extended TMA output example
    ldc: Optional[TMALDCCollocazione] = None
    provenienze: Optional[List[TMAProvenienzaItem]] = None
    scavo: Optional[TMADatiScavo] = None
    nsc: Optional[str] = Field(default=None, max_length=5000)
    fta: Optional[List[TMAFotoRiferimento]] = None
    entita_multimediali: Optional[List[TMAEntitaMultimediale]] = None

    notes: Optional[str] = None

    @field_validator("adsp")
    @classmethod
    def validate_adsp(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in {"1", "2"}:
            raise ValueError("ADSP deve essere '1' o '2'")
        return value


class TMAOut(TMABase):
    id: UUID
    nct: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

