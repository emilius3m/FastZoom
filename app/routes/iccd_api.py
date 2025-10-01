"""
API FastAPI per gestione schede ICCD
Sistema FastZoom - Modulo ICCD

Endpoints:
- GET /api/iccd/schemas/{schema_type} - Recupera schema
- POST /api/iccd/records - Crea nuova scheda
- GET /api/iccd/records - Lista schede con filtri
- GET /api/iccd/records/{record_id} - Dettaglio scheda
- PUT /api/iccd/records/{record_id} - Aggiorna scheda
- DELETE /api/iccd/records/{record_id} - Elimina scheda
- POST /api/iccd/records/{record_id}/validate - Valida scheda
- POST /api/iccd/records/{record_id}/publish - Pubblica scheda
- GET /api/iccd/sites/{site_id}/records - Schede per sito
- GET /api/iccd/export/{record_id}/pdf - Esporta PDF
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
import jsonschema
import io

from app.database import get_db
from app.models.iccd_models import ICCDRecord, ICCDRelation, ICCDMedia
from app.models.auth import User
from app.auth.dependencies import get_current_user, require_permissions
from app.data.iccd_si_schema_complete import SCHEMA_SI_300, validate_si_record
from app.data.iccd_ra_schema_complete import SCHEMA_RA_300, validate_ra_record
from app.data.iccd_ca_schema_complete import SCHEMA_CA_300, validate_ca_record
from pydantic import BaseModel, Field, validator

# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(
    prefix="/api/iccd",
    tags=["ICCD"],
    responses={404: {"description": "Not found"}}
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ICCDRecordCreate(BaseModel):
    """Schema per creazione record ICCD"""
    schema_type: str = Field(..., description="Tipo scheda (SI, RA, CA, MA)")
    site_id: UUID = Field(..., description="ID sito archeologico")
    record_data: Dict[str, Any] = Field(..., description="Dati scheda ICCD completi")

    @validator('schema_type')
    def validate_schema_type(cls, v):
        allowed = ['SI', 'RA', 'CA', 'MA', 'NU', 'TMA']
        if v.upper() not in allowed:
            raise ValueError(f'schema_type deve essere uno di: {", ".join(allowed)}')
        return v.upper()


class ICCDRecordUpdate(BaseModel):
    """Schema per aggiornamento record ICCD"""
    record_data: Dict[str, Any]
    status: Optional[str] = None

    @validator('status')
    def validate_status(cls, v):
        if v is not None:
            allowed = ['draft', 'validated', 'published', 'archived']
            if v not in allowed:
                raise ValueError(f'status deve essere uno di: {", ".join(allowed)}')
        return v


class ICCDRecordResponse(BaseModel):
    """Schema risposta record ICCD"""
    id: UUID
    nct_complete: str
    schema_type: str
    schema_version: str
    level: str
    site_id: UUID
    object_definition: Optional[str]
    object_name: Optional[str]
    status: str
    is_public: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ICCDRecordDetail(ICCDRecordResponse):
    """Schema dettaglio completo record ICCD"""
    record_data: Dict[str, Any]
    chronology_generic: Optional[str]
    chronology_from: Optional[int]
    chronology_to: Optional[int]
    region: Optional[str]
    province: Optional[str]
    municipality: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]


class ICCDValidationRequest(BaseModel):
    """Richiesta validazione scheda ICCD"""
    schema_type: str = Field(..., description="Tipo scheda (SI, RA, CA)")
    level: str = Field(..., description="Livello catalogazione (P, C, A)")
    iccd_data: Dict[str, Any] = Field(..., description="Dati scheda ICCD")


class ICCDValidationResult(BaseModel):
    """Risultato validazione scheda"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    completeness: float
    required_fields_missing: List[str]


# ============================================================================
# SCHEMA ENDPOINTS
# ============================================================================

@router.get("/schemas/{schema_type}", response_model=Dict[str, Any])
async def get_schema(
        schema_type: str = Path(..., description="Tipo schema ICCD")
):
    """
    Recupera lo schema JSON per un tipo di scheda ICCD

    Parametri:
    - schema_type: SI, RA, CA, MA, etc.

    Returns:
        JSON Schema completo con UI Schema
    """
    schema_type = schema_type.upper()

    # Schemi supportati
    if schema_type == "SI":
        return SCHEMA_SI_300
    elif schema_type == "RA":
        return SCHEMA_RA_300
    elif schema_type == "CA":
        return SCHEMA_CA_300

    # Altri schemi da implementare
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Schema {schema_type} non ancora implementato"
    )


