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
async def upload_photo(
        site_id: UUID,
        photos: List[UploadFile] = File(...),
        # Basic metadata
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        photo_type: Optional[str] = Form(None),
        photographer: Optional[str] = Form(None),
        keywords: Optional[str] = Form(None),
        # Queue control
        use_queue: Optional[bool] = Form(False),
        priority: Optional[str] = Form("normal"),

        # Archaeological metadata
        inventory_number: Optional[str] = Form(None),
        catalog_number: Optional[str] = Form(None),
        excavation_area: Optional[str] = Form(None),
        stratigraphic_unit: Optional[str] = Form(None),
        grid_square: Optional[str] = Form(None),
        depth_level: Optional[float] = Form(None),
        find_date: Optional[str] = Form(None),
        finder: Optional[str] = Form(None),
        excavation_campaign: Optional[str] = Form(None),

        # Material and object
        material: Optional[str] = Form(None),
        material_details: Optional[str] = Form(None),
        object_type: Optional[str] = Form(None),
        object_function: Optional[str] = Form(None),

        # Dimensions
        length_cm: Optional[float] = Form(None),
        width_cm: Optional[float] = Form(None),
        height_cm: Optional[float] = Form(None),
        diameter_cm: Optional[float] = Form(None),
        weight_grams: Optional[float] = Form(None),

        # Chronology
        chronology_period: Optional[str] = Form(None),
        chronology_culture: Optional[str] = Form(None),
        dating_from: Optional[str] = Form(None),
        dating_to: Optional[str] = Form(None),
        dating_notes: Optional[str] = Form(None),

        # Conservation
        conservation_status: Optional[str] = Form(None),
        conservation_notes: Optional[str] = Form(None),
        restoration_history: Optional[str] = Form(None),

        # References
        bibliography: Optional[str] = Form(None),
        comparative_references: Optional[str] = Form(None),
        external_links: Optional[str] = Form(None),

        # Rights
        copyright_holder: Optional[str] = Form(None),
        license_type: Optional[str] = Form(None),
        usage_rights: Optional[str] = Form(None),

        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Upload foto al sito archeologico - MODULAR SERVICE VERSION"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Prepare upload request using Pydantic schema
    upload_request = PhotoUploadRequest(
        title=title,
        description=description,
        photo_type=photo_type,
        photographer=photographer,
        keywords=keywords,
        use_queue=use_queue,
        priority=priority,
        inventory_number=inventory_number,
        catalog_number=catalog_number,
        excavation_area=excavation_area,
        stratigraphic_unit=stratigraphic_unit,
        grid_square=grid_square,
        depth_level=depth_level,
        find_date=find_date,
        finder=finder,
        excavation_campaign=excavation_campaign,
        material=material,
        material_details=material_details,
        object_type=object_type,
        object_function=object_function,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        diameter_cm=diameter_cm,
        weight_grams=weight_grams,
        chronology_period=chronology_period,
        chronology_culture=chronology_culture,
        dating_from=dating_from,
        dating_to=dating_to,
        dating_notes=dating_notes,
        conservation_status=conservation_status,
        conservation_notes=conservation_notes,
        restoration_history=restoration_history,
        bibliography=bibliography,
        comparative_references=comparative_references,
        external_links=external_links,
        copyright_holder=copyright_holder,
        license_type=license_type,
        usage_rights=usage_rights
    )

    # Use modular upload service
    upload_service = PhotoUploadService()
    return await upload_service.process_photo_upload(
        site_id=site_id,
        user_id=current_user_id,
        photos=photos,
        upload_request=upload_request,
        db=db
    )


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


# REMOVED: Duplicate endpoints get_photo_thumbnail and get_photo_full
# These are now handled by the consolidated _simple versions above:
# - get_photo_thumbnail_simple at line 36
# - get_photo_full_simple at line 52
# - get_photo_download_simple at line 68


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
        bulk_service = PhotoBulkService(db)
        return await bulk_service.update_single_photo(
            site_id=str(site_id),
            photo_id=str(photo_id),
            user_id=str(current_user_id),
            update_data=update_data
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
    deletion_service = PhotoDeletionService(db)
    return await deletion_service.delete_photo(
        site_id=str(site_id),
        photo_id=str(photo_id),
        user_id=str(current_user_id)
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
        bulk_service = PhotoBulkService(db)
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
        deepzoom_service = PhotoDeepZoomService(db)
        return await deepzoom_service.start_background_processor(
            site_id=str(site_id),
            user_id=str(current_user_id)
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
        deepzoom_service = PhotoDeepZoomService(db)
        return await deepzoom_service.stop_background_processor(
            site_id=str(site_id),
            user_id=str(current_user_id)
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
        deepzoom_service = PhotoDeepZoomService(db)
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
        deepzoom_service = PhotoDeepZoomService(db)
        return await deepzoom_service.get_photo_task_status(
            site_id=str(site_id),
            photo_id=str(photo_id)
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
        bulk_service = PhotoBulkService(db)
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


@router.post("/sites/{site_id}/photos/deep-zoom/start-background")
async def start_deep_zoom_background_processor(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id)
):
    """Avvia il processore background per deep zoom tiles"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        await deep_zoom_background_service.start_background_processor()

        logger.info(f"Deep zoom background processor started by user {current_user_id} for site {site_id}")

        return {
            "message": "Deep zoom background processor started successfully",
            "site_id": str(site_id),
            "started_by": str(current_user_id),
            "started_at": datetime.now().isoformat()
        }

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
        current_user_id: UUID = Depends(get_current_user_id)
):
    """Ferma il processore background per deep zoom tiles"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        await deep_zoom_background_service.stop_background_processor()

        logger.info(f"Deep zoom background processor stopped by user {current_user_id} for site {site_id}")

        return {
            "message": "Deep zoom background processor stopped successfully",
            "site_id": str(site_id),
            "stopped_by": str(current_user_id),
            "stopped_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to stop deep zoom background processor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop background processor: {str(e)}"
        )


@router.get("/sites/{site_id}/photos/deep-zoom/background-status")
async def get_deep_zoom_background_status(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access)
):
    """Ottieni lo stato del processore background per deep zoom tiles"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        queue_status = await deep_zoom_background_service.get_queue_status()

        return {
            "site_id": str(site_id),
            "background_status": queue_status,
            "timestamp": datetime.now().isoformat()
        }

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
        site_access: tuple = Depends(get_site_access)
):
    """Ottieni lo stato del task di processing per una foto specifica"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        task_status = await deep_zoom_background_service.get_task_status(str(photo_id))

        if not task_status:
            # Fallback to processing status from MinIO
            processing_status = await deep_zoom_minio_service.get_processing_status(str(site_id), str(photo_id))

            return {
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "task_status": None,
                "processing_status": processing_status,
                "message": "Task not found in background service, checking MinIO status"
            }

        return {
            "site_id": str(site_id),
            "photo_id": str(photo_id),
            "task_status": task_status,
            "message": "Task status from background service"
        }

    except Exception as e:
        logger.error(f"Failed to get photo deep zoom task status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task status: {str(e)}"
        )


async def _handle_queued_upload(
        site_id: UUID,
        photos: List[UploadFile],
        title: Optional[str],
        description: Optional[str],
        photo_type: Optional[str],
        photographer: Optional[str],
        keywords: Optional[str],
        inventory_number: Optional[str],
        catalog_number: Optional[str],
        excavation_area: Optional[str],
        stratigraphic_unit: Optional[str],
        grid_square: Optional[str],
        depth_level: Optional[float],
        find_date: Optional[str],
        finder: Optional[str],
        excavation_campaign: Optional[str],
        material: Optional[str],
        material_details: Optional[str],
        object_type: Optional[str],
        object_function: Optional[str],
        length_cm: Optional[float],
        width_cm: Optional[float],
        height_cm: Optional[float],
        diameter_cm: Optional[float],
        weight_grams: Optional[float],
        chronology_period: Optional[str],
        chronology_culture: Optional[str],
        dating_from: Optional[str],
        dating_to: Optional[str],
        dating_notes: Optional[str],
        conservation_status: Optional[str],
        conservation_notes: Optional[str],
        restoration_history: Optional[str],
        bibliography: Optional[str],
        comparative_references: Optional[str],
        external_links: Optional[str],
        copyright_holder: Optional[str],
        license_type: Optional[str],
        usage_rights: Optional[str],
        site_access: tuple,
        current_user_id: UUID,
        db: AsyncSession,
        priority: str = "normal"
):
    """Handle upload through queue system"""

    from app.services.request_queue_service import request_queue_service, RequestPriority

    # Map priority string to enum
    priority_map = {
        "critical": RequestPriority.CRITICAL,
        "high": RequestPriority.HIGH,
        "normal": RequestPriority.NORMAL,
        "low": RequestPriority.LOW,
        "bulk": RequestPriority.BULK
    }

    request_priority = priority_map.get(priority.lower(), RequestPriority.NORMAL)

    # Prepare upload data for queue
    upload_data = {
        'site_id': str(site_id),
        'user_id': str(current_user_id),
        'photos_count': len(photos),
        'metadata': {
            'title': title,
            'description': description,
            'photo_type': photo_type,
            'photographer': photographer,
            'keywords': keywords,
            'inventory_number': inventory_number,
            'catalog_number': catalog_number,
            'excavation_area': excavation_area,
            'stratigraphic_unit': stratigraphic_unit,
            'grid_square': grid_square,
            'depth_level': depth_level,
            'find_date': find_date,
            'finder': finder,
            'excavation_campaign': excavation_campaign,
            'material': material,
            'material_details': material_details,
            'object_type': object_type,
            'object_function': object_function,
            'length_cm': length_cm,
            'width_cm': width_cm,
            'height_cm': height_cm,
            'diameter_cm': diameter_cm,
            'weight_grams': weight_grams,
            'chronology_period': chronology_period,
            'chronology_culture': chronology_culture,
            'dating_from': dating_from,
            'dating_to': dating_to,
            'dating_notes': dating_notes,
            'conservation_status': conservation_status,
            'conservation_notes': conservation_notes,
            'restoration_history': restoration_history,
            'bibliography': bibliography,
            'comparative_references': comparative_references,
            'external_links': external_links,
            'copyright_holder': copyright_holder,
            'license_type': license_type,
            'usage_rights': usage_rights
        }
    }

    # Estimate processing time based on file count
    estimated_duration = len(photos) * 30  # 30 seconds per photo estimate

    try:
        # Enqueue upload request
        request_id = await request_queue_service.enqueue_request(
            request_type="POST_/api/site/{site_id}/photos/upload",
            payload=upload_data,
            priority=request_priority,
            user_id=str(current_user_id),
            site_id=str(site_id),
            timeout_seconds=600 + (len(photos) * 60),  # Base 10min + 1min per photo
            max_retries=3,
            estimated_duration=estimated_duration
        )

        # Store files temporarily for queue processing
        temp_files = []
        upload_paths = []

        try:
            from app.services.storage_service import storage_service

            for photo in photos:
                # Save to temporary location
                filename, file_path, file_size = await storage_service.save_upload_file(
                    photo, str(site_id), str(current_user_id), temp=True
                )
                temp_files.append({
                    'filename': filename,
                    'file_path': file_path,
                    'file_size': file_size,
                    'original_filename': photo.filename
                })
                upload_paths.append(file_path)

            # Update request payload with file info
            upload_data['temp_files'] = temp_files

            logger.info(
                f"Queued upload request {request_id} for {len(photos)} photos with priority {request_priority.name}")

            return JSONResponse({
                'message': f'Upload queued for processing',
                'request_id': request_id,
                'status': 'queued',
                'priority': request_priority.name,
                'photos_count': len(photos),
                'estimated_wait': await request_queue_service._estimate_wait_time(request_priority),
                'queue_status_url': f'/api/queue/request/{request_id}'
            }, status_code=status.HTTP_202_ACCEPTED)

        except Exception as e:
            # Clean up temp files if queueing fails
            logger.error(f"Failed to prepare temp files for queue: {e}")
            try:
                from app.services.storage_service import storage_service
                for file_path in upload_paths:
                    await storage_service.delete_file(file_path)
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup temp files: {cleanup_error}")
            raise

    except Exception as e:
        logger.error(f"Failed to queue upload request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue upload: {str(e)}"
        )


async def process_queued_upload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process queued upload request"""

    from app.services.storage_service import storage_service
    from app.services.photo_metadata_service import photo_metadata_service
    from app.services.deep_zoom_background_service import deep_zoom_background_service
    from app.models import Photo
    from sqlalchemy import select
    import uuid
    import aiofiles
    from io import BytesIO

    logger.info(f"Processing queued upload for site {payload['site_id']}")

    try:
        site_id = uuid.UUID(payload['site_id'])
        user_id = uuid.UUID(payload['user_id'])
        metadata = payload['metadata']
        temp_files = payload.get('temp_files', [])

        # Process each photo
        uploaded_photos = []
        photos_needing_tiles = []

        for temp_file in temp_files:
            try:
                # Check if temp file exists before moving
                from app.services.storage_service import storage_service
                temp_file_exists = await storage_service.file_exists(temp_file['file_path'])
                if not temp_file_exists:
                    logger.error(f"Temp file not found: {temp_file['file_path']}")
                    continue

                # Move temp file to permanent location
                permanent_path = await storage_service.move_temp_file(
                    temp_file['file_path'],
                    str(site_id),
                    str(user_id)
                )

                # Extract metadata from the actual file
                file_metadata = {}
                try:
                    # Create a file-like object from the permanent path for metadata extraction
                    async with aiofiles.open(permanent_path, 'rb') as f:
                        # Create a simple file-like object for metadata extraction
                        content = await f.read()
                        file_like = BytesIO(content)
                        file_like.filename = temp_file['original_filename']

                        exif_data, extracted_metadata = await photo_metadata_service.extract_metadata_from_file(
                            file_like, temp_file['filename']
                        )
                        file_metadata = extracted_metadata
                except Exception as metadata_error:
                    logger.warning(f"Failed to extract metadata for {temp_file.get('filename')}: {metadata_error}")
                    # Continue with empty metadata if extraction fails

                # Create photo record
                photo_record = await photo_metadata_service.create_photo_record(
                    filename=temp_file['filename'],
                    original_filename=temp_file['original_filename'],
                    file_path=permanent_path,
                    file_size=temp_file['file_size'],
                    site_id=str(site_id),
                    uploaded_by=str(user_id),
                    metadata=file_metadata,
                    archaeological_metadata=metadata
                )

                # Save to database
                from app.database.base import async_session_maker
                async with async_session_maker() as db:
                    try:
                        db.add(photo_record)
                        await db.commit()
                        await db.refresh(photo_record)
                        logger.info(f"Photo record saved with ID: {photo_record.id}")
                    except Exception as db_commit_error:
                        logger.error(
                            f"Database commit failed for queued photo {temp_file.get('filename')}: {db_commit_error}")
                        # Don't try to rollback here - let the session handle it naturally
                        raise Exception(f"Database error: Unable to save photo record: {db_commit_error}")

                    # Generate thumbnail after database save
                    try:
                        async with aiofiles.open(permanent_path, 'rb') as f:
                            content = await f.read()
                            file_like = BytesIO(content)
                            file_like.filename = temp_file['original_filename']

                            thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                                file_like, str(photo_record.id)
                            )

                            if thumbnail_path:
                                photo_record.thumbnail_path = thumbnail_path
                                try:
                                    await db.commit()
                                    logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
                                except Exception as thumbnail_commit_error:
                                    logger.error(f"Failed to commit thumbnail update: {thumbnail_commit_error}")
                                    # Don't try to rollback here - let the session handle it naturally
                            else:
                                logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")
                    except Exception as thumbnail_error:
                        logger.error(f"Thumbnail generation error for photo {photo_record.id}: {thumbnail_error}")
                        # Don't fail the upload if thumbnail generation fails

                uploaded_photos.append({
                    'photo_id': str(photo_record.id),
                    'filename': temp_file['filename'],
                    'original_filename': temp_file['original_filename'],
                    'file_size': temp_file['file_size'],
                    'file_path': permanent_path,
                    'metadata': {
                        'width': photo_record.width,
                        'height': photo_record.height,
                        'photo_date': photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                        'camera_model': photo_record.camera_model
                    },
                    'archaeological_metadata': {
                        'inventory_number': photo_record.inventory_number,
                        'excavation_area': photo_record.excavation_area,
                        'material': photo_record.material,
                        'chronology_period': photo_record.chronology_period,
                        'photo_type': photo_record.photo_type,
                        'photographer': photo_record.photographer,
                        'description': photo_record.description,
                        'keywords': photo_record.keywords
                    }
                })

                # Check if tiles are needed (larger files or high resolution)
                width = photo_record.width or 0
                height = photo_record.height or 0
                max_dimension = max(width, height)
                file_size_mb = temp_file['file_size'] / (1024 * 1024)

                if max_dimension > 2000 or file_size_mb > 5:  # Large images need tiles
                    photos_needing_tiles.append({
                        'photo_id': str(photo_record.id),
                        'file_path': permanent_path,
                        'width': width,
                        'height': height,
                        'archaeological_metadata': metadata
                    })

                logger.info(
                    f"Queued upload: Successfully processed photo {photo_record.id} ({temp_file['original_filename']})")

            except Exception as e:
                logger.error(f"Error processing queued photo {temp_file.get('filename')}: {e}")
                continue

        # Schedule tile processing if needed
        if photos_needing_tiles:
            try:
                await deep_zoom_background_service.schedule_batch_processing(
                    photos_list=photos_needing_tiles,
                    site_id=str(site_id)
                )
                logger.info(f"Scheduled deep zoom processing for {len(photos_needing_tiles)} photos")
            except Exception as tile_error:
                logger.error(f"Failed to schedule tile processing: {tile_error}")
                # Don't fail entire upload if tile scheduling fails

        return {
            'status': 'completed',
            'message': f'Processed {len(uploaded_photos)} photos successfully',
            'uploaded_photos': uploaded_photos,
            'photos_needing_tiles': len(photos_needing_tiles),
            'processed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error processing queued upload: {e}")
        raise Exception(f"Upload processing failed: {str(e)}")


