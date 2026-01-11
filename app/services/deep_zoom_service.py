from typing import Dict, Any, List, Optional, Union
from uuid import UUID
from datetime import datetime, timezone
import io
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import UploadFile
from loguru import logger

from app.models import Photo, UserActivity
from app.services.deep_zoom_minio_service import DeepZoomMinIOService
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.models.deepzoom_enums import DeepZoomStatus
from app.services.archaeological_minio_service import ArchaeologicalMinIOService
from app.core.domain_exceptions import (
    ResourceNotFoundError,
    PhotoNotFoundError,
    DomainValidationError,
    StorageError
)

class DeepZoomService:
    """
    Service for managing Deep Zoom operations.
    Coordinators Database, MinIO Storage, and Background Processing.
    """

    def __init__(
        self, 
        db: AsyncSession,
        deep_zoom_minio_service: DeepZoomMinIOService,
        storage_service: ArchaeologicalMinIOService
    ):
        self.db = db
        self.minio_service = deep_zoom_minio_service
        self.storage_service = storage_service

    async def _get_photo_or_raise(self, site_id: str, photo_id: str) -> Photo:
        """
        Helper method to retrieve a photo ensuring it belongs to the site.
        Raises PhotoNotFoundError if not found.
        """
        query = select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
        result = await self.db.execute(query)
        photo = result.scalar_one_or_none()
        
        if not photo:
            raise PhotoNotFoundError(f"Photo {photo_id} not found in site {site_id}")
        return photo

    async def get_deep_zoom_info(self, site_id: str, photo_id: str) -> Dict[str, Any]:
        """
        Get metadata about the deep zoom tiles for a specific photo.
        """
        # Ensure photo exists (optional, but good for consistency)
        await self._get_photo_or_raise(site_id, photo_id)
        return await self.minio_service.get_deep_zoom_info(site_id, photo_id)

    async def get_tile_content(
        self, 
        site_id: str, 
        photo_id: str, 
        level: int, 
        x: int, 
        y: int
    ) -> Optional[bytes]:
        """
        Retrieve the binary content of a specific tile.
        """
        # We don't check DB here for performance reasons on high-volume tile requests
        # The MinIO service will handle missing object errors
        return await self.minio_service.get_tile_content(site_id, photo_id, level, x, y)

    async def get_processing_status(self, site_id: str, photo_id: str) -> Dict[str, Any]:
        """
        Get the full processing status of a photo, combining DB state and MinIO/Task state.
        """
        photo = await self._get_photo_or_raise(site_id, photo_id)
        
        minio_status = await self.minio_service.get_processing_status(site_id, photo_id)
        
        return {
            "photo_id": photo_id,
            "site_id": site_id,
            "status": photo.deepzoom_status,
            "has_deep_zoom": photo.has_deep_zoom,
            "levels": photo.max_zoom_level,
            "tile_count": photo.tile_count,
            "processed_at": photo.deepzoom_processed_at.isoformat() if photo.deepzoom_processed_at else None,
            "minio_status": minio_status
        }

    async def process_photo(
        self, 
        site_id: str, 
        photo_id: str, 
        user_id: UUID,
        force_reprocess: bool = False
    ) -> Dict[str, Any]:
        """
        Initiate Deep Zoom processing for a photo. 
        Loads original file and schedules background task.
        """
        photo = await self._get_photo_or_raise(site_id, photo_id)

        # Check if already done or processing unless forced
        if not force_reprocess:
             task_status = await deep_zoom_background_service.get_task_status(photo_id)
             if task_status and task_status['status'] in [DeepZoomStatus.SCHEDULED.value, DeepZoomStatus.PROCESSING.value]:
                 raise DomainValidationError(f"Processing already in progress for photo {photo_id}")

        try:
            # Load original file content
            photo_data = await self.storage_service.get_file(photo.filepath)
        except Exception as e:
            logger.error(f"Failed to retrieve file {photo.filepath}: {e}")
            raise ResourceNotFoundError(f"Original image file not found: {e}")

        # Prepare metadata for the processor
        arch_metadata = {
            'inventory_number': photo.inventory_number,
            'excavation_area': photo.excavation_area,
            'material': photo.material.value if photo.material else None,
            'chronology_period': photo.chronology_period,
            'photo_type': photo.photo_type.value if photo.photo_type else None,
            'photographer': photo.photographer,
            'description': photo.description,
            'keywords': photo.keywords
        }

        # Schedule task
        result = await deep_zoom_background_service.schedule_tile_processing(
            photo_id=photo_id,
            site_id=site_id,
            file_path=photo.filepath,
            original_file_content=photo_data,
            archaeological_metadata=arch_metadata
        )

        # Update DB status
        photo.deepzoom_status = DeepZoomStatus.SCHEDULED.value
        # Commit potentially done here or by caller. 
        # Ideally Service handles unit of work if it owns it.
        # We will add an activity log.
        
        activity = UserActivity(
            user_id=user_id,
            site_id=site_id,
            activity_type="TILES_GENERATION",
            activity_desc=f"Started deep zoom processing for {photo.filename}",
            extra_data={"photo_id": photo_id, "force": force_reprocess}
        )
        self.db.add(activity)
        await self.db.commit()

        return result

    async def verify_and_repair(
        self, 
        site_id: str, 
        photo_id: str, 
        user_id: UUID, 
        auto_repair: bool = True
    ) -> Dict[str, Any]:
        """
        Verify consistency of tiles and optionally repair (regenerate) them.
        """
        photo = await self._get_photo_or_raise(site_id, photo_id)
        
        tile_info = await self.minio_service.get_deep_zoom_info(site_id, photo_id)
        processing_status = await self.minio_service.get_processing_status(site_id, photo_id)
        task_status = await deep_zoom_background_service.get_task_status(photo_id)

        status_code = "unknown"
        message = ""
        repair_needed = False

        if task_status and task_status['status'] in [DeepZoomStatus.SCHEDULED.value, DeepZoomStatus.PROCESSING.value, DeepZoomStatus.RETRYING.value]:
            status_code = DeepZoomStatus.PROCESSING.value
            message = f"Processing in progress ({task_status['status']})"
        elif tile_info and tile_info.get('available', False):
            status_code = "complete"
            message = "Tiles available and valid"
        elif processing_status and processing_status.get('status') == DeepZoomStatus.FAILED.value:
            status_code = DeepZoomStatus.FAILED.value
            message = f"Previous processing failed: {processing_status.get('error')}"
            repair_needed = True
        else:
            status_code = "missing"
            message = "Tiles not found"
            repair_needed = True

        result = {
            "photo_id": photo_id,
            "site_id": site_id,
            "status": status_code,
            "message": message,
            "repair_needed": repair_needed,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if auto_repair and repair_needed:
            try:
                # Trigger repair (re-process)
                repair_info = await self.process_photo(
                    site_id=site_id, 
                    photo_id=photo_id, 
                    user_id=user_id, 
                    force_reprocess=True
                )
                result["repair_action"] = {
                    "action": "scheduled",
                    "details": repair_info
                }
                
                # Log specific repair activity
                activity = UserActivity(
                    user_id=user_id,
                    site_id=site_id,
                    activity_type="TILES_REPAIR",
                    activity_desc=f"Auto-repair started for {photo.filename}",
                    extra_data={"photo_id": photo_id}
                )
                self.db.add(activity)
                await self.db.commit()
                
            except Exception as e:
                logger.error(f"Auto-repair failed for {photo_id}: {e}")
                result["repair_action"] = {
                    "action": "failed",
                    "error": str(e)
                }
        
        return result

    async def get_batch_status(
        self, 
        site_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get status for all photos in a site (paginated).
        """
        # Get photos
        query = select(Photo).where(Photo.site_id == site_id).limit(limit).offset(offset)
        result = await self.db.execute(query)
        photos = result.scalars().all()
        
        batch_status = []
        status_counts = {"processing": 0, "complete": 0, "failed": 0, "missing": 0}

        for photo in photos:
            # We do a lighter check here for performance
            # Ideally we should trust DB status, but we sync with background service cache if possible
            # For now, we mirror the previous logic but slightly optimized
            
            p_status = "unknown"
            if photo.deepzoom_status:
                p_status = photo.deepzoom_status
            
            # Simple mapping
            if p_status in [DeepZoomStatus.SCHEDULED.value, DeepZoomStatus.PROCESSING.value]:
                status_counts['processing'] += 1
            elif p_status == DeepZoomStatus.COMPLETED.value:
                status_counts['complete'] += 1
            elif p_status in [DeepZoomStatus.FAILED.value, DeepZoomStatus.ERROR.value]:
                 status_counts['failed'] += 1
            else:
                 status_counts['missing'] += 1
            
            batch_status.append({
                "photo_id": str(photo.id),
                "filename": photo.filename,
                "status": p_status,
                "has_deep_zoom": photo.has_deep_zoom
            })

        return {
            "site_id": site_id,
            "photos": batch_status,
            "counts": status_counts,
            "pagination": {"limit": limit, "offset": offset}
        }