@router.get("/schemas", response_model=List[Dict[str, str]])
async def list_schemas():
    """Lista tutti gli schemi ICCD disponibili"""
    return [
        {
            "id": "SI",
            "name": "Siti Archeologici",
            "version": "3.00",
            "status": "implemented"
        },
        {
            "id": "RA",
            "name": "Reperti Archeologici",
            "version": "3.00",
            "status": "implemented"
        },
        {
            "id": "CA",
            "name": "Complessi Archeologici",
            "version": "3.00",
            "status": "implemented"
        },
        {
            "id": "MA",
            "name": "Monumenti Archeologici",
            "version": "3.00",
            "status": "planned"
        }
    ]


# ============================================================================
# RECORD CRUD ENDPOINTS
# ============================================================================

@router.post("/records", response_model=ICCDRecordDetail, status_code=status.HTTP_201_CREATED)
async def create_record(
        record_data: ICCDRecordCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Crea una nuova scheda ICCD

    Validazione automatica dei dati secondo schema
    Generazione automatica NCT
    """
    # Valida dati contro schema
    if record_data.schema_type == "SI":
        is_valid, errors = validate_si_record(record_data.record_data)
    elif record_data.schema_type == "RA":
        is_valid, errors = validate_ra_record(record_data.record_data)
    elif record_data.schema_type == "CA":
        is_valid, errors = validate_ca_record(record_data.record_data)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Schema {record_data.schema_type} non ancora implementato"
        )
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Dati non validi", "errors": errors}
        )

    # Genera NCT
    nct_region = record_data.record_data.get('CD', {}).get('NCT', {}).get('NCTR', '12')
    nct_number = _generate_nct_number()

    # Estrai campi per query rapide
    extracted_fields = _extract_fields_from_data(record_data.record_data)

    # Crea record
    new_record = ICCDRecord(
        schema_type=record_data.schema_type,
        schema_version="3.00",
        level=record_data.record_data.get('CD', {}).get('LIR', 'C'),
        nct_region=nct_region,
        nct_number=nct_number,
        nct_suffix=record_data.record_data.get('CD', {}).get('NCT', {}).get('NCTS'),
        site_id=record_data.site_id,
        record_data=record_data.record_data,
        created_by=current_user.id,
        status='draft',
        **extracted_fields
    )

    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return new_record


@router.get("/records", response_model=List[ICCDRecordResponse])
async def list_records(
        schema_type: Optional[str] = Query(None, description="Filtra per tipo scheda"),
        site_id: Optional[UUID] = Query(None, description="Filtra per sito"),
        status: Optional[str] = Query(None, description="Filtra per stato"),
        search: Optional[str] = Query(None, description="Ricerca full-text"),
        chronology_from: Optional[int] = Query(None, description="Filtra cronologia da"),
        chronology_to: Optional[int] = Query(None, description="Filtra cronologia a"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Lista schede ICCD con filtri avanzati

    Supporta:
    - Filtro per tipo scheda
    - Filtro per sito
    - Filtro per stato
    - Ricerca full-text
    - Filtro cronologico
    - Paginazione
    """
    query = db.query(ICCDRecord).filter(ICCDRecord.deleted_at.is_(None))

    # Applica filtri
    if schema_type:
        query = query.filter(ICCDRecord.schema_type == schema_type.upper())

    if site_id:
        query = query.filter(ICCDRecord.site_id == site_id)

    if status:
        query = query.filter(ICCDRecord.status == status)

    if search:
        # Full-text search su campi indicizzati
        search_filter = or_(
            ICCDRecord.object_definition.ilike(f'%{search}%'),
            ICCDRecord.object_name.ilike(f'%{search}%'),
            ICCDRecord.municipality.ilike(f'%{search}%')
        )
        query = query.filter(search_filter)

    if chronology_from is not None:
        query = query.filter(ICCDRecord.chronology_to >= chronology_from)

    if chronology_to is not None:
        query = query.filter(ICCDRecord.chronology_from <= chronology_to)

    # Ordinamento e paginazione
    total = query.count()
    records = query.order_by(ICCDRecord.created_at.desc()).offset(skip).limit(limit).all()

    return records


@router.get("/records/{record_id}", response_model=ICCDRecordDetail)
async def get_record(
        record_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Recupera dettaglio completo di una scheda ICCD"""
    record = db.query(ICCDRecord).filter(
        ICCDRecord.id == record_id,
        ICCDRecord.deleted_at.is_(None)
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheda ICCD non trovata"
        )

    return record


@router.put("/records/{record_id}", response_model=ICCDRecordDetail)
async def update_record(
        record_id: UUID,
        update_data: ICCDRecordUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Aggiorna una scheda ICCD esistente

    Validazione automatica dei dati
    Aggiornamento campi estratti per performance
    """
    record = db.query(ICCDRecord).filter(
        ICCDRecord.id == record_id,
        ICCDRecord.deleted_at.is_(None)
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheda ICCD non trovata"
        )

    # Valida nuovi dati
    if record.schema_type == "SI":
        is_valid, errors = validate_si_record(update_data.record_data)
    elif record.schema_type == "RA":
        is_valid, errors = validate_ra_record(update_data.record_data)
    elif record.schema_type == "CA":
        is_valid, errors = validate_ca_record(update_data.record_data)
    else:
        is_valid, errors = True, []
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Dati non validi", "errors": errors}
        )

    # Aggiorna dati
    record.record_data = update_data.record_data

    if update_data.status:
        record.status = update_data.status

    # Rigenera campi estratti
    extracted_fields = _extract_fields_from_data(update_data.record_data)
    for key, value in extracted_fields.items():
        setattr(record, key, value)

    record.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(record)

    return record


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
        record_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Elimina (soft delete) una scheda ICCD

    Implementa soft delete per preservare dati
    """
    record = db.query(ICCDRecord).filter(
        ICCDRecord.id == record_id,
        ICCDRecord.deleted_at.is_(None)
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheda ICCD non trovata"
        )

    # Soft delete
    record.deleted_at = datetime.utcnow()
    db.commit()

    return None


# ============================================================================
# VALIDATION & WORKFLOW ENDPOINTS
# ============================================================================

@router.post("/validate", response_model=ICCDValidationResult)
async def validate_iccd_data(
        validation_request: ICCDValidationRequest
):
    """
    Valida dati ICCD contro lo schema senza salvare

    Permette validazione preliminare dei dati prima del salvataggio
    """
    # Valida schema_type
    schema_type = validation_request.schema_type.upper()
    if schema_type not in ['SI', 'RA', 'CA']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo schema '{validation_request.schema_type}' non supportato"
        )

    # Valida level
    if validation_request.level not in ['P', 'C', 'A']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Livello '{validation_request.level}' non valido"
        )

    # Valida contro schema appropriato
    if schema_type == "SI":
        is_valid, errors = validate_si_record(validation_request.iccd_data)
        schema = SCHEMA_SI_300
    elif schema_type == "RA":
        is_valid, errors = validate_ra_record(validation_request.iccd_data)
        schema = SCHEMA_RA_300
    elif schema_type == "CA":
        is_valid, errors = validate_ca_record(validation_request.iccd_data)
        schema = SCHEMA_CA_300
    else:
        is_valid, errors = True, []
        schema = {}

    # Calcola completezza
    completeness = _calculate_completeness(validation_request.iccd_data, schema)

    # Identifica campi obbligatori mancanti
    missing_required = _find_missing_required_fields(validation_request.iccd_data, schema)

    return ICCDValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=[],
        completeness=completeness,
        required_fields_missing=missing_required
    )


@router.post("/records/{record_id}/validate", response_model=ICCDValidationResult)
async def validate_record(
        record_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Valida una scheda ICCD contro lo schema

    Returns:
        Risultato validazione dettagliato con errori e warning
    """
    record = db.query(ICCDRecord).filter(
        ICCDRecord.id == record_id,
        ICCDRecord.deleted_at.is_(None)
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheda ICCD non trovata"
        )

    # Valida
    if record.schema_type == "SI":
        is_valid, errors = validate_si_record(record.record_data)
    elif record.schema_type == "RA":
        is_valid, errors = validate_ra_record(record.record_data)
    elif record.schema_type == "CA":
        is_valid, errors = validate_ca_record(record.record_data)
    else:
        is_valid, errors = True, []

    # Calcola completezza
    if record.schema_type == "SI":
        schema = SCHEMA_SI_300
    elif record.schema_type == "RA":
        schema = SCHEMA_RA_300
    elif record.schema_type == "CA":
        schema = SCHEMA_CA_300
    else:
        schema = {}
    completeness = _calculate_completeness(record.record_data, schema)

    # Identifica campi obbligatori mancanti
    missing_required = _find_missing_required_fields(record.record_data, schema)

    return ICCDValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=[],
        completeness=completeness,
        required_fields_missing=missing_required
    )


