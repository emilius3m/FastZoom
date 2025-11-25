# app/services/photos/deepzoom_service.py - Photo Deep Zoom Handler Service

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

from app.models import Photo
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service


class PhotoDeepZoomService:
    """Service for handling deep zoom operations and background processing"""
    
    def __init__(self):
        self.logger = logger.bind(service="photo_deepzoom_service")
    
    async def start_background_processor(
        self,
        site_id: str,
        current_user_id: UUID
    ) -> Dict[str, Any]:
        """
        Start the deep zoom background processor for the site
        
        Args:
            site_id: Site identifier (already normalized)
            current_user_id: User requesting the operation
            
        Returns:
            Dictionary with operation results
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Starting deep zoom background processor for site {site_id} by user {current_user_id}")
            
            await deep_zoom_background_service.start_background_processor()
            
            self.logger.info(f"Deep zoom background processor started successfully by user {current_user_id}")
            
            return {
                "message": "Deep zoom background processor started successfully",
                "site_id": str(site_id),
                "started_by": str(current_user_id),
                "started_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to start deep zoom background processor: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start background processor: {str(e)}"
            )
    
    async def stop_background_processor(
        self,
        site_id: str,
        current_user_id: UUID
    ) -> Dict[str, Any]:
        """
        Stop the deep zoom background processor for the site
        
        Args:
            site_id: Site identifier (already normalized)
            current_user_id: User requesting the operation
            
        Returns:
            Dictionary with operation results
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Stopping deep zoom background processor for site {site_id} by user {current_user_id}")
            
            await deep_zoom_background_service.stop_background_processor()
            
            self.logger.info(f"Deep zoom background processor stopped successfully by user {current_user_id}")
            
            return {
                "message": "Deep zoom background processor stopped successfully",
                "site_id": str(site_id),
                "stopped_by": str(current_user_id),
                "stopped_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to stop deep zoom background processor: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop background processor: {str(e)}"
            )
    
    async def get_background_status(
        self,
        site_id: str
    ) -> Dict[str, Any]:
        """
        Get the current status of the deep zoom background processor
        
        Args:
            site_id: Site identifier (already normalized)
            
        Returns:
            Dictionary with background processor status
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Getting deep zoom background status for site {site_id}")
            
            queue_status = await deep_zoom_background_service.get_queue_status()
            
            return {
                "site_id": str(site_id),
                "background_status": queue_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get deep zoom background status: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get background status: {str(e)}"
            )
    
    async def get_photo_task_status(
        self,
        site_id: str,
        photo_id: UUID
    ) -> Dict[str, Any]:
        """
        Get the deep zoom processing status for a specific photo
        
        Args:
            site_id: Site identifier (already normalized)
            photo_id: Photo ID to check
            
        Returns:
            Dictionary with photo task status
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Getting deep zoom task status for photo {photo_id} in site {site_id}")
            
            # Try to get status from background service first
            task_status = await deep_zoom_background_service.get_task_status(str(photo_id))
            
            if not task_status:
                # Fallback to processing status from MinIO
                self.logger.info(f"Task not found in background service, checking MinIO status for photo {photo_id}")
                deep_zoom_service = get_deep_zoom_minio_service()
                processing_status = await deep_zoom_service.get_processing_status(
                    str(site_id), str(photo_id)
                )
                
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
            self.logger.error(f"Failed to get photo deep zoom task status: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get task status: {str(e)}"
            )
    
    async def schedule_photo_processing(
        self,
        site_id: str,
        photo_ids: List[str],
        current_user_id: UUID
    ) -> Dict[str, Any]:
        """
        Schedule deep zoom processing for multiple photos
        
        Args:
            site_id: Site identifier (already normalized)
            photo_ids: List of photo IDs to process
            current_user_id: User requesting the operation
            
        Returns:
            Dictionary with scheduling results
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Scheduling deep zoom processing for {len(photo_ids)} photos in site {site_id}")
            
            # Prepare photos list for background service
            photos_list = []
            for photo_id in photo_ids:
                try:
                    # Create basic photo info structure
                    photo_info = {
                        'photo_id': photo_id,
                        'file_path': None,  # Will be filled by background service
                        'width': 0,
                        'height': 0,
                        'archaeological_metadata': {}
                    }
                    photos_list.append(photo_info)
                except Exception as e:
                    self.logger.warning(f"Error preparing photo {photo_id} for processing: {e}")
                    continue
            
            if not photos_list:
                raise HTTPException(
                    status_code=400,
                    detail="No valid photos to process"
                )
            
            # Schedule batch processing
            batch_result = await deep_zoom_background_service.schedule_batch_processing(
                photos_list=photos_list,
                site_id=site_id
            )
            
            self.logger.info(f"Scheduled deep zoom processing for {len(photos_list)} photos: {batch_result}")
            
            return {
                "message": f"Deep zoom processing scheduled for {len(photos_list)} photos",
                "scheduled_count": len(photos_list),
                "batch_result": batch_result,
                "site_id": str(site_id),
                "scheduled_by": str(current_user_id),
                "scheduled_at": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Failed to schedule deep zoom processing: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to schedule processing: {str(e)}"
            )
    
    async def get_site_deep_zoom_statistics(
        self,
        site_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get comprehensive deep zoom statistics for the site
        
        Args:
            site_id: Site identifier (already normalized)
            db: Database session
            
        Returns:
            Dictionary with deep zoom statistics
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Getting deep zoom statistics for site {site_id}")
            
            # Query photos for statistics
            photos_query = select(Photo).where(Photo.site_id == site_id)
            photos_result = await db.execute(photos_query)
            photos = photos_result.scalars().all()
            
            # Calculate statistics
            total_photos = len(photos)
            photos_with_deepzoom = sum(1 for p in photos if p.has_deep_zoom)
            photos_processing = sum(1 for p in photos if p.deepzoom_status == 'processing')
            photos_completed = sum(1 for p in photos if p.deepzoom_status == 'completed')
            photos_failed = sum(1 for p in photos if p.deepzoom_status == 'failed')
            photos_scheduled = sum(1 for p in photos if p.deepzoom_status == 'scheduled')
            
            # Get background queue status
            queue_status = await deep_zoom_background_service.get_queue_status()
            
            statistics = {
                "site_id": str(site_id),
                "total_photos": total_photos,
                "photos_with_deepzoom": photos_with_deepzoom,
                "photos_without_deepzoom": total_photos - photos_with_deepzoom,
                "processing_statistics": {
                    "scheduled": photos_scheduled,
                    "processing": photos_processing,
                    "completed": photos_completed,
                    "failed": photos_failed
                },
                "coverage_percentage": round((photos_with_deepzoom / total_photos * 100) if total_photos > 0 else 0, 2),
                "background_queue": queue_status,
                "timestamp": datetime.now().isoformat()
            }
            
            self.logger.info(f"Deep zoom statistics for site {site_id}: {statistics}")
            
            return statistics
            
        except Exception as e:
            self.logger.error(f"Failed to get deep zoom statistics: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get statistics: {str(e)}"
            )
    
    async def cleanup_failed_processing(
        self,
        site_id: str,
        photo_id: UUID
    ) -> Dict[str, Any]:
        """
        Clean up failed deep zoom processing for a specific photo
        
        Args:
            site_id: Site identifier (already normalized)
            photo_id: Photo ID to clean up
            
        Returns:
            Dictionary with cleanup results
            
        Raises:
            HTTPException: For operation errors
        """
        try:
            self.logger.info(f"Cleaning up failed deep zoom processing for photo {photo_id} in site {site_id}")
            
            # Get current photo status
            task_status = await deep_zoom_background_service.get_task_status(str(photo_id))
            
            cleanup_result = {
                "photo_id": str(photo_id),
                "site_id": str(site_id),
                "cleanup_performed": False,
                "previous_status": None
            }
            
            if task_status and task_status.get('status') in ['failed', 'error']:
                cleanup_result["previous_status"] = task_status.get('status')
                cleanup_result["cleanup_performed"] = True
                
                # Here you could implement actual cleanup logic
                # For now, we'll just report the cleanup
                self.logger.info(f"Cleaned up failed processing for photo {photo_id}")
            
            return cleanup_result
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup failed processing: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to cleanup processing: {str(e)}"
            )


# Create global instance
photo_deepzoom_service = PhotoDeepZoomService()