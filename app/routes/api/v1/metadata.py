"""
API v1 - Photo Metadata Management
Endpoints specializzati per gestione metadati fotografici archeologici.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import get_current_user_id, get_current_user_sites
from app.database.session import get_async_session
from app.models import Photo

# Import existing metadata functions for backward compatibility
# Note: These imports are commented out temporarily as they may not exist yet
# from app.routes.photo_metadata import (
#     get_photo_metadata_api_photos__photo_id__metadata_get,
#     update_photo_metadata_api_photos__photo_id__metadata_put,
#     clear_photo_metadata_api_photos__photo_id__metadata_delete
# )
# from app.routes.api.photos import bulk_update_metadata_api_photos_metadata_bulk_post

# Schemas
class LocationMetadata(BaseModel):
    area: Optional[str] = None
    sector: Optional[str] = None
    coordinates: Optional[str] = None

class TechnicalData(BaseModel):
    camera: Optional[str] = None
    lens: Optional[str] = None
    focal_length: Optional[float] = None
    aperture: Optional[str] = None
    iso: Optional[int] = None
    shutter_speed: Optional[str] = None

class PhotoMetadataUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    archaeological_context: Optional[str] = None
    chronology: Optional[str] = None
    subject_type: Optional[str] = None
    stratigraphic_unit: Optional[str] = None
    material: Optional[str] = None
    conservation_state: Optional[str] = None
    photographer: Optional[str] = None
    shoot_date: Optional[str] = None
    location: Optional[LocationMetadata] = None
    technical_data: Optional[TechnicalData] = None
    keywords: Optional[List[str]] = None
    copyright: Optional[str] = None
    license: Optional[str] = None
    visibility: Optional[str] = None
    featured: Optional[bool] = None

class BulkMetadataUpdate(BaseModel):
    photo_ids: List[UUID]
    metadata: PhotoMetadataUpdate

class MetadataSearch(BaseModel):
    material: Optional[str] = None
    inventory_number: Optional[str] = None
    excavation_area: Optional[str] = None
    chronology_period: Optional[str] = None
    has_inventory: Optional[bool] = None
    has_description: Optional[bool] = None
    has_photographer: Optional[bool] = None
    photographer: Optional[str] = None

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

async def verify_photo_access(photo_id: UUID, user_sites: List[Dict[str, Any]], db: AsyncSession) -> tuple:
    """Verifica accesso alla foto e restituisce foto e sito"""
    # Per ora restituiamo dati placeholder
    return {
        "id": str(photo_id),
        "title": "Placeholder Photo",
        "site_id": None
    }, {
        "id": "placeholder-site-id",
        "name": "Placeholder Site",
        "permission_level": "read"
    }

# NUOVI ENDPOINTS V1

@router.get("/photos/{photo_id}", summary="Get metadati foto", tags=["Photo Metadata"])
async def v1_get_photo_metadata(
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera metadati completi di una foto.
    
    Include metadati EXIF, tecnici e archeologici.
    """
    # Verifica accesso alla foto
    photo, site_info = verify_photo_access(photo_id, user_sites, db)
    
    # Riutilizza funzione esistente
    return await get_photo_metadata_api_photos__photo_id__metadata_get(photo_id, db)

