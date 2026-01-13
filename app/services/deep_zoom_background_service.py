# app/services/deep_zoom_background_service.py - Background processing service for deep zoom tiles

import asyncio
import json
import io
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from loguru import logger
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.routes.api.dependencies import normalize_site_id
import math

from app.core.interfaces.storage import FileStorageInterface
from app.core.interfaces.image import ImageProcessorInterface
from app.repositories.photo_repository import PhotoRepository
from app.database.session import AsyncSessionLocal
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom.image_processor import DeepZoomImageProcessor

from app.models.deepzoom_enums import DeepZoomStatus




@dataclass
class TileProcessingTask:
    """Task for processing a single photo's tiles"""
    photo_id: str
    site_id: str
    file_path: str
    original_file_content: bytes
    archaeological_metadata: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3
    status: DeepZoomStatus = DeepZoomStatus.SCHEDULED
    error_message: Optional[str] = None
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # 🔧 SNAPSHOT-BASED: Add snapshot data field to eliminate database queries
    snapshot_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class DeepZoomBackgroundService:
    """Background processing service for deep zoom tiles with retry mechanism (Clean Architecture)"""
    
    def __init__(
        self,
        storage_service: Optional[FileStorageInterface] = None,
        image_processor: Optional[ImageProcessorInterface] = None,
        session_factory = None
    ):
        self.tile_size = 256
        self.overlap = 0
        self.format = 'jpg'
        self.max_concurrent_tasks = 3  # Limit concurrent processing
        self.max_concurrent_uploads = 10  # Limit concurrent uploads
        self.task_queue = asyncio.Queue()
        self.processing_tasks = {}
        self.completed_tasks = {}
        self.failed_tasks = {}
        self._worker_task = None
        self._running = False
        
        # Dependency Injection
        self.storage = storage_service or archaeological_minio_service
        self.image_processor = image_processor or DeepZoomImageProcessor()
        self.session_factory = session_factory or AsyncSessionLocal
        
        # CRITICO: Locks per task deduplication e concorrenza
        self._processing_lock = asyncio.Lock()
        self._task_locks = {}  # photo_id -> Lock
        self._processing_photo_ids = set()  # Track currently processing photos
        
        # Task timeout and cleanup settings
        self.task_timeout_seconds = 1800  # 30 minutes max per task
        self.stuck_task_check_interval = 300  # Check every 5 minutes
        self.last_stuck_task_check = datetime.now()
        
        # Health tracking
        self.service_start_time = datetime.now()
        self.total_tasks_processed = 0
        self.total_tasks_failed = 0
        
        # Batch processing context tracking
        self._batch_context = {}  # site_id -> {"photos": [], "started_at": datetime}
        self._photo_order = {}  # photo_id -> position in batch

    async def start_background_processor(self):
        """Start the background processor worker"""
        if self._running:
            logger.warning("Background processor already running")
            return
            
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue_worker())
        logger.debug("Deep zoom background processor started")

    async def stop_background_processor(self):
        """Stop the background processor worker"""
        if not self._running:
            return
            
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Deep zoom background processor stopped")

    async def schedule_tile_processing(
        self,
        photo_id: str,
        site_id: str,
        file_path: str,
        original_file_content: bytes,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Schedule a photo for tile processing with deduplication"""
        
        # 🔧 UUID NORMALIZATION: Normalize site_id for consistent handling
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.warning(f"Invalid site_id format: {site_id}")
            # Continue with original site_id but log warning to avoid breaking pipeline
        
        # Use normalized site_id if available, otherwise use original
        effective_site_id = normalized_site_id if normalized_site_id else site_id
        
        # CRITICO: Acquisisci lock per deduplicazione atomica
        async with self._processing_lock:
            # Verifica se il task è già in coda o in elaborazione
            if photo_id in self.processing_tasks:
                existing_task = self.processing_tasks[photo_id]
                if existing_task.status in [DeepZoomStatus.SCHEDULED, DeepZoomStatus.PROCESSING, DeepZoomStatus.RETRYING]:
                    logger.info(f"🔄 Task already scheduled/processing for photo {photo_id}")
                    return {
                        'photo_id': photo_id,
                        'site_id': effective_site_id,
                        'status': 'already_scheduled',
                        'message': f'Task already {existing_task.status.value}',
                        'scheduled_at': datetime.now().isoformat()
                    }
            
            # Verifica se il task è stato completato di recente (evita duplicati)
            if photo_id in self.completed_tasks:
                completed_task = self.completed_tasks[photo_id]
                # Considera completato solo se meno di 1 ora fa
                if completed_task.completed_at and (datetime.now() - completed_task.completed_at).total_seconds() < 3600:
                    logger.info(f"✅ Task already completed recently for photo {photo_id}")
                    return {
                        'photo_id': photo_id,
                        'site_id': effective_site_id,
                        'status': 'already_completed',
                        'message': 'Task completed recently',
                        'completed_at': completed_task.completed_at.isoformat()
                    }
            
            # Crea nuovo task with normalized site_id
            task = TileProcessingTask(
                photo_id=photo_id,
                site_id=effective_site_id,  # Use normalized site_id
                file_path=file_path,
                original_file_content=original_file_content,
                archaeological_metadata=archaeological_metadata
            )
            
            # Aggiungi a coda e tracking
            await self.task_queue.put(task)
            self.processing_tasks[photo_id] = task
            self._processing_photo_ids.add(photo_id)
            
            logger.info(f"📋 Scheduled tile processing for photo {photo_id}")
            
            return {
                'photo_id': photo_id,
                'site_id': effective_site_id,
                'status': 'scheduled',
                'message': 'Tile processing scheduled in background',
                'scheduled_at': datetime.now().isoformat()
            }

    async def schedule_batch_processing(
        self,
        photos_list: List[Dict[str, Any]],
        site_id: str
    ) -> Dict[str, Any]:
        """Schedule multiple photos for batch processing"""
        
        # 🔧 UUID NORMALIZATION: Normalize site_id for batch processing
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.warning(f"Invalid site_id format in batch processing: {site_id}")
            # Continue with original site_id but log warning
        
        # Use normalized site_id if available, otherwise use original
        effective_site_id = normalized_site_id if normalized_site_id else site_id
        
        # Initialize batch context with normalized site_id
        async with self._processing_lock:
            if effective_site_id not in self._batch_context:
                self._batch_context[effective_site_id] = {
                    "photos": [],
                    "started_at": datetime.now()
                }
            
            # Add photos to batch context
            batch_context = self._batch_context[effective_site_id]
            for i, photo_info in enumerate(photos_list):
                photo_id = photo_info['photo_id']
                # Check for existing photos using both 'photo_id' and 'id' keys for compatibility
                existing_photos = [p.get('photo_id', p.get('id')) for p in batch_context['photos']]
                if photo_id not in existing_photos:
                    self._photo_order[photo_id] = len(batch_context['photos'])
                    batch_context['photos'].append(photo_info)
        
        scheduled_count = 0
        for photo_info in photos_list:
            try:
                # Load file content from MinIO
                from app.services.archaeological_minio_service import archaeological_minio_service
                original_file_content = await archaeological_minio_service.get_file(photo_info['file_path'])
                
                # 🔧 VALIDATION: Basic content validation before scheduling
                if not original_file_content or len(original_file_content) < 100:
                    logger.error(f"❌ Invalid or empty image content for photo {photo_info['photo_id']}: {len(original_file_content) if original_file_content else 0} bytes")
                    continue
                
                await self.schedule_tile_processing(
                    photo_id=photo_info['photo_id'],
                    site_id=effective_site_id,  # Use normalized site_id
                    file_path=photo_info['file_path'],
                    original_file_content=original_file_content,
                    archaeological_metadata=photo_info.get('archaeological_metadata', photo_info.get('metadata', {}))
                )
                scheduled_count += 1
                
            except Exception as e:
                logger.error(f"Failed to schedule processing for photo {photo_info.get('photo_id')}: {e}")
        
        logger.info(f"📋 Scheduled {scheduled_count} photos for batch processing")
        
        return {
            'site_id': effective_site_id,
            'scheduled_count': scheduled_count,
            'total_photos': len(photos_list),
            'status': 'scheduled',
            'message': f'{scheduled_count} photos scheduled for background processing'
        }

    async def schedule_batch_processing_with_snapshots(
        self,
        photo_snapshots: List[Dict[str, Any]],
        site_id: str
    ) -> Dict[str, Any]:
        """
        🔧 SNAPSHOT-BASED SOLUTION: Schedule multiple photos for batch processing using complete snapshots.
        
        This method eliminates race conditions by using complete photo snapshots instead of
        querying the database for photo records that may not be visible due to SQLite WAL delays.
        
        Args:
            photo_snapshots: List of complete photo snapshots with all necessary data
            site_id: Site ID for batch processing
            
        Returns:
            Dict with scheduling results
        """
        
        # 🔧 UUID NORMALIZATION: Normalize site_id for batch processing
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.warning(f"Invalid site_id format in snapshot batch processing: {site_id}")
            # Continue with original site_id but log warning
        
        # Use normalized site_id if available, otherwise use original
        effective_site_id = normalized_site_id if normalized_site_id else site_id
        
        # Initialize batch context with normalized site_id
        async with self._processing_lock:
            if effective_site_id not in self._batch_context:
                self._batch_context[effective_site_id] = {
                    "photos": [],
                    "started_at": datetime.now()
                }
            
            # Add photo snapshots to batch context
            batch_context = self._batch_context[effective_site_id]
            for i, photo_snapshot in enumerate(photo_snapshots):
                photo_id = photo_snapshot['id']
                # Check for existing photos using both 'photo_id' and 'id' keys for compatibility
                existing_photos = [p.get('photo_id', p.get('id')) for p in batch_context['photos']]
                if photo_id not in existing_photos:
                    self._photo_order[photo_id] = len(batch_context['photos'])
                    batch_context['photos'].append(photo_snapshot)
        
        scheduled_count = 0
        logger.info(f"🔧 SNAPSHOT-BASED: Processing {len(photo_snapshots)} photo snapshots for site {effective_site_id}")
        
        for photo_snapshot in photo_snapshots:
            try:
                photo_id = photo_snapshot['id']
                
                # 🔧 SNAPSHOT-BASED: Use snapshot data directly instead of querying database
                logger.debug(f"🔧 SNAPSHOT-BASED: Processing snapshot for photo {photo_id}")
                
                # Load file content from MinIO using snapshot file_path
                from app.services.archaeological_minio_service import archaeological_minio_service
                
                # Extract object_name from file_path (may be full URL or relative path)
                raw_file_path = photo_snapshot['file_path']
                bucket_name = archaeological_minio_service.buckets['photos']
                
                # If file_path is a full URL, extract just the object name
                if raw_file_path.startswith('http://') or raw_file_path.startswith('https://'):
                    # URL format: http://host:port/bucket/object_name
                    # Extract everything after the bucket name
                    import re
                    match = re.search(rf'/{bucket_name}/(.+)$', raw_file_path)
                    if match:
                        object_name = match.group(1)
                    else:
                        # Fallback: try to extract path after last occurrence of bucket name
                        parts = raw_file_path.split(f'/{bucket_name}/')
                        object_name = parts[-1] if len(parts) > 1 else raw_file_path
                else:
                    object_name = raw_file_path
                
                logger.debug(f"🔧 SNAPSHOT-BASED: Extracted object_name '{object_name}' from file_path '{raw_file_path}'")
                
                original_file_content = await archaeological_minio_service.get_file(
                    bucket=bucket_name,
                    object_name=object_name
                )
                
                # 🔧 VALIDATION: Basic content validation before scheduling
                if not original_file_content or len(original_file_content) < 100:
                    logger.error(f"❌ SNAPSHOT-BASED: Invalid or empty image content for photo {photo_id}: {len(original_file_content) if original_file_content else 0} bytes")
                    continue
                
                # Extract archaeological metadata from snapshot (check both possible keys)
                archaeological_metadata = photo_snapshot.get('archaeological_metadata', photo_snapshot.get('metadata', {}))
                
                # Add additional metadata from snapshot if available
                if 'metadata' in photo_snapshot and 'archaeological_metadata' in photo_snapshot:
                    # If both exist, merge them
                    archaeological_metadata.update(photo_snapshot['metadata'])
                elif 'metadata' in photo_snapshot:
                    # If only metadata exists, use it
                    archaeological_metadata = photo_snapshot['metadata']
                
                # Schedule tile processing using snapshot data
                await self.schedule_tile_processing_with_snapshot(
                    photo_snapshot=photo_snapshot,
                    original_file_content=original_file_content,
                    archaeological_metadata=archaeological_metadata
                )
                scheduled_count += 1
                
                logger.debug(f"🔧 SNAPSHOT-BASED: Successfully scheduled photo {photo_id} from snapshot")
                
            except Exception as e:
                logger.error(f"🔧 SNAPSHOT-BASED: Failed to schedule processing for photo {photo_snapshot.get('id', 'unknown')}: {e}")
                import traceback
                logger.error(f"🔧 SNAPSHOT-BASED: Error traceback: {traceback.format_exc()}")
        
        logger.info(f"🔧 SNAPSHOT-BASED: Scheduled {scheduled_count} photos from snapshots for batch processing")
        
        return {
            'site_id': effective_site_id,
            'scheduled_count': scheduled_count,
            'total_photos': len(photo_snapshots),
            'status': 'scheduled',
            'message': f'{scheduled_count} photos scheduled from snapshots for background processing',
            'processing_method': 'snapshot-based'
        }

    async def schedule_tile_processing_with_snapshot(
        self,
        photo_snapshot: Dict[str, Any],
        original_file_content: bytes,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        🔧 SNAPSHOT-BASED SOLUTION: Schedule a photo for tile processing using complete snapshot.
        
        This method eliminates race conditions by using complete photo snapshot instead of
        querying the database for photo records that may not be visible due to SQLite WAL delays.
        
        Args:
            photo_snapshot: Complete photo snapshot with all necessary data
            original_file_content: Raw file content from MinIO
            archaeological_metadata: Archaeological metadata from snapshot
            
        Returns:
            Dict with scheduling results
        """
        
        photo_id = photo_snapshot['id']
        site_id = photo_snapshot['site_id']
        
        # 🔧 UUID NORMALIZATION: Normalize site_id for consistent handling
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.warning(f"Invalid site_id format in snapshot processing: {site_id}")
            # Continue with original site_id but log warning
        
        # Use normalized site_id if available, otherwise use original
        effective_site_id = normalized_site_id if normalized_site_id else site_id
        
        # CRITICO: Acquisisci lock per deduplicazione atomica
        async with self._processing_lock:
            # Verifica se il task è già in coda o in elaborazione
            if photo_id in self.processing_tasks:
                existing_task = self.processing_tasks[photo_id]
                if existing_task.status in [DeepZoomStatus.SCHEDULED, DeepZoomStatus.PROCESSING, DeepZoomStatus.RETRYING]:
                    logger.info(f"🔧 SNAPSHOT-BASED: Task already scheduled/processing for photo {photo_id}")
                    return {
                        'photo_id': photo_id,
                        'site_id': effective_site_id,
                        'status': 'already_scheduled',
                        'message': f'Task already {existing_task.status.value}',
                        'scheduled_at': datetime.now().isoformat(),
                        'processing_method': 'snapshot-based'
                    }
            
            # Verifica se il task è stato completato di recente (evita duplicati)
            if photo_id in self.completed_tasks:
                completed_task = self.completed_tasks[photo_id]
                # Considera completato solo se meno di 1 ora fa
                if completed_task.completed_at and (datetime.now() - completed_task.completed_at).total_seconds() < 3600:
                    logger.info(f"🔧 SNAPSHOT-BASED: Task already completed recently for photo {photo_id}")
                    return {
                        'photo_id': photo_id,
                        'site_id': effective_site_id,
                        'status': 'already_completed',
                        'message': 'Task completed recently',
                        'completed_at': completed_task.completed_at.isoformat(),
                        'processing_method': 'snapshot-based'
                    }
            
            # 🔧 SNAPSHOT-BASED: Crea nuovo task con dati completi dal snapshot
            task = TileProcessingTask(
                photo_id=photo_id,
                site_id=effective_site_id,  # Use normalized site_id
                file_path=photo_snapshot['file_path'],
                original_file_content=original_file_content,
                archaeological_metadata=archaeological_metadata or photo_snapshot.get('archaeological_metadata', photo_snapshot.get('metadata', {}))
            )
            
            # 🔧 SNAPSHOT-BASED: Store snapshot data in task for later use
            # This eliminates the need for database queries during processing
            task.snapshot_data = photo_snapshot
            
            # Aggiungi a coda e tracking
            await self.task_queue.put(task)
            self.processing_tasks[photo_id] = task
            self._processing_photo_ids.add(photo_id)
            
            logger.info(f"🔧 SNAPSHOT-BASED: Scheduled tile processing for photo {photo_id} from snapshot")
            
            return {
                'photo_id': photo_id,
                'site_id': effective_site_id,
                'status': 'scheduled',
                'message': 'Tile processing scheduled from snapshot in background',
                'scheduled_at': datetime.now().isoformat(),
                'processing_method': 'snapshot-based'
            }

    async def _process_queue_worker(self):
        """Background worker that processes the queue with stuck task detection (Clean Architecture)"""
        logger.info("🔄 Background queue worker started")
        
        # Create semaphore to limit concurrent processing
        processing_semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        
        while self._running:
            try:
                # Check for stuck tasks periodically
                await self._check_and_cleanup_stuck_tasks()
                
                # Get task from queue with timeout
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                # Process task with semaphore
                asyncio.create_task(
                    self._process_single_task_with_semaphore(task, processing_semaphore)
                )
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in queue worker: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on errors

    async def _check_and_cleanup_stuck_tasks(self):
        """Check for and cleanup stuck tasks that have been processing too long"""
        try:
            current_time = datetime.now()
            
            # Check if it's time to run stuck task detection
            if (current_time - self.last_stuck_task_check).total_seconds() < self.stuck_task_check_interval:
                return
            
            self.last_stuck_task_check = current_time
            logger.debug("🔍 [STUCK TASK] Running stuck task detection...")
            
            stuck_tasks = []
            
            async with self._processing_lock:
                for photo_id, task in self.processing_tasks.items():
                    # Check if task has been running too long
                    if task.status == DeepZoomStatus.PROCESSING and task.started_at:
                        processing_time = (current_time - task.started_at).total_seconds()
                        if processing_time > self.task_timeout_seconds:
                            stuck_tasks.append((photo_id, task, processing_time))
                            logger.warning(f"⚠️ [STUCK TASK] Photo {photo_id} stuck for {processing_time:.1f}s")
            
            # Cleanup stuck tasks
            for photo_id, task, processing_time in stuck_tasks:
                await self._cleanup_stuck_task(photo_id, task, processing_time)
                
            if stuck_tasks:
                logger.info(f"🧹 [STUCK TASK] Cleaned up {len(stuck_tasks)} stuck tasks")
            else:
                logger.debug("🔍 [STUCK TASK] No stuck tasks found")
                
        except Exception as e:
            logger.error(f"❌ [STUCK TASK] Error in stuck task detection: {e}")

    async def _cleanup_stuck_task(self, photo_id: str, task: TileProcessingTask, processing_time: float):
        """Clean up a stuck task by moving it to failed status and re-queuing if needed"""
        try:
            logger.warning(f"🧹 [STUCK TASK] Cleaning up stuck task for photo {photo_id} ({processing_time:.1f}s)")
            
            # Move task to failed status
            task.status = DeepZoomStatus.FAILED
            task.error_message = f"Task stuck for {processing_time:.1f}s, cleaned up automatically"
            task.completed_at = datetime.now()
            
            # Update database status (only for legacy path)
            if hasattr(task, 'snapshot_data') and task.snapshot_data:
                logger.debug(f"🔧 SNAPSHOT-BASED: Skipping database update for stuck task {photo_id}")
            else:
                await self._update_photo_database_status(photo_id, "failed")
            await self._update_processing_status(
                task, "failed", 0, error=task.error_message
            )
            
            # Move to failed tasks
            self.failed_tasks[photo_id] = task
            
            # Remove from processing tasks
            if photo_id in self.processing_tasks:
                del self.processing_tasks[photo_id]
            
            # Remove from tracking
            self._processing_photo_ids.discard(photo_id)
            
            # Clean up task lock
            if photo_id in self._task_locks:
                del self._task_locks[photo_id]
            
            # Update failure counter
            self.total_tasks_failed += 1
            
            # Try to re-queue if retries remaining
            if task.retry_count < task.max_retries:
                logger.info(f"🔄 [STUCK TASK] Re-queuing photo {photo_id} for retry")
                task.retry_count += 1
                task.status = DeepZoomStatus.RETRYING
                task.started_at = None  # Reset start time
                
                # Re-add to queue after a delay
                await asyncio.sleep(30)  # 30 second delay before retry
                await self.task_queue.put(task)
                self.processing_tasks[photo_id] = task
                self._processing_photo_ids.add(photo_id)
            else:
                logger.error(f"💀 [STUCK TASK] Photo {photo_id} exceeded max retries, permanently failed")
                # Send failure notification
                await self._send_completion_notification(task, False)
                
        except Exception as e:
            logger.error(f"❌ [STUCK TASK] Error cleaning up stuck task {photo_id}: {e}")
            # Force cleanup even if something goes wrong
            try:
                self.processing_tasks.pop(photo_id, None)
                self._processing_photo_ids.discard(photo_id)
                self._task_locks.pop(photo_id, None)
            except:
                pass

    async def _process_single_task_with_semaphore(
        self, 
        task: TileProcessingTask, 
        semaphore: asyncio.Semaphore
    ):
        """Process a single task with semaphore control"""
        async with semaphore:
            await self._process_single_task(task)

    async def _process_single_task(self, task: TileProcessingTask):
        """Process a single photo's tiles with proper locking using dependency injection"""
        
        # Lock per task
        if task.photo_id not in self._task_locks:
            self._task_locks[task.photo_id] = asyncio.Lock()
        
        async with self._task_locks[task.photo_id]:
            # Double check
            if task.photo_id not in self.processing_tasks:
                return
            
            task.status = DeepZoomStatus.PROCESSING
            task.started_at = datetime.now()
            
            try:
                logger.info(f"🔄 Processing tiles for photo {task.photo_id} (attempt {task.retry_count + 1})")
                
                await self._update_photo_database_status(task.photo_id, "processing")
                await self._update_processing_status(task, "processing", 0)
                
                # 1. Generate tiles using ImageProcessor
                tiles_data, original_width, original_height = await self._generate_tiles(
                    task.original_file_content, task.photo_id, task.site_id
                )
                
                total_tiles = self._count_total_tiles(tiles_data)
                task.status = DeepZoomStatus.UPLOADING
                await self._update_processing_status(task, "uploading", 10, total_tiles, len(tiles_data))
                
                # 2. Upload tiles using StorageInterface
                completed_tiles = await self._upload_tiles_concurrent(
                    task, tiles_data, total_tiles
                )
                
                # 3. Create metadata
                task.status = DeepZoomStatus.COMPLETED
                metadata_url = await self._create_and_upload_metadata(
                    task, tiles_data, original_width, original_height
                )
                
                # 4. Finalize
                task.completed_at = datetime.now()
                task.status = DeepZoomStatus.COMPLETED
                
                await self._update_photo_database_status(
                    task.photo_id,
                    "completed",
                    tile_count=completed_tiles,
                    levels=len(tiles_data),
                    max_zoom_level=len(tiles_data)
                )
                
                # Cleanup
                if task.photo_id in self.processing_tasks:
                    del self.processing_tasks[task.photo_id]
                self.completed_tasks[task.photo_id] = task
                self._processing_photo_ids.discard(task.photo_id)
                self._cleanup_batch_context(task.site_id, task.photo_id)
                self.total_tasks_processed += 1
                
                logger.success(f"✅ Deep Zoom processing completed for {task.photo_id}")
                await self._send_completion_notification(task, True, completed_tiles)

            except Exception as e:
                logger.error(f"❌ Processing failed for {task.photo_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                task.error_message = str(e)
                # Retry logic
                if task.retry_count < task.max_retries:
                     task.retry_count += 1
                     task.status = DeepZoomStatus.RETRYING
                     task.started_at = None
                     # Re-queue
                     await asyncio.sleep(10)
                     await self.task_queue.put(task)
                     self.processing_tasks[task.photo_id] = task
                else:
                     task.status = DeepZoomStatus.FAILED
                     await self._update_photo_database_status(task.photo_id, "failed")
                     self.failed_tasks[task.photo_id] = task
                     if task.photo_id in self.processing_tasks:
                        del self.processing_tasks[task.photo_id]
                     self._processing_photo_ids.discard(task.photo_id)
                     self._cleanup_batch_context(task.site_id, task.photo_id)
                     self.total_tasks_failed += 1
                     
                     await self._send_completion_notification(task, False)



    async def _generate_tiles(
        self,
        content: bytes,
        photo_id: str,
        site_id: str
    ) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """Generate tiles using injected ImageProcessor"""
        
        return await asyncio.to_thread(self._generate_tiles_sync, content, photo_id, site_id)
        
    def _generate_tiles_sync(
        self,
        content: bytes,
        photo_id: str,
        site_id: str
    ) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        
        if not self.image_processor or not self.image_processor.validate_image(content):
            raise ValueError("Invalid image content or missing processor")
            
        image = self.image_processor.open_image(content)
        width, height = self.image_processor.get_dimensions(image)
        
        max_dim = max(width, height)
        levels = math.ceil(math.log2(max_dim)) + 1
        
        tiles_data = {}
        
        for level in range(levels):
            level_tiles = {}
            scale = 2 ** (levels - 1 - level)
            level_w = max(1, width // scale)
            level_h = max(1, height // scale)
            
            for y in range(0, level_h, self.tile_size):
                for x in range(0, level_w, self.tile_size):
                    col = x // self.tile_size
                    row = y // self.tile_size
                    
                    # Using processor level semantics (0=full res in logic, but wait...)
                    # My processor resize_for_tile uses 'level' as reduction power.
                    # Service uses 'level' as 0=smallest.
                    # Reduction power = levels - 1 - level.
                    reduction_level = levels - 1 - level
                    
                    tile_bytes = self.image_processor.resize_for_tile(
                        image, self.tile_size, self.overlap,
                        reduction_level,
                        col, row
                    )
                    
                    if tile_bytes:
                        level_tiles[f"{col}_{row}"] = tile_bytes
            
            tiles_data[level] = level_tiles
            
        return tiles_data, width, height

    async def _upload_tiles_concurrent(
        self,
        task: TileProcessingTask,
        tiles_data: Dict[int, Dict[str, bytes]],
        total_tiles: int
    ) -> int:
        """Upload tiles using StorageInterface with concurrency control"""
        
        logger.info(f"📤 Starting concurrent task upload for {total_tiles} tiles")
        
        upload_semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
        async def upload_worker(level, tile_coords, tile_data):
            async with upload_semaphore:
                try:
                    col = tile_coords.split('_')[0]
                    row = tile_coords.split('_')[1]
                    
                    metadata = {
                        "level": str(level),
                        "col": col,
                        "row": row,
                        "format": self.format,
                        "tile_size": str(self.tile_size)
                    }
                    
                    await self.storage.upload_deep_zoom_tile(
                        site_id=task.site_id,
                        photo_id=task.photo_id,
                        level=level,
                        x=int(col),
                        y=int(row),
                        content=tile_data,
                        content_type=f"image/{self.format}",
                        metadata=metadata
                    )
                    return True
                except Exception as e:
                    logger.error(f"Upload failed for tile {level}/{tile_coords}: {e}")
                    return False

        # Create tasks
        tasks = []
        for level, tiles_level in tiles_data.items():
            for tile_coords, tile_data in tiles_level.items():
                tasks.append(upload_worker(level, tile_coords, tile_data))
                
        results = await asyncio.gather(*tasks)
        completed_tiles = sum(1 for r in results if r)
        
        if completed_tiles < len(tasks):
            logger.warning(f"⚠️ Only {completed_tiles}/{len(tasks)} tiles uploaded successfully")
        
        return completed_tiles

    # _upload_single_tile logic has been consolidated into _upload_tiles_concurrent


    async def _create_and_upload_metadata(
        self,
        task: TileProcessingTask,
        tiles_data: Dict[int, Dict[str, bytes]],
        width: int,
        height: int
    ) -> str:
        """Create and upload metadata.json for tiles with comprehensive debugging"""
        import time
        metadata_start_time = time.time()
        
        with logger.contextualize(
            operation="create_and_upload_metadata",
            photo_id=task.photo_id,
            site_id=task.site_id,
            width=width,
            height=height,
            levels=len(tiles_data),
            service="deep_zoom_background_service"
        ):
            try:
                logger.info(
                    "🔧 METADATA CREATION STARTED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "image_width": width,
                        "image_height": height,
                        "levels_count": len(tiles_data),
                        "tile_size": self.tile_size,
                        "tile_format": self.format,
                        "metadata_creation_start_time": datetime.now().isoformat()
                    }
                )
                
                # Calculate comprehensive statistics
                total_tiles = self._count_total_tiles(tiles_data)
                level_statistics = {}
                tiles_by_level = {}
                
                level_analysis_start_time = time.time()
                for level, tiles_level in tiles_data.items():
                    tile_count = len(tiles_level)
                    tiles_list = list(tiles_level.keys())
                    
                    level_statistics[level] = {
                        "tile_count": tile_count,
                        "tiles": tiles_list
                    }
                    
                    # Calculate tile coordinates range for debugging
                    if tiles_list:
                        x_coords = [int(tile.split('_')[0]) for tile in tiles_list]
                        y_coords = [int(tile.split('_')[1]) for tile in tiles_list]
                        tiles_by_level[level] = {
                            "tile_count": tile_count,
                            "x_range": [min(x_coords), max(x_coords)],
                            "y_range": [min(y_coords), max(y_coords)],
                            "tiles_sample": tiles_list[:5]  # First 5 tiles as sample
                        }
                    else:
                        tiles_by_level[level] = {
                            "tile_count": 0,
                            "x_range": [0, 0],
                            "y_range": [0, 0],
                            "tiles_sample": []
                        }
                
                level_analysis_time = time.time() - level_analysis_start_time
                
                logger.debug(
                    "📊 TILE LEVEL ANALYSIS COMPLETED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "total_tiles": total_tiles,
                        "level_analysis_time_ms": round(level_analysis_time * 1000, 2),
                        "tiles_by_level": tiles_by_level,
                        "average_tiles_per_level": round(total_tiles / len(tiles_data), 2) if tiles_data else 0
                    }
                )
                
                # Create comprehensive metadata
                metadata_creation_start_time = time.time()
                metadata = {
                    "photo_id": task.photo_id,
                    "site_id": task.site_id,
                    "width": width,
                    "height": height,
                    "levels": len(tiles_data),
                    "tile_size": self.tile_size,
                    "overlap": self.overlap,
                    "format": self.format,
                    "tile_format": self.format,
                    "total_tiles": total_tiles,
                    "created": datetime.now().isoformat(),
                    "archaeological_metadata": task.archaeological_metadata or {},
                    "processing_info": {
                        "service_version": "deep_zoom_background_service_v2",
                        "tile_size_pixels": self.tile_size,
                        "overlap_pixels": self.overlap,
                        "max_level": len(tiles_data) - 1 if tiles_data else 0,
                        "min_level": 0
                    },
                    "level_info": level_statistics,
                    "performance_metrics": {
                        "total_tiles_generated": total_tiles,
                        "levels_processed": len(tiles_data),
                        "average_tiles_per_level": round(total_tiles / len(tiles_data), 2) if tiles_data else 0
                    }
                }
                
                metadata_creation_time = time.time() - metadata_creation_start_time
                
                logger.debug(
                    "📋 METADATA STRUCTURE CREATED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "metadata_creation_time_ms": round(metadata_creation_time * 1000, 2),
                        "metadata_keys": list(metadata.keys()),
                        "metadata_size_estimate": len(str(metadata)),
                        "archaeological_metadata_keys": list((task.archaeological_metadata or {}).keys()),
                        "level_info_keys": list(level_statistics.keys())
                    }
                )
                
                # Serialize metadata
                serialization_start_time = time.time()
                metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
                metadata_bytes = metadata_json.encode('utf-8')
                serialization_time = time.time() - serialization_start_time
                
                logger.debug(
                    "📄 METADATA SERIALIZATION COMPLETED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "serialization_time_ms": round(serialization_time * 1000, 2),
                        "metadata_json_size_bytes": len(metadata_bytes),
                        "metadata_json_size_kb": round(len(metadata_bytes) / 1024, 2),
                        "metadata_object_count": len(metadata),
                        "level_info_count": len(level_statistics)
                    }
                )
                
                # Prepare object name and upload details
                metadata_object_name = f"{task.site_id}/tiles/{task.photo_id}/metadata.json"
                
                logger.info(
                    "📤 METADATA UPLOAD INITIATED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "metadata_object_name": metadata_object_name,
                        "metadata_size_bytes": len(metadata_bytes),
                        "content_type": "application/json",
                        "upload_start_time": datetime.now().isoformat()
                    }
                )
                
                # Prepare comprehensive metadata for MinIO
                minio_metadata = {
                    'x-amz-meta-photo-id': str(task.photo_id),
                    'x-amz-meta-site-id': str(task.site_id),
                    'x-amz-meta-document-type': 'deep_zoom_metadata',
                    'x-amz-meta-created': datetime.now().isoformat(),
                    'x-amz-meta-width': str(width),
                    'x-amz-meta-height': str(height),
                    'x-amz-meta-levels': str(len(tiles_data)),
                    'x-amz-meta-tile-count': str(total_tiles),
                    'x-amz-meta-tile-format': str(self.format),
                    'x-amz-meta-tile-size': str(self.tile_size)
                }
                
                # Add archaeological metadata if available
                if task.archaeological_metadata:
                    for key, value in task.archaeological_metadata.items():
                        if value is not None:
                            minio_metadata[f'x-amz-meta-arch-{key.lower().replace("_", "-")}'] = str(value)
                
                # Upload to MinIO with timing
                upload_start_time = time.time()
                from app.services.archaeological_minio_service import archaeological_minio_service
                
                logger.info(
                    "🗄️ MINIO METADATA UPLOAD STARTED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "bucket_name": archaeological_minio_service.buckets['tiles'],
                        "object_name": metadata_object_name,
                        "content_type": "application/json",
                        "metadata_size_bytes": len(metadata_bytes),
                        "minio_metadata_keys": list(minio_metadata.keys()),
                        "upload_start_time": datetime.now().isoformat()
                    }
                )
                
                result = await asyncio.to_thread(
                    archaeological_minio_service._client.put_object,
                    bucket_name=archaeological_minio_service.buckets['tiles'],
                    object_name=metadata_object_name,
                    data=io.BytesIO(metadata_bytes),
                    length=len(metadata_bytes),
                    content_type='application/json',
                    metadata=minio_metadata
                )
                
                upload_time = time.time() - upload_start_time
                total_metadata_time = time.time() - metadata_start_time
                
                # Calculate upload performance metrics
                upload_speed_kb_per_sec = round((len(metadata_bytes) / 1024) / upload_time, 2) if upload_time > 0 else 0
                
                logger.success(
                    "✅ METADATA UPLOAD COMPLETED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "metadata_object_name": metadata_object_name,
                        "minio_result": str(result),
                        "performance_metrics": {
                            "total_metadata_time_ms": round(total_metadata_time * 1000, 2),
                            "level_analysis_time_ms": round(level_analysis_time * 1000, 2),
                            "metadata_creation_time_ms": round(metadata_creation_time * 1000, 2),
                            "serialization_time_ms": round(serialization_time * 1000, 2),
                            "upload_time_ms": round(upload_time * 1000, 2),
                            "upload_speed_kb_per_sec": upload_speed_kb_per_sec
                        },
                        "metadata_details": {
                            "size_bytes": len(metadata_bytes),
                            "size_kb": round(len(metadata_bytes) / 1024, 2),
                            "total_tiles": total_tiles,
                            "levels": len(tiles_data),
                            "tile_format": self.format,
                            "image_dimensions": f"{width}x{height}"
                        },
                        "minio_details": {
                            "bucket": archaeological_minio_service.buckets['tiles'],
                            "object_url": f"minio://{archaeological_minio_service.buckets['tiles']}/{metadata_object_name}",
                            "metadata_count": len(minio_metadata)
                        }
                    }
                )
                
                final_url = f"minio://{archaeological_minio_service.buckets['tiles']}/{metadata_object_name}"
                
                logger.info(
                    "🎉 METADATA PROCESSING COMPLETED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "final_metadata_url": final_url,
                        "total_processing_time_ms": round(total_metadata_time * 1000, 2),
                        "processing_success": True
                    }
                )
                
                return final_url
            
            except Exception as e:
                total_metadata_time = time.time() - metadata_start_time
                
                logger.error(
                    "❌ METADATA CREATION/UPLOAD FAILED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_metadata_time_ms": round(total_metadata_time * 1000, 2),
                        "failure_point": "metadata_processing",
                        "tiles_data_levels": len(tiles_data),
                        "image_dimensions": f"{width}x{height}"
                    }
                )
                
                import traceback
                logger.error(
                    "📋 METADATA ERROR TRACEBACK",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
                raise Exception(f"Metadata creation/upload failed: {str(e)}")

    def _count_total_tiles(self, tiles_data: Dict[int, Dict[str, bytes]]) -> int:
        """Count total tiles in all levels"""
        return sum(len(tiles_level) for tiles_level in tiles_data.values())

    async def _update_processing_status(
        self,
        task: TileProcessingTask,
        status: str,
        progress: int,
        total_tiles: int = 0,
        levels: int = 0,
        completed_tiles: int = 0,
        error: str = None
    ):
        """Update processing status"""
        try:
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            status_data = {
                "photo_id": task.photo_id,
                "site_id": task.site_id,
                "status": status,
                "progress": progress,
                "total_tiles": total_tiles,
                "completed_tiles": completed_tiles,
                "levels": levels,
                "tile_size": self.tile_size,
                "updated": datetime.now().isoformat(),
                "retry_count": task.retry_count,
                "max_retries": task.max_retries
            }
            
            if error:
                status_data["error"] = error
                
            status_json = json.dumps(status_data, indent=2, ensure_ascii=False)
            status_bytes = status_json.encode('utf-8')
            
            status_object_name = f"{task.site_id}/tiles/{task.photo_id}/processing_status.json"
            
            await asyncio.to_thread(
                archaeological_minio_service._client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=status_object_name,
                data=io.BytesIO(status_bytes),
                length=len(status_bytes),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")

    async def _update_processing_status_full(
        self,
        task: TileProcessingTask,
        full_status: Dict[str, Any]
    ):
        """Update full processing status"""
        try:
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            status_json = json.dumps(full_status, indent=2, ensure_ascii=False)
            status_bytes = status_json.encode('utf-8')
            
            status_object_name = f"{task.site_id}/tiles/{task.photo_id}/processing_status.json"
            
            await asyncio.to_thread(
                archaeological_minio_service._client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=status_object_name,
                data=io.BytesIO(status_bytes),
                length=len(status_bytes),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error(f"Failed to update full processing status: {e}")

    async def _update_photo_database_status(
        self,
        photo_id: str,
        status: str,
        tile_count: int = None,
        levels: int = None,
        max_zoom_level: int = None,
        use_snapshot: bool = False
    ):
        """Update photo status in database using PhotoRepository"""
        if not self.session_factory:
            logger.warning("No session factory available for updates")
            return

        async with self.session_factory() as session:
            try:
                repo = PhotoRepository(session)
                
                # Map deepzoom status to Photo update
                await repo.update_deep_zoom_status(
                    photo_id=UUID(photo_id),
                    status=status,
                    has_deep_zoom=(status == "completed"),
                    tile_count=tile_count,
                    max_zoom_level=max_zoom_level or levels
                )
                
                await session.commit()
                logger.info(f"✅ Database updated for photo {photo_id}: status={status}")
                
            except Exception as e:
                logger.error(f"Failed to update photo status for {photo_id}: {e}")
                await session.rollback()

    async def _send_processing_notification(
        self,
        task: TileProcessingTask,
        stage: str,
        progress: int = 0,
        tile_count: int = 0,
        levels: int = 0
    ):
        """Send intermediate progress notification during tile generation"""
        try:
            from app.routes.api.notifications_ws import notification_manager
            
            # Get batch context
            current_photo = self._get_current_photo_position(task.photo_id)
            total_photos = self._get_total_batch_size(task.site_id)
            
            await notification_manager.broadcast_tiles_progress(
                site_id=task.site_id,
                photo_id=task.photo_id,
                status=stage,
                progress=progress,
                tile_count=tile_count,
                levels=levels,
                current_photo=current_photo,
                total_photos=total_photos,
                error=None
            )
                
        except ImportError:
            logger.warning("Notification manager not available")
        except Exception as e:
            logger.error(f"Failed to send processing notification: {e}")

    async def _send_completion_notification(
        self,
        task: TileProcessingTask,
        success: bool,
        tile_count: int = 0,
        levels: int = 0,
        photo_filename: str = None
    ):
        """Send WebSocket notification for task completion"""
        try:
            from app.routes.api.notifications_ws import notification_manager
            
            # Get batch context
            current_photo = self._get_current_photo_position(task.photo_id)
            total_photos = self._get_total_batch_size(task.site_id)
            
            if success:
                await notification_manager.broadcast_tiles_progress(
                    site_id=task.site_id,
                    photo_id=task.photo_id,
                    status='completed',
                    progress=100,
                    photo_filename=photo_filename,
                    tile_count=tile_count,
                    levels=levels,
                    current_photo=current_photo,
                    total_photos=total_photos,
                    error=None
                )
            else:
                await notification_manager.broadcast_tiles_progress(
                    site_id=task.site_id,
                    photo_id=task.photo_id,
                    status='failed',
                    progress=0,
                    current_photo=current_photo,
                    total_photos=total_photos,
                    error=task.error_message
                )
                
        except ImportError:
            logger.warning("Notification manager not available")
        except Exception as e:
            logger.error(f"Failed to send completion notification: {e}")

    def _get_current_photo_position(self, photo_id: str) -> Optional[int]:
        """Get the position of the current photo in the processing queue"""
        return self._photo_order.get(photo_id, 0)

    def _get_total_batch_size(self, site_id: str) -> int:
        """Get the total number of photos being processed for a site"""
        if site_id in self._batch_context:
            return len(self._batch_context[site_id]["photos"])
        return 1  # Default to 1 if no batch context

    def _cleanup_batch_context(self, site_id: str, photo_id: str):
        """Clean up batch context when a photo is completed"""
        if site_id in self._batch_context:
            batch = self._batch_context[site_id]
            # Handle both 'photo_id' and 'id' keys for compatibility
            batch['photos'] = [p for p in batch['photos'] if p.get('photo_id', p.get('id')) != photo_id]
            
            # Clean up photo order tracking
            if photo_id in self._photo_order:
                del self._photo_order[photo_id]
            
            # Remove empty batch context
            if not batch['photos']:
                del self._batch_context[site_id]

    async def get_task_status(self, photo_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a processing task"""
        # Check in all task collections
        for task_dict in [self.processing_tasks, self.completed_tasks, self.failed_tasks]:
            if photo_id in task_dict:
                task = task_dict[photo_id]
                return {
                    "photo_id": task.photo_id,
                    "site_id": task.site_id,
                    "status": task.status.value,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                    "error_message": task.error_message,
                    "created_at": task.created_at.isoformat(),
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None
                }
        
        return None

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get overall queue status"""
        return {
            "queue_size": self.task_queue.qsize(),
            "processing_tasks": len(self.processing_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "is_running": self._running,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "max_concurrent_uploads": self.max_concurrent_uploads,
            "service_start_time": self.service_start_time.isoformat(),
            "total_tasks_processed": self.total_tasks_processed,
            "total_tasks_failed": self.total_tasks_failed,
            "last_stuck_task_check": self.last_stuck_task_check.isoformat(),
            "task_timeout_seconds": self.task_timeout_seconds,
            "processing_photo_ids": list(self._processing_photo_ids)
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status of the background service"""
        try:
            current_time = datetime.now()
            uptime_seconds = (current_time - self.service_start_time).total_seconds()
            
            # Check worker health
            worker_health = {
                "is_running": self._running,
                "worker_task_exists": self._worker_task is not None,
                "worker_task_done": self._worker_task.done() if self._worker_task else None,
                "worker_task_cancelled": self._worker_task.cancelled() if self._worker_task else None,
                "worker_task_exception": str(self._worker_task.exception()) if self._worker_task and self._worker_task.done() and self._worker_task.exception() else None
            }
            
            # Check for stuck tasks
            stuck_tasks = []
            for photo_id, task in self.processing_tasks.items():
                if task.status == DeepZoomStatus.PROCESSING and task.started_at:
                    processing_time = (current_time - task.started_at).total_seconds()
                    if processing_time > self.task_timeout_seconds:
                        stuck_tasks.append({
                            "photo_id": photo_id,
                            "processing_time_seconds": processing_time,
                            "started_at": task.started_at.isoformat()
                        })
            
            # Calculate health metrics
            health_metrics = {
                "service_uptime_seconds": uptime_seconds,
                "success_rate": (
                    self.total_tasks_processed / (self.total_tasks_processed + self.total_tasks_failed)
                    if (self.total_tasks_processed + self.total_tasks_failed) > 0 else 1.0
                ),
                "queue_health": {
                    "is_empty": self.task_queue.qsize() == 0,
                    "size": self.task_queue.qsize(),
                    "max_concurrent_reached": len(self.processing_tasks) >= self.max_concurrent_tasks
                },
                "task_health": {
                    "processing_count": len(self.processing_tasks),
                    "stuck_count": len(stuck_tasks),
                    "failed_count": len(self.failed_tasks),
                    "completed_count": len(self.completed_tasks)
                }
            }
            
            # Determine overall health status
            overall_status = "healthy"
            health_issues = []
            
            if not self._running:
                overall_status = "stopped"
                health_issues.append("Service is not running")
            elif self._worker_task is None:
                overall_status = "unhealthy"
                health_issues.append("Worker task is None")
            elif self._worker_task.done():
                overall_status = "unhealthy"
                if self._worker_task.cancelled():
                    health_issues.append("Worker task was cancelled")
                elif self._worker_task.exception():
                    health_issues.append(f"Worker task failed: {self._worker_task.exception()}")
                else:
                    health_issues.append("Worker task completed unexpectedly")
            elif len(stuck_tasks) > 0:
                overall_status = "degraded"
                health_issues.append(f"{len(stuck_tasks)} stuck tasks detected")
            elif self.task_queue.qsize() > 100:
                overall_status = "degraded"
                health_issues.append("Queue size is very large")
            elif health_metrics["success_rate"] < 0.8 and (self.total_tasks_processed + self.total_tasks_failed) > 10:
                overall_status = "degraded"
                health_issues.append(f"Low success rate: {health_metrics['success_rate']:.2%}")
            
            return {
                "status": overall_status,
                "timestamp": current_time.isoformat(),
                "uptime_seconds": uptime_seconds,
                "worker_health": worker_health,
                "health_metrics": health_metrics,
                "stuck_tasks": stuck_tasks,
                "health_issues": health_issues,
                "queue_status": await self.get_queue_status()
            }
            
        except Exception as e:
            logger.error(f"❌ [HEALTH] Error getting health status: {e}")
            return {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "health_issues": [f"Health check failed: {str(e)}"]
            }

    async def reset_service(self) -> Dict[str, Any]:
        """Reset the background service - emergency recovery"""
        try:
            logger.warning("🔄 [RESET] Resetting background service...")
            
            # Stop the service
            await self.stop_background_processor()
            
            # Clear queues and task tracking
            async with self._processing_lock:
                # Clear the queue
                while not self.task_queue.empty():
                    try:
                        self.task_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                
                # Move processing tasks to failed
                failed_count = len(self.processing_tasks)
                for photo_id, task in self.processing_tasks.items():
                    task.status = DeepZoomStatus.FAILED
                    task.error_message = "Service reset - task marked as failed"
                    task.completed_at = datetime.now()
                    self.failed_tasks[photo_id] = task
                
                # Clear processing tracking
                self.processing_tasks.clear()
                self._processing_photo_ids.clear()
                self._task_locks.clear()
            
            # Restart the service
            await self.start_background_processor()
            
            logger.info(f"🔄 [RESET] Service reset completed - {failed_count} tasks moved to failed")
            
            return {
                "status": "reset_completed",
                "timestamp": datetime.now().isoformat(),
                "failed_tasks_moved": failed_count,
                "service_running": self._running
            }
            
        except Exception as e:
            logger.error(f"❌ [RESET] Service reset failed: {e}")
            return {
                "status": "reset_failed",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }


# Global instance
deep_zoom_background_service = DeepZoomBackgroundService()