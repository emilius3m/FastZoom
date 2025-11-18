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
        request: Request,
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

    # DEBUG: Log request details
    logger.info(f"🔍 DEBUG - Request URL: {request.url}")
    logger.info(f"🔍 DEBUG - Request headers: {dict(request.headers)}")
    logger.info(f"🔍 DEBUG - Request method: {request.method}")
    
    # DEBUG: Log all incoming form data with types
    logger.info(f"🔍 DEBUG - Form data received:")
    logger.info(f"  - title: {title} (type: {type(title).__name__})")
    logger.info(f"  - description: {description} (type: {type(description).__name__})")
    logger.info(f"  - photo_type: {photo_type} (type: {type(photo_type).__name__})")
    logger.info(f"  - photographer: {photographer} (type: {type(photographer).__name__})")
    logger.info(f"  - keywords: {keywords} (type: {type(keywords).__name__})")
    logger.info(f"  - use_queue: {use_queue} (type: {type(use_queue).__name__})")
    logger.info(f"  - priority: {priority} (type: {type(priority).__name__})")
    
    logger.info(f"🔍 DEBUG - Archaeological data:")
    logger.info(f"  - inventory_number: {inventory_number} (type: {type(inventory_number).__name__})")
    logger.info(f"  - catalog_number: {catalog_number} (type: {type(catalog_number).__name__})")
    logger.info(f"  - excavation_area: {excavation_area} (type: {type(excavation_area).__name__})")
    logger.info(f"  - stratigraphic_unit: {stratigraphic_unit} (type: {type(stratigraphic_unit).__name__})")
    logger.info(f"  - grid_square: {grid_square} (type: {type(grid_square).__name__})")
    logger.info(f"  - depth_level: {depth_level} (type: {type(depth_level).__name__})")
    logger.info(f"  - find_date: {find_date} (type: {type(find_date).__name__})")
    logger.info(f"  - finder: {finder} (type: {type(finder).__name__})")
    logger.info(f"  - excavation_campaign: {excavation_campaign} (type: {type(excavation_campaign).__name__})")
    
    logger.info(f"🔍 DEBUG - Material data:")
    logger.info(f"  - material: {material} (type: {type(material).__name__})")
    logger.info(f"  - material_details: {material_details} (type: {type(material_details).__name__})")
    logger.info(f"  - object_type: {object_type} (type: {type(object_type).__name__})")
    logger.info(f"  - object_function: {object_function} (type: {type(object_function).__name__})")
    
    logger.info(f"🔍 DEBUG - Dimension data:")
    logger.info(f"  - length_cm: {length_cm} (type: {type(length_cm).__name__})")
    logger.info(f"  - width_cm: {width_cm} (type: {type(width_cm).__name__})")
    logger.info(f"  - height_cm: {height_cm} (type: {type(height_cm).__name__})")
    logger.info(f"  - diameter_cm: {diameter_cm} (type: {type(diameter_cm).__name__})")
    logger.info(f"  - weight_grams: {weight_grams} (type: {type(weight_grams).__name__})")
    
    logger.info(f"🔍 DEBUG - Chronology data:")
    logger.info(f"  - chronology_period: {chronology_period} (type: {type(chronology_period).__name__})")
    logger.info(f"  - chronology_culture: {chronology_culture} (type: {type(chronology_culture).__name__})")
    logger.info(f"  - dating_from: {dating_from} (type: {type(dating_from).__name__})")
    logger.info(f"  - dating_to: {dating_to} (type: {type(dating_to).__name__})")
    logger.info(f"  - dating_notes: {dating_notes} (type: {type(dating_notes).__name__})")
    
    logger.info(f"🔍 DEBUG - Conservation data:")
    logger.info(f"  - conservation_status: {conservation_status} (type: {type(conservation_status).__name__})")
    logger.info(f"  - conservation_notes: {conservation_notes} (type: {type(conservation_notes).__name__})")
    logger.info(f"  - restoration_history: {restoration_history} (type: {type(restoration_history).__name__})")
    
    logger.info(f"🔍 DEBUG - References data:")
    logger.info(f"  - bibliography: {bibliography} (type: {type(bibliography).__name__})")
    logger.info(f"  - comparative_references: {comparative_references} (type: {type(comparative_references).__name__})")
    logger.info(f"  - external_links: {external_links} (type: {type(external_links).__name__})")
    
    logger.info(f"🔍 DEBUG - Rights data:")
    logger.info(f"  - copyright_holder: {copyright_holder} (type: {type(copyright_holder).__name__})")
    logger.info(f"  - license_type: {license_type} (type: {type(license_type).__name__})")
    logger.info(f"  - usage_rights: {usage_rights} (type: {type(usage_rights).__name__})")
    
    # DEBUG: Log photos info
    logger.info(f"🔍 DEBUG - Photos info:")
    for i, photo in enumerate(photos):
        logger.info(f"  - Photo {i}: {photo.filename} (size: {photo.size}, content_type: {photo.content_type})")
    
    # Prepare upload data as dictionary to avoid Pydantic validation issues
    upload_data = {
        'title': title,
        'description': description,
        'photo_type': photo_type,
        'photographer': photographer,
        'keywords': keywords,
        'use_queue': use_queue,
        'priority': priority,
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
    
    # DEBUG: Log the dictionary data before Pydantic validation
    logger.info(f"🔍 DEBUG - Upload data dictionary: {upload_data}")
    
    # Create PhotoUploadRequest from dictionary to allow validation
    try:
        upload_request = PhotoUploadRequest(**upload_data)
        logger.info(f"✅ DEBUG - PhotoUploadRequest created successfully")
    except Exception as validation_error:
        logger.error(f"❌ Pydantic validation failed: {validation_error}")
        logger.error(f"🔍 DEBUG - Validation error type: {type(validation_error).__name__}")
        
        # Get detailed validation errors
        if hasattr(validation_error, 'errors'):
            logger.error(f"🔍 DEBUG - Validation errors: {validation_error.errors()}")
        elif hasattr(validation_error, 'json'):
            logger.error(f"🔍 DEBUG - Validation errors JSON: {validation_error.json()}")
        else:
            logger.error(f"🔍 DEBUG - Validation error details: {getattr(validation_error, 'errors', 'No errors available')}")
        
        # Try to create PhotoUploadRequest with only the fields that are not None
        filtered_data = {k: v for k, v in upload_data.items() if v is not None and v != ''}
        logger.info(f"🔍 DEBUG - Trying with filtered data: {filtered_data}")
        logger.info(f"🔍 DEBUG - Filtered data length: {len(filtered_data)} vs original: {len(upload_data)}")
        
        try:
            upload_request = PhotoUploadRequest(**filtered_data)
            logger.info(f"✅ DEBUG - PhotoUploadRequest created with filtered data")
        except Exception as filtered_validation_error:
            logger.error(f"❌ Filtered Pydantic validation also failed: {filtered_validation_error}")
            logger.error(f"🔍 DEBUG - Filtered validation error type: {type(filtered_validation_error).__name__}")
            
            if hasattr(filtered_validation_error, 'errors'):
                logger.error(f"🔍 DEBUG - Filtered validation errors: {filtered_validation_error.errors()}")
            elif hasattr(filtered_validation_error, 'json'):
                logger.error(f"🔍 DEBUG - Filtered validation errors JSON: {filtered_validation_error.json()}")
            
            # Create detailed error response
            error_details = {
                "error": str(filtered_validation_error),
                "type": type(filtered_validation_error).__name__,
                "validation_details": getattr(filtered_validation_error, 'errors', None),
                "upload_data": upload_data,
                "filtered_data": filtered_data
            }
            
            logger.error(f"🔍 DEBUG - Complete error details: {error_details}")
            
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Validation error: {str(filtered_validation_error)}",
                    "validation_errors": getattr(filtered_validation_error, 'errors', None),
                    "debug_data": error_details
                }
            )

    # Use modular upload service
    upload_service = PhotoUploadService()
    return await upload_service.process_photo_upload(
        site_id=site_id,
        user_id=current_user_id,
        photos=photos,
        upload_request=upload_request,
        db=db,
        raw_metadata=upload_data  # Pass raw data as fallback
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


# DUPLICATE ENDPOINTS REMOVED - These were conflicting with the modular service versions above
# The modular service versions (lines 507-590) should be used instead


