# app/services/tiles_verification_service.py - Periodic verification service for missing tiles

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from uuid import UUID

from app.database.base import async_session_maker
from app.models import Photo
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.archaeological_minio_service import archaeological_minio_service


class VerificationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class VerificationTask:
    """Task for periodic verification of tiles"""
    task_id: str
    site_id: str
    status: VerificationStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_photos: int = 0
    processed_photos: int = 0
    missing_tiles: int = 0
    failed_tiles: int = 0
    repaired_tiles: int = 0
    error_message: Optional[str] = None
    auto_repair_enabled: bool = True


class TilesVerificationService:
    """Service for periodic verification and automatic repair of missing tiles"""
    
    def __init__(self):
        self.verification_interval = timedelta(hours=24)  # Run every 24 hours
        self.batch_size = 50  # Process photos in batches
        self.max_concurrent_verifications = 3
        self.auto_repair_enabled = True
        self._verification_task = None
        self._running = False
        self._current_tasks = {}
        self._completed_tasks = {}
        self._task_lock = asyncio.Lock()
        
    async def start_periodic_verification(self):
        """Start the periodic verification service"""
        if self._running:
            logger.warning("Tiles verification service already running")
            return
            
        self._running = True
        self._verification_task = asyncio.create_task(self._periodic_verification_worker())
        logger.info("🔍 Tiles verification service started")
    
    async def stop_periodic_verification(self):
        """Stop the periodic verification service"""
        if not self._running:
            return
            
        self._running = False
        if self._verification_task:
            self._verification_task.cancel()
            try:
                await self._verification_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 Tiles verification service stopped")
    
    async def _periodic_verification_worker(self):
        """Background worker that runs periodic verification"""
        logger.info("🔄 Periodic verification worker started")
        
        while self._running:
            try:
                # Run verification for all sites
                await self._verify_all_sites()
                
                # Sleep until next verification
                await asyncio.sleep(self.verification_interval.total_seconds())
                
            except asyncio.CancelledError:
                logger.info("Periodic verification worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic verification worker: {e}")
                # Sleep for a shorter interval on error
                await asyncio.sleep(300)  # 5 minutes
    
    async def _verify_all_sites(self):
        """Verify tiles for all sites"""
        try:
            async with async_session_maker() as db:
                # Get all unique site IDs from photos
                site_ids_query = select(Photo.site_id).distinct()
                site_ids_result = await db.execute(site_ids_query)
                site_ids = [row[0] for row in site_ids_result.fetchall()]
                
                logger.info(f"Starting verification for {len(site_ids)} sites")
                
                # Create semaphore to limit concurrent verifications
                semaphore = asyncio.Semaphore(self.max_concurrent_verifications)
                
                # Run verification for each site concurrently
                verification_tasks = []
                for site_id in site_ids:
                    task = self._verify_site_with_semaphore(semaphore, str(site_id))
                    verification_tasks.append(task)
                
                # Wait for all verifications to complete
                results = await asyncio.gather(*verification_tasks, return_exceptions=True)
                
                # Process results
                successful_verifications = 0
                failed_verifications = 0
                
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Verification failed for site {site_ids[i]}: {result}")
                        failed_verifications += 1
                    else:
                        logger.info(f"Verification completed for site {site_ids[i]}: {result}")
                        successful_verifications += 1
                
                logger.info(f"Site verification completed: {successful_verifications} successful, {failed_verifications} failed")
                
        except Exception as e:
            logger.error(f"Error verifying all sites: {e}")
    
    async def _verify_site_with_semaphore(self, semaphore: asyncio.Semaphore, site_id: str):
        """Verify site with semaphore control"""
        async with semaphore:
            return await self._verify_site(site_id)
    
    async def _verify_site(self, site_id: str) -> Dict[str, Any]:
        """Verify tiles for a specific site"""
        task_id = f"site_{site_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create verification task
        task = VerificationTask(
            task_id=task_id,
            site_id=site_id,
            status=VerificationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            auto_repair_enabled=self.auto_repair_enabled
        )
        
        async with self._task_lock:
            self._current_tasks[task_id] = task
        
        try:
            logger.info(f"Starting verification for site {site_id} (task: {task_id})")
            
            task.status = VerificationStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            
            # Get all photos for the site
            async with async_session_maker() as db:
                photos_query = select(Photo).where(Photo.site_id == UUID(site_id))
                photos_result = await db.execute(photos_query)
                photos = photos_result.scalars().all()
                
                task.total_photos = len(photos)
                logger.info(f"Found {len(photos)} photos to verify for site {site_id}")
                
                # Process photos in batches
                missing_tiles_photos = []
                
                for i in range(0, len(photos), self.batch_size):
                    batch = photos[i:i + self.batch_size]
                    
                    # Verify batch
                    batch_results = await self._verify_photo_batch(site_id, batch)
                    
                    # Collect photos with missing tiles
                    for photo, has_tiles in batch_results:
                        task.processed_photos += 1
                        
                        if not has_tiles:
                            missing_tiles_photos.append(photo)
                            task.missing_tiles += 1
                    
                    # Log progress
                    progress = (task.processed_photos / task.total_photos) * 100
                    logger.info(f"Site {site_id} verification progress: {progress:.1f}% ({task.processed_photos}/{task.total_photos})")
                    
                    # Small delay between batches
                    await asyncio.sleep(0.1)
                
                # Auto-repair missing tiles if enabled
                if task.auto_repair_enabled and missing_tiles_photos:
                    logger.info(f"Starting auto-repair for {len(missing_tiles_photos)} photos with missing tiles")
                    repair_results = await self._auto_repair_photos(site_id, missing_tiles_photos)
                    
                    task.repaired_tiles = repair_results.get('repaired', 0)
                    task.failed_tiles = repair_results.get('failed', 0)
                
                # Mark task as completed
                task.status = VerificationStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                
                # Move to completed tasks
                async with self._task_lock:
                    if task_id in self._current_tasks:
                        del self._current_tasks[task_id]
                    self._completed_tasks[task_id] = task
                
                result = {
                    "task_id": task_id,
                    "site_id": site_id,
                    "status": "completed",
                    "total_photos": task.total_photos,
                    "processed_photos": task.processed_photos,
                    "missing_tiles": task.missing_tiles,
                    "repaired_tiles": task.repaired_tiles,
                    "failed_tiles": task.failed_tiles,
                    "duration": (task.completed_at - task.started_at).total_seconds() if task.started_at else 0
                }
                
                logger.info(f"Verification completed for site {site_id}: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Verification failed for site {site_id}: {e}")
            
            task.status = VerificationStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            
            # Move to completed tasks
            async with self._task_lock:
                if task_id in self._current_tasks:
                    del self._current_tasks[task_id]
                self._completed_tasks[task_id] = task
            
            return {
                "task_id": task_id,
                "site_id": site_id,
                "status": "failed",
                "error": str(e),
                "processed_photos": task.processed_photos,
                "missing_tiles": task.missing_tiles
            }
    
    async def _verify_photo_batch(self, site_id: str, photos: List[Photo]) -> List[Tuple[Photo, bool]]:
        """Verify a batch of photos for tiles"""
        results = []
        
        # Create semaphore for concurrent verification
        semaphore = asyncio.Semaphore(10)  # Limit concurrent checks
        
        # Create verification tasks
        verification_tasks = []
        for photo in photos:
            task = self._verify_single_photo_with_semaphore(semaphore, site_id, photo)
            verification_tasks.append(task)
        
        # Wait for all verifications to complete
        batch_results = await asyncio.gather(*verification_tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.error(f"Error verifying photo {photos[i].id}: {result}")
                results.append((photos[i], False))  # Assume no tiles on error
            else:
                results.append((photos[i], result))
        
        return results
    
    async def _verify_single_photo_with_semaphore(
        self, 
        semaphore: asyncio.Semaphore, 
        site_id: str, 
        photo: Photo
    ) -> bool:
        """Verify single photo with semaphore control"""
        async with semaphore:
            return await self._verify_single_photo(site_id, photo)
    
    async def _verify_single_photo(self, site_id: str, photo: Photo) -> bool:
        """Verify if a single photo has tiles"""
        try:
            # Check if tiles are already marked as available in database
            if photo.has_deep_zoom and photo.deepzoom_status == 'completed':
                # Verify tiles actually exist in storage
                tile_info = await deep_zoom_minio_service.get_deep_zoom_info(site_id, str(photo.id))
                if tile_info and tile_info.get('available', False):
                    return True
            
            # Check if there's a processing task
            task_status = await deep_zoom_background_service.get_task_status(str(photo.id))
            if task_status and task_status['status'] in ['pending', 'processing', 'retrying']:
                return True  # Consider as "has tiles" since processing is underway
            
            # Check processing status
            processing_status = await deep_zoom_minio_service.get_processing_status(site_id, str(photo.id))
            if processing_status and processing_status.get('status') in ['processing', 'uploading']:
                return True
            
            # Check if tiles exist in storage
            tile_info = await deep_zoom_minio_service.get_deep_zoom_info(site_id, str(photo.id))
            return tile_info is not None and tile_info.get('available', False)
            
        except Exception as e:
            logger.error(f"Error verifying photo {photo.id}: {e}")
            return False
    
    async def _auto_repair_photos(self, site_id: str, photos: List[Photo]) -> Dict[str, int]:
        """Automatically repair tiles for photos"""
        repaired = 0
        failed = 0
        
        # Create semaphore for concurrent repairs
        semaphore = asyncio.Semaphore(3)  # Limit concurrent repairs
        
        # Create repair tasks
        repair_tasks = []
        for photo in photos:
            task = self._repair_single_photo_with_semaphore(semaphore, site_id, photo)
            repair_tasks.append(task)
        
        # Wait for all repairs to complete
        repair_results = await asyncio.gather(*repair_tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(repair_results):
            if isinstance(result, Exception):
                logger.error(f"Error repairing photo {photos[i].id}: {result}")
                failed += 1
            elif result:
                repaired += 1
            else:
                failed += 1
        
        logger.info(f"Auto-repair completed for site {site_id}: {repaired} repaired, {failed} failed")
        
        return {
            "repaired": repaired,
            "failed": failed
        }
    
    async def _repair_single_photo_with_semaphore(
        self, 
        semaphore: asyncio.Semaphore, 
        site_id: str, 
        photo: Photo
    ) -> bool:
        """Repair single photo with semaphore control"""
        async with semaphore:
            return await self._repair_single_photo(site_id, photo)
    
    async def _repair_single_photo(self, site_id: str, photo: Photo) -> bool:
        """Repair tiles for a single photo"""
        try:
            # Load original file content
            original_file_content = await archaeological_minio_service.get_file(photo.filepath)
            
            # Prepare archaeological metadata
            archaeological_metadata = {
                'inventory_number': photo.inventory_number,
                'excavation_area': photo.excavation_area,
                'material': photo.material,  # Already stored as string value
                'chronology_period': photo.chronology_period,
                'photo_type': photo.photo_type,  # Already stored as string value
                'photographer': photo.photographer,
                'description': photo.description,
                'keywords': photo.keywords
            }
            
            # Schedule tile processing
            result = await deep_zoom_background_service.schedule_tile_processing(
                photo_id=str(photo.id),
                site_id=site_id,
                file_path=photo.filepath,
                original_file_content=original_file_content,
                archaeological_metadata=archaeological_metadata
            )
            
            # Update database status
            async with async_session_maker() as db:
                photo_query = select(Photo).where(Photo.id == photo.id)
                photo_result = await db.execute(photo_query)
                photo_record = photo_result.scalar_one_or_none()
                
                if photo_record:
                    photo_record.deepzoom_status = 'scheduled'
                    await db.commit()
            
            logger.info(f"Auto-repair scheduled for photo {photo.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to repair photo {photo.id}: {e}")
            return False
    
    async def get_verification_status(self) -> Dict[str, Any]:
        """Get overall verification service status"""
        async with self._task_lock:
            current_tasks = list(self._current_tasks.values())
            completed_tasks = list(self._completed_tasks.values())
        
        # Calculate statistics
        total_processed = sum(task.processed_photos for task in completed_tasks)
        total_missing = sum(task.missing_tiles for task in completed_tasks)
        total_repaired = sum(task.repaired_tiles for task in completed_tasks)
        
        return {
            "service_running": self._running,
            "verification_interval_hours": self.verification_interval.total_seconds() / 3600,
            "auto_repair_enabled": self.auto_repair_enabled,
            "current_tasks": [
                {
                    "task_id": task.task_id,
                    "site_id": task.site_id,
                    "status": task.status.value,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "total_photos": task.total_photos,
                    "processed_photos": task.processed_photos,
                    "missing_tiles": task.missing_tiles,
                    "repaired_tiles": task.repaired_tiles
                }
                for task in current_tasks
            ],
            "statistics": {
                "total_completed_tasks": len(completed_tasks),
                "total_photos_processed": total_processed,
                "total_missing_tiles_found": total_missing,
                "total_tiles_repaired": total_repaired,
                "repair_success_rate": (total_repaired / total_missing * 100) if total_missing > 0 else 0
            },
            "recent_tasks": [
                {
                    "task_id": task.task_id,
                    "site_id": task.site_id,
                    "status": task.status.value,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "total_photos": task.total_photos,
                    "missing_tiles": task.missing_tiles,
                    "repaired_tiles": task.repaired_tiles
                }
                for task in sorted(completed_tasks, key=lambda t: t.completed_at or datetime.min, reverse=True)[:10]
            ]
        }
    
    async def trigger_manual_verification(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Trigger manual verification for specific site or all sites"""
        if site_id:
            logger.info(f"Manual verification triggered for site {site_id}")
            result = await self._verify_site(site_id)
            return result
        else:
            logger.info("Manual verification triggered for all sites")
            await self._verify_all_sites()
            return {
                "message": "Manual verification started for all sites",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def configure_settings(
        self,
        verification_interval_hours: Optional[int] = None,
        batch_size: Optional[int] = None,
        max_concurrent_verifications: Optional[int] = None,
        auto_repair_enabled: Optional[bool] = None
    ):
        """Configure verification service settings"""
        if verification_interval_hours is not None:
            self.verification_interval = timedelta(hours=verification_interval_hours)
        
        if batch_size is not None:
            self.batch_size = batch_size
        
        if max_concurrent_verifications is not None:
            self.max_concurrent_verifications = max_concurrent_verifications
        
        if auto_repair_enabled is not None:
            self.auto_repair_enabled = auto_repair_enabled
        
        logger.info(f"Verification service configured: interval={self.verification_interval}, "
                   f"batch_size={self.batch_size}, max_concurrent={self.max_concurrent_verifications}, "
                   f"auto_repair={self.auto_repair_enabled}")


# Global instance
tiles_verification_service = TilesVerificationService()