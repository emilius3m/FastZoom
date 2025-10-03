"""
Pydantic Schemas per API ICCD
Validazione e serializzazione dati schede ICCD
"""

from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class SchemaType(str, Enum):
    """Tipi di schede ICCD supportate"""
    SI = "SI"  # Siti Archeologici
    RA = "RA"  # Reperti Archeologici
    CA = "CA"  # Complessi Archeologici
    MA = "MA"  # Monumenti Archeologici
    NU = "NU"  # Numismatica
    TMA = "TMA"  # Tabula Peutingeriana


class RecordStatus(str, Enum):
    """Stati possibili di una scheda"""
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class LevelType(str, Enum):
    """Livelli di ricerca ICCD"""
    P = "P"  # Precatalogazione
    I = "I"  # Inventario
    C = "C"  # Catalogazione
    A = "A"  # Approfondimento


class AccessProfile(str, Enum):
    """Profili di accesso ai dati"""
    PUBLIC = "1"  # Libero
    RESTRICTED_ENTITIES = "2"  # Riservato enti
    RESTRICTED = "3"  # Riservato


# ============================================================================
# BASE MODELS
# ============================================================================

class ICCDBaseModel(BaseModel):
    """Base model con configurazione comune"""

    class Config:
        from_attributes = True
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# ============================================================================
# NCT (CODICE UNIVOCO) MODELS
# ============================================================================

class NCTCreate(ICCDBaseModel):
    """Schema per creazione NCT"""
    NCTR: str = Field(..., pattern="^[0-9]{2}$", description="Codice regione ISTAT")
    NCTN: Optional[str] = Field(None, pattern="^[0-9]{8}$", description="Numero catalogo (auto-generato)")
    NCTS: Optional[str] = Field(None, pattern="^[A-Z]{0,2}$", description="Suffisso opzionale")


class NCTResponse(ICCDBaseModel):
    """Schema risposta NCT"""
    NCTR: str
    NCTN: str
    NCTS: Optional[str]
    nct_complete: str = Field(..., description="NCT completo (NCTR+NCTN+NCTS)")


# ============================================================================
# RECORD MODELS
# ============================================================================

class ICCDRecordBase(ICCDBaseModel):
    """Schema base per record ICCD"""
    schema_type: SchemaType
    site_id: UUID
    record_data: Dict[str, Any]


class ICCDRecordCreate(ICCDRecordBase):
    """Schema per creazione record ICCD"""
    level: LevelType = LevelType.C

    @root_validator
    def validate_record_data(cls, values):
        """Valida struttura base dati"""
        record_data = values.get('record_data', {})

        # Verifica presenza paragrafo CD
        if 'CD' not in record_data:
            raise ValueError('Paragrafo CD obbligatorio')

        # Verifica NCT
        cd = record_data['CD']
        if 'NCT' not in cd:
            raise ValueError('NCT obbligatorio in paragrafo CD')

        return values


class ICCDRecordUpdate(ICCDBaseModel):
    """Schema per aggiornamento record"""
    record_data: Optional[Dict[str, Any]] = None
    status: Optional[RecordStatus] = None
    is_public: Optional[bool] = None

    @validator('record_data')
    def validate_not_empty(cls, v):
        if v is not None and not v:
            raise ValueError('record_data non può essere vuoto')
        return v


class ICCDRecordResponse(ICCDBaseModel):
    """Schema risposta base record"""
    id: UUID
    nct_complete: str
    schema_type: SchemaType
    schema_version: str
    level: LevelType
    site_id: UUID

    # Campi estratti
    object_definition: Optional[str]
    object_name: Optional[str]
    chronology_generic: Optional[str]
    chronology_from: Optional[int]
    chronology_to: Optional[int]

    # Localizzazione
    region: Optional[str]
    province: Optional[str]
    municipality: Optional[str]

    # Coordinate
    latitude: Optional[float]
    longitude: Optional[float]

    # Stato
    status: RecordStatus
    validation_status: str
    is_public: bool

    # Timestamp
    created_at: datetime
    updated_at: Optional[datetime]
    validated_at: Optional[datetime]

    # Creator
    created_by: UUID


