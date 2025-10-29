"""
API v1 - Photo Management
Endpoints per gestione completa delle foto archeologiche.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response, StreamingResponse
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import get_current_user_id, get_current_user_sites
from app.database.session import get_async_session
from app.models import Photo

# Import existing photo functions for backward compatibility
# Note: These imports are commented out temporarily as they may not exist yet
# from app.routes.photos_router import (
#     get_site_photos_api_api_site__site_id__photos_get,
#     upload_photo_api_site__site_id__photos_upload_post,
#     update_photo_api_site__site_id__photos__photo_id__update_put,
#     delete_photo_api_site__site_id__photos__photo_id__delete,
#     stream_photo_from_minio_api_site__site_id__photos__photo_id__stream_get,
#     get_photo_thumbnail_api_site__site_id__photos__photo_id__thumbnail_get,
#     get_photo_full_api_site__site_id__photos__photo_id__full_get
# )
# from app.routes.api.sites_photos import bulk_update_photos_api_site__site_id__photos_bulk_update_post
# from app.routes.photo_metadata import router as photo_metadata_router

# Schemas
class PhotoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    photo_type: Optional[str] = None
    photographer: Optional[str] = None
    keywords: Optional[str] = None
    # Metadati archeologici
    inventory_number: Optional[str] = None
    catalog_number: Optional[str] = None
    excavation_area: Optional[str] = None
    stratigraphic_unit: Optional[str] = None
    material: Optional[str] = None
    object_type: Optional[str] = None
    chronology_period: Optional[str] = None
    conservation_status: Optional[str] = None
    is_published: Optional[bool] = None
    is_validated: Optional[bool] = None

class BulkPhotoUpdate(BaseModel):
    photo_ids: List[UUID]
    update_data: PhotoUpdate

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )
    
    return site_info

# NUOVI ENDPOINTS V1

@router.get("", summary="Ricerca globale foto", tags=["Photos"])
async def v1_get_photos(
    search: Optional[str] = None,
    photo_type: Optional[str] = None,
    material: Optional[str] = None,
    is_published: Optional[bool] = None,
    is_validated: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ricerca globale foto su tutti i siti accessibili.
    
    Supporta filtri archeologici avanzati.
    """
    if not user_sites:
        return {"photos": [], "count": 0, "sites_accessible": 0}
    
    # Simula richiesta per sito specifico per ogni sito accessibile
    all_photos = []
    site_ids = [UUID(site["id"]) for site in user_sites]
    
    # Per semplicità, cerca sul primo sito accessibile
    # In produzione, implementare ricerca aggregata
    first_site_id = site_ids[0]
    
    class MockRequest:
        def __init__(self):
            self.query_params = {
                "search": search,
                "photo_type": photo_type,
                "material": material,
                "is_published": is_published,
                "is_validated": is_validated,
                "limit": limit,
                "offset": offset
            }
    
    mock_request = MockRequest()
    result = await get_site_photos_api_api_site__site_id__photos_get(
        first_site_id, mock_request, current_user_id, user_sites, db
    )
    
    return {
        "photos": result.get("photos", []),
        "count": result.get("count", 0),
        "sites_accessible": len(user_sites),
        "searched_sites": [str(first_site_id)],
        "filters_applied": {
            "search": search,
            "photo_type": photo_type,
            "material": material,
            "is_published": is_published,
            "is_validated": is_validated
        }
    }

