# app/routes/api/v2/photos.py - API Versioning per Foto (V2)
"""
API Versioning - Implementazione tecnica #9

Endpoint V2 per foto - versione moderna con service layer e repository pattern.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.routes.api.dependencies import get_site_access
from app.services.photo_upload_service import PhotoUploadService, get_photo_upload_service
from app.repositories.photo_repository import PhotoRepository
from app.schema.photo_schemas import PhotoResponse, PhotoCreateRequest, PhotoMetadataUpdate
from app.routes.api.notifications_ws import notification_manager

# Router V2
v2_photos_router = APIRouter(prefix="/photos", tags=["photos-v2"])

# Dependency per repository
def get_photo_repository(db: AsyncSession = Depends(get_async_session)) -> PhotoRepository:
    return PhotoRepository(db)


# Request/Response Models V2
class PhotoUploadResponse(BaseModel):
    message: str
    uploaded_photos: List[Dict[str, Any]]
    total_uploaded: int
    errors: List[Dict[str, str]]
    photos_needing_tiles: int

class PhotoListResponse(BaseModel):
    photos: List[PhotoResponse]
    pagination: Dict[str, Any]
    filters_applied: Dict[str, Any]

class BulkOperationResponse(BaseModel):
    message: str
    affected_count: int
    errors: List[Dict[str, str]]


@v2_photos_router.post("/{site_id}/upload")
async def upload_photos_v2(
    site_id: UUID,
    photos: List[UploadFile] = File(...),
    archaeological_metadata: Optional[Dict[str, Any]] = None,
    upload_service: PhotoUploadService = Depends(get_photo_upload_service),
    current_user_id: UUID = Depends(get_current_user_id)
) -> PhotoUploadResponse:
    """
    Upload foto - Versione V2 (moderna)

    Utilizza service layer e repository pattern per migliore manutenibilità.
    Supporta metadati archeologici avanzati.
    """
    result = await upload_service.upload_photos(
        site_id, photos, current_user_id, archaeological_metadata
    )

    return PhotoUploadResponse(**result)


@v2_photos_router.get("/{site_id}")
async def get_site_photos_v2(
    site_id: UUID,
    # Paginazione
    page: int = Query(1, ge=1, description="Numero pagina"),
    per_page: int = Query(24, ge=1, le=100, description="Elementi per pagina"),

    # Filtri avanzati
    search: Optional[str] = Query(None, description="Ricerca testuale"),
    photo_type: Optional[str] = Query(None, description="Tipo foto"),
    material: Optional[str] = Query(None, description="Materiale"),
    excavation_area: Optional[str] = Query(None, description="Area scavo"),
    chronology_period: Optional[str] = Query(None, description="Periodo cronologico"),
    is_published: Optional[bool] = Query(None, description="Solo pubblicate"),
    is_validated: Optional[bool] = Query(None, description="Solo validate"),

    # Ordinamento
    sort_by: str = Query("created_desc", description="Ordinamento"),

    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository)
) -> PhotoListResponse:
    """
    Recupera foto sito - Versione V2

    Filtri avanzati e ordinamento flessibile con repository pattern.
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Costruisci filtri
    filters = {}
    if search:
        filters['search'] = search
    if photo_type:
        filters['photo_type'] = photo_type
    if material:
        filters['material'] = material
    if excavation_area:
        filters['excavation_area'] = excavation_area
    if chronology_period:
        filters['chronology_period'] = chronology_period
    if is_published is not None:
        filters['is_published'] = is_published
    if is_validated is not None:
        filters['is_validated'] = is_validated

    # Calcola offset
    skip = (page - 1) * per_page

    # Recupera foto con repository
    photos = await photo_repo.get_site_photos(
        site_id=site_id,
        skip=skip,
        limit=per_page,
        filters=filters,
        order_by=sort_by
    )

    # Converti in Pydantic models
    photos_data = [PhotoResponse.from_orm(photo) for photo in photos]

    # Conta totale per paginazione
    total_photos = await photo_repo.count({"site_id": site_id})

    # Invia notifica WebSocket per i filtri applicati
    try:
        await notification_manager.broadcast_photo_filters_applied(
            site_id=str(site_id),
            filters=filters,
            total_results=len(photos_data),
            search_query=filters.get('search'),
            applied_filters_count=len([k for k, v in filters.items() if v and v != ''])
        )
    except Exception as e:
        # Non bloccare la risposta se la notifica fallisce
        logger.warning(f"Failed to send photo filters notification: {e}")

    return PhotoListResponse(
        photos=photos_data,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total_photos,
            "total_pages": (total_photos + per_page - 1) // per_page
        },
        filters_applied=filters
    )


