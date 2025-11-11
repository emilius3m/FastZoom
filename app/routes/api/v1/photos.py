# app/routes/api/v1/photos.py - Photos API v1 endpoints

from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile
from fastapi.responses import JSONResponse
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
from app.core.security import get_current_user_id_with_blacklist
from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.models import UserActivity
from app.routes.api.dependencies import get_site_access
from app.services.storage_service import storage_service
from app.services.photo_metadata_service import photo_metadata_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.services.storage_management_service import storage_management_service

router = APIRouter()


@router.post("/sites/{site_id}/photos/upload", summary="Upload foto sito", tags=["Photos"])
async def v1_upload_photo(
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
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """API v1 per upload foto al sito archeologico"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Ensure MinIO buckets exist before uploading
        try:
            await storage_management_service.ensure_buckets_exist()
        except Exception as storage_error:
            logger.error(f"Storage service initialization failed: {storage_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is currently unavailable. Please try again later."
            )
        
        # Check storage health before uploading
        try:
            storage_usage = await storage_management_service.get_storage_usage()
            if storage_usage.get('total_size_gb', 0) > 8:  # >80% of 10GB
                logger.warning(f"Storage usage critical ({storage_usage.get('total_size_gb', 0)}GB), triggering cleanup")
                cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=1000)
                logger.info(f"Pre-upload cleanup: {cleanup_result}")
        except Exception as storage_health_error:
            logger.error(f"Storage health check failed: {storage_health_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage health check failed. Please try again later."
            )

        # Prepara TUTTI i metadati archeologici da form utente (una sola volta)
        archaeological_metadata_from_form = {}
        
        # Basic metadata
        if title:
            archaeological_metadata_from_form['title'] = title
        if description:
            archaeological_metadata_from_form['description'] = description
        if photographer:
            archaeological_metadata_from_form['photographer'] = photographer
        if keywords:
            archaeological_metadata_from_form['keywords'] = keywords
        if photo_type:
            archaeological_metadata_from_form['photo_type'] = photo_type
        
        # Archaeological context
        if inventory_number:
            archaeological_metadata_from_form['inventory_number'] = inventory_number
        if catalog_number:
            archaeological_metadata_from_form['catalog_number'] = catalog_number
        if excavation_area:
            archaeological_metadata_from_form['excavation_area'] = excavation_area
        if stratigraphic_unit:
            archaeological_metadata_from_form['stratigraphic_unit'] = stratigraphic_unit
        if grid_square:
            archaeological_metadata_from_form['grid_square'] = grid_square
        if depth_level is not None:
            archaeological_metadata_from_form['depth_level'] = depth_level
        if find_date:
            try:
                archaeological_metadata_from_form['find_date'] = datetime.fromisoformat(find_date.replace('Z', '+00:00'))
            except ValueError:
                try:
                    archaeological_metadata_from_form['find_date'] = datetime.strptime(find_date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid find_date format: {find_date}")
        if finder:
            archaeological_metadata_from_form['finder'] = finder
        if excavation_campaign:
            archaeological_metadata_from_form['excavation_campaign'] = excavation_campaign
        
        # Material and object
        if material:
            archaeological_metadata_from_form['material'] = material
        if material_details:
            archaeological_metadata_from_form['material_details'] = material_details
        if object_type:
            archaeological_metadata_from_form['object_type'] = object_type
        if object_function:
            archaeological_metadata_from_form['object_function'] = object_function
        
        # Dimensions
        if length_cm is not None:
            archaeological_metadata_from_form['length_cm'] = length_cm
        if width_cm is not None:
            archaeological_metadata_from_form['width_cm'] = width_cm
        if height_cm is not None:
            archaeological_metadata_from_form['height_cm'] = height_cm
        if diameter_cm is not None:
            archaeological_metadata_from_form['diameter_cm'] = diameter_cm
        if weight_grams is not None:
            archaeological_metadata_from_form['weight_grams'] = weight_grams
        
        # Chronology
        if chronology_period:
            archaeological_metadata_from_form['chronology_period'] = chronology_period
        if chronology_culture:
            archaeological_metadata_from_form['chronology_culture'] = chronology_culture
        if dating_from:
            archaeological_metadata_from_form['dating_from'] = dating_from
        if dating_to:
            archaeological_metadata_from_form['dating_to'] = dating_to
        if dating_notes:
            archaeological_metadata_from_form['dating_notes'] = dating_notes
        
        # Conservation
        if conservation_status:
            archaeological_metadata_from_form['conservation_status'] = conservation_status
        if conservation_notes:
            archaeological_metadata_from_form['conservation_notes'] = conservation_notes
        if restoration_history:
            archaeological_metadata_from_form['restoration_history'] = restoration_history
        
        # References
        if bibliography:
            archaeological_metadata_from_form['bibliography'] = bibliography
        if comparative_references:
            archaeological_metadata_from_form['comparative_references'] = comparative_references
        if external_links:
            archaeological_metadata_from_form['external_links'] = external_links
        
        # Rights
        if copyright_holder:
            archaeological_metadata_from_form['copyright_holder'] = copyright_holder
        if license_type:
            archaeological_metadata_from_form['license_type'] = license_type
        if usage_rights:
            archaeological_metadata_from_form['usage_rights'] = usage_rights
        
        logger.info(f"📋 Processing {len(photos)} photos with metadata: {list(archaeological_metadata_from_form.keys())}")
        
        # Processa tutte le foto in parallelo con asyncio.gather()
        async def process_single_photo(file: UploadFile) -> Optional[dict]:
            """Processa una singola foto in modo asincrono con error handling completo"""
            photo_record = None
            filename = None
            file_path = None
            
            try:
                # 1. Salva file su MinIO con error handling
                try:
                    filename, file_path, file_size = await storage_service.save_upload_file(
                        file, str(site_id), str(current_user_id)
                    )
                except Exception as storage_error:
                    logger.error(f"Failed to save file {file.filename} to storage: {storage_error}")
                    raise HTTPException(
                        status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                        detail=f"Storage service error: Unable to save file {file.filename}"
                    )

                # 2. Estrai metadati dal file caricato con error handling
                try:
                    await file.seek(0)  # Reset file pointer
                    exif_data, metadata = await photo_metadata_service.extract_metadata_from_file(
                        file, filename
                    )
                except Exception as metadata_error:
                    logger.error(f"Failed to extract metadata from {file.filename}: {metadata_error}")
                    # Continue with empty metadata if extraction fails
                    exif_data, metadata = {}, {}

                # 3. Crea record nel database CON metadati archeologici con error handling
                try:
                    photo_record = await photo_metadata_service.create_photo_record(
                        filename=filename,
                        original_filename=file.filename,
                        file_path=file_path,
                        file_size=file_size,
                        site_id=str(site_id),
                        uploaded_by=str(current_user_id),
                        metadata=metadata,
                        archaeological_metadata=archaeological_metadata_from_form
                    )
                except Exception as record_creation_error:
                    logger.error(f"Failed to create photo record for {file.filename}: {record_creation_error}")
                    # Clean up uploaded file if record creation fails
                    try:
                        await storage_service.delete_file(file_path)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup file after record creation failure: {cleanup_error}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Database error: Unable to create photo record for {file.filename}"
                    )

                # 4. Create a NEW database session for this parallel task to avoid transaction conflicts
                from app.database.base import async_session_maker
                async with async_session_maker() as task_db:
                    try:
                        # Start transaction in new session
                        async with task_db.begin():
                            # Add photo record to transaction
                            task_db.add(photo_record)
                            
                            # Flush to get ID without committing
                            await task_db.flush()
                            await task_db.refresh(photo_record)
                            logger.info(f"Photo record flushed with ID: {photo_record.id}")
                            
                            # 5. Genera thumbnail DOPO che il record è stato salvato con error handling
                            try:
                                await file.seek(0)  # Reset file pointer per thumbnail
                                thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                                    file, str(photo_record.id)
                                )

                                if thumbnail_path:
                                    photo_record.thumbnail_path = thumbnail_path
                                    logger.info(f"Thumbnail generated: {thumbnail_path}")
                                else:
                                    logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")
                            except Exception as thumbnail_error:
                                logger.error(f"Thumbnail generation error for photo {photo_record.id}: {thumbnail_error}")
                                # Don't fail entire upload if thumbnail generation fails
                                # Just log error and continue
                            
                            # 6. Log attività con error handling
                            try:
                                activity = UserActivity(
                                    user_id=current_user_id,
                                    site_id=site_id,
                                    activity_type="UPLOAD",
                                    activity_desc=f"Caricata foto: {file.filename}",
                                    extra_data=json.dumps({
                                        "photo_id": str(photo_record.id),
                                        "filename": filename,
                                        "file_size": file_size
                                    })
                                )
                                task_db.add(activity)
                                logger.info(f"Activity log added for photo {photo_record.id}")
                            except Exception as activity_error:
                                logger.error(f"Failed to log activity for photo {photo_record.id}: {activity_error}")
                                # Don't fail upload if activity logging fails
                        
                        # Transaction commits automatically here
                        logger.info(f"Transaction committed successfully for photo {photo_record.id}")
                        
                    except Exception as db_error:
                        logger.error(f"Database transaction failed for photo {file.filename}: {db_error}")
                        # Clean up uploaded file if database transaction fails
                        try:
                            await storage_service.delete_file(file_path)
                        except Exception as cleanup_error:
                            logger.error(f"Failed to cleanup file after DB transaction failure: {cleanup_error}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Database error: Unable to save photo record"
                        )

                logger.info(f"Photo {photo_record.id} saved with thumbnail_path: {photo_record.thumbnail_path}")
                logger.info(f"Photo uploaded successfully: {photo_record.id} by user {current_user_id}")

                return {
                    "photo_id": str(photo_record.id),
                    "filename": filename,
                    "file_size": file_size,
                    "file_path": file_path,
                    "metadata": {
                        "width": photo_record.width,
                        "height": photo_record.height,
                        "photo_date": photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                        "camera_model": photo_record.camera_model
                    },
                    "archaeological_metadata": {
                        'inventory_number': photo_record.inventory_number,
                        'excavation_area': photo_record.excavation_area,
                        'material': photo_record.material,
                        'chronology_period': photo_record.chronology_period,
                        'photo_type': photo_record.photo_type,
                        'photographer': photo_record.photographer,
                        'description': photo_record.description,
                        'keywords': photo_record.keywords
                    }
                }
                
            except HTTPException as he:
                # Re-raise HTTP exceptions as-is
                if he.status_code == 507:  # Storage full
                    logger.error(f"Storage full during upload of {file.filename}")
                    try:
                        cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=2000)
                        if cleanup_result['success']:
                            logger.info(f"Emergency cleanup successful: {cleanup_result['total_freed_mb']}MB freed")
                        else:
                            logger.error(f"Emergency cleanup failed: {cleanup_result}")
                    except Exception as cleanup_error:
                        logger.error(f"Cleanup attempt failed: {cleanup_error}")
                raise he
                
            except Exception as photo_error:
                logger.error(f"Unexpected error processing photo {file.filename}: {photo_error}")
                # Clean up file if it exists
                if file_path:
                    try:
                        await storage_service.delete_file(file_path)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup file after error: {cleanup_error}")
                # Return None for this photo but don't fail entire batch
                return None

        # Processa tutte le foto in parallelo con error handling
        try:
            logger.info(f"🚀 Starting parallel processing of {len(photos)} photos")
            upload_tasks = [process_single_photo(file) for file in photos]
            upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)
            
            # Filtra risultati validi
            uploaded_photos = []
            failed_photos = []
            
            for i, result in enumerate(upload_results):
                if isinstance(result, Exception):
                    logger.error(f"Upload task failed for photo {photos[i].filename}: {result}")
                    failed_photos.append({
                        "filename": photos[i].filename,
                        "error": str(result)
                    })
                elif result is not None:
                    uploaded_photos.append(result)
                else:
                    # None result indicates a failed upload that was handled gracefully
                    failed_photos.append({
                        "filename": photos[i].filename,
                        "error": "Processing failed but was handled gracefully"
                    })
            
            logger.info(f"✅ Parallel processing completed: {len(uploaded_photos)} photos uploaded successfully, {len(failed_photos)} failed")
            
            # If no photos were uploaded successfully, raise an error
            if not uploaded_photos and failed_photos:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"All photo uploads failed. First error: {failed_photos[0]['error']}"
                )
                
        except Exception as parallel_error:
            logger.error(f"Parallel processing error: {parallel_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error during parallel processing: {str(parallel_error)}"
            )

        # Prepare response metadata
        response_metadata = {
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "total_uploaded": len(uploaded_photos),
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Include failed photos information if any
        if 'failed_photos' in locals() and failed_photos:
            response_metadata["failed_photos"] = failed_photos
            response_metadata["total_failed"] = len(failed_photos)

        # Return uploaded_photos as direct field with metadata
        response_data = {
            "uploaded_photos": uploaded_photos,
            **response_metadata
        }

        logger.info(f"✅ Upload API response: {len(uploaded_photos)} foto caricate")

        return JSONResponse(response_data)

    except HTTPException as he:
        # Re-raise HTTP exceptions with proper status codes
        raise he
    except Exception as e:
        logger.error(f"Unexpected upload error: {str(e)}")
        # Clean up any temporary files if they exist
        try:
            if 'file_path' in locals():
                await storage_service.delete_file(file_path)
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup during error handling: {cleanup_error}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during upload: {str(e)}"
        )


@router.get("/sites/{site_id}/photos", summary="Foto sito", tags=["Photos"])
async def v1_get_site_photos(
        site_id: UUID,
        search: str = None,
        photo_type: str = None,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """API v1 per ottenere foto del sito con filtri base"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Query base
    photos_query = select(Photo).where(Photo.site_id == str(site_id))

    # Apply filters
    if search:
        search_term = f"%{search}%"
        photos_query = photos_query.where(
            or_(
                Photo.filename.ilike(search_term),
                Photo.title.ilike(search_term),
                Photo.description.ilike(search_term),
                Photo.inventory_number.ilike(search_term),
                Photo.keywords.ilike(search_term)
            )
        )

    if photo_type:
        try:
            photos_query = photos_query.where(Photo.photo_type == PhotoType(photo_type))
        except ValueError:
            pass

    # Order by creation date desc
    photos_query = photos_query.order_by(Photo.created_at.desc())

    # Execute query
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    # Convert to response format
    photos_data = []
    for photo in photos:
        photo_dict = {
            "id": str(photo.id),
            "site_id": str(photo.site_id),
            "filename": photo.filename,
            "original_filename": photo.original_filename,
            "file_size": photo.file_size,
            "mime_type": photo.mime_type,
            
            # Image metadata
            "width": photo.width,
            "height": photo.height,
            "format": photo.format,
            "color_space": photo.color_space,
            "color_profile": photo.color_profile,
            
            # Photo metadata
            "title": photo.title,
            "description": photo.description,
            "keywords": photo.get_keywords_list(),
            "photo_type": str(photo.photo_type) if photo.photo_type else None,
            "photographer": photo.photographer,
            "photo_date": photo.photo_date.isoformat() if photo.photo_date else None,
            
            # URLs
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "full_url": f"/photos/{photo.id}/full",
            "file_url": f"/photos/{photo.id}/full",
            
            # Management
            "is_published": photo.is_published,
            "is_validated": photo.is_validated,
            "created_at": photo.created_at.isoformat(),
            "updated_at": photo.updated_at.isoformat() if photo.updated_at else None,
        }
        photos_data.append(photo_dict)

    logger.info(f"Photos API v1: Returned {len(photos_data)} photos with filters: search={search}, photo_type={photo_type}")

    return JSONResponse(photos_data)