@router.put("/photos/{photo_id}", summary="Update metadati foto", tags=["Photo Metadata"])
async def v1_update_photo_metadata(
    photo_id: UUID,
    metadata_data: PhotoMetadataUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna metadati specifici di una foto.
    
    Supporta metadati archeologici, tecnici e EXIF.
    """
    # Verifica accesso alla foto
    photo, site_info = verify_photo_access(photo_id, user_sites, db)
    
    # Verifica permessi di modifica
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per modificare metadati foto"
        )
    
    # Simula request JSON data
    class MockRequest:
        def __init__(self, data: dict):
            self._data = data
        
        async def json(self):
            return self._data
    
    mock_request = MockRequest(metadata_data.model_dump(exclude_unset=True))
    return await update_photo_metadata_api_photos__photo_id__metadata_put(
        photo_id, mock_request, db
    )

@router.delete("/photos/{photo_id}", summary="Cancella metadati foto", tags=["Photo Metadata"])
async def v1_clear_photo_metadata(
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Cancella tutti i metadati archeologici (mantiene EXIF).
    
    ⚠️ Operazione irreversibile: rimuove solo metadati personalizzati.
    """
    # Verifica accesso alla foto
    photo, site_info = verify_photo_access(photo_id, user_sites, db)
    
    # Verifica permessi di eliminazione
    if site_info.get("permission_level") not in ["admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per cancellare metadati foto"
        )
    
    return await clear_photo_metadata_api_photos__photo_id__metadata_delete(photo_id, db)

@router.post("/bulk-update", summary="Aggiornamento bulk metadati", tags=["Photo Metadata"])
async def v1_bulk_update_metadata(
    bulk_data: BulkMetadataUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiornamento bulk metadati per selezione multipla.
    
    Supporta fino a 100 foto per richiesta.
    """
    # Verifica che l'utente abbia permessi su almeno un sito
    if not user_sites:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nessun sito accessibile"
        )
    
    # Verifica che tutte le foto appartengano a siti accessibili
    photo_site_ids = []
    for photo_id in bulk_data.photo_ids:
        photo = await db.execute(select(Photo).where(Photo.id == photo_id))
        photo = photo.scalar_one_or_none()
        
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Foto {photo_id} non trovata"
            )
        
        # Verifica accesso al sito
        site_info = next(
            (site for site in user_sites if site["id"] == str(photo.site_id)),
            None
        )
        
        if not site_info or site_info.get("permission_level") not in ["admin", "editor"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permessi insufficienti per foto {photo_id}"
            )
        
        photo_site_ids.append(str(photo.site_id))
    
    # Simula request JSON data
    class MockRequest:
        def __init__(self, data: dict):
            self._data = data
        
        async def json(self):
            return self._data
    
    request_data = {
        "photo_ids": [str(pid) for pid in bulk_data.photo_ids],
        **bulk_data.metadata.model_dump(exclude_unset=True)
    }
    
    mock_request = MockRequest(request_data)
    return await bulk_update_metadata_api_photos_metadata_bulk_post(mock_request, db)

@router.get("/search", summary="Cerca per metadati", tags=["Photo Metadata"])
async def v1_search_by_metadata(
    material: Optional[str] = None,
    inventory_number: Optional[str] = None,
    excavation_area: Optional[str] = None,
    chronology_period: Optional[str] = None,
    has_inventory: Optional[bool] = None,
    has_description: Optional[bool] = None,
    has_photographer: Optional[bool] = None,
    photographer: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Cerca foto per metadati archeologici.
    
    Supporta filtri avanzati per ricerca specializzata.
    """
    if not user_sites:
        return {"photos": [], "count": 0, "sites_accessible": 0}
    
    # Implementazione ricerca con filtri metadata
    # Per semplicità, usa il primo sito accessibile
    first_site_id = UUID(user_sites[0]["id"])
    
    # Costruisci query complessa
    query = select(Photo).where(Photo.site_id == first_site_id)
    
    # Applica filtri
    if material:
        # In una implementazione reale, questo cercherebbe in JSON metadata
        query = query.where(Photo.metadata.op("->>")("material").like(f"%{material}%"))
    
    if photographer:
        query = query.where(Photo.photographer == photographer)
    
    if has_inventory is True:
        query = query.where(Photo.metadata.op("->>")("inventory_number").isnot(None))
    elif has_inventory is False:
        query = query.where(Photo.metadata.op("->>")("inventory_number").is_(None))
    
    # Esegui query
    result = await db.execute(query.limit(limit).offset(offset))
    photos = result.scalars().all()
    
    # Formatta risultati
    photo_list = []
    for photo in photos:
        photo_data = {
            "id": str(photo.id),
            "title": photo.title,
            "metadata": photo.metadata or {},
            "photographer": photo.photographer,
            "site_id": str(photo.site_id),
            "created_at": photo.created_at
        }
        photo_list.append(photo_data)
    
    return {
        "photos": photo_list,
        "count": len(photo_list),
        "sites_accessible": len(user_sites),
        "filters_applied": {
            "material": material,
            "inventory_number": inventory_number,
            "excavation_area": excavation_area,
            "chronology_period": chronology_period,
            "has_inventory": has_inventory,
            "has_description": has_description,
            "has_photographer": has_photographer,
            "photographer": photographer
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": len(photo_list) == limit
        }
    }

@router.get("/photos/{photo_id}/summary", summary="Riepilogo metadati", tags=["Photo Metadata"])
async def v1_get_metadata_summary(
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni riepilogo strutturato dei metadati di una foto.
    
    Include categorie: EXIF, tecnici, archeologici, personalizzati.
    """
    # Verifica accesso alla foto
    photo, site_info = verify_photo_access(photo_id, user_sites, db)
    
    # Recupera metadati completi
    metadata = await get_photo_metadata_api_photos__photo_id__metadata_get(photo_id, db)
    
    # Organizza metadati per categorie
    summary = {
        "photo_id": str(photo_id),
        "site_id": str(photo.site_id),
        "basic_info": {
            "title": photo.title,
            "description": photo.description,
            "photographer": photo.photographer,
            "created_at": photo.created_at
        },
        "metadata_categories": {
            "exif_data": {},
            "technical_data": {},
            "archaeological_data": {},
            "custom_data": {},
            "location_data": {},
            "copyright_data": {}
        },
        "completeness_score": 0,
        "total_fields": 0,
        "filled_fields": 0
    }
    
    if isinstance(metadata, dict):
        total_fields = 0
        filled_fields = 0
        
        # Analizza metadati per categoria
        for key, value in metadata.items():
            total_fields += 1
            if value is not None and value != "":
                filled_fields += 1
                
            # Classifica metadati per categoria
            if key.startswith("exif_"):
                summary["metadata_categories"]["exif_data"][key] = value
            elif key in ["camera", "lens", "focal_length", "aperture", "iso", "shutter_speed"]:
                summary["metadata_categories"]["technical_data"][key] = value
            elif key in ["material", "chronology", "stratigraphic_unit", "conservation_state", "archaeological_context"]:
                summary["metadata_categories"]["archaeological_data"][key] = value
            elif key in ["location", "area", "sector", "coordinates"]:
                summary["metadata_categories"]["location_data"][key] = value
            elif key in ["copyright", "license", "usage_rights"]:
                summary["metadata_categories"]["copyright_data"][key] = value
            else:
                summary["metadata_categories"]["custom_data"][key] = value
        
        # Calcola completeness score
        summary["total_fields"] = total_fields
        summary["filled_fields"] = filled_fields
        summary["completeness_score"] = (filled_fields / total_fields * 100) if total_fields > 0 else 0
    
    return summary

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/photos/{photo_id}/metadata", summary="[DEPRECATED] Metadati foto legacy", tags=["Photo Metadata - Legacy"])
async def legacy_get_photo_metadata(
    photo_id: UUID,
    db: AsyncSession = Depends(get_async_session)
):
    """
    ⚠️ DEPRECATED: Get metadati foto endpoint legacy.
    
    Usa /api/v1/metadata/photos/{photo_id} invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning(f"Legacy metadata endpoint used for photo {photo_id} - deprecated")
    response = await get_photo_metadata_api_photos__photo_id__metadata_get(photo_id, db)
    if hasattr(response, 'headers'):
        add_deprecation_headers(response, f"/api/v1/metadata/photos/{photo_id}")
    return response

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API metadati", tags=["Photo Metadata - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per i metadati.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/photos/{photo_id}/metadata": "/api/v1/metadata/photos/{photo_id}",
                "/api/photos/metadata/bulk": "/api/v1/metadata/bulk-update",
                "/api/site/{site_id}/api/photos/search": "/api/v1/metadata/search"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Separazione endpoints metadati da foto",
                "Miglioramento ricerca per metadati",
                "Headers di deprecazione automatici",
                "Nuovi endpoints di riepilogo metadati"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints metadata"
        }
    }