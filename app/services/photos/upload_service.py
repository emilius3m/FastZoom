# app/services/photos/upload_service.py - Photo upload business logic service

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from fastapi import HTTPException, status, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.base import async_session_maker
from app.models import Photo, UserActivity
from app.services.storage_service import storage_service
from app.services.photo_service import photo_metadata_service
from app.services.storage_management_service import storage_management_service
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.schemas.photos import PhotoUploadRequest


class PhotoUploadService:
    """
    Service class for handling photo upload business logic.
    Separates upload concerns from routing layer for better testability and maintainability.
    """

    def __init__(self):
        self.parallel_processing_threshold = 3  # Files count to trigger parallel vs sequential
        self.max_file_size_mb = 50  # Maximum file size limit
        self.min_dimension_for_tiles = 2000  # Minimum dimension for deep zoom tiles

    async def process_photo_upload(
        self,
        site_id: UUID,
        user_id: UUID,
        photos: List[UploadFile],
        upload_request: PhotoUploadRequest,
        db: AsyncSession
    ) -> JSONResponse:
        """
        Main entry point for photo upload processing.
        Handles queue detection, storage checks, and coordinate processing.
        """
        
        # Check if we should use queue based on system load or explicit request
        should_queue = await self._should_use_queue(upload_request.use_queue)
        
        if should_queue:
            return await self._handle_queued_upload(
                site_id, user_id, photos, upload_request, db, upload_request.priority
            )

        # Process upload directly with storage and processing coordination
        return await self._process_direct_upload(
            site_id, user_id, photos, upload_request, db
        )

    async def _should_use_queue(self, explicit_request: bool) -> bool:
        """Determine if upload should be queued based on system conditions."""
        
        if explicit_request:
            return True
            
        try:
            from app.services.request_queue_service import request_queue_service
            from app.core.config import get_settings
            settings = get_settings()
            
            return (
                settings.queue_enabled and
                (request_queue_service.system_monitor.is_system_overloaded() or
                 request_queue_service.system_monitor.get_load_factor() > 0.6)
            )
        except Exception as e:
            logger.warning(f"Failed to check queue conditions: {e}")
            return False

    async def _process_direct_upload(
        self,
        site_id: UUID,
        user_id: UUID,
        photos: List[UploadFile],
        upload_request: PhotoUploadRequest,
        db: AsyncSession
    ) -> JSONResponse:
        """
        Process photos upload directly without queueing.
        """
        
        # Pre-upload validation and storage checks
        await self._validate_and_prepare_storage(photos)

        # Prepare archaeological metadata from Pydantic schema
        archaeological_metadata = self._prepare_archaeological_metadata(upload_request)

        logger.info(f"📋 Processing {len(photos)} photos with upload service: {list(archaeological_metadata.keys())}")

        # Process photos (parallel or sequential based on count)
        upload_results = await self._process_photos_parallel_or_sequential(
            photos, site_id, user_id, archaeological_metadata
        )

        # Filter and validate results
        uploaded_photos, failed_photos = self._filter_upload_results(photos, upload_results)

        # Handle tile processing for large images
        photos_needing_tiles = await self._identify_photos_needing_tiles(uploaded_photos, site_id, db)

        # Schedule deep zoom processing if needed
        await self._schedule_tile_processing(photos_needing_tiles, site_id)

        # Prepare and return response
        return self._prepare_upload_response(uploaded_photos, failed_photos, photos_needing_tiles)

    async def _validate_and_prepare_storage(self, photos: List[UploadFile]):
        """Validate files and ensure storage is ready."""
        
        # Check storage health and capacity
        try:
            await storage_management_service.ensure_buckets_exist()
        except Exception as storage_error:
            logger.error(f"Storage service initialization failed: {storage_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is currently unavailable. Please try again later."
            )

        # Check storage capacity
        try:
            storage_usage = await storage_management_service.get_storage_usage()
            if storage_usage.get('total_size_gb', 0) > 8:  # >80% of 10GB
                logger.warning(f"Storage usage critical ({storage_usage.get('total_size_gb', 0)}GB)")
                cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=1000)
                logger.info(f"Pre-upload cleanup: {cleanup_result}")
        except Exception as storage_health_error:
            logger.error(f"Storage health check failed: {storage_health_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage health check failed. Please try again later."
            )

    def _prepare_archaeological_metadata(self, upload_request: PhotoUploadRequest) -> Dict[str, Any]:
        """Convert Pydantic schema to dictionary for database operations."""
        
        metadata = {}
        
        # Basic metadata
        if upload_request.title:
            metadata['title'] = upload_request.title
        if upload_request.description:
            metadata['description'] = upload_request.description
        if upload_request.photographer:
            metadata['photographer'] = upload_request.photographer
        if upload_request.keywords:
            metadata['keywords'] = upload_request.keywords
        if upload_request.photo_type:
            metadata['photo_type'] = upload_request.photo_type

        # Archaeological context
        if upload_request.inventory_number:
            metadata['inventory_number'] = upload_request.inventory_number
        if upload_request.catalog_number:
            metadata['catalog_number'] = upload_request.catalog_number
        if upload_request.excavation_area:
            metadata['excavation_area'] = upload_request.excavation_area
        if upload_request.stratigraphic_unit:
            metadata['stratigraphic_unit'] = upload_request.stratigraphic_unit
        if upload_request.grid_square:
            metadata['grid_square'] = upload_request.grid_square
        if upload_request.depth_level is not None:
            metadata['depth_level'] = upload_request.depth_level
        if upload_request.find_date:
            try:
                metadata['find_date'] = datetime.fromisoformat(upload_request.find_date.replace('Z', '+00:00'))
            except ValueError:
                try:
                    metadata['find_date'] = datetime.strptime(upload_request.find_date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid find_date format: {upload_request.find_date}")
        if upload_request.finder:
            metadata['finder'] = upload_request.finder
        if upload_request.excavation_campaign:
            metadata['excavation_campaign'] = upload_request.excavation_campaign

        # Material and object
        if upload_request.material:
            metadata['material'] = upload_request.material
        if upload_request.material_details:
            metadata['material_details'] = upload_request.material_details
        if upload_request.object_type:
            metadata['object_type'] = upload_request.object_type
        if upload_request.object_function:
            metadata['object_function'] = upload_request.object_function

        # Dimensions
        if upload_request.length_cm is not None:
            metadata['length_cm'] = upload_request.length_cm
        if upload_request.width_cm is not None:
            metadata['width_cm'] = upload_request.width_cm
        if upload_request.height_cm is not None:
            metadata['height_cm'] = upload_request.height_cm
        if upload_request.diameter_cm is not None:
            metadata['diameter_cm'] = upload_request.diameter_cm
        if upload_request.weight_grams is not None:
            metadata['weight_grams'] = upload_request.weight_grams

        # Chronology
        if upload_request.chronology_period:
            metadata['chronology_period'] = upload_request.chronology_period
        if upload_request.chronology_culture:
            metadata['chronology_culture'] = upload_request.chronology_culture
        if upload_request.dating_from:
            metadata['dating_from'] = upload_request.dating_from
        if upload_request.dating_to:
            metadata['dating_to'] = upload_request.dating_to
        if upload_request.dating_notes:
            metadata['dating_notes'] = upload_request.dating_notes

        # Conservation
        if upload_request.conservation_status:
            metadata['conservation_status'] = upload_request.conservation_status
        if upload_request.conservation_notes:
            metadata['conservation_notes'] = upload_request.conservation_notes
        if upload_request.restoration_history:
            metadata['restoration_history'] = upload_request.restoration_history

        # References
        if upload_request.bibliography:
            metadata['bibliography'] = upload_request.bibliography
        if upload_request.comparative_references:
            metadata['comparative_references'] = upload_request.comparative_references
        if upload_request.external_links:
            metadata['external_links'] = upload_request.external_links

        # Rights
        if upload_request.copyright_holder:
            metadata['copyright_holder'] = upload_request.copyright_holder
        if upload_request.license_type:
            metadata['license_type'] = upload_request.license_type
        if upload_request.usage_rights:
            metadata['usage_rights'] = upload_request.usage_rights

        return metadata

    async def _process_photos_parallel_or_sequential(
        self,
        photos: List[UploadFile],
        site_id: UUID,
        user_id: UUID,
        archaeological_metadata: Dict[str, Any]
    ) -> List:
        """
        Process photos using parallel or sequential approach based on file count.
        """
        
        if len(photos) == 1:
            logger.info("Processing single photo sequentially to avoid database session conflicts")
            result = await self._process_single_photo(photos[0], site_id, user_id, archaeological_metadata)
            return [result]
        else:
            # Use parallel processing with timeout protection
            logger.info(f"Processing {len(photos)} photos in parallel with timeout protection")
            
            upload_tasks = [
                self._process_single_photo(photo, site_id, user_id, archaeological_metadata)
                for photo in photos
            ]

            try:
                upload_results = await asyncio.wait_for(
                    asyncio.gather(*upload_tasks, return_exceptions=True),
                    timeout=300.0  # 5 minutes timeout
                )
                logger.info(f"✅ Parallel processing completed within timeout: {len(photos)} photos")
                return upload_results
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=408, 
                    detail="Upload processing timed out after 5 minutes"
                )

    async def _process_single_photo(
        self,
        file: UploadFile,
        site_id: UUID,
        user_id: UUID,
        archaeological_metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single photo with complete error handling and transaction management.
        """
        
        photo_record = None
        filename = None
        file_path = None
        
        try:
            # 1. Save file to storage
            filename, file_path, file_size = await storage_service.save_upload_file(
                file, str(site_id), str(user_id)
            )

            # 2. Extract metadata from uploaded file
            await file.seek(0)  # Reset file pointer
            exif_data, metadata = await photo_metadata_service.extract_metadata_from_file(
                file, filename
            )

            # 3. Create photo record in database
            photo_record = await photo_metadata_service.create_photo_record(
                filename=filename,
                original_filename=file.filename,
                file_path=file_path,
                file_size=file_size,
                site_id=str(site_id),
                uploaded_by=str(user_id),
                metadata=metadata,
                archaeological_metadata=archaeological_metadata
            )

            # 4. Handle database transaction and thumbnail generation
            async with async_session_maker() as task_db:
                try:
                    async with task_db.begin():
                        # Add photo record to transaction
                        task_db.add(photo_record)
                        await task_db.flush()
                        await task_db.refresh(photo_record)

                        # 5. Generate thumbnail
                        try:
                            await file.seek(0)  # Reset file pointer for thumbnail
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
                            # Don't fail the entire upload if thumbnail generation fails

                        # 6. Log activity
                        activity = UserActivity(
                            user_id=str(user_id),
                            site_id=str(site_id),
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

            logger.info(f"Photo {photo_record.id} uploaded successfully by user {user_id}")

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
            # Return None for this photo but don't fail the entire batch
            return None

    def _filter_upload_results(
        self, 
        photos: List[UploadFile], 
        upload_results: List
    ) -> Tuple[List[Dict], List[Dict]]:
        """Filter and categorize upload results into successes and failures."""
        
        uploaded_photos = []
        failed_photos = []

        for i, result in enumerate(upload_results):
            if isinstance(result, Exception):
                error_msg = str(result)
                if "database" in error_msg.lower() and (
                        "lock" in error_msg.lower() or "conflict" in error_msg.lower()):
                    error_msg = f"Database conflict during photo {photos[i].filename} processing: {error_msg}"
                logger.error(f"❌ Upload task failed for photo {photos[i].filename}: {error_msg}")
                failed_photos.append({
                    "filename": photos[i].filename,
                    "error": error_msg
                })
            elif result is not None:
                uploaded_photos.append(result)
            else:
                # None result indicates a failed upload that was handled gracefully
                failed_photos.append({
                    "filename": photos[i].filename,
                    "error": "Processing failed but was handled gracefully"
                })

        logger.info(
            f"📊 Upload processing summary: {len(uploaded_photos)} photos uploaded successfully, "
            f"{len(failed_photos)} failed out of {len(photos)} total"
        )

        return uploaded_photos, failed_photos

    async def _identify_photos_needing_tiles(
        self, 
        uploaded_photos: List[Dict], 
        site_id: UUID, 
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Identify which photos need deep zoom tile processing.
        """
        
        photos_needing_tiles = []
        
        if not uploaded_photos:
            return photos_needing_tiles

        logger.info(f"🔧 TILE DETECTION: Processing {len(uploaded_photos)} uploaded photos for tile requirements")

        # Create new database session for tile detection
        async with async_session_maker() as tile_db:
            try:
                for photo_data in uploaded_photos:
                    photo_id = photo_data["photo_id"]
                    
                    # Use already extracted dimensions from metadata
                    width = photo_data.get("metadata", {}).get("width", 0)
                    height = photo_data.get("metadata", {}).get("height", 0)
                    max_dimension = max(width, height) if width and height else 0

                    logger.info(f"🔧 Photo {photo_id} dimensions: {width}x{height}, max_dimension: {max_dimension}")

                    if max_dimension > self.min_dimension_for_tiles:
                        logger.info(f"📋 Photo {photo_id} needs tiles: {width}x{height}")

                        # Query photo record to update status
                        photo_query = select(Photo).where(Photo.id == UUID(photo_id))
                        result = await tile_db.execute(photo_query)
                        photo_record = result.scalar_one_or_none()

                        if photo_record:
                            photo_record.deepzoom_status = 'scheduled'
                            await tile_db.commit()

                            photos_needing_tiles.append({
                                'photo_id': photo_id,
                                'file_path': photo_data['file_path'],
                                'width': width,
                                'height': height,
                                'archaeological_metadata': photo_data.get('archaeological_metadata', {})
                            })
                            logger.info(f"🔧 Added photo {photo_id} to photos_needing_tiles")
                        else:
                            logger.error(f"🔧 Photo record not found for {photo_id}")

            except Exception as session_error:
                logger.error(f"🔧 Tile detection error: {session_error}")
                # Don't fail the entire upload if tile detection fails

        return photos_needing_tiles

    async def _schedule_tile_processing(self, photos_needing_tiles: List[Dict], site_id: UUID):
        """Schedule deep zoom processing for photos that need tiles."""
        
        if not photos_needing_tiles:
            logger.info("🎯 No photos require tile processing")
            return

        try:
            logger.info(f"🎯 Scheduling {len(photos_needing_tiles)} photos for tile processing")

            # Validate photos data structure
            validated_photos_list = []
            for tile_photo in photos_needing_tiles:
                if all(key in tile_photo for key in ['photo_id', 'file_path', 'width', 'height']):
                    validated_photos_list.append(tile_photo)
                else:
                    logger.warning(f"🎯 Skipping invalid photo data: {tile_photo}")

            if validated_photos_list:
                # Schedule batch processing with background service
                batch_result = await deep_zoom_background_service.schedule_batch_processing(
                    photos_list=validated_photos_list,
                    site_id=str(site_id)
                )

                logger.info(f"✅ Tile scheduling completed: {batch_result}")
                
                # Verify scheduling success
                if batch_result and isinstance(batch_result, dict):
                    scheduled_count = batch_result.get('scheduled_count', 0)
                    if scheduled_count > 0:
                        logger.info(f"✅ Tile scheduling SUCCESS: {scheduled_count} photos scheduled")
                    else:
                        logger.warning(f"⚠️ Tile scheduling WARNING: {scheduled_count} photos scheduled")

        except Exception as batch_error:
            logger.error(f"🔴 Tile scheduling ERROR: {batch_error}")
            # Don't fail the upload if tile scheduling fails

    def _prepare_upload_response(
        self, 
        uploaded_photos: List[Dict], 
        failed_photos: List[Dict],
        photos_needing_tiles: List[Dict]
    ) -> JSONResponse:
        """Prepare the final upload response."""
        
        # Validate uploaded_photos structure
        if not isinstance(uploaded_photos, list):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response format: uploaded_photos must be a list"
            )

        # Validate each photo entry
        for i, photo in enumerate(uploaded_photos):
            if not isinstance(photo, dict):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Invalid photo entry at index {i}: must be a dictionary"
                )
            required_fields = ['photo_id', 'filename', 'file_size']
            for field in required_fields:
                if field not in photo:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Invalid photo entry at index {i}: missing required field '{field}'"
                    )

        response_data = {
            "uploaded_photos": uploaded_photos,
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "total_uploaded": len(uploaded_photos),
            "photos_needing_tiles": len(photos_needing_tiles),
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        }

        if failed_photos:
            response_data["failed_photos"] = failed_photos
            response_data["total_failed"] = len(failed_photos)

        logger.info(f"✅ Upload API response: {len(uploaded_photos)} foto caricate, {len(photos_needing_tiles)} necessitano tiles")

        return JSONResponse(response_data)

    async def _handle_queued_upload(
        self,
        site_id: UUID,
        user_id: UUID,
        photos: List[UploadFile],
        upload_request: PhotoUploadRequest,
        db: AsyncSession,
        priority: str = "normal"
    ) -> JSONResponse:
        """Handle upload through queue system."""
        
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
            'user_id': str(user_id),
            'photos_count': len(photos),
            'metadata': upload_request.dict(exclude_unset=True)
        }

        # Estimate processing time
        estimated_duration = len(photos) * 30  # 30 seconds per photo estimate

        try:
            # Enqueue upload request
            request_id = await request_queue_service.enqueue_request(
                request_type="POST_/api/site/{site_id}/photos/upload",
                payload=upload_data,
                priority=request_priority,
                user_id=str(user_id),
                site_id=str(site_id),
                timeout_seconds=600 + (len(photos) * 60),  # Base 10min + 1min per photo
                max_retries=3,
                estimated_duration=estimated_duration
            )

            # Store files temporarily for queue processing
            temp_files = []
            upload_paths = []

            try:
                for photo in photos:
                    # Save to temporary location
                    filename, file_path, file_size = await storage_service.save_upload_file(
                        photo, str(site_id), str(user_id), temp=True
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

                logger.info(f"Queued upload request {request_id} for {len(photos)} photos with priority {request_priority.name}")

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


# Global service instance
photo_upload_service = PhotoUploadService()