class ICCDRecordDetail(ICCDRecordResponse):
    """Schema risposta dettagliata con dati completi"""
    record_data: Dict[str, Any]

    # Relazioni
    parent_id: Optional[UUID]

    # Validatore
    validated_by: Optional[UUID]


class ICCDRecordList(ICCDBaseModel):
    """Schema lista paginata"""
    items: List[ICCDRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# SEARCH & FILTER MODELS
# ============================================================================

class ICCDSearchFilters(ICCDBaseModel):
    """Filtri avanzati per ricerca ICCD"""

    # Filtri base
    schema_type: Optional[SchemaType] = None
    site_id: Optional[UUID] = None
    status: Optional[RecordStatus] = None
    level: Optional[LevelType] = None
    is_public: Optional[bool] = None

    # Ricerca testuale
    search: Optional[str] = Field(None, description="Ricerca full-text")
    object_definition: Optional[str] = None
    object_name: Optional[str] = None

    # Filtri cronologici
    chronology_generic: Optional[str] = None
    chronology_from: Optional[int] = Field(None, ge=-10000, le=3000)
    chronology_to: Optional[int] = Field(None, ge=-10000, le=3000)
    date_range_overlap: bool = Field(True, description="Trova sovrapposizioni temporali")

    # Filtri geografici
    region: Optional[str] = None
    province: Optional[str] = None
    municipality: Optional[str] = None

    # Filtri coordinate (bounding box)
    bbox_min_lat: Optional[float] = Field(None, ge=-90, le=90)
    bbox_min_lon: Optional[float] = Field(None, ge=-180, le=180)
    bbox_max_lat: Optional[float] = Field(None, ge=-90, le=90)
    bbox_max_lon: Optional[float] = Field(None, ge=-180, le=180)

    # Filtri avanzati JSON
    json_path: Optional[str] = Field(None, description="JSON path per filtro custom")
    json_value: Optional[str] = Field(None, description="Valore da cercare nel JSON path")

    # Ordinamento
    sort_by: Optional[str] = Field("created_at", description="Campo per ordinamento")
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")

    # Paginazione
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)

    @root_validator
    def validate_bbox(cls, values):
        """Valida bounding box"""
        bbox_fields = ['bbox_min_lat', 'bbox_min_lon', 'bbox_max_lat', 'bbox_max_lon']
        bbox_values = [values.get(f) for f in bbox_fields]

        # Se un campo bbox è presente, tutti devono esserlo
        if any(v is not None for v in bbox_values):
            if not all(v is not None for v in bbox_values):
                raise ValueError('Tutti i campi bbox devono essere specificati insieme')

            # Valida coordinate
            if values['bbox_min_lat'] >= values['bbox_max_lat']:
                raise ValueError('bbox_min_lat deve essere < bbox_max_lat')
            if values['bbox_min_lon'] >= values['bbox_max_lon']:
                raise ValueError('bbox_min_lon deve essere < bbox_max_lon')

        return values

    @root_validator
    def validate_chronology(cls, values):
        """Valida range cronologico"""
        from_year = values.get('chronology_from')
        to_year = values.get('chronology_to')

        if from_year is not None and to_year is not None:
            if from_year > to_year:
                raise ValueError('chronology_from deve essere <= chronology_to')

        return values


class ICCDFacets(ICCDBaseModel):
    """Facets per ricerca aggregata"""
    field: str = Field(..., description="Campo da aggregare")
    limit: int = Field(10, ge=1, le=100, description="Numero max risultati")