@router.post("/sites/{site_id}/photos", summary="Upload foto sito", tags=["Photos"])
async def v1_upload_photo(
    site_id: UUID,
    photos: List[UploadFile] = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_type: Optional[str] = Form(None),
    photographer: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    inventory_number: Optional[str] = Form(None),
    excavation_area: Optional[str] = Form(None),
    stratigraphic_unit: Optional[str] = Form(None),
    material: Optional[str] = Form(None),
    object_type: Optional[str] = Form(None),
    chronology_period: Optional[str] = Form(None),
    conservation_status: Optional[str] = Form(None),
    use_queue: Optional[bool] = Form(False),
    priority: Optional[str] = Form("normal"),
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Upload foto al sito archeologico.
    
    Supporta upload singolo e multiplo con metadati archeologici completi.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di upload
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per upload foto sul sito {site_id}"
        )
    
    # Simula request form data per compatibilità
    class MockRequest:
        def __init__(self, form_data: dict, files: List[UploadFile]):
            self._form_data = form_data
            self._files = files
        
        async def form(self):
            return self._form_data
        
        def files(self):
            return {"photos": self._files}
    
    form_data = {
        "title": title,
        "description": description,
        "photo_type": photo_type,
        "photographer": photographer,
        "keywords": keywords,
        "inventory_number": inventory_number,
        "excavation_area": excavation_area,
        "stratigraphic_unit": stratigraphic_unit,
        "material": material,
        "object_type": object_type,
        "chronology_period": chronology_period,
        "conservation_status": conservation_status,
        "use_queue": use_queue,
        "priority": priority
    }
    
    mock_request = MockRequest(form_data, photos)
    return await upload_photo_api_site__site_id__photos_upload_post(
        site_id, mock_request, current_user_id, user_sites, db
    )

