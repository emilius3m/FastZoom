# app/routes/api/v1/photos.py - Photo management API endpoints v1

from fastapi import APIRouter, Depends, Request, HTTPException, status, Form, File, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
import json
import asyncio

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.models import UserActivity
from app.models import USFile
from app.routes.api.dependencies import get_site_access, get_photo_site_access, get_normalized_site_id
from app.services.storage_service import storage_service
from app.services.photo_service import photo_metadata_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.services.storage_management_service import storage_management_service
from app.services.photo_serving_service import photo_serving_service

# Import nuovi servizi modulari
from app.services.photos.upload_service import PhotoUploadService
from app.services.photos.query_service import PhotoQueryService
from app.services.photos.bulk_service import PhotoBulkService
from app.services.photos.deletion_service import PhotoDeletionService
from app.services.photos.deepzoom_service import PhotoDeepZoomService

# Import schemi Pydantic
from app.schemas.photos import PhotoUploadRequest, BulkUpdateRequest, BulkDeleteRequest, PhotoQueryFilters


# Export as 'router' for consistency with other API v1 modules
router = APIRouter()


# Consolidated photo serving endpoints - moved from photos_router.py
@router.get("/photos/{photo_id}/thumbnail")
async def get_photo_thumbnail_simple(
        photo_id: UUID,
        site_access: tuple = Depends(get_photo_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Serve thumbnail foto - CONSOLIDATED"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")
        
    return await photo_serving_service.serve_photo_thumbnail(photo_id, db)


@router.get("/photos/{photo_id}/full")
async def get_photo_full_simple(
        photo_id: UUID,
        site_access: tuple = Depends(get_photo_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Serve immagine completa - CONSOLIDATED"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")
        
    return await photo_serving_service.serve_photo_full(photo_id, db)


@router.get("/photos/{photo_id}/download")
async def download_photo_simple(
        photo_id: UUID,
        site_access: tuple = Depends(get_photo_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Scarica file originale foto - CONSOLIDATED"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")
        
    return await photo_serving_service.serve_photo_download(photo_id, db)


@router.get("/sites/{site_id}/photos")
async def get_site_photos_api(
        site_id: str,  # Changed from UUID to str to handle both formats
        # Basic filters
        search: str = None,
        photo_type: str = None,

        # Archaeological filters
        material: str = None,
        conservation_status: str = None,
        excavation_area: str = None,
        stratigraphic_unit: str = None,
        chronology_period: str = None,
        object_type: str = None,

        # Status filters
        is_published: bool = None,
        is_validated: bool = None,
        has_deep_zoom: bool = None,

        # Date filters
        upload_date_from: str = None,
        upload_date_to: str = None,
        photo_date_from: str = None,
        photo_date_to: str = None,
        find_date_from: str = None,
        find_date_to: str = None,

        # Dimension filters
        min_width: int = None,
        max_width: int = None,
        min_height: int = None,
        max_height: int = None,
        min_file_size_mb: float = None,
        max_file_size_mb: float = None,

        # Metadata presence filters
        has_inventory: bool = None,
        has_description: bool = None,
        has_photographer: bool = None,

        # Sorting
        sort_by: str = "created_desc",

        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """API avanzata per ottenere foto del sito con filtri archeologici completi - MODULAR SERVICE VERSION"""

    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Handle site_id normalization
    if isinstance(site_id, str):
        from app.routes.api.dependencies import normalize_site_id
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            raise HTTPException(status_code=404, detail="ID sito non valido")
    else:
        normalized_site_id = str(site_id)

    # Prepare query filters using Pydantic schema
    query_filters = PhotoQueryFilters(
        search=search,
        photo_type=photo_type,
        material=material,
        conservation_status=conservation_status,
        excavation_area=excavation_area,
        stratigraphic_unit=stratigraphic_unit,
        chronology_period=chronology_period,
        object_type=object_type,
        is_published=is_published,
        is_validated=is_validated,
        has_deep_zoom=has_deep_zoom,
        upload_date_from=upload_date_from,
        upload_date_to=upload_date_to,
        photo_date_from=photo_date_from,
        photo_date_to=photo_date_to,
        find_date_from=find_date_from,
        find_date_to=find_date_to,
        min_width=min_width,
        max_width=max_width,
        min_height=min_height,
        max_height=max_height,
        min_file_size_mb=min_file_size_mb,
        max_file_size_mb=max_file_size_mb,
        has_inventory=has_inventory,
        has_description=has_description,
        has_photographer=has_photographer,
        sort_by=sort_by
    )

    # Use modular query service
    query_service = PhotoQueryService()
    general_photos, us_photos = await query_service.query_site_photos(
        site_id=normalized_site_id,
        filters=query_filters,
        db=db
    )
    
    # Combine both photo types into a single flat array for frontend compatibility
    all_photos = general_photos + us_photos
    
    return all_photos


@router.post("/sites/{site_id}/photos/upload")
async def upload_photos(
    site_id: UUID,
    photos: List[UploadFile] = File(...),  # ✅ Lista di file
    inventory_number: Optional[str] = Form(None),
    excavation_area: Optional[str] = Form(None),
    stratigraphic_unit: Optional[str] = Form(None),
    material: Optional[str] = Form(None),
    photo_type: Optional[str] = Form(None),
    photo_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # JSON string
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Upload foto al sito archeologico con metadati come campi separati - FIXED VERSION
    
    Args:
        site_id: UUID del sito archeologico
        photos: Lista di file foto da caricare
        inventory_number: Numero di inventario
        excavation_area: Area di scavo
        stratigraphic_unit: Unità stratigrafica
        material: Materiale
        photo_type: Tipo foto
        photo_date: Data scatto
        description: Descrizione
        tags: Tags come JSON string
        
    Returns:
        JSONResponse con risultati del caricamento
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    logger.info(f"📥 Received {len(photos)} files for upload")
    
    # Parse tags se presente
    tags_list = []
    if tags:
        try:
            tags_list = json.loads(tags)
        except:
            tags_list = []
    
    # Costruisci metadata dict dai campi del form
    metadata_dict = {
        'title': f"Upload {len(photos)} photos",
        'description': description or '',
        'photographer': '',
        'photo_type': photo_type,
        'inventory_number': inventory_number,
        'excavation_area': excavation_area,
        'stratigraphic_unit': stratigraphic_unit,
        'material': material,
        'photo_date': photo_date,
        'keywords': tags_list,
        'use_queue': False,
        'priority': 'normal'
    }
    
    # Remove None values to avoid validation issues
    metadata_dict = {k: v for k, v in metadata_dict.items() if v is not None and v != ''}
    
    logger.info(f"📋 Metadata prepared: {list(metadata_dict.keys())}")

    # Validate with Pydantic schema
    try:
        upload_request = PhotoUploadRequest(**metadata_dict)
        logger.info("PhotoUploadRequest validated successfully",
                   photo_type=upload_request.photo_type,
                   inventory_number=upload_request.inventory_number)
    except Exception as validation_error:
        logger.error(f"Pydantic validation failed: {validation_error}")
        
        # Extract detailed validation errors and make them JSON serializable
        validation_errors = None
        if hasattr(validation_error, 'errors'):
            try:
                validation_errors = validation_error.errors()
                # Ensure all values in validation errors are JSON serializable
                if validation_errors:
                    validation_errors = json.loads(json.dumps(validation_errors, default=str))
            except Exception as json_error:
                logger.warning(f"Failed to serialize validation errors: {json_error}")
                validation_errors = [{"msg": str(validation_error), "type": "validation_error"}]
        
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Metadata validation failed",
                "validation_errors": validation_errors,
                "error_type": type(validation_error).__name__,
                "received_metadata": metadata_dict
            }
        )

    # Use modular upload service with raw metadata for better compatibility
    upload_service = PhotoUploadService()
    result = await upload_service.process_photo_upload(
        site_id=site_id,
        user_id=current_user_id,
        photos=photos,
        upload_request=upload_request,
        db=db,
        raw_metadata=metadata_dict
    )

    # 🔧 FIX: Commit esplicito per rendere i dati visibili ad altre sessioni
    await db.commit()
    logger.info("✅ Database changes committed - data now visible to all sessions")

    return result


@router.get("/sites/{site_id}/photos/{photo_id}/stream")
async def stream_photo_from_minio(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Stream foto - CONSOLIDATED"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Use consolidated photo serving service for consistent behavior
    return await photo_serving_service.serve_photo_full(photo_id, db)


@router.get("/sites/{site_id}/api/photos/search")
async def search_photos_by_metadata(
        site_id: UUID,
        material: Optional[str] = None,
        inventory_number: Optional[str] = None,
        excavation_area: Optional[str] = None,
        chronology_period: Optional[str] = None,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Cerca foto per metadati archeologici"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    search_results = await archaeological_minio_service.search_photos_by_metadata(
        site_id=str(site_id),
        material=material,
        inventory_number=inventory_number,
        excavation_area=excavation_area,
        chronology_period=chronology_period
    )

    return JSONResponse({
        "results": search_results,
        "total": len(search_results)
    })


@router.put("/sites/{site_id}/photos/{photo_id}/update")
async def update_photo(
        site_id: UUID,
        photo_id: UUID,
        request: Request,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna metadati foto archeologica - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        update_data = await request.json()
        logger.info(f"PUT /site/{site_id}/photos/{photo_id}/update - Received data: {update_data}")
    except Exception as e:
        logger.error(f"PUT /site/{site_id}/photos/{photo_id}/update - JSON parsing error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")

    try:
        # Use modular update logic from bulk service (single update mode)
        bulk_service = PhotoBulkService()
        return await bulk_service.update_single_photo(
            site_id=str(site_id),
            photo_id=str(photo_id),
            user_id=str(current_user_id),
            update_data=update_data,
            db=db
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Single photo update error: {e}")
        raise HTTPException(status_code=500, detail=f"Errore aggiornamento foto: {str(e)}")


@router.delete("/sites/{site_id}/photos/{photo_id}")
async def delete_photo(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Elimina foto dal sito archeologico - PROTETTO contro eliminazione foto US - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Use modular deletion service
    deletion_service = PhotoDeletionService()
    return await deletion_service.delete_single_photo(
        site_id=str(site_id),
        photo_id=photo_id,
        current_user_id=current_user_id,
        db=db
    )

@router.post("/sites/{site_id}/photos/bulk-delete")
async def bulk_delete_photos(
        site_id: str,  # Changed from UUID to str to handle both formats
        delete_data: dict,
        normalized_site_id: str = Depends(get_normalized_site_id),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Elimina più foto in blocco - PROTETTO contro eliminazione foto US - MODULAR SERVICE VERSION"""
    # The dependency handles both normalization and site access verification

    try:
        # Prepare bulk delete request using Pydantic schema
        from app.schemas.photos import BulkDeleteRequest
        bulk_delete_request = BulkDeleteRequest(
            photo_ids=delete_data.get("photo_ids", [])
        )

        # Use modular bulk service
        bulk_service = PhotoBulkService()
        return await bulk_service.bulk_delete_photos(
            site_id=normalized_site_id,
            delete_request=bulk_delete_request,
            current_user_id=current_user_id,
            db=db
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        raise HTTPException(status_code=500, detail=f"Errore eliminazione in blocco: {str(e)}")


# === DEEP ZOOM ENDPOINTS - MODULAR SERVICE VERSION ===

@router.post("/sites/{site_id}/photos/deep-zoom/start-background")
async def start_deep_zoom_background_processor(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Avvia il processore background per deep zoom tiles - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Use modular deep zoom service
        deepzoom_service = PhotoDeepZoomService()
        return await deepzoom_service.start_background_processor(
            site_id=str(site_id),
            current_user_id=current_user_id
        )

    except Exception as e:
        logger.error(f"Failed to start deep zoom background processor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start background processor: {str(e)}"
        )


@router.post("/sites/{site_id}/photos/deep-zoom/stop-background")
async def stop_deep_zoom_background_processor(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Ferma il processore background per deep zoom tiles - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Use modular deep zoom service
        deepzoom_service = PhotoDeepZoomService()
        return await deepzoom_service.stop_background_processor(
            site_id=str(site_id),
            current_user_id=current_user_id
        )

    except Exception as e:
        logger.error(f"Failed to stop deep zoom background processor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop background processor: {str(e)}"
        )


@router.get("/sites/{site_id}/photos/deep-zoom/background-status")
async def get_deep_zoom_background_status(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni lo stato del processore background per deep zoom tiles - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        # Use modular deep zoom service
        deepzoom_service = PhotoDeepZoomService()
        return await deepzoom_service.get_background_status(
            site_id=str(site_id)
        )

    except Exception as e:
        logger.error(f"Failed to get deep zoom background status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get background status: {str(e)}"
        )


@router.get("/sites/{site_id}/photos/{photo_id}/deep-zoom/task-status")
async def get_photo_deep_zoom_task_status(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni lo stato del task di processing per una foto specifica - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        # Use modular deep zoom service
        deepzoom_service = PhotoDeepZoomService()
        return await deepzoom_service.get_photo_task_status(
            site_id=str(site_id),
            photo_id=photo_id
        )

    except Exception as e:
        logger.error(f"Failed to get photo deep zoom task status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task status: {str(e)}"
        )


@router.post("/sites/{site_id}/photos/bulk-update")
async def bulk_update_photos(
        site_id: UUID,
        update_data: dict,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna più foto in blocco con supporto completo per metadati archeologici - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Prepare bulk update request using Pydantic schema
        bulk_update_request = BulkUpdateRequest(
            photo_ids=update_data.get("photo_ids", []),
            metadata=update_data.get("metadata", {}),
            add_tags=update_data.get("add_tags", []),
            remove_tags=update_data.get("remove_tags", [])
        )

        # Use modular bulk service
        bulk_service = PhotoBulkService()
        return await bulk_service.bulk_update_photos(
            site_id=str(site_id),
            update_request=bulk_update_request,
            current_user_id=current_user_id,
            db=db
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk update error: {e}")
        raise HTTPException(status_code=500, detail=f"Errore aggiornamento in blocco: {str(e)}")


async def log_user_activity(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        activity_type: str,
        activity_desc: str,
        extra_data: str = None,
        in_transaction: bool = False
):
    """Log attività utente nel sistema"""
    try:
        activity = UserActivity(
            user_id=user_id,
            site_id=site_id,
            activity_type=activity_type,
            activity_desc=activity_desc,
            extra_data=extra_data
        )

        db.add(activity)
        
        # Only commit if not already in a transaction
        if not in_transaction:
            await db.commit()
        
        logger.info(f"Activity logged: {activity_type} by {user_id}")

    except Exception as e:
        logger.error(f"Error logging activity: {e}")
        # Don't rollback here - let the calling transaction handle it
        # await db.rollback()  # REMOVED: This conflicts with async with db.begin()


# DUPLICATE ENDPOINTS REMOVED - These were conflicting with the modular service versions above
# The modular service versions (lines 507-590) should be used instead


