# app/routes/api/v1/photos.py - API Versioning per Foto (V1)
"""
API Versioning - Implementazione tecnica #9

Endpoint V1 per foto - versione legacy mantenuta per backward compatibility.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.routes.api.dependencies import get_site_access
from app.services.photo_upload_service import PhotoUploadService, get_photo_upload_service
from app.repositories.photo_repository import PhotoRepository

# Router V1
v1_photos_router = APIRouter(prefix="/photos", tags=["photos-v1"])

# Dependency per repository
def get_photo_repository(db: AsyncSession = Depends(get_async_session)) -> PhotoRepository:
    return PhotoRepository(db)


@v1_photos_router.post("/{site_id}/upload")
async def upload_photos_v1(
    site_id: UUID,
    photos: List[UploadFile] = File(...),
    upload_service: PhotoUploadService = Depends(get_photo_upload_service),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """
    Upload foto - Versione V1 (legacy)

    Questa è la versione legacy mantenuta per backward compatibility.
    Per nuove implementazioni, vedere V2.

    @deprecated: Utilizzare /api/v2/photos/upload per nuove implementazioni
    """
    return await upload_service.upload_photos(site_id, photos, current_user_id)


@v1_photos_router.get("/{site_id}")
async def get_site_photos_v1(
    site_id: UUID,
    page: int = 1,
    per_page: int = 24,
    search: Optional[str] = None,
    photo_type: Optional[str] = None,
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera foto sito - Versione V1

    Versione legacy con filtri basilari.
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Calcola offset
    skip = (page - 1) * per_page

    # Filtri V1 (basilari)
    filters = {}
    if search:
        filters['search'] = search
    if photo_type:
        filters['photo_type'] = photo_type

    # Recupera foto
    photos = await photo_repo.get_site_photos(
        site_id=site_id,
        skip=skip,
        limit=per_page,
        filters=filters
    )

    # Converti in formato V1
    photos_data = []
    for photo in photos:
        photo_dict = {
            "id": str(photo.id),
            "filename": photo.filename,
            "title": photo.title,
            "description": photo.description,
            "photo_type": photo.photo_type.value if photo.photo_type else None,
            "file_size": photo.file_size,
            "width": photo.width,
            "height": photo.height,
            "created_at": photo.created.isoformat(),
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "full_url": f"/photos/{photo.id}/full"
        }
        photos_data.append(photo_dict)

    # Conta totale per paginazione
    total_photos = await photo_repo.count({"site_id": site_id})

    return {
        "photos": photos_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_photos,
            "total_pages": (total_photos + per_page - 1) // per_page
        }
    }


@v1_photos_router.put("/{site_id}/{photo_id}")
async def update_photo_v1(
    site_id: UUID,
    photo_id: UUID,
    update_data: Dict[str, Any],
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """
    Aggiorna foto - Versione V1

    Versione legacy che accetta qualsiasi campo.
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Aggiorna metadati
    updated_photo = await photo_repo.update_photo_metadata(photo_id, update_data)

    if not updated_photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    return {
        "message": "Foto aggiornata con successo",
        "photo_id": str(photo_id)
    }


@v1_photos_router.delete("/{site_id}/{photo_id}")
async def delete_photo_v1(
    site_id: UUID,
    photo_id: UUID,
    site_access: tuple = Depends(get_site_access),
    photo_repo: PhotoRepository = Depends(get_photo_repository),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """
    Elimina foto - Versione V1
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Verifica che la foto appartenga al sito
    photo = await photo_repo.get(photo_id)
    if not photo or photo.site_id != site_id:
        raise HTTPException(status_code=404, detail="Foto non trovata nel sito")

    # Elimina
    deleted = await photo_repo.remove(photo_id)

    if deleted:
        return {"message": "Foto eliminata con successo"}
    else:
        raise HTTPException(status_code=500, detail="Errore durante eliminazione")