@v2_photos_router.get("/{site_id}/statistics")
async def get_site_photos_statistics_v2(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository)
):
    """
    Statistiche foto sito - Versione V2

    Endpoint dedicato per statistiche con repository ottimizzato.
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    stats = await photo_repo.get_site_photos_statistics(site_id)
    return stats


@v2_photos_router.put("/{site_id}/{photo_id}/metadata")
async def update_photo_metadata_v2(
    site_id: UUID,
    photo_id: UUID,
    metadata: PhotoMetadataUpdate,
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """
    Aggiorna metadati foto - Versione V2

    Utilizza schema Pydantic per validazione e repository per persistenza.
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Converti Pydantic model in dict
    update_data = metadata.dict(exclude_unset=True, exclude_none=True)

    # Aggiorna con repository
    updated_photo = await photo_repo.update_photo_metadata(photo_id, update_data)

    if not updated_photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    return {
        "message": "Metadati foto aggiornati con successo",
        "photo_id": str(photo_id),
        "updated_fields": list(update_data.keys())
    }


@v2_photos_router.post("/{site_id}/bulk-update")
async def bulk_update_photos_v2(
    site_id: UUID,
    photo_ids: List[UUID],
    metadata: PhotoMetadataUpdate,
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    current_user_id: UUID = Depends(get_current_user_id)
) -> BulkOperationResponse:
    """
    Aggiornamento bulk foto - Versione V2

    Operazione ottimizzata con repository pattern.
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    if not photo_ids:
        raise HTTPException(status_code=400, detail="Nessuna foto selezionata")

    # Converti Pydantic model
    update_data = metadata.dict(exclude_unset=True, exclude_none=True)

    # Bulk update con repository
    affected_count = await photo_repo.bulk_update_photos(
        photo_ids, site_id, update_data
    )

    return BulkOperationResponse(
        message=f"Aggiornate {affected_count} foto",
        affected_count=affected_count,
        errors=[]
    )


@v2_photos_router.delete("/{site_id}/bulk-delete")
async def bulk_delete_photos_v2(
    site_id: UUID,
    photo_ids: List[UUID],
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    current_user_id: UUID = Depends(get_current_user_id)
) -> BulkOperationResponse:
    """
    Eliminazione bulk foto - Versione V2

    Operazione sicura con verifica permessi.
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    if not photo_ids:
        raise HTTPException(status_code=400, detail="Nessuna foto selezionata")

    # Bulk delete con repository
    deleted_count = await photo_repo.delete_photos(photo_ids, site_id)

    return BulkOperationResponse(
        message=f"Eliminate {deleted_count} foto",
        affected_count=deleted_count,
        errors=[]
    )


@v2_photos_router.get("/{site_id}/search")
async def search_photos_v2(
    site_id: UUID,
    # Parametri ricerca
    inventory_number: Optional[str] = None,
    excavation_area: Optional[str] = None,
    material: Optional[str] = None,
    chronology_period: Optional[str] = None,
    photographer: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),

    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository)
):
    """
    Ricerca avanzata foto - Versione V2

    Ricerca per metadati archeologici con repository ottimizzato.
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Costruisci criteri ricerca
    search_criteria = {}
    if inventory_number:
        search_criteria['inventory_number'] = inventory_number
    if excavation_area:
        search_criteria['excavation_area'] = excavation_area
    if material:
        search_criteria['material'] = material
    if chronology_period:
        search_criteria['chronology_period'] = chronology_period
    if photographer:
        search_criteria['photographer'] = photographer

    if not search_criteria:
        raise HTTPException(status_code=400, detail="Specificare almeno un criterio di ricerca")

    # Ricerca con repository
    photos = await photo_repo.search_photos_by_metadata(
        site_id, search_criteria, limit
    )

    # Converti in response models
    photos_data = [PhotoResponse.from_orm(photo) for photo in photos]

    return {
        "query": search_criteria,
        "results": photos_data,
        "total": len(photos_data)
    }