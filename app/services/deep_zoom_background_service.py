# app/services/deep_zoom_background_service.py - Background processing service for deep zoom tiles

import asyncio
import json
import io
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from loguru import logger
from dataclasses import dataclass
from enum import Enum

from PIL import Image
import math

from app.services.deep_zoom_minio_service import deep_zoom_minio_service


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
        
        # CRITICO: Acquisisci lock per deduplicazione atomica
        async with self._processing_lock:
            # Verifica se il task è già in coda o in elaborazione
            if photo_id in self.processing_tasks:
                existing_task = self.processing_tasks[photo_id]
                if existing_task.status in [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING, ProcessingStatus.RETRYING]:
                    logger.info(f"🔄 Task already scheduled/processing for photo {photo_id}")
                    return {
                        'photo_id': photo_id,
                        'site_id': site_id,
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
                        'site_id': site_id,
                        'status': 'already_completed',
                        'message': 'Task completed recently',
                        'completed_at': completed_task.completed_at.isoformat()
                    }
            
            # Crea nuovo task
            task = TileProcessingTask(
                photo_id=photo_id,
                site_id=site_id,
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
                'site_id': site_id,
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
        
        scheduled_count = 0
        for photo_info in photos_list:
            try:
                # Load file content from MinIO
                from app.services.archaeological_minio_service import archaeological_minio_service
                original_file_content = await archaeological_minio_service.get_file(photo_info['file_path'])
                
                await self.schedule_tile_processing(
                    photo_id=photo_info['photo_id'],
                    site_id=site_id,
                    file_path=photo_info['file_path'],
                    original_file_content=original_file_content,
                    archaeological_metadata=photo_info.get('archaeological_metadata', {})
                )
                scheduled_count += 1
                
            except Exception as e:
                logger.error(f"Failed to schedule processing for photo {photo_info.get('photo_id')}: {e}")
        
        logger.info(f"📋 Scheduled {scheduled_count} photos for batch processing")
        
        return {
            'site_id': site_id,
            'scheduled_count': scheduled_count,
            'total_photos': len(photos_list),
            'status': 'scheduled',
            'message': f'{scheduled_count} photos scheduled for background processing'
        }

    async def _process_queue_worker(self):
        """Background worker that processes the queue"""
        logger.info("🔄 Background queue worker started")
        
        # Create semaphore to limit concurrent processing
        processing_semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        
        while self._running:
            try:
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
                
                # Generate tiles with memory-efficient processing
                tiles_data, original_width, original_height = await self._generate_tiles_memory_efficient(
                    task.original_file_content, task.photo_id, task.site_id
                )
                
                total_tiles = self._count_total_tiles(tiles_data)
                task.status = ProcessingStatus.UPLOADING
                await self._update_processing_status(task, "uploading", 10, total_tiles, len(tiles_data))
                
                # Upload tiles with concurrent control
                completed_tiles = await self._upload_tiles_concurrent(
                    task, tiles_data, total_tiles
                )
                
                # Create metadata
                task.status = ProcessingStatus.COMPLETED
                await self._update_processing_status(task, "finalizing", 90)
                
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
                
                logger.info(f"✅ Completed tile processing for photo {task.photo_id}: {completed_tiles} tiles")
                
                # Send WebSocket notification
                await self._send_completion_notification(task, True)
                
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
        """Update photo deep zoom status in database"""
        try:
            # Avoid circular import
            from app.database.base import async_session_maker
            from app.models import Photo
            from sqlalchemy import select
            from datetime import datetime
            import uuid
            
            # Convert string photo_id to UUID if needed
            if isinstance(photo_id, str):
                try:
                    photo_uuid = uuid.UUID(photo_id)
                except ValueError as e:
                    logger.error(f"Invalid UUID format for photo_id {photo_id}: {e}")
                    return
            else:
                photo_uuid = photo_id
            
            async with async_session_maker() as db:
                try:
                    # Get photo record
                    photo_query = select(Photo).where(Photo.id == photo_uuid)
                    result = await db.execute(photo_query)
                    photo = result.scalar_one_or_none()
                    
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
                        logger.info(f"Updated photo {photo_id} deep zoom status to: {status}")
                    else:
                        logger.warning(f"Photo {photo_id} not found for status update")
                except Exception as e:
                    logger.error(f"Database error in status update: {e}")
                    await db.rollback()
                    
        except Exception as e:
            logger.error(f"Failed to update photo database status for {photo_id}: {e}")

    async def _send_completion_notification(self, task: TileProcessingTask, success: bool):
        """Send WebSocket notification for task completion"""
        try:
            from app.routes.api.notifications_ws import notification_manager
            
            if success:
                await notification_manager.broadcast_tiles_progress(
                    site_id=task.site_id,
                    photo_id=task.photo_id,
                    status='completed',
                    progress=100,
                    tile_count=task.completed_at and 0,  # Will be updated by caller
                    levels=0,  # Will be updated by caller
                    error=None
                )
            else:
                await notification_manager.broadcast_tiles_progress(
                    site_id=task.site_id,
                    photo_id=task.photo_id,
                    status='failed',
                    progress=0,
                    error=task.error_message
                )
                
        except ImportError:
            logger.warning("Notification manager not available")
        except Exception as e:
            logger.error(f"Failed to send completion notification: {e}")

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
            "max_concurrent_uploads": self.max_concurrent_uploads
        }


# Global instance
deep_zoom_background_service = DeepZoomBackgroundService()