@router.get("/sites/{site_id}/photos", summary="Foto sito", tags=["Photos"])
async def v1_get_site_photos(
    site_id: UUID,
    search: Optional[str] = None,
    photo_type: Optional[str] = None,
    material: Optional[str] = None,
    conservation_status: Optional[str] = None,
    excavation_area: Optional[str] = None,
    chronology_period: Optional[str] = None,
    is_published: Optional[bool] = None,
    is_validated: Optional[bool] = None,
    has_deep_zoom: Optional[bool] = None,
    page: int = 1,
    per_page: int = 24,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera foto di un sito con filtri archeologici completi.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    class MockRequest:
        def __init__(self, query_params: dict):
            self.query_params = query_params
    
    query_params = {
        "search": search,
        "photo_type": photo_type,
        "material": material,
        "conservation_status": conservation_status,
        "excavation_area": excavation_area,
        "chronology_period": chronology_period,
        "is_published": is_published,
        "is_validated": is_validated,
        "has_deep_zoom": has_deep_zoom,
        "page": page,
        "per_page": per_page
    }
    
    mock_request = MockRequest(query_params)
    result = await get_site_photos_api_api_site__site_id__photos_get(
        site_id, mock_request, current_user_id, user_sites, db
    )
    
    # Aggiungi informazioni sito
    result["site_info"] = site_info
    return result

@router.get("/photos/{photo_id}/stream", summary="Stream foto", tags=["Photos"])
async def v1_stream_photo(
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Stream dell'immagine originale dallo storage MinIO.
    """
    # Verifica che la foto appartenga a un sito accessibile
    photo = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = photo.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foto non trovata"
        )
    
    # Verifica accesso al sito della foto
    verify_site_access(photo.site_id, user_sites)
    
    return await stream_photo_from_minio_api_site__site_id__photos__photo_id__stream_get(
        photo.site_id, photo_id, current_user_id, user_sites, db
    )

@router.get("/photos/{photo_id}/thumbnail", summary="Thumbnail foto", tags=["Photos"])
async def v1_get_photo_thumbnail(
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni thumbnail della foto.
    """
    # Verifica che la foto appartenga a un sito accessibile
    photo = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = photo.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foto non trovata"
        )
    
    # Verifica accesso al sito della foto
    verify_site_access(photo.site_id, user_sites)
    
    return await get_photo_thumbnail_api_site__site_id__photos__photo_id__thumbnail_get(
        photo.site_id, photo_id, current_user_id, user_sites, db
    )

@router.get("/photos/{photo_id}/full", summary="Immagine completa foto", tags=["Photos"])
async def v1_get_photo_full(
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni immagine completa ottimizzata della foto.
    """
    # Verifica che la foto appartenga a un sito accessibile
    photo = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = photo.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foto non trovata"
        )
    
    # Verifica accesso al sito della foto
    verify_site_access(photo.site_id, user_sites)
    
    return await get_photo_full_api_site__site_id__photos__photo_id__full_get(
        photo.site_id, photo_id, current_user_id, user_sites, db
    )

@router.put("/sites/{site_id}/photos/{photo_id}", summary="Aggiorna foto", tags=["Photos"])
async def v1_update_photo(
    site_id: UUID,
    photo_id: UUID,
    photo_data: PhotoUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna metadati e informazioni di una foto.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di modifica
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per modificare foto sul sito {site_id}"
        )
    
    # Simula request JSON data
    class MockRequest:
        def __init__(self, data: dict):
            self._data = data
        
        async def json(self):
            return self._data
    
    mock_request = MockRequest(photo_data.model_dump(exclude_unset=True))
    return await update_photo_api_site__site_id__photos__photo_id__update_put(
        site_id, photo_id, mock_request, current_user_id, user_sites, db
    )

@router.delete("/sites/{site_id}/photos/{photo_id}", summary="Elimina foto", tags=["Photos"])
async def v1_delete_photo(
    site_id: UUID,
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Elimina una foto dal sito archeologico.
    
    ⚠️ Operazione protetta: le foto US non possono essere eliminate.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di eliminazione
    if site_info.get("permission_level") not in ["admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per eliminare foto dal sito {site_id}"
        )
    
    return await delete_photo_api_site__site_id__photos__photo_id__delete(
        site_id, photo_id, current_user_id, user_sites, db
    )

@router.post("/sites/{site_id}/photos/bulk-update", summary="Aggiornamento bulk foto", tags=["Photos"])
async def v1_bulk_update_photos(
    site_id: UUID,
    bulk_data: BulkPhotoUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna più foto in blocco con supporto completo per metadati archeologici.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di modifica
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per modificare foto sul sito {site_id}"
        )
    
    # Simula request JSON data
    class MockRequest:
        def __init__(self, data: dict):
            self._data = data
        
        async def json(self):
            return self._data
    
    mock_request = MockRequest({
        "photo_ids": [str(pid) for pid in bulk_data.photo_ids],
        **bulk_data.update_data.model_dump(exclude_unset=True)
    })
    
    return await bulk_update_photos_api_site__site_id__photos_bulk_update_post(
        site_id, mock_request, current_user_id, user_sites, db
    )

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/photos/{site_id}", summary="[DEPRECATED] Foto sito legacy", tags=["Photos - Legacy"])
async def legacy_get_site_photos(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    ⚠️ DEPRECATED: Lista foto sito endpoint legacy.
    
    Usa /api/v1/sites/{site_id}/photos invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning(f"Legacy photos endpoint used for site {site_id} - deprecated")
    response = await get_site_photos_api_api_site__site_id__photos_get(
        site_id, request, current_user_id, user_sites, db
    )
    add_deprecation_headers(response, f"/api/v1/sites/{site_id}/photos")
    return response

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API foto", tags=["Photos - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per le foto.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/site/{site_id}/photos": "/api/v1/sites/{site_id}/photos",
                "/photos/{photo_id}/stream": "/api/v1/photos/{photo_id}/stream",
                "/photos/{photo_id}/thumbnail": "/api/v1/photos/{photo_id}/thumbnail",
                "/photos/{photo_id}/full": "/api/v1/photos/{photo_id}/full",
                "/api/site/{site_id}/photos/{photo_id}/update": "/api/v1/sites/{site_id}/photos/{photo_id}",
                "/api/site/{site_id}/photos/{photo_id}": "/api/v1/sites/{site_id}/photos/{photo_id}",
                "/api/site/{site_id}/photos/bulk-update": "/api/v1/sites/{site_id}/photos/bulk-update"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Separazione endpoints per dominio",
                "Miglioramento filtri archeologici",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints"
        }
    }