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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="start_background_processor",
            site_id=str(site_id),
            user_id=str(current_user_id),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "🔄 BACKGROUND PROCESSOR START REQUEST",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "start_background_processor"
                    }
                )
                
                processor_start_time = time.time()
                await deep_zoom_background_service.start_background_processor()
                processor_start_time = time.time() - processor_start_time
                
                self.logger.success(
                    "✅ BACKGROUND PROCESSOR STARTED SUCCESSFULLY",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "processor_start_time_ms": round(processor_start_time * 1000, 2),
                        "started_at": datetime.now().isoformat()
                    }
                )
                
                total_time = time.time() - operation_start_time
                
                return {
                    "message": "Deep zoom background processor started successfully",
                    "site_id": str(site_id),
                    "started_by": str(current_user_id),
                    "started_at": datetime.now().isoformat(),
                    "processor_start_time_ms": round(processor_start_time * 1000, 2),
                    "total_operation_time_ms": round(total_time * 1000, 2)
                }
            
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ BACKGROUND PROCESSOR START FAILED",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "background_processor_start"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 BACKGROUND PROCESSOR START ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="stop_background_processor",
            site_id=str(site_id),
            user_id=str(current_user_id),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "🛑 BACKGROUND PROCESSOR STOP REQUEST",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "stop_background_processor"
                    }
                )
                
                processor_stop_time = time.time()
                await deep_zoom_background_service.stop_background_processor()
                processor_stop_time = time.time() - processor_stop_time
                
                self.logger.success(
                    "✅ BACKGROUND PROCESSOR STOPPED SUCCESSFULLY",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "processor_stop_time_ms": round(processor_stop_time * 1000, 2),
                        "stopped_at": datetime.now().isoformat()
                    }
                )
                
                total_time = time.time() - operation_start_time
                
                return {
                    "message": "Deep zoom background processor stopped successfully",
                    "site_id": str(site_id),
                    "stopped_by": str(current_user_id),
                    "stopped_at": datetime.now().isoformat(),
                    "processor_stop_time_ms": round(processor_stop_time * 1000, 2),
                    "total_operation_time_ms": round(total_time * 1000, 2)
                }
            
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ BACKGROUND PROCESSOR STOP FAILED",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "background_processor_stop"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 BACKGROUND PROCESSOR STOP ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="get_background_status",
            site_id=str(site_id),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "📊 BACKGROUND STATUS REQUEST",
                    extra={
                        "site_id": str(site_id),
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "get_background_status"
                    }
                )
                
                status_fetch_time = time.time()
                queue_status = await deep_zoom_background_service.get_queue_status()
                status_fetch_time = time.time() - status_fetch_time
                
                self.logger.info(
                    "✅ BACKGROUND STATUS RETRIEVED",
                    extra={
                        "site_id": str(site_id),
                        "status_fetch_time_ms": round(status_fetch_time * 1000, 2),
                        "queue_status": queue_status,
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                total_time = time.time() - operation_start_time
                
                return {
                    "site_id": str(site_id),
                    "background_status": queue_status,
                    "timestamp": datetime.now().isoformat(),
                    "status_fetch_time_ms": round(status_fetch_time * 1000, 2),
                    "total_operation_time_ms": round(total_time * 1000, 2)
                }
            
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ BACKGROUND STATUS RETRIEVAL FAILED",
                    extra={
                        "site_id": str(site_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "background_status_retrieval"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 BACKGROUND STATUS ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="get_photo_task_status",
            site_id=str(site_id),
            photo_id=str(photo_id),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "🔍 PHOTO TASK STATUS REQUEST",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "get_photo_task_status"
                    }
                )
                
                # Try to get status from background service first
                background_check_time = time.time()
                task_status = await deep_zoom_background_service.get_task_status(str(photo_id))
                background_check_time = time.time() - background_check_time
                
                self.logger.info(
                    "📊 BACKGROUND SERVICE STATUS CHECK",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "task_status_found": task_status is not None,
                        "background_check_time_ms": round(background_check_time * 1000, 2),
                        "task_status": task_status
                    }
                )
                
                if not task_status:
                    # Fallback to processing status from MinIO
                    self.logger.info(
                        "🔄 FALLING BACK TO MINIO STATUS",
                        extra={
                            "site_id": str(site_id),
                            "photo_id": str(photo_id),
                            "reason": "task_not_found_in_background_service",
                            "fallback_method": "minio_processing_status"
                        }
                    )
                    
                    minio_check_time = time.time()
                    deep_zoom_service = get_deep_zoom_minio_service()
                    processing_status = await deep_zoom_service.get_processing_status(
                        str(site_id), str(photo_id)
                    )
                    minio_check_time = time.time() - minio_check_time
                    
                    total_time = time.time() - operation_start_time
                    
                    self.logger.info(
                        "✅ MINIO FALLBACK STATUS RETRIEVED",
                        extra={
                            "site_id": str(site_id),
                            "photo_id": str(photo_id),
                            "minio_check_time_ms": round(minio_check_time * 1000, 2),
                            "processing_status": processing_status,
                            "fallback_used": True
                        }
                    )
                    
                    return {
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "task_status": None,
                        "processing_status": processing_status,
                        "message": "Task not found in background service, checking MinIO status",
                        "background_check_time_ms": round(background_check_time * 1000, 2),
                        "minio_check_time_ms": round(minio_check_time * 1000, 2),
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "fallback_used": True
                    }
                
                total_time = time.time() - operation_start_time
                
                self.logger.success(
                    "✅ PHOTO TASK STATUS RETRIEVED FROM BACKGROUND",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "task_status": task_status,
                        "background_check_time_ms": round(background_check_time * 1000, 2),
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "fallback_used": False
                    }
                )
                
                return {
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "task_status": task_status,
                    "message": "Task status from background service",
                    "background_check_time_ms": round(background_check_time * 1000, 2),
                    "total_operation_time_ms": round(total_time * 1000, 2),
                    "fallback_used": False
                }
            
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ PHOTO TASK STATUS RETRIEVAL FAILED",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "photo_task_status_retrieval"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 PHOTO TASK STATUS ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="schedule_photo_processing",
            site_id=str(site_id),
            user_id=str(current_user_id),
            photo_count=len(photo_ids),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "📅 BATCH PROCESSING SCHEDULING STARTED",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "photo_count": len(photo_ids),
                        "photo_ids": photo_ids[:10],  # Log first 10 IDs to avoid huge logs
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "schedule_photo_processing"
                    }
                )
                
                # Prepare photos list for background service
                preparation_start_time = time.time()
                photos_list = []
                failed_photos = []
                
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
                        failed_photos.append({
                            'photo_id': photo_id,
                            'error': str(e),
                            'error_type': type(e).__name__
                        })
                        self.logger.warning(
                            "⚠️ PHOTO PREPARATION FAILED",
                            extra={
                                "site_id": str(site_id),
                                "photo_id": photo_id,
                                "error": str(e),
                                "error_type": type(e).__name__
                            }
                        )
                        continue
                
                preparation_time = time.time() - preparation_start_time
                
                self.logger.info(
                    "📋 PHOTO PREPARATION COMPLETED",
                    extra={
                        "site_id": str(site_id),
                        "total_photos": len(photo_ids),
                        "successful_preparations": len(photos_list),
                        "failed_preparations": len(failed_photos),
                        "preparation_time_ms": round(preparation_time * 1000, 2),
                        "failed_photos": failed_photos[:5]  # Log first 5 failures
                    }
                )
                
                if not photos_list:
                    self.logger.error(
                        "❌ NO VALID PHOTOS TO PROCESS",
                        extra={
                            "site_id": str(site_id),
                            "total_requested": len(photo_ids),
                            "failed_count": len(failed_photos),
                            "all_photos_failed": True
                        }
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="No valid photos to process"
                    )
                
                # Schedule batch processing
                scheduling_start_time = time.time()
                batch_result = await deep_zoom_background_service.schedule_batch_processing(
                    photos_list=photos_list,
                    site_id=site_id
                )
                scheduling_time = time.time() - scheduling_start_time
                
                total_time = time.time() - operation_start_time
                
                self.logger.success(
                    "✅ BATCH PROCESSING SCHEDULED SUCCESSFULLY",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "scheduled_count": len(photos_list),
                        "batch_result": batch_result,
                        "preparation_time_ms": round(preparation_time * 1000, 2),
                        "scheduling_time_ms": round(scheduling_time * 1000, 2),
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failed_photos_count": len(failed_photos)
                    }
                )
                
                return {
                    "message": f"Deep zoom processing scheduled for {len(photos_list)} photos",
                    "scheduled_count": len(photos_list),
                    "batch_result": batch_result,
                    "site_id": str(site_id),
                    "scheduled_by": str(current_user_id),
                    "scheduled_at": datetime.now().isoformat(),
                    "preparation_time_ms": round(preparation_time * 1000, 2),
                    "scheduling_time_ms": round(scheduling_time * 1000, 2),
                    "total_operation_time_ms": round(total_time * 1000, 2),
                    "failed_photos": failed_photos
                }
            
            except HTTPException:
                raise
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ BATCH PROCESSING SCHEDULING FAILED",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "photo_count": len(photo_ids),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "batch_processing_scheduling"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 BATCH SCHEDULING ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "user_id": str(current_user_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="get_site_deep_zoom_statistics",
            site_id=str(site_id),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "📊 DEEP ZOOM STATISTICS REQUEST",
                    extra={
                        "site_id": str(site_id),
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "get_site_deep_zoom_statistics"
                    }
                )
                
                # Query photos for statistics
                database_query_time = time.time()
                photos_query = select(Photo).where(Photo.site_id == site_id)
                photos_result = await db.execute(photos_query)
                photos = photos_result.scalars().all()
                database_query_time = time.time() - database_query_time
                
                self.logger.info(
                    "🗄️ DATABASE QUERY COMPLETED",
                    extra={
                        "site_id": str(site_id),
                        "photos_count": len(photos),
                        "database_query_time_ms": round(database_query_time * 1000, 2)
                    }
                )
                
                # Calculate statistics
                calculation_start_time = time.time()
                total_photos = len(photos)
                photos_with_deepzoom = sum(1 for p in photos if p.has_deep_zoom)
                photos_processing = sum(1 for p in photos if p.deepzoom_status == 'processing')
                photos_completed = sum(1 for p in photos if p.deepzoom_status == 'completed')
                photos_failed = sum(1 for p in photos if p.deepzoom_status == 'failed')
                photos_scheduled = sum(1 for p in photos if p.deepzoom_status == 'scheduled')
                photos_not_started = sum(1 for p in photos if not p.deepzoom_status or p.deepzoom_status == 'not_started')
                calculation_time = time.time() - calculation_start_time
                
                # Get background queue status
                queue_check_time = time.time()
                queue_status = await deep_zoom_background_service.get_queue_status()
                queue_check_time = time.time() - queue_check_time
                
                total_time = time.time() - operation_start_time
                
                statistics = {
                    "site_id": str(site_id),
                    "total_photos": total_photos,
                    "photos_with_deepzoom": photos_with_deepzoom,
                    "photos_without_deepzoom": total_photos - photos_with_deepzoom,
                    "processing_statistics": {
                        "not_started": photos_not_started,
                        "scheduled": photos_scheduled,
                        "processing": photos_processing,
                        "completed": photos_completed,
                        "failed": photos_failed
                    },
                    "coverage_percentage": round((photos_with_deepzoom / total_photos * 100) if total_photos > 0 else 0, 2),
                    "background_queue": queue_status,
                    "performance_metrics": {
                        "database_query_time_ms": round(database_query_time * 1000, 2),
                        "calculation_time_ms": round(calculation_time * 1000, 2),
                        "queue_check_time_ms": round(queue_check_time * 1000, 2),
                        "total_operation_time_ms": round(total_time * 1000, 2)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
                self.logger.success(
                    "✅ DEEP ZOOM STATISTICS CALCULATED",
                    extra={
                        "site_id": str(site_id),
                        "total_photos": total_photos,
                        "photos_with_deepzoom": photos_with_deepzoom,
                        "coverage_percentage": statistics["coverage_percentage"],
                        "processing_breakdown": statistics["processing_statistics"],
                        "database_query_time_ms": round(database_query_time * 1000, 2),
                        "calculation_time_ms": round(calculation_time * 1000, 2),
                        "queue_check_time_ms": round(queue_check_time * 1000, 2),
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "queue_status": queue_status
                    }
                )
                
                return statistics
            
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ DEEP ZOOM STATISTICS CALCULATION FAILED",
                    extra={
                        "site_id": str(site_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "statistics_calculation"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 STATISTICS ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
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
        import time
        operation_start_time = time.time()
        
        with logger.contextualize(
            operation="cleanup_failed_processing",
            site_id=str(site_id),
            photo_id=str(photo_id),
            service="photo_deepzoom_service"
        ):
            try:
                self.logger.info(
                    "🧹 FAILED PROCESSING CLEANUP REQUEST",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "request_timestamp": datetime.now().isoformat(),
                        "operation": "cleanup_failed_processing"
                    }
                )
                
                # Get current photo status
                status_check_time = time.time()
                task_status = await deep_zoom_background_service.get_task_status(str(photo_id))
                status_check_time = time.time() - status_check_time
                
                self.logger.info(
                    "📊 TASK STATUS CHECK FOR CLEANUP",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "task_status_found": task_status is not None,
                        "status_check_time_ms": round(status_check_time * 1000, 2),
                        "task_status": task_status
                    }
                )
                
                cleanup_result = {
                    "photo_id": str(photo_id),
                    "site_id": str(site_id),
                    "cleanup_performed": False,
                    "previous_status": None,
                    "cleanup_timestamp": datetime.now().isoformat()
                }
                
                if task_status and task_status.get('status') in ['failed', 'error']:
                    cleanup_result["previous_status"] = task_status.get('status')
                    cleanup_result["cleanup_performed"] = True
                    
                    # Here you could implement actual cleanup logic
                    # For now, we'll just report the cleanup
                    self.logger.success(
                        "✅ FAILED PROCESSING CLEANUP COMPLETED",
                        extra={
                            "site_id": str(site_id),
                            "photo_id": str(photo_id),
                            "previous_status": task_status.get('status'),
                            "cleanup_performed": True,
                            "status_check_time_ms": round(status_check_time * 1000, 2),
                            "cleanup_timestamp": datetime.now().isoformat()
                        }
                    )
                else:
                    self.logger.info(
                        "ℹ️ NO CLEANUP NEEDED",
                    extra={
                            "site_id": str(site_id),
                            "photo_id": str(photo_id),
                            "reason": "task_not_in_failed_state",
                            "task_status": task_status.get('status') if task_status else None,
                            "cleanup_performed": False
                        }
                    )
                
                total_time = time.time() - operation_start_time
                cleanup_result["total_operation_time_ms"] = round(total_time * 1000, 2)
                
                self.logger.info(
                    "🎯 CLEANUP OPERATION COMPLETED",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "cleanup_result": cleanup_result,
                        "total_operation_time_ms": round(total_time * 1000, 2)
                    }
                )
                
                return cleanup_result
            
            except Exception as e:
                total_time = time.time() - operation_start_time
                
                self.logger.error(
                    "❌ FAILED PROCESSING CLEANUP ERROR",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_time * 1000, 2),
                        "failure_point": "cleanup_failed_processing"
                    }
                )
                
                import traceback
                self.logger.error(
                    "📋 CLEANUP ERROR TRACEBACK",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to cleanup processing: {str(e)}"
                )


# Create global instance
photo_deepzoom_service = PhotoDeepZoomService()