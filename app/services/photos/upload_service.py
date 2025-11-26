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

# Import from centralized database engine
from app.database.engine import AsyncSessionLocal as async_session_maker
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
        self.debug_mode = False  # Riabilita validazione storage

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
            logger.debug("Step 1: Validating storage and preparing for upload")
            await self._validate_and_prepare_storage(photos)
            logger.debug("Step 1 completed: Storage validation passed")

            # Prepare archaeological metadata from Pydantic schema
            logger.debug("Step 2: Preparing archaeological metadata")
            archaeological_metadata = self._prepare_archaeological_metadata(upload_request, raw_metadata)
            logger.debug("Step 2 completed: Archaeological metadata prepared")

            logger.debug("Processing photos",
                        photo_count=len(photos),
                        metadata_keys=list(archaeological_metadata.keys()))

            # Process photos (parallel or sequential based on count)
            logger.debug("Step 3: Starting photo processing")
            upload_results = await self._process_photos_parallel_or_sequential(
                photos, site_id, user_id, archaeological_metadata, db
            )
            logger.debug("Step 3 completed: Photo processing finished")

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
        if self.debug_mode:
            logger.warning("🚨 DEBUG MODE: Skipping storage validation to identify hang point")
            return  # Skip storage validation in debug mode
            
        logger.debug("🔍 STORAGE VALIDATION: Starting storage health check")
        
        # Check storage health and capacity with timeout
        try:
            logger.debug("🔍 STORAGE VALIDATION: Checking buckets exist")
            # Add timeout to prevent hanging
            import asyncio
            await asyncio.wait_for(
                storage_management_service.ensure_buckets_exist(),
                timeout=30.0  # 30 seconds timeout
            )
            logger.debug("🔍 STORAGE VALIDATION: Buckets check completed")
        except asyncio.TimeoutError:
            logger.error("Storage service timeout - buckets check took too long")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is temporarily unavailable. Please try again later."
            )
        except Exception as storage_error:
            logger.error(f"Storage service initialization failed: {storage_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is currently unavailable. Please try again later."
            )

        # ✅ CRITICAL FIX: Skip expensive storage usage calculation during upload
        # Just do a quick bucket existence check instead
        logger.debug("🔍 STORAGE VALIDATION: Skipping detailed storage check (performance optimization)")

        # Quick check - just verify buckets exist without listing all objects
        try:
            bucket_check = await asyncio.wait_for(
                storage_management_service.ensure_buckets_exist(),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("Bucket validation timeout")
            bucket_check = {'created_buckets': [], 'existing_buckets': []}

        if not bucket_check.get('created_buckets') and not bucket_check.get('existing_buckets'):
            logger.error("❌ No buckets available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage buckets not available"
            )

        logger.debug("✅ STORAGE VALIDATION: Quick bucket check completed")
        storage_usage = {
            'total_size_gb': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.debug("🔍 STORAGE VALIDATION: All storage validation steps completed")

    def _prepare_archaeological_metadata(self, upload_request: PhotoUploadRequest, raw_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convert Pydantic schema to dictionary for database operations."""
        
        # Use raw metadata if available to avoid Pydantic validation issues
        if raw_metadata:
            metadata = {}
            
            # Filter out None/empty values from raw metadata
            for key, value in raw_metadata.items():
                if value is not None and value != '':
                    metadata[key] = value
            
            # ✅ CRITICAL FIX: Ensure archaeological fields are included from raw_metadata
            # Map frontend form field names to database field names
            field_mapping = {
                'excavation_area': 'excavation_area',  # Already matches
                'stratigraphic_unit': 'stratigraphic_unit',  # Already matches
                'photo_date': 'photo_date',  # Already matches
                # Add other mappings as needed
            }
            
            # Apply field mapping and ensure all fields are included
            for frontend_field, db_field in field_mapping.items():
                if frontend_field in raw_metadata and raw_metadata[frontend_field]:
                    metadata[db_field] = raw_metadata[frontend_field]
            
            logger.debug(f"📋 Raw metadata processed: {list(metadata.keys())}")
            
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
        Process photos ALWAYS sequentially for SQLite compatibility.
        
        SQLite is single-writer - parallel processing causes database locks.
        """
        
        logger.info(f"🔄 Processing {len(photos)} photos sequentially (SQLite mode)")
        results = []
        
        for i, photo in enumerate(photos, 1):
            logger.debug(f"📸 Processing photo {i}/{len(photos)}: {photo.filename}")
            
            try:
                result = await self._process_single_photo(
                    photo,
                    site_id,
                    user_id,
                    archaeological_metadata,
                    db
                )
                results.append(result)
                logger.info(f"✅ Photo {i}/{len(photos)} completed: {photo.filename}")
                
                # CRITICAL: Small delay between photos for SQLite write lock release
                if i < len(photos):
                    await asyncio.sleep(0.15)  # 150ms delay
                    
            except Exception as e:
                logger.error(f"❌ Failed to process {photo.filename}: {str(e)}")
                results.append(e)
                # Continue processing remaining photos
                continue
        
        logger.info(f"✨ Batch complete: {len([r for r in results if not isinstance(r, Exception)])}/{len(photos)} succeeded")
        return results

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

                # ✅ CRITICAL FIX: Create photo record with better error handling
                try:
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
                    # 🔧 CRITICAL FIX: Log stratigraphic_unit registration for debugging
                    stratigraphic_unit_value = archaeological_metadata.get('stratigraphic_unit')
                    if stratigraphic_unit_value:
                        logger.info(f"🔧 PHOTO STRATIGRAPHIC_UNIT REGISTRATION: {stratigraphic_unit_value}")
                        logger.info(f"🔧 PHOTO ID: {photo_record.id if photo_record else 'unknown'}")
                        logger.info(f"🔧 PHOTO FILENAME: {filename}")
                    logger.debug(f"✅ Photo record created successfully: {photo_record.id if photo_record else 'unknown'}")
                except Exception as create_error:
                    logger.error(
                        "❌ PHOTO RECORD CREATION FAILED",
                        error=str(create_error),
                        error_type=type(create_error).__name__,
                        filename=filename,
                        site_id=str(site_id),
                        user_id=str(user_id),
                        metadata_keys=list(metadata.keys()) if metadata else [],
                        arch_metadata_keys=list(archaeological_metadata.keys()) if archaeological_metadata else [],
                        exc_info=True
                    )
                    raise

                # ✅ FIX: Gestione transazione compatibile con SQLite
                try:
                    # ✅ CRITICAL FIX: Add photo record without nested commits
                    task_db.add(photo_record)
                    await task_db.flush()  # Flush senza commit per transazione outer
                    photo_id = photo_record.id
                    # ✅ NO commit in nested transaction - gestito dal chiamante
                    await task_db.refresh(photo_record)
                    logger.debug(f"✅ Photo record flushed: {photo_id}")
                    
                except Exception as db_error:
                    # ✅ FIX: Logging corretto con messaggio errore visibile
                    import traceback
                    error_traceback = traceback.format_exc()
                    
                    # Log con messaggio errore incluso nella stringa
                    logger.error(
                        f"❌ DATABASE OPERATION FAILED: {type(db_error).__name__}: {str(db_error)}"
                    )
                    logger.error(
                        f"Photo ID: {photo_record.id if photo_record else 'unknown'}, "
                        f"Metadata keys: {list(archaeological_metadata.keys()) if archaeological_metadata else []}"
                    )
                    logger.error(f"❌ FULL TRACEBACK:\n{error_traceback}")
                    
                    # Log strutturato aggiuntivo per debugging
                    logger.bind(
                        error=str(db_error),
                        error_type=type(db_error).__name__,
                        photo_id=photo_record.id if photo_record else "unknown",
                        metadata_keys=list(archaeological_metadata.keys()) if archaeological_metadata else []
                    ).error("Database operation exception details")
                    
                    # Log metadata that was being processed
                    if archaeological_metadata:
                        logger.error(
                            "❌ METADATA BEING PROCESSED",
                            metadata=archaeological_metadata,
                            metadata_type=type(archaeological_metadata).__name__
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
                        logger.debug(f"✅ Thumbnail path updated: {thumbnail_path}")
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
                    # ✅ NO commit in nested transaction - gestito dal chiamante
                    await task_db.flush()  # Flush per generare ID activity
                    logger.debug(f"✅ Activity flushed for photo {photo_record.id}")
                    
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
                # ✅ FIX: Logging migliorato per debug
                import traceback
                error_details = traceback.format_exc()
                
                # Log l'errore completo nella stringa del messaggio
                logger.error(
                    f"❌ UNEXPECTED ERROR: {type(photo_error).__name__}: {str(photo_error)}"
                )
                logger.error(
                    f"Context - File: {file.filename if file else 'Unknown'}, "
                    f"Path: {file_path if file_path else 'Unknown'}, "
                    f"Size: {file_size if 'file_size' in locals() else 'Unknown'}"
                )
                logger.error(f"❌ FULL TRACEBACK:\n{error_details}")
                
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
        """
        Schedule deep zoom processing for photos that need tiles.
        
        🔧 SNAPSHOT-BASED SOLUTION: Creates complete photo snapshots to eliminate race conditions.
        All necessary data is passed to the background service to avoid database queries.
        """
        
        with logger.contextualize(
            operation="schedule_tile_processing",
            site_id=str(site_id),
            photos_count=len(photos_needing_tiles)
        ):
            if not photos_needing_tiles:
                logger.debug("No photos require tile processing")
                return

            try:
                logger.info("Starting tile scheduling with snapshot-based approach", photo_count=len(photos_needing_tiles))

                # 🔧 SNAPSHOT CREATION: Create complete photo snapshots with all necessary data
                photo_snapshots = []
                for tile_photo in photos_needing_tiles:
                    try:
                        # Validate basic structure
                        if not all(key in tile_photo for key in ['photo_id', 'file_path', 'width', 'height']):
                            logger.warning("Skipping invalid photo data", photo_data=tile_photo)
                            continue
                        
                        # Create comprehensive snapshot with all data needed for tile processing
                        photo_snapshot = {
                            # Core identification
                            'id': tile_photo['photo_id'],
                            'site_id': str(site_id),
                            
                            # File information
                            'file_path': tile_photo['file_path'],
                            'width': tile_photo['width'],
                            'height': tile_photo['height'],
                            'filename': tile_photo.get('filename', f"photo_{tile_photo['photo_id']}"),
                            'file_size': tile_photo.get('file_size', 0),
                            
                            # Metadata from photo processing
                            'created_at': tile_photo.get('created_at', datetime.now(timezone.utc).isoformat()),
                            'photo_date': tile_photo.get('photo_date'),
                            'camera_model': tile_photo.get('camera_model'),
                            
                            # Archaeological metadata
                            'archaeological_metadata': tile_photo.get('archaeological_metadata', {}),
                            
                            # Additional metadata that might be needed
                            'metadata': tile_photo.get('metadata', {}),
                            
                            # Processing flags
                            'needs_tiles': True,
                            'min_dimension_for_tiles': self.min_dimension_for_tiles
                        }
                        
                        # Add any additional metadata fields that might be present
                        if 'inventory_number' in tile_photo:
                            photo_snapshot['inventory_number'] = tile_photo['inventory_number']
                        if 'excavation_area' in tile_photo:
                            photo_snapshot['excavation_area'] = tile_photo['excavation_area']
                        if 'stratigraphic_unit' in tile_photo:
                            photo_snapshot['stratigraphic_unit'] = tile_photo['stratigraphic_unit']
                        if 'material' in tile_photo:
                            photo_snapshot['material'] = tile_photo['material']
                        if 'chronology_period' in tile_photo:
                            photo_snapshot['chronology_period'] = tile_photo['chronology_period']
                        if 'photo_type' in tile_photo:
                            photo_snapshot['photo_type'] = tile_photo['photo_type']
                        if 'photographer' in tile_photo:
                            photo_snapshot['photographer'] = tile_photo['photographer']
                        if 'description' in tile_photo:
                            photo_snapshot['description'] = tile_photo['description']
                        if 'keywords' in tile_photo:
                            photo_snapshot['keywords'] = tile_photo['keywords']
                        
                        photo_snapshots.append(photo_snapshot)
                        logger.debug(f"Created snapshot for photo {tile_photo['photo_id']}",
                                   snapshot_keys=list(photo_snapshot.keys()))
                        
                    except Exception as snapshot_error:
                        logger.error(f"Failed to create snapshot for photo {tile_photo.get('photo_id', 'unknown')}: {snapshot_error}")
                        # Continue with other photos even if one snapshot fails
                        continue

                if photo_snapshots:
                    logger.info(f"Created {len(photo_snapshots)} complete photo snapshots for tile processing")
                    
                    # 🔧 SNAPSHOT-BASED CALL: Pass complete snapshots to background service
                    batch_result = await deep_zoom_background_service.schedule_batch_processing_with_snapshots(
                        photo_snapshots=photo_snapshots,
                        site_id=str(site_id)
                    )

                    logger.debug("Tile scheduling with snapshots completed", result=batch_result)
                    
                    # Verify scheduling success
                    if batch_result and isinstance(batch_result, dict):
                        scheduled_count = batch_result.get('scheduled_count', 0)
                        if scheduled_count > 0:
                            logger.info("Snapshot-based tile scheduling successful",
                                       scheduled_count=scheduled_count,
                                       total_snapshots=len(photo_snapshots))
                        else:
                            logger.warning("Snapshot-based tile scheduling warning",
                                         scheduled_count=scheduled_count,
                                         total_snapshots=len(photo_snapshots))
                    else:
                        logger.error("Unexpected result from snapshot-based tile scheduling", result=batch_result)
                else:
                    logger.warning("No valid photo snapshots created for tile processing")

            except Exception as batch_error:
                logger.error("Snapshot-based tile scheduling error",
                           error=str(batch_error),
                           error_type=type(batch_error).__name__,
                           photos_count=len(photos_needing_tiles))
                # Don't fail the upload if tile scheduling fails
                import traceback
                logger.error(f"Tile scheduling traceback: {traceback.format_exc()}")

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