class ICCDSearchResult(ICCDBaseModel):
    """Risultato ricerca avanzata"""
    records: List[ICCDRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int

    # Aggregazioni
    facets: Optional[Dict[str, List[Dict[str, Any]]]] = None

    # Statistiche
    statistics: Optional[Dict[str, Any]] = None


# ============================================================================
# VALIDATION MODELS
# ============================================================================

class ValidationError(ICCDBaseModel):
    """Singolo errore di validazione"""
    field: str
    message: str
    severity: str = Field(..., pattern="^(error|warning|info)$")


class ICCDValidationResult(ICCDBaseModel):
    """Risultato validazione scheda"""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]

    # Metriche completezza
    completeness_percentage: float = Field(..., ge=0, le=100)
    required_fields_total: int
    required_fields_filled: int
    optional_fields_total: int
    optional_fields_filled: int

    # Campi mancanti
    missing_required: List[str]
    missing_optional: List[str]

    # Suggerimenti
    suggestions: Optional[List[str]] = None


# ============================================================================
# RELATION MODELS - RIMOSSI: LE RELAZIONI SONO GESTITE TRAMITE PARENT_ID
# ============================================================================
# Le relazioni tra schede ICCD sono ora gestite direttamente tramite il campo
# parent_id in ICCDBaseRecord, seguendo la gerarchia ICCD standard.

# ============================================================================
# MEDIA MODELS
# ============================================================================

class ICCDMediaType(str, Enum):
    """Tipi di media ICCD"""
    PHOTO = "photo"
    DRAWING = "drawing"
    DOCUMENT = "document"
    VIDEO = "video"
    MODEL_3D = "3d_model"


class ICCDMediaCreate(ICCDBaseModel):
    """Schema per associazione media"""
    record_id: UUID
    media_type: ICCDMediaType
    media_code: Optional[str] = None
    file_path: str
    display_order: int = 0


class ICCDMediaResponse(ICCDBaseModel):
    """Schema risposta media"""
    id: UUID
    record_id: UUID
    media_type: ICCDMediaType
    media_code: Optional[str]
    file_path: str
    file_name: str
    file_size: Optional[int]
    mime_type: Optional[str]
    width: Optional[int]
    height: Optional[int]
    display_order: int
    created_at: datetime


# ============================================================================
# EXPORT MODELS
# ============================================================================

class ExportFormat(str, Enum):
    """Formati di export supportati"""
    PDF = "pdf"
    JSON = "json"
    XML = "xml"
    CSV = "csv"


class ICCDExportRequest(ICCDBaseModel):
    """Richiesta export schede"""
    record_ids: List[UUID] = Field(..., min_items=1, max_items=100)
    format: ExportFormat
    include_media: bool = False
    include_relations: bool = False


# ============================================================================
# STATISTICS MODELS
# ============================================================================

class ICCDStatistics(ICCDBaseModel):
    """Statistiche generali ICCD"""
    total_records: int
    records_by_type: Dict[str, int]
    records_by_status: Dict[str, int]
    records_by_region: Dict[str, int]

    # Cronologia
    earliest_date: Optional[int]
    latest_date: Optional[int]
    chronology_distribution: Dict[str, int]

    # Completezza media
    avg_completeness: float

    # Ultimo aggiornamento
    last_update: datetime


class SiteICCDStatistics(ICCDBaseModel):
    """Statistiche ICCD per singolo sito"""
    site_id: UUID
    site_name: str

    total_records: int
    records_by_type: Dict[str, int]
    records_published: int
    records_draft: int

    avg_completeness: float
    last_update: Optional[datetime]


# ============================================================================
# BULK OPERATIONS
# ============================================================================

class BulkOperation(str, Enum):
    """Operazioni bulk supportate"""
    PUBLISH = "publish"
    ARCHIVE = "archive"
    DELETE = "delete"
    UPDATE_STATUS = "update_status"


class ICCDBulkRequest(ICCDBaseModel):
    """Richiesta operazione bulk"""
    record_ids: List[UUID] = Field(..., min_items=1, max_items=100)
    operation: BulkOperation
    parameters: Optional[Dict[str, Any]] = None


class ICCDBulkResult(ICCDBaseModel):
    """Risultato operazione bulk"""
    total_requested: int
    successful: int
    failed: int
    errors: List[Dict[str, str]]
    processed_ids: List[UUID]
