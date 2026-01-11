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

from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service
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
                original_file_content = await archaeological_minio_service.get_file(photo_snapshot['file_path'])
                
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
        """Process a single photo's tiles with proper locking using snapshot data"""
        
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
            
            # 🔧 SNAPSHOT-BASED: Determine data source and log accordingly
            use_snapshot = False
            photo_data = {}
            
            if hasattr(task, 'snapshot_data') and task.snapshot_data:
                use_snapshot = True
                photo_data = task.snapshot_data
                logger.info(f"🔧 SNAPSHOT-BASED: Processing photo {task.photo_id} using snapshot data")
                
                # Validate required snapshot fields
                required_fields = ['file_path', 'width', 'height']
                missing_fields = [field for field in required_fields if field not in photo_data]
                
                if missing_fields:
                    logger.warning(f"🔧 SNAPSHOT-BASED: Missing required fields in snapshot for {task.photo_id}: {missing_fields}")
                    use_snapshot = False
                    photo_data = {}
                    
                    # 🔧 SNAPSHOT-BASED: Validate additional optional fields for better error handling
                    if task.snapshot_data:
                        optional_fields = ['file_path', 'width', 'height', 'filename']
                        available_fields = [field for field in optional_fields if field in task.snapshot_data]
                        logger.info(f"🔧 SNAPSHOT-BASED: Available snapshot fields for {task.photo_id}: {available_fields}")
                else:
                    logger.info(f"🔄 Processing photo {task.photo_id} using traditional database queries")
            
            try:
                logger.info(f"🔄 Processing tiles for photo {task.photo_id} (attempt {task.retry_count + 1}) - {'SNAPSHOT' if use_snapshot else 'DATABASE'}")
                
                # 🔧 SNAPSHOT-BASED: Skip database update for processing status
                # Status is tracked via MinIO metadata for snapshot-based processing
                if use_snapshot:
                    logger.debug(f"🔧 SNAPSHOT-BASED: Skipping database update for 'processing' status")
                else:
                    # Legacy path: Update database for processing status
                    await self._update_photo_database_status(task.photo_id, "processing")
                
                await self._update_processing_status(task, "processing", 0)
                
                # Send intermediate notification for processing start
                await self._send_processing_notification(task, "processing", 5)
                
                # 🔧 SNAPSHOT-BASED: Generate tiles with memory-efficient processing
                # Use snapshot data if available, otherwise fall back to traditional method
                tiles_data, original_width, original_height = await self._generate_tiles_memory_efficient(
                    task.original_file_content, task.photo_id, task.site_id, photo_data if use_snapshot else None
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
                
                # Update database with completion (CRITICAL: Always update for completion status)
                # Even in snapshot mode, we need to update the database with completion status
                # so that the UI shows the correct deepzoom_status
                await self._update_photo_database_status(
                    task.photo_id,
                    "completed",
                    tile_count=completed_tiles,
                    levels=len(tiles_data),
                    use_snapshot=use_snapshot
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
                # FIX: task is a dataclass object, not a dict - access attributes directly
                photoid = task.photo_id if hasattr(task, 'photo_id') else 'unknown'
                logger.error(f"❌ Failed to process tiles for photo {photoid}: {e}")
                import traceback
                logger.error(f"❌ Error traceback:\n{traceback.format_exc()}")

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
                    
                    # Update database with failed status (CRITICAL: Always update for failed status)
                    # Even in snapshot mode, we need to update the database with failed status
                    # so that the UI shows the correct deepzoom_status
                    await self._update_photo_database_status(
                        task.photo_id,
                        "failed",
                        use_snapshot=use_snapshot
                    )
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
        site_id: str,
        snapshot_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """Generate tiles with memory-efficient processing using snapshot data when available"""
        
        # Use asyncio.to_thread to move CPU-intensive work off event loop
        return await asyncio.to_thread(
            self._generate_tiles_sync, content, photo_id, site_id, snapshot_data
        )

    def _generate_tiles_sync(
        self,
        content: bytes,
        photo_id: str,
        site_id: str,
        snapshot_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """Synchronous tile generation (runs in thread pool) using snapshot data when available with detailed debugging"""
        import time
        generation_start_time = time.time()
        
        with logger.contextualize(
            operation="generate_tiles_sync",
            photo_id=photo_id,
            site_id=site_id,
            tile_size=self.tile_size,
            format=self.format,
            service="deep_zoom_background_service"
        ):
            try:
                # 🔧 SNAPSHOT-BASED: Log data source
                use_snapshot = bool(snapshot_data)
                logger.info(
                    "🔧 TILE GENERATION STARTED",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "use_snapshot": use_snapshot,
                        "content_size_bytes": len(content),
                        "tile_size": self.tile_size,
                        "generation_start_time": datetime.now().isoformat(),
                        "data_source": "snapshot" if use_snapshot else "traditional"
                    }
                )
                
                # 🔧 VALIDATION: Validate content before processing
                validation_start_time = time.time()
                if not content:
                    logger.error(
                        "❌ IMAGE CONTENT VALIDATION FAILED",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "error": "empty_content",
                            "content_size": 0,
                            "validation_time_ms": round((time.time() - validation_start_time) * 1000, 2)
                        }
                    )
                    raise ValueError("Image content is empty")
                
                if len(content) < 100:  # Most valid images are larger than 100 bytes
                    logger.error(
                        "❌ IMAGE CONTENT VALIDATION FAILED",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "error": "content_too_small",
                            "content_size": len(content),
                            "validation_time_ms": round((time.time() - validation_start_time) * 1000, 2)
                        }
                    )
                    raise ValueError(f"Image content too small: {len(content)} bytes")
                
                # 🔧 VALIDATION: Log content details for debugging
                content_preview = content[:50] if len(content) >= 50 else content
                logger.debug(
                    "🔧 IMAGE CONTENT ANALYSIS",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "content_size": len(content),
                        "content_preview": content_preview.hex() if isinstance(content_preview, bytes) else str(content_preview),
                        "validation_time_ms": round((time.time() - validation_start_time) * 1000, 2)
                    }
                )
                
                # 🔧 VALIDATION: Check common image format signatures
                format_detection_start_time = time.time()
                detected_format = "unknown"
                if len(content) >= 4:
                    # JPEG: FF D8 FF
                    if content[0:2] == b'\xFF\xD8' and content[2] == 0xFF:
                        detected_format = "jpeg"
                        logger.debug(
                            "🔧 IMAGE FORMAT DETECTED: JPEG",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "detected_format": "jpeg",
                                "signature": content[0:4].hex(),
                                "format_detection_time_ms": round((time.time() - format_detection_start_time) * 1000, 2)
                            }
                        )
                    # PNG: 89 50 4E 47
                    elif content[0:4] == b'\x89PNG':
                        detected_format = "png"
                        logger.debug(
                            "🔧 IMAGE FORMAT DETECTED: PNG",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "detected_format": "png",
                                "signature": content[0:8].hex(),
                                "format_detection_time_ms": round((time.time() - format_detection_start_time) * 1000, 2)
                            }
                        )
                    # WEBP: 52 49 46 46 ... 57 45 42 50
                    elif content[0:4] == b'RIFF' and len(content) >= 12 and content[8:12] == b'WEBP':
                        detected_format = "webp"
                        logger.debug(
                            "🔧 IMAGE FORMAT DETECTED: WEBP",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "detected_format": "webp",
                                "signature": content[0:12].hex(),
                                "format_detection_time_ms": round((time.time() - format_detection_start_time) * 1000, 2)
                            }
                        )
                    else:
                        logger.warning(
                            "⚠️ UNKNOWN IMAGE FORMAT",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "detected_format": "unknown",
                                "first_8_bytes": content[:8].hex(),
                                "format_detection_time_ms": round((time.time() - format_detection_start_time) * 1000, 2)
                            }
                        )
                else:
                    logger.warning(
                        "⚠️ CONTENT TOO SMALL FOR FORMAT DETECTION",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "content_size": len(content),
                            "format_detection_time_ms": round((time.time() - format_detection_start_time) * 1000, 2)
                        }
                    )
                
                # 🔧 VALIDATION: Try to open image with better error handling
                image_loading_start_time = time.time()
                try:
                    # Create BytesIO object and reset position
                    image_buffer = io.BytesIO(content)
                    image_buffer.seek(0)
                    
                    # Open image with explicit format validation
                    image = Image.open(image_buffer)
                    
                    # Verify image can be loaded
                    image.verify()  # Verify without loading pixel data
                    
                    # Reopen after verify (verify() closes the file)
                    image_buffer.seek(0)
                    image = Image.open(image_buffer)
                    
                    image_loading_time = time.time() - image_loading_start_time
                    
                    logger.success(
                        "✅ IMAGE VALIDATION SUCCESSFUL",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "image_size": f"{image.width}x{image.height}",
                        "image_mode": image.mode,
                        "image_format": image.format,
                        "detected_format": detected_format,
                        "image_loading_time_ms": round(image_loading_time * 1000, 2),
                        "total_validation_time_ms": round((time.time() - validation_start_time) * 1000, 2)
                    }
                )
                
                except Exception as img_error:
                    image_loading_time = time.time() - image_loading_start_time
                    
                    logger.error(
                        "❌ IMAGE VALIDATION FAILED",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "error": str(img_error),
                            "error_type": type(img_error).__name__,
                            "content_size": len(content),
                            "detected_format": detected_format,
                            "image_loading_time_ms": round(image_loading_time * 1000, 2),
                            "total_validation_time_ms": round((time.time() - validation_start_time) * 1000, 2),
                            "content_preview": content[:100].hex()
                        }
                    )
                    
                    import traceback
                    logger.error(
                        "📋 IMAGE VALIDATION ERROR TRACEBACK",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "traceback": traceback.format_exc(),
                            "error_details": {
                                "error": str(img_error),
                                "error_type": type(img_error).__name__,
                                "module": type(img_error).__module__ if hasattr(type(img_error), '__module__') else 'unknown'
                            }
                        }
                    )
                    
                    raise ValueError(f"Invalid image content: {str(img_error)}")
                
                # Determine format based on image
                format_determination_start_time = time.time()
                original_format = image.format.lower() if image.format else 'jpg'
                original_has_transparency = image.mode in ('RGBA', 'LA') or 'transparency' in image.info
                
                if original_format == 'png' or original_has_transparency:
                    self.format = 'png'
                    format_reason = "png_format_or_transparency"
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                        conversion_performed = "RGB_to_RGBA"
                    else:
                        conversion_performed = "none"
                else:
                    self.format = 'jpg'
                    format_reason = "jpg_format_no_transparency"
                    if image.mode == 'RGBA':
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        background.paste(image, mask=image.split()[-1])
                        image = background
                        conversion_performed = "RGBA_to_RGB"
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')
                        conversion_performed = f"{image.mode}_to_RGB"
                    else:
                        conversion_performed = "none"
                
                format_determination_time = time.time() - format_determination_start_time
                
                logger.info(
                    "🎨 TILE FORMAT DETERMINED",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "original_image_format": original_format,
                        "original_image_mode": image.mode,
                        "has_transparency": original_has_transparency,
                        "selected_tile_format": self.format,
                        "format_reason": format_reason,
                        "conversion_performed": conversion_performed,
                        "final_image_mode": image.mode,
                        "format_determination_time_ms": round(format_determination_time * 1000, 2)
                    }
                )

                # 🔧 SNAPSHOT-BASED: Use dimensions from snapshot if available, otherwise from image
                dimension_resolution_start_time = time.time()
                if snapshot_data and 'width' in snapshot_data and 'height' in snapshot_data:
                    original_width = snapshot_data['width']
                    original_height = snapshot_data['height']
                    dimension_source = "snapshot"
                    
                    logger.debug(
                        "🔧 DIMENSIONS FROM SNAPSHOT",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "snapshot_width": original_width,
                            "snapshot_height": original_height,
                            "dimension_source": "snapshot"
                        }
                    )
                    
                    # Validate that snapshot dimensions match actual image dimensions
                    if abs(image.width - original_width) > 5 or abs(image.height - original_height) > 5:
                        logger.warning(
                            "⚠️ DIMENSION MISMATCH DETECTED",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "snapshot_width": original_width,
                                "snapshot_height": original_height,
                                "actual_width": image.width,
                                "actual_height": image.height,
                                "width_diff": abs(image.width - original_width),
                                "height_diff": abs(image.height - original_height),
                                "dimension_source": "fallback_to_actual"
                            }
                        )
                        # Use actual image dimensions as fallback
                        original_width = image.width
                        original_height = image.height
                        dimension_source = "actual_image_fallback"
                        
                        logger.info(
                            "🔄 USING ACTUAL IMAGE DIMENSIONS",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "final_width": original_width,
                                "final_height": original_height,
                                "dimension_source": dimension_source
                            }
                        )
                    else:
                        logger.info(
                            "✅ SNAPSHOT DIMENSIONS VALIDATED",
                            extra={
                                "photo_id": photo_id,
                                "site_id": site_id,
                                "final_width": original_width,
                                "final_height": original_height,
                                "dimension_source": dimension_source
                            }
                        )
                else:
                    original_width = image.width
                    original_height = image.height
                    dimension_source = "actual_image"
                    
                    logger.debug(
                        "🔄 USING ACTUAL IMAGE DIMENSIONS",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "final_width": original_width,
                            "final_height": original_height,
                            "dimension_source": dimension_source
                        }
                    )
                
                dimension_resolution_time = time.time() - dimension_resolution_start_time

                # Calculate levels
                level_calculation_start_time = time.time()
                max_dimension = max(image.size)
                levels = math.ceil(math.log2(max_dimension)) + 1
                level_calculation_time = time.time() - level_calculation_start_time
                
                logger.info(
                    "📐 TILE PYRAMID CALCULATED",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "image_width": image.width,
                        "image_height": image.height,
                        "max_dimension": max_dimension,
                        "calculated_levels": levels,
                        "tile_size": self.tile_size,
                        "level_calculation_time_ms": round(level_calculation_time * 1000, 2),
                        "dimension_resolution_time_ms": round(dimension_resolution_time * 1000, 2)
                    }
                )

                tiles_data = {}
                total_tiles_generated = 0
                tile_generation_start_time = time.time()

                # Generate tiles for each level
                for level in range(levels):
                    level_start_time = time.time()
                    level_tiles = {}

                    # Calculate dimensions for this level
                    scale = 2 ** (levels - 1 - level)
                    level_width = max(1, image.width // scale)
                    level_height = max(1, image.height // scale)

                    logger.debug(
                        f"🔍 PROCESSING LEVEL {level}",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "level": level,
                            "scale_factor": scale,
                            "level_width": level_width,
                            "level_height": level_height,
                            "tiles_in_level_x": math.ceil(level_width / self.tile_size),
                            "tiles_in_level_y": math.ceil(level_height / self.tile_size)
                        }
                    )

                    # Create resized image for this level
                    resize_start_time = time.time()
                    level_image = image.resize((level_width, level_height), Image.Resampling.LANCZOS)
                    resize_time = time.time() - resize_start_time

                    # Generate tiles for this level
                    tiles_in_level = 0
                    for y in range(0, level_height, self.tile_size):
                        for x in range(0, level_width, self.tile_size):
                            tile_start_time = time.time()
                            
                            # Extract tile
                            tile_box = (x, y, min(x + self.tile_size, level_width), min(y + self.tile_size, level_height))
                            tile = level_image.crop(tile_box)

                            # Pad tile if needed
                            padding_performed = False
                            if tile.size[0] < self.tile_size or tile.size[1] < self.tile_size:
                                padding_performed = True
                                if original_has_transparency:
                                    padded_tile = Image.new('RGBA', (self.tile_size, self.tile_size), (255, 255, 255, 0))
                                    padded_tile.paste(tile, (0, 0), tile if tile.mode == 'RGBA' else None)
                                else:
                                    padded_tile = Image.new('RGB', (self.tile_size, self.tile_size), (255, 255, 255))
                                    padded_tile.paste(tile, (0, 0))
                                tile = padded_tile

                            # Convert to bytes
                            encoding_start_time = time.time()
                            tile_buffer = io.BytesIO()
                            if self.format == 'png':
                                tile.save(tile_buffer, format='PNG', optimize=True)
                            else:
                                # JPEG does not support alpha channel - convert RGBA to RGB
                                if tile.mode == 'RGBA':
                                    # Create white background and paste image on it
                                    rgb_tile = Image.new('RGB', tile.size, (255, 255, 255))
                                    rgb_tile.paste(tile, mask=tile.split()[3])  # Use alpha as mask
                                    tile = rgb_tile
                                elif tile.mode != 'RGB':
                                    tile = tile.convert('RGB')
                                tile.save(tile_buffer, format='JPEG', quality=85, optimize=True)
                            tile_data = tile_buffer.getvalue()
                            encoding_time = time.time() - encoding_start_time

                            # Validate tile data
                            if tile_data is None or len(tile_data) == 0:
                                logger.error(
                                    "❌ TILE GENERATION FAILED",
                                    extra={
                                        "photo_id": photo_id,
                                        "site_id": site_id,
                                        "level": level,
                                        "tile_coords": f"{x//self.tile_size}_{y//self.tile_size}",
                                        "tile_box": tile_box,
                                        "tile_size_before_padding": f"{tile_box[2]-tile_box[0]}x{tile_box[3]-tile_box[1]}",
                                        "padding_performed": padding_performed,
                                        "encoding_time_ms": round(encoding_time * 1000, 2),
                                        "tile_data_size": 0,
                                        "error": "empty_tile_data"
                                    }
                                )
                                continue

                            # Store with coordinates
                            tile_coords = f"{x//self.tile_size}_{y//self.tile_size}"
                            level_tiles[tile_coords] = tile_data
                            tiles_in_level += 1
                            total_tiles_generated += 1
                            
                            tile_total_time = time.time() - tile_start_time
                            
                            # Log every 100th tile to avoid spam
                            if total_tiles_generated % 100 == 0:
                                logger.debug(
                                    f"🔹 TILE GENERATED #{total_tiles_generated}",
                                    extra={
                                        "photo_id": photo_id,
                                        "site_id": site_id,
                                        "level": level,
                                        "tile_coords": tile_coords,
                                        "tile_data_size_bytes": len(tile_data),
                                        "padding_performed": padding_performed,
                                        "encoding_time_ms": round(encoding_time * 1000, 2),
                                        "total_tile_time_ms": round(tile_total_time * 1000, 2),
                                        "tiles_generated_so_far": total_tiles_generated
                                    }
                                )

                    level_time = time.time() - level_start_time
                    logger.debug(
                        f"✅ LEVEL {level} COMPLETED",
                        extra={
                            "photo_id": photo_id,
                            "site_id": site_id,
                            "level": level,
                            "tiles_in_level": tiles_in_level,
                            "level_time_ms": round(level_time * 1000, 2),
                            "resize_time_ms": round(resize_time * 1000, 2),
                            "total_tiles_so_far": total_tiles_generated
                        }
                    )
                    
                    tiles_data[level] = level_tiles

                total_generation_time = time.time() - tile_generation_start_time
                total_operation_time = time.time() - generation_start_time
                
                logger.success(
                    "✅ TILE GENERATION COMPLETED",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "total_levels": levels,
                        "total_tiles_generated": total_tiles_generated,
                        "original_width": original_width,
                        "original_height": original_height,
                        "tile_format": self.format,
                        "tile_size": self.tile_size,
                        "generation_performance": {
                            "total_generation_time_ms": round(total_generation_time * 1000, 2),
                            "total_operation_time_ms": round(total_operation_time * 1000, 2),
                            "average_tile_time_ms": round(total_generation_time / total_tiles_generated * 1000, 2) if total_tiles_generated > 0 else 0,
                            "tiles_per_second": round(total_tiles_generated / total_generation_time, 2) if total_generation_time > 0 else 0
                        },
                        "timing_breakdown": {
                            "validation_time_ms": round((time.time() - validation_start_time) * 1000, 2),
                            "format_determination_time_ms": round(format_determination_time * 1000, 2),
                            "dimension_resolution_time_ms": round(dimension_resolution_time * 1000, 2),
                            "level_calculation_time_ms": round(level_calculation_time * 1000, 2)
                        },
                        "data_source": "snapshot" if use_snapshot else "traditional"
                    }
                )

                return tiles_data, original_width, original_height

            except Exception as e:
                total_operation_time = time.time() - generation_start_time
                
                logger.error(
                    "❌ TILE GENERATION FAILED",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_operation_time_ms": round(total_operation_time * 1000, 2),
                        "content_size": len(content),
                        "failure_point": "tile_generation"
                    }
                )
                
                import traceback
                logger.error(
                    "📋 TILE GENERATION ERROR TRACEBACK",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
                raise Exception(f"Tile generation failed: {str(e)}")

    async def _upload_tiles_concurrent(
        self,
        task: TileProcessingTask,
        tiles_data: Dict[int, Dict[str, bytes]],
        total_tiles: int
    ) -> int:
        """Upload tiles with concurrent control and comprehensive performance metrics"""
        import time
        upload_start_time = time.time()
        
        with logger.contextualize(
            operation="upload_tiles_concurrent",
            photo_id=task.photo_id,
            site_id=task.site_id,
            total_tiles=total_tiles,
            levels_count=len(tiles_data),
            max_concurrent_uploads=self.max_concurrent_uploads,
            service="deep_zoom_background_service"
        ):
            try:
                logger.info(
                    "🚀 CONCURRENT TILE UPLOAD STARTED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "total_tiles": total_tiles,
                        "levels_count": len(tiles_data),
                        "max_concurrent_uploads": self.max_concurrent_uploads,
                        "upload_start_time": datetime.now().isoformat()
                    }
                )
                
                # Create semaphore for upload control
                upload_semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
                
                # Create upload tasks with detailed tracking
                task_creation_start_time = time.time()
                upload_tasks = []
                tile_details_by_level = {}
                
                for level, tiles_level in tiles_data.items():
                    level_tile_count = len(tiles_level)
                    tile_details_by_level[level] = level_tile_count
                    
                    logger.debug(
                        f"🔍 CREATING UPLOAD TASKS FOR LEVEL {level}",
                        extra={
                            "photo_id": task.photo_id,
                            "site_id": task.site_id,
                            "level": level,
                            "tiles_in_level": level_tile_count,
                            "total_tiles_so_far": len(upload_tasks)
                        }
                    )
                    
                    for tile_coords, tile_data in tiles_level.items():
                        upload_task = self._upload_single_tile_with_semaphore(
                            task, level, tile_coords, tile_data, upload_semaphore
                        )
                        upload_tasks.append(upload_task)
                
                task_creation_time = time.time() - task_creation_start_time
                
                logger.info(
                    "📋 UPLOAD TASKS CREATED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "total_upload_tasks": len(upload_tasks),
                        "task_creation_time_ms": round(task_creation_time * 1000, 2),
                        "tiles_by_level": tile_details_by_level,
                        "average_tiles_per_level": round(total_tiles / len(tiles_data), 2) if tiles_data else 0
                    }
                )
                
                # Process uploads in batches to avoid overwhelming the system
                batch_size = 20
                completed_tiles = 0
                successful_uploads = []
                failed_uploads = []
                batch_processing_times = []
                error_types = {}
                
                total_batches = (len(upload_tasks) + batch_size - 1) // batch_size
                
                for batch_num, i in enumerate(range(0, len(upload_tasks), batch_size), 1):
                    batch_start_time = time.time()
                    batch = upload_tasks[i:i + batch_size]
                    
                    logger.info(
                        f"🔄 PROCESSING BATCH {batch_num}/{total_batches}",
                        extra={
                            "photo_id": task.photo_id,
                            "site_id": task.site_id,
                            "batch_number": batch_num,
                            "total_batches": total_batches,
                            "batch_size": len(batch),
                            "batch_start_index": i,
                            "batch_end_index": min(i + batch_size, len(upload_tasks)),
                            "completed_tiles_before_batch": completed_tiles
                        }
                    )
                    
                    batch_results = await asyncio.gather(*batch, return_exceptions=True)
                    batch_processing_time = time.time() - batch_start_time
                    batch_processing_times.append(batch_processing_time)
                    
                    # Process batch results with detailed error tracking
                    batch_successful = 0
                    batch_failed = 0
                    
                    for result_idx, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            failed_uploads.append(result)
                            batch_failed += 1
                            
                            # Track error types for analysis
                            error_type = type(result).__name__
                            error_types[error_type] = error_types.get(error_type, 0) + 1
                            
                            logger.warning(
                                f"❌ TILE UPLOAD FAILED IN BATCH {batch_num}",
                                extra={
                                    "photo_id": task.photo_id,
                                    "site_id": task.site_id,
                                    "batch_number": batch_num,
                                    "result_index": result_idx,
                                    "error_type": error_type,
                                    "error_message": str(result)[:200],  # Truncate long errors
                                    "total_failed_so_far": len(failed_uploads)
                                }
                            )
                        elif result is not None:
                            successful_uploads.append(result)
                            completed_tiles += 1
                            batch_successful += 1
                        else:
                            # None result - treat as failure
                            failed_uploads.append(Exception("Upload returned None"))
                            batch_failed += 1
                            error_types["NoneResult"] = error_types.get("NoneResult", 0) + 1
                    
                    # Update progress
                    progress = 10 + int((completed_tiles / total_tiles) * 80)  # 10-90%
                    await self._update_processing_status(
                        task, "uploading", progress, total_tiles, len(tiles_data), completed_tiles
                    )
                    
                    # Calculate batch performance metrics
                    batch_throughput = len(batch) / batch_processing_time if batch_processing_time > 0 else 0
                    overall_progress = (completed_tiles / total_tiles) * 100 if total_tiles > 0 else 0
                    
                    logger.info(
                        f"✅ BATCH {batch_num} COMPLETED",
                        extra={
                            "photo_id": task.photo_id,
                            "site_id": task.site_id,
                            "batch_number": batch_num,
                            "batch_successful": batch_successful,
                            "batch_failed": batch_failed,
                            "batch_processing_time_ms": round(batch_processing_time * 1000, 2),
                            "batch_throughput_tiles_per_sec": round(batch_throughput, 2),
                            "completed_tiles": completed_tiles,
                            "total_tiles": total_tiles,
                            "overall_progress_percent": round(overall_progress, 2),
                            "progress_update": progress,
                            "successful_uploads": len(successful_uploads),
                            "failed_uploads": len(failed_uploads)
                        }
                    )
                    
                    # Small delay between batches to prevent overwhelming
                    if i + batch_size < len(upload_tasks):
                        await asyncio.sleep(0.1)
                
                # Calculate final performance metrics
                total_upload_time = time.time() - upload_start_time
                average_batch_time = sum(batch_processing_times) / len(batch_processing_times) if batch_processing_times else 0
                success_rate = (completed_tiles / total_tiles) * 100 if total_tiles > 0 else 0
                overall_throughput = completed_tiles / total_upload_time if total_upload_time > 0 else 0
                
                # Log comprehensive upload summary
                logger.success(
                    "🎉 CONCURRENT TILE UPLOAD COMPLETED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "final_results": {
                            "completed_tiles": completed_tiles,
                            "total_tiles": total_tiles,
                            "successful_uploads": len(successful_uploads),
                            "failed_uploads": len(failed_uploads),
                            "success_rate_percent": round(success_rate, 2)
                        },
                        "performance_metrics": {
                            "total_upload_time_ms": round(total_upload_time * 1000, 2),
                            "average_batch_time_ms": round(average_batch_time * 1000, 2),
                            "overall_throughput_tiles_per_sec": round(overall_throughput, 2),
                            "task_creation_time_ms": round(task_creation_time * 1000, 2),
                            "total_batches_processed": len(batch_processing_times),
                            "batch_size_used": batch_size
                        },
                        "error_analysis": {
                            "error_types": error_types,
                            "error_count": len(failed_uploads),
                            "error_rate_percent": round((len(failed_uploads) / total_tiles) * 100, 2) if total_tiles > 0 else 0
                        },
                        "levels_processed": tile_details_by_level
                    }
                )
                
                # Log warnings for any issues
                if failed_uploads:
                    logger.warning(
                        "⚠️ TILE UPLOAD ISSUES DETECTED",
                        extra={
                            "photo_id": task.photo_id,
                            "site_id": task.site_id,
                            "failed_upload_count": len(failed_uploads),
                            "success_rate_percent": round(success_rate, 2),
                            "error_breakdown": error_types,
                            "recommendation": "Check MinIO connectivity and storage capacity" if len(failed_uploads) > total_tiles * 0.1 else "Monitor for patterns"
                        }
                    )
                
                # Performance warnings
                if overall_throughput < 5:  # Less than 5 tiles per second
                    logger.warning(
                        "⚠️ SLOW UPLOAD PERFORMANCE DETECTED",
                        extra={
                            "photo_id": task.photo_id,
                            "site_id": task.site_id,
                            "throughput_tiles_per_sec": round(overall_throughput, 2),
                            "recommended_action": "Consider increasing concurrent uploads or checking network bandwidth"
                        }
                    )
                
                return completed_tiles
            
            except Exception as e:
                total_upload_time = time.time() - upload_start_time
                
                logger.error(
                    "❌ CONCURRENT TILE UPLOAD FAILED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_upload_time_ms": round(total_upload_time * 1000, 2),
                        "tiles_data_levels": len(tiles_data),
                        "total_tiles_expected": total_tiles,
                        "failure_point": "concurrent_upload_coordinator"
                    }
                )
                
                import traceback
                logger.error(
                    "📋 CONCURRENT UPLOAD ERROR TRACEBACK",
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
                
                raise Exception(f"Concurrent tile upload failed: {str(e)}")

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
        """Upload single tile to MinIO with detailed debugging"""
        import time
        upload_start_time = time.time()
        
        with logger.contextualize(
            operation="upload_single_tile",
            photo_id=task.photo_id,
            site_id=task.site_id,
            level=level,
            tile_coords=tile_coords,
            tile_size=self.tile_size,
            format=self.format,
            service="deep_zoom_background_service"
        ):
            try:
                # Validate tile data
                if tile_data is None or len(tile_data) == 0:
                    logger.error(
                        "❌ TILE DATA VALIDATION FAILED",
                        extra={
                            "photo_id": task.photo_id,
                            "site_id": task.site_id,
                            "level": level,
                            "tile_coords": tile_coords,
                            "tile_data_is_none": tile_data is None,
                            "tile_data_length": len(tile_data) if tile_data else 0,
                            "validation_error": "empty_or_null_tile_data"
                        }
                    )
                    return None
                
                # Determine extension
                extension = 'png' if self.format == 'png' else 'jpg'
                object_name = f"{task.site_id}/tiles/{task.photo_id}/{level}/{tile_coords}.{extension}"
                
                logger.debug(
                    "🔍 TILE UPLOAD STARTED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "level": level,
                        "tile_coords": tile_coords,
                        "tile_size": self.tile_size,
                        "format": self.format,
                        "extension": extension,
                        "object_name": object_name,
                        "tile_data_size_bytes": len(tile_data),
                        "upload_start_time": datetime.now().isoformat()
                    }
                )
                
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
                
                # Upload to MinIO with timing
                minio_upload_start_time = time.time()
                from app.services.archaeological_minio_service import archaeological_minio_service
                
                logger.info(
                    "📤 MINIO UPLOAD INITIATED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "level": level,
                        "tile_coords": tile_coords,
                        "bucket_name": archaeological_minio_service.buckets['tiles'],
                        "object_name": object_name,
                        "content_type": 'image/png' if self.format == 'png' else 'image/jpeg',
                        "tile_metadata": tile_metadata,
                        "tile_data_size_bytes": len(tile_data)
                    }
                )
                
                result = await asyncio.to_thread(
                    archaeological_minio_service._client.put_object,
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
                
                minio_upload_time = time.time() - minio_upload_start_time
                total_upload_time = time.time() - upload_start_time
                
                logger.success(
                    "✅ TILE UPLOAD COMPLETED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "level": level,
                        "tile_coords": tile_coords,
                        "object_name": object_name,
                        "minio_upload_time_ms": round(minio_upload_time * 1000, 2),
                        "total_upload_time_ms": round(total_upload_time * 1000, 2),
                        "tile_data_size_bytes": len(tile_data),
                        "upload_speed_kb_per_sec": round((len(tile_data) / 1024) / minio_upload_time, 2) if minio_upload_time > 0 else 0,
                        "bucket_name": archaeological_minio_service.buckets['tiles']
                    }
                )
                
                return object_name
            
            except Exception as e:
                total_upload_time = time.time() - upload_start_time
                
                logger.error(
                    "❌ TILE UPLOAD FAILED",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "level": level,
                        "tile_coords": tile_coords,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "total_upload_time_ms": round(total_upload_time * 1000, 2),
                        "tile_data_size_bytes": len(tile_data) if tile_data else 0,
                        "failure_point": "minio_upload"
                    }
                )
                
                import traceback
                logger.error(
                    "📋 TILE UPLOAD ERROR TRACEBACK",
                    extra={
                        "photo_id": task.photo_id,
                        "site_id": task.site_id,
                        "level": level,
                        "tile_coords": tile_coords,
                        "traceback": traceback.format_exc(),
                        "error_details": {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "module": type(e).__module__ if hasattr(type(e), '__module__') else 'unknown'
                        }
                    }
                )
                
                return None

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
        use_snapshot: bool = False
    ):
        """
        🔧 SNAPSHOT-BASED FIX: Skip database updates entirely for snapshot-based processing.
        
        Status is tracked via MinIO metadata and can be synced later. This completely eliminates
        SQLite WAL snapshot isolation issues for background tasks.
        """
        try:
            # Check if this task is using snapshot data
            task = None
            if photo_id in self.processing_tasks:
                task = self.processing_tasks[photo_id]
            elif photo_id in self.completed_tasks:
                task = self.completed_tasks[photo_id]
            elif photo_id in self.failed_tasks:
                task = self.failed_tasks[photo_id]
            
            if task and hasattr(task, 'snapshot_data') and task.snapshot_data and status != "completed":
                logger.info(f"🔧 SNAPSHOT-BASED: Skipping database update for photo {photo_id} (status: {status})")
                logger.info(f"🔧 SNAPSHOT-BASED: Status '{status}' is tracked in MinIO metadata and processing state")
                return
            
            # CRITICAL FIX: Always allow completion and failed status updates, even in snapshot mode
            # This ensures the UI shows the correct deepzoom_status after tile generation
            if task and hasattr(task, 'snapshot_data') and task.snapshot_data and status in ["completed", "failed"]:
                logger.info(f"🔧 SNAPSHOT-BASED: UPDATING database for photo {photo_id} with {status} status")
                logger.info(f"🔧 SNAPSHOT-BASED: {status.capitalize()} status update is required for UI consistency")
            
            # Only do database updates for non-snapshot processing (legacy path)
            logger.info(f"🔧 DATABASE: Updating photo {photo_id} status to {status}")
            
            # Only do database updates for non-snapshot processing (legacy path)
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
                    # But only for legacy path (non-snapshot) processing
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
                        
                        await db.commit()
                        logger.info(f"✅ Updated photo {photo_id} deep zoom status to: {status} (legacy path)")
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
                                
                                await fresh_db.commit()
                                logger.info(f"✅ Photo {photo_id} status updated via fresh session (legacy path)")
                            else:
                                logger.error(f"❌ Photo {photo_id} not found in any session for status update")
                                # Don't fail the entire processing for status update issues
                                logger.error(f"⚠️ Status update failed for {photo_id} but tiles were processed successfully")
                                return
                                
                except Exception as e:
                    logger.error(f"Database error in status update for {photo_id}: {e}")
                    await db.rollback()
                    raise
                    
        except Exception as e:
            logger.error(f"Failed to update photo database status for {photo_id}: {e}")
            # Don't re-raise to avoid breaking the entire processing pipeline
            # The tile processing is already complete, status update failure shouldn't break it
            logger.error(f"⚠️ Status update failed but tile processing was successful for {photo_id}")

    async def _find_photo_record_with_fallback(
        self,
        photo_id: str,
        db: AsyncSession,
        max_retries: int = 5
    ) -> Optional[Photo]:
        """
        🔧 SNAPSHOT-BASED FIX: Find photo record with retry logic for LEGACY PATH ONLY.
        
        This method is now used ONLY for legacy path processing (non-snapshot) to eliminate
        race conditions during initial processing. The complex retry logic with WAL checkpoints
        is preserved but only used when absolutely necessary for legacy status updates.
        
        SQLite WAL FIX: Adds delay between retries to allow checkpoint.
        """

        logger.debug(f"🔧 LEGACY PATH: Looking up photo {photo_id} for database status update")

        for attempt in range(max_retries):
            try:
                # Add delay before retry (except first attempt)
                if attempt > 0:
                    delay = 0.1 * (2 ** attempt)
                    logger.debug(f"🔧 SNAPSHOT-BASED: Retry {attempt}/{max_retries} for photo {photo_id} after {delay:.1f}s")
                    await asyncio.sleep(delay)

                # Try UUID query first
                try:
                    photo_uuid = UUID(photo_id)
                    result = await db.execute(
                        select(Photo).where(Photo.id == photo_uuid)
                    )
                    photo_obj = result.scalar_one_or_none()

                    if photo_obj:
                        logger.debug(f"🔧 LEGACY PATH: Photo {photo_id} found with UUID (attempt {attempt + 1})")
                        return photo_obj
                except ValueError:
                    pass

                # Try string query
                result = await db.execute(
                    select(Photo).where(Photo.id == photo_id)
                )
                photo_obj = result.scalar_one_or_none()

                if photo_obj:
                    logger.debug(f"🔧 LEGACY PATH: Photo {photo_id} found with string (attempt {attempt + 1})")
                    return photo_obj

                # Force WAL checkpoint on retry (only for legacy path updates)
                if attempt > 0:
                    await db.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
                    logger.debug(f"🔧 LEGACY PATH: Forced WAL checkpoint for database status update (attempt {attempt + 1})")

            except Exception as e:
                logger.warning(f"🔧 LEGACY PATH: Error finding photo {photo_id} for database status (attempt {attempt + 1}): {e}")
                continue

        logger.error(f"🔧 LEGACY PATH: Photo {photo_id} not found after {max_retries} attempts for database status update")
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