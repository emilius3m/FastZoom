"""
Pydantic Schemas per Photo Metadata API
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID


class LocationMetadata(BaseModel):
    """Localizzazione foto"""
    area: Optional[str] = None
    sector: Optional[str] = None
    coordinates: Optional[str] = None


class TechnicalData(BaseModel):
    """Dati tecnici ripresa"""
    camera: Optional[str] = None
    lens: Optional[str] = None
    focal_length: Optional[float] = None
    aperture: Optional[str] = None
    iso: Optional[int] = None
    shutter_speed: Optional[str] = None


class PhotoMetadataBase(BaseModel):
    """Schema base metadati foto"""
    title: str = Field(..., min_length=1, max_length=250)
    description: str = Field(..., min_length=10)
    archaeological_context: Optional[str] = Field(None, max_length=500)
    chronology: Optional[str] = None
    subject_type: str = Field(..., description="Tipo soggetto fotografato")
    stratigraphic_unit: Optional[str] = None
    material: Optional[str] = None
    conservation_state: Optional[str] = None
    photographer: Optional[str] = None
    shoot_date: Optional[date] = None
    location: Optional[LocationMetadata] = None
    technical_data: Optional[TechnicalData] = None
    keywords: Optional[List[str]] = Field(default=[], max_items=20)
    copyright: Optional[str] = None
    license: Optional[str] = None
    visibility: str = Field(default='team', pattern='^(public|team|private)$')
    featured: bool = False

    @validator('subject_type')
    def validate_subject_type(cls, v):
        allowed = ['reperto', 'struttura', 'scavo', 'ambiente', 'dettaglio', 'ricostruzione']
        if v not in allowed:
            raise ValueError(f'subject_type deve essere uno di: {", ".join(allowed)}')
        return v

    @validator('conservation_state')
    def validate_conservation_state(cls, v):
        if v is None:
            return v
        allowed = ['ottimo', 'buono', 'discreto', 'mediocre', 'cattivo']
        if v not in allowed:
            raise ValueError(f'conservation_state deve essere uno di: {", ".join(allowed)}')
        return v

    class Config:
        from_attributes = True


class PhotoMetadataCreate(PhotoMetadataBase):
    """Schema creazione metadati"""
    pass


class PhotoMetadataUpdate(BaseModel):
    """Schema aggiornamento metadati (campi opzionali)"""
    title: Optional[str] = Field(None, min_length=1, max_length=250)
    description: Optional[str] = Field(None, min_length=10)
    archaeological_context: Optional[str] = Field(None, max_length=500)
    chronology: Optional[str] = None
    subject_type: Optional[str] = None
    stratigraphic_unit: Optional[str] = None
    material: Optional[str] = None
    conservation_state: Optional[str] = None
    photographer: Optional[str] = None
    shoot_date: Optional[date] = None
    location: Optional[LocationMetadata] = None
    technical_data: Optional[TechnicalData] = None
    keywords: Optional[List[str]] = Field(None, max_items=20)
    copyright: Optional[str] = None
    license: Optional[str] = None
    visibility: Optional[str] = Field(None, pattern='^(public|team|private)$')
    featured: Optional[bool] = None


class PhotoResponse(BaseModel):
    """Schema risposta foto"""
    id: UUID
    filename: str
    original_filename: str
    file_path: str
    file_size: Optional[int]
    width: Optional[int]
    height: Optional[int]
    mime_type: Optional[str]

    # Metadati
    metadata: Dict[str, Any]

    # Status
    visibility: str
    featured: bool
    has_deep_zoom: bool

    # Relations
    site_id: UUID
    uploaded_by: UUID

    # Timestamp
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class PhotoMetadataResponse(BaseModel):
    """Risposta solo metadati"""
    photo_id: UUID
    metadata: PhotoMetadataBase
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class BulkMetadataUpdate(BaseModel):
    """Aggiornamento bulk metadati"""
    photo_ids: List[UUID] = Field(..., min_items=1, max_items=100)
    metadata: PhotoMetadataUpdate


class BulkMetadataResponse(BaseModel):
    """Risposta operazione bulk"""
    total_requested: int
    successful: int
    failed: int
    errors: List[Dict[str, str]]
    updated_ids: List[UUID]
