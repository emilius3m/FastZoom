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
from sqlalchemy import text
from uuid import UUID

# UUID normalization function (local copy to avoid circular imports)
def normalize_site_id(site_id: str) -> Optional[str]:
    """
    Normalizza l'ID del sito per supportare diversi formati.
    
    Supporta:
    - UUID standard con trattini: eb8d88e1-74e3-46d3-8e86-81f926c01cab
    - Hash esadecimali senza trattini: eeedd3ceda34bf3b47d749a971b22ba
    
    Returns:
        str: L'ID normalizzato o None se non valido
    """
    if not site_id:
        return None
    
    # Rimuovi spazi bianchi
    site_id = site_id.strip()
    
    # Se è un UUID standard con trattini, valida e restituiscilo
    if '-' in site_id:
        try:
            # Crea un oggetto UUID per validare il formato e normalizzare a lowercase
            uuid_obj = uuid.UUID(site_id)
            # Restituisci la stringa normalizzata in lowercase
            return str(uuid_obj)
        except (ValueError, AttributeError):
            return None
    
    # Se è un hash esadecimale senza trattini
    if len(site_id) == 32:
        try:
            # Verifica che sia esadecimale
            int(site_id, 16)
            # Converti in formato UUID standard (inserisci trattini)
            uuid_formatted = f"{site_id[0:8]}-{site_id[8:12]}-{site_id[12:16]}-{site_id[16:20]}-{site_id[20:32]}"
            # Valida il formato UUID risultante
            uuid.UUID(uuid_formatted)
            return uuid_formatted
        except (ValueError, AttributeError):
            return None
    
    # Altri formati non supportati
    return None

from PIL import Image
import math

from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.models import Photo
from sqlalchemy import select


class ProcessingStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


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
    status: ProcessingStatus = ProcessingStatus.PENDING
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
    """Background processing service for deep zoom tiles with retry mechanism"""
    
    def __init__(self):
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
        logger.info("🚀 Deep zoom background processor started")

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
                if existing_task.status in [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING, ProcessingStatus.RETRYING]:
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
                if photo_id not in [p['photo_id'] for p in batch_context['photos']]:
                    self._photo_order[photo_id] = len(batch_context['photos'])
                    batch_context['photos'].append(photo_info)
        
        scheduled_count = 0
        for photo_info in photos_list:
            try:
                # Load file content from MinIO
                from app.services.archaeological_minio_service import archaeological_minio_service
                original_file_content = await archaeological_minio_service.get_file(photo_info['file_path'])
                
                await self.schedule_tile_processing(
                    photo_id=photo_info['photo_id'],
                    site_id=effective_site_id,  # Use normalized site_id
                    file_path=photo_info['file_path'],
                    original_file_content=original_file_content,
                    archaeological_metadata=photo_info.get('archaeological_metadata', {})
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
                if photo_id not in [p['id'] for p in batch_context['photos']]:
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
                original_file_content = await archaeological_minio_service.get_file(photo_snapshot['file_path'])
                
                # Extract archaeological metadata from snapshot
                archaeological_metadata = photo_snapshot.get('archaeological_metadata', {})
                
                # Add additional metadata from snapshot if available
                if 'metadata' in photo_snapshot:
                    archaeological_metadata.update(photo_snapshot['metadata'])
                
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
                if existing_task.status in [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING, ProcessingStatus.RETRYING]:
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
                archaeological_metadata=archaeological_metadata or photo_snapshot.get('archaeological_metadata', {})
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
        """Background worker that processes the queue with stuck task detection"""
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
                    if task.status == ProcessingStatus.PROCESSING and task.started_at:
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
            task.status = ProcessingStatus.FAILED
            task.error_message = f"Task stuck for {processing_time:.1f}s, cleaned up automatically"
            task.completed_at = datetime.now()
            
            # Update database status
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
                task.status = ProcessingStatus.RETRYING
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
        """Process a single photo's tiles with proper locking"""
        
        # CRITICO: Ottieni lock per questo photo_id per evitare duplicati
        if task.photo_id not in self._task_locks:
            self._task_locks[task.photo_id] = asyncio.Lock()
        
        async with self._task_locks[task.photo_id]:
            # Verifica doppio check con lock acquisito
            if task.photo_id not in self.processing_tasks:
                logger.warning(f"Task {task.photo_id} no longer in processing tasks, skipping")
                return
            
            task.status = ProcessingStatus.PROCESSING
            task.started_at = datetime.now()
            
            try:
                logger.info(f"🔄 Processing tiles for photo {task.photo_id} (attempt {task.retry_count + 1})")
                
                # Update status in database
                await self._update_photo_database_status(task.photo_id, "processing")
                await self._update_processing_status(task, "processing", 0)
                
                # Send intermediate notification for processing start
                await self._send_processing_notification(task, "processing", 5)
                
                # Generate tiles with memory-efficient processing
                tiles_data, original_width, original_height = await self._generate_tiles_memory_efficient(
                    task.original_file_content, task.photo_id, task.site_id
                )
                
                total_tiles = self._count_total_tiles(tiles_data)
                task.status = ProcessingStatus.UPLOADING
                await self._update_processing_status(task, "uploading", 10, total_tiles, len(tiles_data))
                
                # Send intermediate notification for uploading stage
                await self._send_processing_notification(task, "uploading", 10, total_tiles, len(tiles_data))
                
                # Upload tiles with concurrent control
                completed_tiles = await self._upload_tiles_concurrent(
                    task, tiles_data, total_tiles
                )
                
                # Create metadata
                task.status = ProcessingStatus.COMPLETED
                await self._update_processing_status(task, "finalizing", 90)
                
                # Send intermediate notification for finalizing stage
                await self._send_processing_notification(task, "finalizing", 90, completed_tiles, len(tiles_data))
                
                metadata_url = await self._create_and_upload_metadata(
                    task, tiles_data, original_width, original_height
                )
                
                # Mark as completed
                task.completed_at = datetime.now()
                task.status = ProcessingStatus.COMPLETED
                
                # Update database with completion
                await self._update_photo_database_status(
                    task.photo_id,
                    "completed",
                    tile_count=completed_tiles,
                    levels=len(tiles_data)
                )
                
                # Update final status
                final_status = {
                    "photo_id": task.photo_id,
                    "site_id": task.site_id,
                    "status": "completed",
                    "progress": 100,
                    "total_tiles": total_tiles,
                    "completed_tiles": completed_tiles,
                    "levels": len(tiles_data),
                    "tile_size": self.tile_size,
                    "tile_format": self.format,
                    "width": original_width,
                    "height": original_height,
                    "metadata_url": metadata_url,
                    "started": task.started_at.isoformat(),
                    "completed": task.completed_at.isoformat(),
                    "archaeological_metadata": task.archaeological_metadata or {}
                }
                
                await self._update_processing_status_full(task, final_status)
                
                # Move to completed tasks
                self.completed_tasks[task.photo_id] = task
                if task.photo_id in self.processing_tasks:
                    del self.processing_tasks[task.photo_id]
                
                # Rimuovi da tracking con lock
                async with self._processing_lock:
                    self._processing_photo_ids.discard(task.photo_id)
                
                # Clean up batch context
                self._cleanup_batch_context(task.site_id, task.photo_id)
                
                # Update success counter
                self.total_tasks_processed += 1
                
                logger.info(f"✅ Completed tile processing for photo {task.photo_id}: {completed_tiles} tiles")
                
                # Get photo filename for notification
                photo_filename = None
                try:
                    from app.services.archaeological_minio_service import archaeological_minio_service
                    if hasattr(task, 'file_path') and task.file_path:
                        # Extract filename from path
                        photo_filename = task.file_path.split('/')[-1]
                except Exception:
                    pass
                
                # Send WebSocket notification with actual data
                await self._send_completion_notification(
                    task,
                    True,
                    tile_count=completed_tiles,
                    levels=len(tiles_data),
                    photo_filename=photo_filename
                )
                
            except Exception as e:
                logger.error(f"❌ Failed to process tiles for photo {task.photo_id}: {e}")
                task.error_message = str(e)
                
                # Check if we should retry
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = ProcessingStatus.RETRYING
                    
                    # Exponential backoff
                    delay = min(300, 30 * (2 ** task.retry_count))  # Max 5 minutes
                    logger.info(f"🔄 Retrying photo {task.photo_id} in {delay}s (attempt {task.retry_count})")
                    
                    await asyncio.sleep(delay)
                    
                    # Re-queue for retry
                    await self.task_queue.put(task)
                    
                    # Update status
                    await self._update_processing_status(
                        task, "retrying", 0, error=f"Retry {task.retry_count}/{task.max_retries}: {str(e)}"
                    )
                    
                else:
                    # Max retries exceeded, mark as failed
                    task.status = ProcessingStatus.FAILED
                    task.completed_at = datetime.now()
                    
                    # Update database with failed status
                    await self._update_photo_database_status(task.photo_id, "failed")
                    await self._update_processing_status(
                        task, "failed", 0, error=f"Failed after {task.max_retries} retries: {str(e)}"
                    )
                    
                    # Move to failed tasks
                    self.failed_tasks[task.photo_id] = task
                    if task.photo_id in self.processing_tasks:
                        del self.processing_tasks[task.photo_id]
                    
                    # Rimuovi da tracking con lock
                    async with self._processing_lock:
                        self._processing_photo_ids.discard(task.photo_id)
                    
                    # Clean up batch context
                    self._cleanup_batch_context(task.site_id, task.photo_id)
                    
                    logger.error(f"💀 Permanently failed processing for photo {task.photo_id}")
                    
                    # Send WebSocket notification
                    await self._send_completion_notification(task, False)

    async def _generate_tiles_memory_efficient(
        self, 
        content: bytes, 
        photo_id: str, 
        site_id: str
    ) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """Generate tiles with memory-efficient processing"""
        
        # Use asyncio.to_thread to move CPU-intensive work off event loop
        return await asyncio.to_thread(
            self._generate_tiles_sync, content, photo_id, site_id
        )

    def _generate_tiles_sync(
        self, 
        content: bytes, 
        photo_id: str, 
        site_id: str
    ) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """Synchronous tile generation (runs in thread pool)"""
        
        try:
            # Open image from bytes
            image = Image.open(io.BytesIO(content))
            
            # Determine format based on image
            original_format = image.format.lower() if image.format else 'jpg'
            original_has_transparency = image.mode in ('RGBA', 'LA') or 'transparency' in image.info
            
            if original_format == 'png' or original_has_transparency:
                self.format = 'png'
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
            else:
                self.format = 'jpg'
                if image.mode == 'RGBA':
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')

            original_width = image.width
            original_height = image.height

            # Calculate levels
            max_dimension = max(image.size)
            levels = math.ceil(math.log2(max_dimension)) + 1

            tiles_data = {}

            # Generate tiles for each level
            for level in range(levels):
                level_tiles = {}

                # Calculate dimensions for this level
                scale = 2 ** (levels - 1 - level)
                level_width = max(1, image.width // scale)
                level_height = max(1, image.height // scale)

                # Create resized image for this level
                level_image = image.resize((level_width, level_height), Image.Resampling.LANCZOS)

                # Generate tiles for this level
                for y in range(0, level_height, self.tile_size):
                    for x in range(0, level_width, self.tile_size):
                        # Extract tile
                        tile_box = (x, y, min(x + self.tile_size, level_width), min(y + self.tile_size, level_height))
                        tile = level_image.crop(tile_box)

                        # Pad tile if needed
                        if tile.size[0] < self.tile_size or tile.size[1] < self.tile_size:
                            if original_has_transparency:
                                padded_tile = Image.new('RGBA', (self.tile_size, self.tile_size), (255, 255, 255, 0))
                                padded_tile.paste(tile, (0, 0), tile if tile.mode == 'RGBA' else None)
                            else:
                                padded_tile = Image.new('RGB', (self.tile_size, self.tile_size), (255, 255, 255))
                                padded_tile.paste(tile, (0, 0))
                            tile = padded_tile

                        # Convert to bytes
                        tile_buffer = io.BytesIO()
                        if self.format == 'png':
                            tile.save(tile_buffer, format='PNG', optimize=True)
                        else:
                            tile.save(tile_buffer, format='JPEG', quality=85, optimize=True)
                        tile_data = tile_buffer.getvalue()

                        # Validate tile data
                        if tile_data is None or len(tile_data) == 0:
                            logger.error(f"Failed to generate tile data for level {level}, coords {x//self.tile_size}_{y//self.tile_size}")
                            continue

                        # Store with coordinates
                        tile_coords = f"{x//self.tile_size}_{y//self.tile_size}"
                        level_tiles[tile_coords] = tile_data

                tiles_data[level] = level_tiles
                logger.debug(f"Generated {len(level_tiles)} tiles for level {level}")

            return tiles_data, original_width, original_height

        except Exception as e:
            logger.error(f"Tile generation failed: {e}")
            raise Exception(f"Tile generation failed: {str(e)}")

    async def _upload_tiles_concurrent(
        self, 
        task: TileProcessingTask, 
        tiles_data: Dict[int, Dict[str, bytes]], 
        total_tiles: int
    ) -> int:
        """Upload tiles with concurrent control"""
        
        # Create semaphore for upload control
        upload_semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
        # Create upload tasks
        upload_tasks = []
        for level, tiles_level in tiles_data.items():
            for tile_coords, tile_data in tiles_level.items():
                upload_task = self._upload_single_tile_with_semaphore(
                    task, level, tile_coords, tile_data, upload_semaphore
                )
                upload_tasks.append(upload_task)
        
        # Process uploads in batches to avoid overwhelming the system
        batch_size = 20
        completed_tiles = 0
        successful_uploads = []
        failed_uploads = []
        
        for i in range(0, len(upload_tasks), batch_size):
            batch = upload_tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            # Process batch results
            for result in batch_results:
                if isinstance(result, Exception):
                    failed_uploads.append(result)
                elif result is not None:
                    successful_uploads.append(result)
                    completed_tiles += 1
            
            # Update progress
            progress = 10 + int((completed_tiles / total_tiles) * 80)  # 10-90%
            await self._update_processing_status(
                task, "uploading", progress, total_tiles, len(tiles_data), completed_tiles
            )
            
            logger.info(f"Uploaded {completed_tiles}/{total_tiles} tiles for photo {task.photo_id}")
            
            # Small delay between batches to prevent overwhelming
            if i + batch_size < len(upload_tasks):
                await asyncio.sleep(0.1)
        
        if failed_uploads:
            logger.warning(f"Some tile uploads failed for photo {task.photo_id}: {len(failed_uploads)} errors")
        
        return completed_tiles

    async def _upload_single_tile_with_semaphore(
        self,
        task: TileProcessingTask,
        level: int,
        tile_coords: str,
        tile_data: bytes,
        semaphore: asyncio.Semaphore
    ) -> Optional[str]:
        """Upload single tile with semaphore control"""
        async with semaphore:
            return await self._upload_single_tile(task, level, tile_coords, tile_data)

    async def _upload_single_tile(
        self,
        task: TileProcessingTask,
        level: int,
        tile_coords: str,
        tile_data: bytes
    ) -> Optional[str]:
        """Upload single tile to MinIO"""
        try:
            # Validate tile data
            if tile_data is None or len(tile_data) == 0:
                return None
            
            # Determine extension
            extension = 'png' if self.format == 'png' else 'jpg'
            object_name = f"{task.site_id}/tiles/{task.photo_id}/{level}/{tile_coords}.{extension}"
            
            # Prepare metadata
            tile_metadata = {
                'photo_id': task.photo_id,
                'site_id': task.site_id,
                'level': level,
                'tile_coords': tile_coords,
                'tile_size': self.tile_size,
                'format': self.format
            }
            
            if task.archaeological_metadata:
                tile_metadata.update({
                    'inventory_number': task.archaeological_metadata.get('inventory_number'),
                    'excavation_area': task.archaeological_metadata.get('excavation_area'),
                    'material': task.archaeological_metadata.get('material')
                })
            
            # Upload to MinIO
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            result = await asyncio.to_thread(
                archaeological_minio_service.client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=object_name,
                data=io.BytesIO(tile_data),
                length=len(tile_data),
                content_type='image/png' if self.format == 'png' else 'image/jpeg',
                metadata={
                    'x-amz-meta-photo-id': str(tile_metadata.get('photo_id', '')),
                    'x-amz-meta-site-id': str(tile_metadata.get('site_id', '')),
                    'x-amz-meta-level': str(tile_metadata.get('level', '')),
                    'x-amz-meta-tile-coords': str(tile_metadata.get('tile_coords', '')),
                    'x-amz-meta-tile-size': str(tile_metadata.get('tile_size', '')),
                    'x-amz-meta-inventory-number': str(tile_metadata.get('inventory_number', '')),
                    'x-amz-meta-excavation-area': str(tile_metadata.get('excavation_area', '')),
                    'x-amz-meta-material': str(tile_metadata.get('material', ''))
                }
            )
            
            return object_name
            
        except Exception as e:
            logger.error(f"Tile upload error for {task.photo_id}: {e}")
            return None

    async def _create_and_upload_metadata(
        self,
        task: TileProcessingTask,
        tiles_data: Dict[int, Dict[str, bytes]],
        width: int,
        height: int
    ) -> str:
        """Create and upload metadata.json for tiles"""
        
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
            "total_tiles": self._count_total_tiles(tiles_data),
            "created": datetime.now().isoformat(),
            "archaeological_metadata": task.archaeological_metadata or {}
        }
        
        # Add level information
        level_info = {}
        for level, tiles_level in tiles_data.items():
            level_info[level] = {
                "tile_count": len(tiles_level),
                "tiles": list(tiles_level.keys())
            }
        metadata["level_info"] = level_info
        
        # Upload metadata
        metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
        metadata_bytes = metadata_json.encode('utf-8')
        
        metadata_object_name = f"{task.site_id}/tiles/{task.photo_id}/metadata.json"
        
        try:
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            result = await asyncio.to_thread(
                archaeological_minio_service.client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=metadata_object_name,
                data=io.BytesIO(metadata_bytes),
                length=len(metadata_bytes),
                content_type='application/json',
                metadata={
                    'x-amz-meta-photo-id': task.photo_id,
                    'x-amz-meta-site-id': task.site_id,
                    'x-amz-meta-document-type': 'deep_zoom_metadata',
                    'x-amz-meta-created': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Deep zoom metadata uploaded: {metadata_object_name}")
            return f"minio://{archaeological_minio_service.buckets['tiles']}/{metadata_object_name}"
            
        except Exception as e:
            logger.error(f"Metadata upload failed: {e}")
            raise Exception(f"Metadata upload failed: {str(e)}")

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
                archaeological_minio_service.client.put_object,
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
                archaeological_minio_service.client.put_object,
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
        levels: int = None
    ):
        """
        🔧 DATABASE CONSISTENCY FIX: Update photo deep zoom status in database
        
        This method now implements the same robust photo lookup logic as the upload service
        to prevent "photo record not found" errors due to UUID/string type mismatches
        and transaction isolation issues.
        """
        try:
            # Avoid circular import
            # Import from centralized database engine
            from app.database.engine import AsyncSessionLocal as async_session_maker
            from app.models import Photo
            from sqlalchemy import select
            from datetime import datetime
            
            # CRITICAL FIX: Photo.id is stored as STRING, not UUID object
            # Use the photo_id as string directly since Photo.id is String(36)
            photo_id_str = str(photo_id)
            
            async with async_session_maker() as db:
                try:
                    # 🔧 ENHANCED: Use the same robust lookup logic as upload service
                    photo = await self._find_photo_record_with_fallback(photo_id_str, db)
                    
                    if photo:
                        # Update status
                        photo.deepzoom_status = status
                        
                        if status == "completed":
                            photo.has_deep_zoom = True
                            photo.deep_zoom_processed_at = datetime.now()
                            if tile_count is not None:
                                photo.tile_count = tile_count
                            if levels is not None:
                                photo.max_zoom_level = levels
                        elif status == "failed":
                            photo.has_deep_zoom = False
                            photo.deep_zoom_processed_at = datetime.now()
                        elif status == "processing":
                            photo.deepzoom_status = "processing"
                        
                        await db.commit()
                        logger.info(f"✅ Updated photo {photo_id} deep zoom status to: {status}")
                    else:
                        # 🔧 ENHANCED: Try with a completely fresh session as last resort
                        logger.warning(f"🔧 Photo {photo_id} not found in main session, trying fresh session...")
                        
                        async with async_session_maker() as fresh_db:
                            photo_fresh = await self._find_photo_record_with_fallback(photo_id_str, fresh_db)
                            
                            if photo_fresh:
                                logger.info(f"✅ Photo {photo_id} found in fresh session, updating status")
                                photo_fresh.deepzoom_status = status
                                
                                if status == "completed":
                                    photo_fresh.has_deep_zoom = True
                                    photo_fresh.deep_zoom_processed_at = datetime.now()
                                    if tile_count is not None:
                                        photo_fresh.tile_count = tile_count
                                    if levels is not None:
                                        photo_fresh.max_zoom_level = levels
                                elif status == "failed":
                                    photo_fresh.has_deep_zoom = False
                                    photo_fresh.deep_zoom_processed_at = datetime.now()
                                elif status == "processing":
                                    photo_fresh.deepzoom_status = "processing"
                                
                                await fresh_db.commit()
                                logger.info(f"✅ Photo {photo_id} status updated via fresh session")
                            else:
                                logger.error(f"❌ Photo {photo_id} not found in any session - THIS IS THE ROOT CAUSE!")
                                # Don't raise here to avoid breaking the entire pipeline
                                logger.error(f"❌ Deep zoom status update failed for {photo_id} - photo record not found")
                                return
                                
                except Exception as e:
                    logger.error(f"Database error in status update for {photo_id}: {e}")
                    await db.rollback()
                    raise
                    
        except Exception as e:
            logger.error(f"Failed to update photo database status for {photo_id}: {e}")
            # 🔧 SNAPSHOT-BASED: Don't re-raise to avoid breaking the entire processing pipeline
            # The tile processing can continue even if status update fails
            logger.error(f"⚠️ Deep zoom status update failed but continuing processing for {photo_id}")
            
            # Log snapshot information if available
            task = None
            if photo_id in self.processing_tasks:
                task = self.processing_tasks[photo_id]
            elif photo_id in self.completed_tasks:
                task = self.completed_tasks[photo_id]
            elif photo_id in self.failed_tasks:
                task = self.failed_tasks[photo_id]
            
            if task and hasattr(task, 'snapshot_data') and task.snapshot_data:
                logger.info(f"🔧 SNAPSHOT-BASED: Processing continues with snapshot data for {photo_id}")

    async def _find_photo_record_with_fallback(
        self,
        photo_id: str,
        db: AsyncSession,
        max_retries: int = 5
    ) -> Optional[Photo]:
        # Find photo record with retry logic and exponential backoff.
        # SQLite WAL FIX: Adds delay between retries to allow checkpoint.

        for attempt in range(max_retries):
            try:
                # Add delay before retry (except first attempt)
                if attempt > 0:
                    delay = 0.1 * (2 ** attempt)
                    logger.debug(f"Retry {attempt}/{max_retries} for photo {photo_id} after {delay:.1f}s")
                    await asyncio.sleep(delay)

                # Try UUID query first
                try:
                    photo_uuid = UUID(photo_id)
                    result = await db.execute(
                        select(Photo).where(Photo.id == photo_uuid)
                    )
                    photo_obj = result.scalar_one_or_none()

                    if photo_obj:
                        logger.debug(f"Photo {photo_id} found with UUID (attempt {attempt + 1})")
                        return photo_obj
                except ValueError:
                    pass

                # Try string query
                result = await db.execute(
                    select(Photo).where(Photo.id == photo_id)
                )
                photo_obj = result.scalar_one_or_none()

                if photo_obj:
                    logger.debug(f"Photo {photo_id} found with string (attempt {attempt + 1})")
                    return photo_obj

                # Force WAL checkpoint on retry
                if attempt > 0:
                    await db.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
                    logger.debug(f"Forced WAL checkpoint (attempt {attempt + 1})")

            except Exception as e:
                logger.warning(f"Error finding photo {photo_id} (attempt {attempt + 1}): {e}")
                continue

        logger.error(f"Photo {photo_id} not found after {max_retries} attempts")
        return None

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
            batch['photos'] = [p for p in batch['photos'] if p['photo_id'] != photo_id]
            
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
                if task.status == ProcessingStatus.PROCESSING and task.started_at:
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
                    task.status = ProcessingStatus.FAILED
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