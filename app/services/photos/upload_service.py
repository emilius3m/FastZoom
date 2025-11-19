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
        db: AsyncSession,
        raw_metadata: Optional[Dict[str, Any]] = None
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
            site_id, user_id, photos, upload_request, db, raw_metadata
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
        db: AsyncSession,
        raw_metadata: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """
        Process photos upload directly without queueing.
        """
        import time
        start_time = time.time()
        
        with logger.contextualize(
            operation="process_direct_upload",
            site_id=str(site_id),
            user_id=str(user_id),
            photo_count=len(photos)
        ):
            logger.info("Starting direct upload processing")
            
            # Pre-upload validation and storage checks
            await self._validate_and_prepare_storage(photos)

            # Prepare archaeological metadata from Pydantic schema
            archaeological_metadata = self._prepare_archaeological_metadata(upload_request, raw_metadata)

            logger.debug("Processing photos",
                        photo_count=len(photos),
                        metadata_keys=list(archaeological_metadata.keys()))

            # Process photos (parallel or sequential based on count)
            upload_results = await self._process_photos_parallel_or_sequential(
                photos, site_id, user_id, archaeological_metadata, db
            )

            # Filter and validate results
            uploaded_photos, failed_photos = self._filter_upload_results(photos, upload_results)

            # Handle tile processing for large images
            photos_needing_tiles = await self._identify_photos_needing_tiles(uploaded_photos, site_id, db)

            # Schedule deep zoom processing if needed
            await self._schedule_tile_processing(photos_needing_tiles, site_id)

            duration = time.time() - start_time
            logger.info("Direct upload completed",
                       uploaded_count=len(uploaded_photos),
                       failed_count=len(failed_photos),
                       tiles_needed=len(photos_needing_tiles),
                       duration=duration)

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

    def _prepare_archaeological_metadata(self, upload_request: PhotoUploadRequest, raw_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convert Pydantic schema to dictionary for database operations."""
        
        # Use raw metadata if available to avoid Pydantic validation issues
        if raw_metadata:
            metadata = {}
            
            # Filter out None/empty values from raw metadata
            for key, value in raw_metadata.items():
                if value is not None and value != '':
                    metadata[key] = value
        else:
            metadata = {}
            
            # Basic metadata from Pydantic model
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

        # Add remaining fields from Pydantic model if not already in metadata
        remaining_fields = {
            'inventory_number', 'catalog_number', 'excavation_area', 'stratigraphic_unit',
            'grid_square', 'depth_level', 'find_date', 'finder', 'excavation_campaign',
            'material', 'material_details', 'object_type', 'object_function',
            'length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams',
            'chronology_period', 'chronology_culture', 'dating_from', 'dating_to', 'dating_notes',
            'conservation_status', 'conservation_notes', 'restoration_history',
            'bibliography', 'comparative_references', 'external_links',
            'copyright_holder', 'license_type', 'usage_rights'
        }
        
        for field in remaining_fields:
            if field not in metadata:
                value = getattr(upload_request, field, None)
                if value is not None and value != '':
                    # Handle date fields specially
                    if field in ['find_date', 'dating_from', 'dating_to'] and isinstance(value, str):
                        try:
                            metadata[field] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        except ValueError:
                            try:
                                metadata[field] = datetime.strptime(value, '%Y-%m-%d')
                            except ValueError:
                                logger.warning(f"Invalid {field} format: {value}")
                                metadata[field] = value
                    else:
                        metadata[field] = value

        return metadata

    async def _process_photos_parallel_or_sequential(
        self,
        photos: List[UploadFile],
        site_id: UUID,
        user_id: UUID,
        archaeological_metadata: Dict[str, Any],
        db: AsyncSession
    ) -> List:
        """
        Process photos using parallel or sequential approach based on file count.
        """
        
        if len(photos) == 1:
            logger.debug("Processing single photo sequentially")
            result = await self._process_single_photo(photos[0], site_id, user_id, archaeological_metadata, db)
            return [result]
        else:
            # Use parallel processing with timeout protection
            logger.debug("Processing photos in parallel", photo_count=len(photos))
            
            upload_tasks = [
                self._process_single_photo(photo, site_id, user_id, archaeological_metadata, db)
                for photo in photos
            ]

            try:
                upload_results = await asyncio.wait_for(
                    asyncio.gather(*upload_tasks, return_exceptions=True),
                    timeout=300.0  # 5 minutes timeout
                )
                logger.info("Parallel processing completed", photo_count=len(photos))
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
        archaeological_metadata: Dict[str, Any],
        task_db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single photo with complete error handling and transaction management.
        Uses the passed database session with async context manager pattern.
        """
        import time
        start_time = time.time()
        
        photo_record = None
        filename = None
        file_path = None
        
        with logger.contextualize(
            operation="process_single_photo",
            site_id=str(site_id),
            user_id=str(user_id),
            filename=file.filename
        ):
            try:
                logger.info("Starting single photo processing")
                
                # 1. Save file to storage (outside transaction)
                filename, file_path, file_size = await storage_service.save_upload_file(
                    file, str(site_id), str(user_id)
                )

                # 2. Extract metadata from uploaded file (outside transaction)
                await file.seek(0)  # Reset file pointer
                exif_data, metadata = await photo_metadata_service.extract_metadata_from_file(
                    file, filename
                )

                # 3. Create photo record object (not saved yet)
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

                # ✅ FIX: Gestione transazione compatibile con SQLite
                try:
                    # Verifica se c'è già una transazione attiva
                    if task_db.in_transaction():
                        logger.debug("Using existing transaction")
                        # Usa la transazione esistente
                        task_db.add(photo_record)
                        await task_db.flush()
                        # ✅ CRITICAL FIX: Non usare refresh dentro transazione con SQLite
                        # Usa expire_on_commit=False o accedi ai dati prima del commit
                        photo_id = photo_record.id
                        logger.debug(f"✅ Photo flushed in existing transaction: {photo_id}")
                    else:
                        # Crea nuova transazione solo se necessario
                        logger.debug("Creating new transaction")
                        async with task_db.begin():
                            task_db.add(photo_record)
                            await task_db.flush()
                            photo_id = photo_record.id
                            logger.debug(f"✅ Photo flushed in new transaction: {photo_id}")
                    
                    # ✅ FIX: Non fare refresh qui - SQLite non lo supporta bene
                    # I dati sono già accessibili dopo flush()
                    
                except Exception as db_error:
                    logger.error(
                        "Database operation failed",
                        error=str(db_error),
                        error_type=type(db_error).__name__,
                        photo_id=photo_record.id if photo_record else "unknown",
                        exc_info=True  # ✅ CRITICAL: Aggiunto stack trace
                    )
                    raise
                
                # 5. Generate thumbnail (outside main transaction)
                try:
                    await file.seek(0)
                    thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                        file, str(photo_record.id)
                    )
                    
                    if thumbnail_path:
                        photo_record.thumbnail_path = thumbnail_path
                        # ✅ FIX: Update separato per thumbnail
                        try:
                            await task_db.commit()
                            logger.debug(f"✅ Thumbnail path updated: {thumbnail_path}")
                        except Exception as commit_error:
                            logger.error(
                                "Thumbnail commit failed",
                                photo_id=str(photo_record.id),
                                error=str(commit_error),
                                exc_info=True
                            )
                            # Non fallire per thumbnail
                    else:
                        logger.warning(f"Thumbnail generation failed for {photo_record.id}")
                        
                except Exception as thumbnail_error:
                    logger.error(
                        "Thumbnail generation error",
                        photo_id=str(photo_record.id),
                        error=str(thumbnail_error),
                        exc_info=True  # ✅ Stack trace
                    )
                    # Don't fail upload for thumbnail
                
                # 6. Log activity in separate transaction
                try:
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
                    await task_db.commit()  # ✅ Commit esplicito per activity
                    logger.debug(f"✅ Activity logged for photo {photo_record.id}")
                    
                except Exception as activity_error:
                    logger.error(
                        "Activity logging failed",
                        photo_id=str(photo_record.id),
                        error=str(activity_error),
                        exc_info=True
                    )
                    # Non fallire upload per activity log
                
                duration = time.time() - start_time
                logger.info(
                    "Photo processed successfully",
                    photo_id=str(photo_record.id),
                    duration=duration,
                    file_size=file_size
                )
                
                # ✅ FIX: Accedi a tutti i dati necessari PRIMA di uscire dal metodo
                # per evitare lazy loading issues con SQLite
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
                logger.error(
                    "HTTP exception during photo processing",
                    status_code=he.status_code,
                    detail=he.detail,
                    exc_info=True
                )
                
                if he.status_code == 507:  # Storage full
                    logger.error("Storage full during upload")
                    try:
                        cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=2000)
                        if cleanup_result['success']:
                            logger.info("Emergency cleanup successful", freed_mb=cleanup_result['total_freed_mb'])
                        else:
                            logger.error("Emergency cleanup failed", result=cleanup_result)
                    except Exception as cleanup_error:
                        logger.error("Cleanup attempt failed", error=str(cleanup_error))
                raise he
                
            except Exception as photo_error:
                # ✅ CRITICAL FIX: Log completo con stack trace
                import traceback
                error_details = traceback.format_exc()
                
                logger.error(
                    "Unexpected error processing photo",
                    error=str(photo_error),
                    error_type=type(photo_error).__name__,
                    filename=file.filename if file else "Unknown",
                    site_id=str(site_id),
                    user_id=str(user_id),
                    file_path=file_path if file_path else "Unknown",
                    file_size=file_size if 'file_size' in locals() else "Unknown",
                    exc_info=True  # ✅ QUESTO È CRITICO - mostra stack trace completo
                )
                
                # Log separato per traceback completo
                logger.error(
                    "Full traceback for debugging",
                    traceback=error_details
                )
                
                # Rollback esplicito per SQLite
                if task_db.in_transaction():
                    try:
                        await task_db.rollback()
                        logger.debug("Transaction rolled back")
                    except Exception as rollback_error:
                        logger.error(
                            "Rollback failed",
                            error=str(rollback_error),
                            exc_info=True
                        )
                
                # Clean up file if it exists
                if file_path:
                    try:
                        await storage_service.delete_file(file_path)
                        logger.info(f"✅ Cleaned up file: {file_path}")
                    except Exception as cleanup_error:
                        logger.error(
                            "File cleanup failed",
                            file_path=file_path,
                            error=str(cleanup_error),
                            exc_info=True
                        )
                
                # Return None to indicate failure but don't crash entire batch
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
                logger.error("Upload task failed", filename=photos[i].filename, error=error_msg)
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

        logger.info("Upload processing summary",
                   uploaded=len(uploaded_photos),
                   failed=len(failed_photos),
                   total=len(photos))

        return uploaded_photos, failed_photos

    async def _identify_photos_needing_tiles(
        self,
        uploaded_photos: List[Dict],
        site_id: UUID,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Identify which photos need deep zoom tile processing.
        
        🔧 DATABASE CONSISTENCY FIX: This method now handles:
        1. UUID/string type compatibility issues
        2. Transaction visibility timing
        3. Retry logic for photo record lookup
        4. Comprehensive error handling
        """
        import time
        start_time = time.time()
        photos_needing_tiles = []
        
        with logger.contextualize(
            operation="identify_photos_needing_tiles",
            site_id=str(site_id),
            photo_count=len(uploaded_photos)
        ):
            if not uploaded_photos:
                logger.debug("No photos to process for tiles")
                return photos_needing_tiles

            logger.info("Starting tile detection processing")

            # 🔧 FIX: Use the existing database session for better transaction consistency
            # instead of creating a new session that might not see committed records
            try:
                # Add a small delay to ensure all photo records are fully committed
                await asyncio.sleep(0.05)
                
                for photo_data in uploaded_photos:
                    photo_id = photo_data["photo_id"]
                    
                    # Use already extracted dimensions from metadata
                    width = photo_data.get("metadata", {}).get("width", 0)
                    height = photo_data.get("metadata", {}).get("height", 0)
                    max_dimension = max(width, height) if width and height else 0

                    logger.debug("Checking photo dimensions",
                                photo_id=photo_id,
                                width=width,
                                height=height,
                                max_dimension=max_dimension)

                    if max_dimension > self.min_dimension_for_tiles:
                        logger.debug("Photo needs tiles", photo_id=photo_id, dimensions=f"{width}x{height}")

                        # 🔧 CRITICAL FIX: Implement multi-approach photo record lookup
                        photo_record = await self._find_photo_record_with_retry(photo_id, db)

                        if photo_record:
                            # Update status using the same session
                            photo_record.deepzoom_status = 'scheduled'
                            # Don't commit here - let the outer transaction handle it
                            
                            photos_needing_tiles.append({
                                'photo_id': photo_id,
                                'file_path': photo_data['file_path'],
                                'width': width,
                                'height': height,
                                'archaeological_metadata': photo_data.get('archaeological_metadata', {})
                            })
                            logger.debug("Photo added to tiles processing", photo_id=photo_id)
                        else:
                            # 🔧 ENHANCED: Try with a fresh session as fallback
                            logger.warning("Photo not found in main session, trying fallback", photo_id=photo_id)
                            photo_record_fallback = await self._find_photo_record_in_fresh_session(photo_id)
                            
                            if photo_record_fallback:
                                logger.debug("Photo found in fallback session", photo_id=photo_id)
                                photo_record_fallback.deepzoom_status = 'scheduled'
                                
                                async with async_session_maker() as fallback_db:
                                    fallback_db.add(photo_record_fallback)
                                    await fallback_db.commit()
                                    await fallback_db.refresh(photo_record_fallback)
                                
                                photos_needing_tiles.append({
                                    'photo_id': photo_id,
                                    'file_path': photo_data['file_path'],
                                    'width': width,
                                    'height': height,
                                    'archaeological_metadata': photo_data.get('archaeological_metadata', {})
                                })
                                logger.debug("Photo added via fallback session", photo_id=photo_id)
                            else:
                                logger.error("Photo record not found in any session", photo_id=photo_id)

            except Exception as session_error:
                logger.error("Tile detection error", error=str(session_error))
                # Don't fail the entire upload if tile detection fails
                import traceback
                logger.error("Tile detection traceback", traceback=traceback.format_exc())

            duration = time.time() - start_time
            logger.info("Tile detection completed",
                       photos_needing_tiles=len(photos_needing_tiles),
                       duration=duration)

            return photos_needing_tiles

    async def _find_photo_record_with_retry(self, photo_id: str, db: AsyncSession) -> Optional[Photo]:
        """
        🔧 NEW METHOD: Find photo record with multiple approaches and retry logic
        
        Args:
            photo_id: Photo ID as string
            db: Database session
            
        Returns:
            Photo record or None if not found
        """
        max_retries = 3
        retry_delay = 0.01  # 10ms
        
        for attempt in range(max_retries):
            try:
                # 🔧 APPROACH 1: String-based query (most reliable for String(36) field)
                photo_query = select(Photo).where(Photo.id == photo_id)
                result = await db.execute(photo_query)
                photo_record = result.scalar_one_or_none()
                
                if photo_record:
                    logger.debug(f"🔧 Photo {photo_id} found with string query (attempt {attempt + 1})")
                    return photo_record
                
                # 🔧 APPROACH 2: UUID-based query (for compatibility)
                try:
                    photo_uuid = uuid.UUID(photo_id)
                    uuid_query = select(Photo).where(Photo.id == str(photo_uuid))
                    uuid_result = await db.execute(uuid_query)
                    photo_record_uuid = uuid_result.scalar_one_or_none()
                    
                    if photo_record_uuid:
                        logger.debug(f"🔧 Photo {photo_id} found with UUID query (attempt {attempt + 1})")
                        return photo_record_uuid
                except ValueError:
                    logger.debug(f"🔧 Invalid UUID format for {photo_id}, skipping UUID query")
                
                # 🔧 APPROACH 3: Case-insensitive query (last resort)
                # Using func.lower() for SQLAlchemy compatibility
                from sqlalchemy import func
                case_insensitive_query = select(Photo).where(func.lower(Photo.id) == photo_id.lower())
                case_result = await db.execute(case_insensitive_query)
                photo_record_case = case_result.scalar_one_or_none()
                
                if photo_record_case:
                    logger.debug(f"🔧 Photo {photo_id} found with case-insensitive query (attempt {attempt + 1})")
                    return photo_record_case
                
                # If none found and this isn't the last attempt, wait and retry
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    
            except Exception as query_error:
                logger.warning(f"🔧 Query error for photo {photo_id} (attempt {attempt + 1}): {query_error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
        
        logger.warning(f"🔧 Photo {photo_id} not found after {max_retries} attempts with all query approaches")
        return None

    async def _find_photo_record_in_fresh_session(self, photo_id: str) -> Optional[Photo]:
        """
        🔧 NEW METHOD: Find photo record in a completely fresh database session
        
        This method handles cases where the original session has isolation issues
        and cannot see recently committed records.
        
        Args:
            photo_id: Photo ID as string
            
        Returns:
            Photo record or None if not found
        """
        try:
            async with async_session_maker() as fresh_db:
                # Use the same multi-approach query logic
                photo_query = select(Photo).where(Photo.id == photo_id)
                result = await fresh_db.execute(photo_query)
                photo_record = result.scalar_one_or_none()
                
                if photo_record:
                    logger.info(f"🔧 Photo {photo_id} found in fresh session")
                    return photo_record
                
                # Try UUID-based query
                try:
                    photo_uuid = uuid.UUID(photo_id)
                    uuid_query = select(Photo).where(Photo.id == str(photo_uuid))
                    uuid_result = await fresh_db.execute(uuid_query)
                    photo_record_uuid = uuid_result.scalar_one_or_none()
                    
                    if photo_record_uuid:
                        logger.info(f"🔧 Photo {photo_id} found in fresh session with UUID query")
                        return photo_record_uuid
                except ValueError:
                    pass
                
        except Exception as fresh_session_error:
            logger.error(f"🔧 Fresh session error for photo {photo_id}: {fresh_session_error}")
        
        return None

    async def _schedule_tile_processing(self, photos_needing_tiles: List[Dict], site_id: UUID):
        """Schedule deep zoom processing for photos that need tiles."""
        
        with logger.contextualize(
            operation="schedule_tile_processing",
            site_id=str(site_id),
            photos_count=len(photos_needing_tiles)
        ):
            if not photos_needing_tiles:
                logger.debug("No photos require tile processing")
                return

            try:
                logger.info("Starting tile scheduling", photo_count=len(photos_needing_tiles))

                # Validate photos data structure
                validated_photos_list = []
                for tile_photo in photos_needing_tiles:
                    if all(key in tile_photo for key in ['photo_id', 'file_path', 'width', 'height']):
                        validated_photos_list.append(tile_photo)
                    else:
                        logger.warning("Skipping invalid photo data", photo_data=tile_photo)

                if validated_photos_list:
                    # Schedule batch processing with background service
                    batch_result = await deep_zoom_background_service.schedule_batch_processing(
                        photos_list=validated_photos_list,
                        site_id=str(site_id)
                    )

                    logger.debug("Tile scheduling completed", result=batch_result)
                    
                    # Verify scheduling success
                    if batch_result and isinstance(batch_result, dict):
                        scheduled_count = batch_result.get('scheduled_count', 0)
                        if scheduled_count > 0:
                            logger.info("Tile scheduling successful", scheduled_count=scheduled_count)
                        else:
                            logger.warning("Tile scheduling warning", scheduled_count=scheduled_count)

            except Exception as batch_error:
                logger.error("Tile scheduling error", error=str(batch_error))
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

        # ✅ FIX: Response format compatible with frontend expectations
        # Frontend expects 'successful' and 'failed' arrays for batch upload handling
        response_data = {
            "successful": uploaded_photos,
            "failed": failed_photos,
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "total_uploaded": len(uploaded_photos),
            "photos_needing_tiles": len(photos_needing_tiles),
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Maintain backward compatibility with existing frontend code
        response_data["uploaded_photos"] = uploaded_photos  # For backward compatibility
        if failed_photos:
            response_data["failed_photos"] = failed_photos  # For backward compatibility
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