@router.post("/records/{record_id}/publish", response_model=ICCDRecordDetail)
async def publish_record(
        record_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Pubblica una scheda ICCD

    Richiede validazione completa
    Cambia stato a 'published' e is_public=True
    """
    record = db.query(ICCDRecord).filter(
        ICCDRecord.id == record_id,
        ICCDRecord.deleted_at.is_(None)
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheda ICCD non trovata"
        )

    # Valida prima di pubblicare
    if record.schema_type == "SI":
        is_valid, errors = validate_si_record(record.record_data)
    elif record.schema_type == "RA":
        is_valid, errors = validate_ra_record(record.record_data)
    elif record.schema_type == "CA":
        is_valid, errors = validate_ca_record(record.record_data)
    else:
        is_valid, errors = True, []
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Impossibile pubblicare scheda non valida", "errors": errors}
        )

    # Pubblica
    record.status = 'published'
    record.is_public = True
    record.validated_by = current_user.id
    record.validated_at = datetime.utcnow()

    db.commit()
    db.refresh(record)

    return record


# ============================================================================
# SITE-SPECIFIC ENDPOINTS
# ============================================================================

@router.get("/sites/{site_id}/records", response_model=List[ICCDRecordResponse])
async def get_site_records(
        site_id: UUID,
        schema_type: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Recupera tutte le schede ICCD di un sito"""
    query = db.query(ICCDRecord).filter(
        ICCDRecord.site_id == site_id,
        ICCDRecord.deleted_at.is_(None)
    )

    if schema_type:
        query = query.filter(ICCDRecord.schema_type == schema_type.upper())

    records = query.order_by(ICCDRecord.created_at.desc()).all()

    return records


@router.get("/sites/{site_id}/statistics")
async def get_site_statistics(
        site_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Statistiche schede ICCD per sito"""
    stats = db.query(
        ICCDRecord.schema_type,
        func.count(ICCDRecord.id).label('count'),
        func.count(func.nullif(ICCDRecord.status == 'published', False)).label('published')
    ).filter(
        ICCDRecord.site_id == site_id,
        ICCDRecord.deleted_at.is_(None)
    ).group_by(ICCDRecord.schema_type).all()

    return [
        {
            "schema_type": s.schema_type,
            "total": s.count,
            "published": s.published
        }
        for s in stats
    ]


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.get("/export/{record_id}/pdf")
async def export_pdf(
        record_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Esporta scheda ICCD in formato PDF

    TODO: Implementare generazione PDF conforme ICCD
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Export PDF in fase di implementazione"
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _generate_nct_number() -> str:
    """Genera numero NCT univoco di 8 cifre"""
    import time
    timestamp = str(int(time.time() * 1000))[-8:]
    return timestamp


def _extract_fields_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae campi per query rapide dal JSON"""
    extracted = {}

    # Oggetto
    if 'OG' in data and 'OGT' in data['OG']:
        extracted['object_definition'] = data['OG']['OGT'].get('OGTD')
        extracted['object_name'] = data['OG']['OGT'].get('OGTN')

    # Cronologia
    if 'DT' in data:
        if 'DTZ' in data['DT'] and len(data['DT']['DTZ']) > 0:
            extracted['chronology_generic'] = data['DT']['DTZ'][0].get('DTZG')

        if 'DTS' in data['DT'] and len(data['DT']['DTS']) > 0:
            extracted['chronology_from'] = data['DT']['DTS'][0].get('DTSI')
            extracted['chronology_to'] = data['DT']['DTS'][0].get('DTSF')

    # Localizzazione
    if 'LC' in data and 'PVC' in data['LC']:
        extracted['region'] = data['LC']['PVC'].get('PVCR')
        extracted['province'] = data['LC']['PVC'].get('PVCP')
        extracted['municipality'] = data['LC']['PVC'].get('PVCC')

    # Coordinate
    if 'GP' in data and 'GPP' in data['GP']:
        extracted['latitude'] = data['GP']['GPP'].get('GPPY')
        extracted['longitude'] = data['GP']['GPP'].get('GPPX')

    return extracted


def _calculate_completeness(data: Dict[str, Any], schema: Dict[str, Any]) -> float:
    """Calcola percentuale completezza scheda"""
    if not schema or 'schema' not in schema:
        return 0.0

    total_fields = _count_fields(schema['schema'].get('properties', {}))
    filled_fields = _count_filled_fields(data)

    if total_fields == 0:
        return 0.0

    return round((filled_fields / total_fields) * 100, 2)


def _count_fields(properties: Dict[str, Any], depth: int = 0) -> int:
    """Conta totale campi nello schema (ricorsivo)"""
    if depth > 5:  # Limita ricorsione
        return 0

    count = 0
    for prop in properties.values():
        if prop.get('type') == 'object' and 'properties' in prop:
            count += _count_fields(prop['properties'], depth + 1)
        else:
            count += 1

    return count


def _count_filled_fields(data: Dict[str, Any], depth: int = 0) -> int:
    """Conta campi compilati (ricorsivo)"""
    if depth > 5:
        return 0

    count = 0
    for value in data.values():
        if isinstance(value, dict):
            count += _count_filled_fields(value, depth + 1)
        elif value is not None and value != '' and value != []:
            count += 1

    return count


def _find_missing_required_fields(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """Trova campi obbligatori mancanti"""
    missing = []

    if not schema or 'schema' not in schema:
        return missing

    properties = schema['schema'].get('properties', {})
    required = schema['schema'].get('required', [])

    for req in required:
        if req not in data or not data[req]:
            missing.append(req)

    return missing
