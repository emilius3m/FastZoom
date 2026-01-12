# app/services/deep_zoom_minio_service.py - DEEP ZOOM OTTIMIZZATO PER MINIO ARCHEOLOGICO

import io
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from loguru import logger
from fastapi import UploadFile, HTTPException, BackgroundTasks

from PIL import Image
import math
from app.models.deepzoom_enums import DeepZoomStatus

# Import diretto evitato per evitare circular import
# Il servizio archeologico verrà passato come parametro o usato tramite import locale


class DeepZoomMinIOService:
    """Deep zoom ottimizzato per MinIO con supporto archeologico"""

    def __init__(self, archaeological_minio_service):
        self.storage = archaeological_minio_service
        self.tile_size = 256  # Standard deep zoom tile size
        self.overlap = 0      # Tile overlap for seamless viewing
        self.format = 'jpg'   # Tile format

    @logger.catch(
        reraise=True,
        message="Failed to create processing status for {photo_id}",
        level="ERROR"
    )
    async def create_processing_status(
        self,
        photo_id: str,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Crea stato di processing per tiles in background
        
        Returns:
            Dict con informazioni di stato
        """
        with logger.contextualize(
            operation="create_processing_status",
            photo_id=photo_id,
            site_id=site_id,
            has_metadata=archaeological_metadata is not None
        ):
            try:
                # Crea status metadata iniziale
                status = {
                    "photo_id": photo_id,
                    "site_id": site_id,
                    "status": DeepZoomStatus.PROCESSING.value,
                    "progress": 0,
                    "total_tiles": 0,
                    "completed_tiles": 0,
                    "levels": 0,
                    "tile_size": self.tile_size,
                    "started": datetime.now().isoformat(),
                    "archaeological_metadata": archaeological_metadata or {}
                }
                
                # Upload status iniziale tramite storage service
                object_name = f"{site_id}/tiles/{photo_id}/processing_status.json"
                await self.storage.upload_json(
                    bucket=self.storage.buckets['tiles'],
                    object_name=object_name,
                    data=status
                )
                
                logger.success(
                    "Deep zoom processing status created",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "object_name": object_name,
                        "tile_size": self.tile_size
                    }
                )
                return status
                
            except Exception as e:
                logger.error(
                    "Failed to create processing status",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                raise

    @logger.catch(
        reraise=True,
        message="Failed to schedule background tiles generation for {photo_id}",
        level="ERROR"
    )
    def schedule_tiles_generation_background(
        self,
        background_tasks: BackgroundTasks,
        photo_id: str,
        original_file_content: bytes,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Programma generazione tiles in background con FastAPI BackgroundTasks
        
        Args:
            background_tasks: FastAPI BackgroundTasks
            photo_id: ID della foto
            original_file_content: Contenuto del file originale
            site_id: ID del sito archeologico
            archaeological_metadata: Metadati archeologici
            
        Returns:
            Dict con informazioni di scheduling
        """
        with logger.contextualize(
            operation="schedule_tiles_generation_background",
            photo_id=photo_id,
            site_id=site_id,
            file_size=len(original_file_content),
            has_metadata=archaeological_metadata is not None
        ):
            # Aggiungi task in background
            background_tasks.add_task(
                self._process_tiles_background,
                photo_id,
                original_file_content,
                site_id,
                archaeological_metadata
            )
            
            scheduled_at = datetime.now().isoformat()
            logger.info(
                "Deep zoom tiles generation scheduled in background",
                extra={
                    "photo_id": photo_id,
                    "site_id": site_id,
                    "file_size": len(original_file_content),
                    "scheduled_at": scheduled_at,
                    "tile_size": self.tile_size
                }
            )
            
            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'status': DeepZoomStatus.SCHEDULED.value,
                'message': 'Deep zoom tiles generation scheduled in background',
                'scheduled_at': scheduled_at
            }

    @logger.catch(
        reraise=True,
        message="Failed to schedule async tiles generation for {photo_id}",
        level="ERROR"
    )
    async def schedule_tiles_generation_async(
        self,
        photo_id: str,
        original_file_content: bytes,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        FIXED: Programma generazione tiles in background con asyncio.create_task
        per vero processing asincrono non bloccante
        
        Args:
            photo_id: ID della foto
            original_file_content: Contenuto del file originale
            site_id: ID del sito archeologico
            archaeological_metadata: Metadati archeologici
            
        Returns:
            Dict con informazioni di scheduling
        """
        with logger.contextualize(
            operation="schedule_tiles_generation_async",
            photo_id=photo_id,
            site_id=site_id,
            file_size=len(original_file_content),
            has_metadata=archaeological_metadata is not None
        ):
            # FIXED: Usa asyncio.create_task per esecuzione veramente asincrona
            asyncio.create_task(
                self._process_tiles_background(
                    photo_id,
                    original_file_content,
                    site_id,
                    archaeological_metadata
                )
            )
            
            scheduled_at = datetime.now().isoformat()
            logger.success(
                "Deep zoom tiles generation scheduled asynchronously",
                extra={
                    "photo_id": photo_id,
                    "site_id": site_id,
                    "file_size": len(original_file_content),
                    "scheduled_at": scheduled_at,
                    "tile_size": self.tile_size
                }
            )
            
            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'status': DeepZoomStatus.SCHEDULED.value,
                'message': 'Deep zoom tiles generation scheduled asynchronously',
                'scheduled_at': scheduled_at
            }

    @logger.catch(
        reraise=True,
        message="Batch tiles processing failed for site {site_id}",
        level="ERROR"
    )
    async def process_tiles_batch_sequential(
        self,
        photos_list: List[Dict[str, Any]],
        site_id: str
    ):
        """
        Processa un batch di foto SEQUENZIALMENTE (una alla volta)
        DOPO che tutti gli upload sono completati
        Invia notifiche WebSocket per ogni foto completata
        
        Args:
            photos_list: Lista di dict con photo_id, file_path, archaeological_metadata
            site_id: ID del sito archeologico
        """
        with logger.contextualize(
            operation="process_tiles_batch_sequential",
            site_id=site_id,
            total_photos=len(photos_list)
        ):
            total_photos = len(photos_list)
            
            logger.info(
                "Batch processing started",
                extra={
                    "site_id": site_id,
                    "total_photos": total_photos,
                    "processing_mode": "sequential"
                }
            )
            
            # Import notification manager
            try:
                from app.routes.api.notifications_ws import notification_manager
                has_websocket = True
                logger.debug("WebSocket notifications enabled")
            except ImportError:
                has_websocket = False
                logger.warning("WebSocket notifications not available")
            
            completed_count = 0
            failed_count = 0
            
            for idx, photo_info in enumerate(photos_list, 1):
                photo_id = photo_info['photo_id']
                file_path = photo_info['file_path']
                archaeological_metadata = photo_info.get('archaeological_metadata', {})
                width = photo_info.get('width', 0)
                height = photo_info.get('height', 0)
                
                # Estrai filename dall'ultimo segmento del file_path
                filename = file_path.split('/')[-1] if '/' in file_path else file_path
                
                with logger.contextualize(
                    photo_id=photo_id,
                    filename=filename,
                    batch_position=f"{idx}/{total_photos}",
                    dimensions=f"{width}x{height}"
                ):
                    try:
                        logger.info(
                            "Processing tiles for photo",
                            extra={
                                "photo_id": photo_id,
                                "filename": filename,
                                "width": width,
                                "height": height,
                                "batch_progress": f"{idx}/{total_photos}"
                            }
                        )
                        
                        # Invia notifica inizio processing
                        if has_websocket:
                            await notification_manager.broadcast_tiles_progress(
                                site_id=site_id,
                                photo_id=photo_id,
                                status=DeepZoomStatus.PROCESSING.value,
                                progress=0,
                                photo_filename=filename,
                                current_photo=idx,
                                total_photos=total_photos
                            )
                        
                        # Carica file da MinIO usando storage service
                        original_file_content = await self.storage.get_file(
                            bucket=self.storage.buckets['photos'],
                            object_name=file_path.split('/')[-1]  # Estrai filename dal path
                        )
                        
                        # Processa tiles per questa foto
                        await self._process_tiles_background(
                            photo_id,
                            original_file_content,
                            site_id,
                            archaeological_metadata
                        )
                        
                        completed_count += 1
                        logger.success(
                            "Tiles processing completed for photo",
                            extra={
                                "photo_id": photo_id,
                                "completed_count": completed_count,
                                "total_photos": total_photos,
                                "success_rate": f"{(completed_count/idx)*100:.1f}%"
                            }
                        )
                        
                        # Ottieni info finali sui tiles
                        tile_info = await self.get_deep_zoom_info(site_id, photo_id)
                        tile_count = tile_info.get('total_tiles', 0) if tile_info else 0
                        levels = tile_info.get('levels', 0) if tile_info else 0
                        
                        # Invia notifica completamento
                        if has_websocket:
                            await notification_manager.broadcast_tiles_progress(
                                site_id=site_id,
                                photo_id=photo_id,
                                status=DeepZoomStatus.COMPLETED.value,
                                progress=100,
                                photo_filename=filename,
                                tile_count=tile_count,
                                levels=levels,
                                current_photo=idx,
                                total_photos=total_photos
                            )
                        
                    except Exception as e:
                        failed_count += 1
                        logger.error(
                            "Tiles processing failed for photo",
                            extra={
                                "photo_id": photo_id,
                                "filename": filename,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "failed_count": failed_count,
                                "batch_progress": f"{idx}/{total_photos}"
                            }
                        )
                        
                        # Update database with failed status
                        await self._update_photo_database_status(photo_id, DeepZoomStatus.FAILED.value)
                        await self._update_processing_status(
                            photo_id, site_id, DeepZoomStatus.FAILED.value, 0, error=str(e)
                        )
                        
                        # Invia notifica errore
                        if has_websocket:
                            await notification_manager.broadcast_tiles_progress(
                                site_id=site_id,
                                photo_id=photo_id,
                                status=DeepZoomStatus.FAILED.value,
                                progress=0,
                                photo_filename=filename,
                                current_photo=idx,
                                total_photos=total_photos,
                                error=str(e)
                            )
            
            logger.info(
                "Batch processing completed",
                extra={
                    "site_id": site_id,
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "total_photos": total_photos,
                    "success_rate": f"{(completed_count/total_photos)*100:.1f}%",
                    "processing_mode": "sequential"
                }
            )

    async def _schedule_and_process_tiles(
        self,
        photo_id: str,
        site_id: str,
        file_path: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        NUOVO METODO: Carica il file da MinIO in background e processa tiles
        Questo evita di bloccare l'upload principale
        """
        try:
            logger.info(f"🔄 Background task started: Loading file from MinIO for photo {photo_id}")
            
            # Carica file da MinIO in background usando storage service
            original_file_content = await self.storage.get_file(
                bucket=self.storage.buckets['photos'],
                object_name=file_path.split('/')[-1]  # Estrai filename dal path
            )
            
            logger.info(f"✅ File loaded from MinIO, starting tiles generation for photo {photo_id}")
            
            # Processa tiles
            await self._process_tiles_background(
                photo_id,
                original_file_content,
                site_id,
                archaeological_metadata
            )
            
        except Exception as e:
            logger.error(f"❌ Background file loading failed for photo {photo_id}: {e}")
            await self._update_photo_database_status(photo_id, DeepZoomStatus.FAILED.value)
            await self._update_processing_status(
                photo_id, site_id, DeepZoomStatus.FAILED.value, 0, error=f"File loading failed: {str(e)}"
            )

    @logger.catch(
        reraise=True,
        message="Background tiles processing failed for photo {photo_id}",
        level="ERROR"
    )
    async def _process_tiles_background(
        self,
        photo_id: str,
        original_file_content: bytes,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Processa tiles in background senza bloccare l'upload principale
        """
        with logger.contextualize(
            operation="_process_tiles_background",
            photo_id=photo_id,
            site_id=site_id,
            file_size=len(original_file_content),
            has_metadata=archaeological_metadata is not None
        ):
            try:
                logger.info(
                    "Starting background tiles generation",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "file_size": len(original_file_content),
                        "tile_size": self.tile_size
                    }
                )
                
                # 1. Update database status to "processing"
                await self._update_photo_database_status(photo_id, DeepZoomStatus.PROCESSING.value)
                
                # 2. Aggiorna status a "processing"
                await self._update_processing_status(photo_id, site_id, DeepZoomStatus.PROCESSING.value, 0)
                
                # 2. Genera tiles in memoria
                tiles_data, original_width, original_height = await self._generate_tiles_from_bytes(
                    original_file_content, photo_id, site_id
                )
                
                total_tiles = self._count_total_tiles(tiles_data)
                levels_count = len(tiles_data)
                
                logger.info(
                    "Tiles generated in memory",
                    extra={
                        "photo_id": photo_id,
                        "total_tiles": total_tiles,
                        "levels": levels_count,
                        "dimensions": f"{original_width}x{original_height}",
                        "format": self.format
                    }
                )
                
                await self._update_processing_status(photo_id, site_id, DeepZoomStatus.UPLOADING.value, 10, total_tiles, levels_count)
                
                # 3. Upload tiles con progress tracking
                completed_tiles = 0
                upload_tasks = []
                
                for level, tiles_level in tiles_data.items():
                    for tile_coords, tile_data in tiles_level.items():
                        # Usa estensione dinamica basata sul formato
                        extension = 'png' if self.format == 'png' else 'jpg'
                        object_name = f"{site_id}/tiles/{photo_id}/{level}/{tile_coords}.{extension}"

                        # Metadati archeologici
                        tile_metadata = {
                            'photo_id': photo_id,
                            'site_id': site_id,
                            'level': level,
                            'tile_coords': tile_coords,
                            'tile_size': self.tile_size,
                            'format': self.format
                        }

                        if archaeological_metadata:
                            tile_metadata.update({
                                'inventory_number': archaeological_metadata.get('inventory_number'),
                                'excavation_area': archaeological_metadata.get('excavation_area'),
                                'material': archaeological_metadata.get('material')
                            })

                        task = self._upload_single_tile_with_metadata(
                            object_name, tile_data, tile_metadata
                        )
                        upload_tasks.append(task)
                
                # Upload tiles con progress tracking ogni 10 tiles
                batch_size = 10
                successful_uploads = []
                failed_uploads = []
                
                for i in range(0, len(upload_tasks), batch_size):
                    batch = upload_tasks[i:i + batch_size]
                    batch_results = await asyncio.gather(*batch, return_exceptions=True)
                    
                    # Processa risultati batch
                    for result in batch_results:
                        if result is not None and not isinstance(result, Exception):
                            successful_uploads.append(result)
                        else:
                            failed_uploads.append(result)
                    
                    completed_tiles += len(batch)
                    progress = 10 + int((completed_tiles / total_tiles) * 80)  # 10-90%
                    
                    await self._update_processing_status(
                        photo_id, site_id, DeepZoomStatus.UPLOADING.value, progress, total_tiles, levels_count, completed_tiles
                    )
                    
                    if completed_tiles % 50 == 0:  # Log every 50 tiles to reduce noise
                        logger.info(
                            "Tiles upload progress",
                            extra={
                                "photo_id": photo_id,
                                "completed_tiles": completed_tiles,
                                "total_tiles": total_tiles,
                                "progress_percent": f"{progress}%",
                                "successful_uploads": len(successful_uploads),
                                "failed_uploads": len(failed_uploads)
                            }
                        )
                
                if failed_uploads:
                    logger.warning(
                        "Some tile uploads failed",
                        extra={
                            "photo_id": photo_id,
                            "failed_count": len(failed_uploads),
                            "successful_count": len(successful_uploads),
                            "failure_rate": f"{(len(failed_uploads)/len(upload_tasks))*100:.1f}%"
                        }
                    )

                # 4. Crea metadata finale
                await self._update_processing_status(photo_id, site_id, DeepZoomStatus.FINALIZING.value, 90)
                
                metadata_url = await self._create_and_upload_metadata(
                    photo_id, site_id, tiles_data, archaeological_metadata, original_width, original_height
                )
                
                # 5. Completa con successo
                final_status = {
                    "photo_id": photo_id,
                    "site_id": site_id,
                    "status": DeepZoomStatus.COMPLETED.value,
                    "progress": 100,
                    "total_tiles": total_tiles,
                    "completed_tiles": len(successful_uploads),
                    "failed_tiles": len(failed_uploads),
                    "levels": len(tiles_data),
                    "tile_size": self.tile_size,
                    "tile_format": self.format,
                    "width": original_width,
                    "height": original_height,
                    "metadata_url": metadata_url,
                    "started": datetime.now().isoformat(),
                    "completed": datetime.now().isoformat(),
                    "archaeological_metadata": archaeological_metadata or {}
                }
                
                await self._update_processing_status_full(photo_id, site_id, final_status)
                
                # Update database with completion status
                await self._update_photo_database_status(
                    photo_id,
                    DeepZoomStatus.COMPLETED.value,
                    tile_count=len(successful_uploads),
                    levels=len(tiles_data)
                )
                
                logger.success(
                    "Background tiles generation completed successfully",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "successful_uploads": len(successful_uploads),
                        "failed_uploads": len(failed_uploads),
                        "total_tiles": total_tiles,
                        "levels": len(tiles_data),
                        "dimensions": f"{original_width}x{original_height}",
                        "format": self.format,
                        "success_rate": f"{(len(successful_uploads)/total_tiles)*100:.1f}%"
                    }
                )

            except Exception as e:
                logger.error(
                    "Background tiles generation failed",
                    extra={
                        "photo_id": photo_id,
                        "site_id": site_id,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                
                # Update database with failed status
                await self._update_photo_database_status(photo_id, DeepZoomStatus.FAILED.value)
                
                # Aggiorna status a "failed"
                try:
                    await self._update_processing_status(
                        photo_id, site_id, DeepZoomStatus.FAILED.value, 0, error=str(e)
                    )
                except Exception as status_error:
                    logger.error(
                        "Failed to update error status",
                        extra={
                            "photo_id": photo_id,
                            "status_error": str(status_error),
                            "original_error": str(e)
                        }
                    )

    async def process_and_upload_tiles(
        self,
        photo_id: str,
        original_file: UploadFile,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Use bytes-based methods instead.
        Maintained for backward compatibility.
        
        Args:
            original_file: FastAPI UploadFile (deprecated)
        
        Recommendation: Use _process_tiles_background with bytes directly
        """
        logger.warning("process_and_upload_tiles is deprecated. Use bytes-based methods instead.")
        
        try:
            # Read bytes and delegate to bytes-based method
            content = await original_file.read()
            await original_file.seek(0)
            
            # Processa in background (ma asp etta per compatibilità)
            return await self._process_tiles_background(photo_id, content, site_id, archaeological_metadata)
            
        except Exception as e:
            logger.error(f"Deep zoom processing failed for {photo_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Deep zoom processing failed: {str(e)}")

    async def generate_tiles_in_memory(self, original_file: UploadFile) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """
        DEPRECATED: Use generate_tiles_from_bytes() instead.
        Maintained for backward compatibility only.
        
        Args:
            original_file: FastAPI UploadFile (deprecated)
            
        Returns:
            Tuple[Dict[level, Dict[tile_coords, tile_data]], original_width, original_height]
            
        Recommendation: Use generate_tiles_from_bytes(file_data: bytes) instead
        """
        logger.warning("generate_tiles_in_memory is deprecated. Use generate_tiles_from_bytes instead.")
        
        try:
            # Read bytes and delegate to bytes-based method
            content = await original_file.read()
            await original_file.seek(0)  # Reset for other uses
            
            return await self.generate_tiles_from_bytes(content)

        except Exception as e:
            logger.error(f"Tile generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Tile generation failed: {str(e)}")

    async def generate_tiles_from_bytes(self, file_data: bytes) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """
        Generate deep zoom tiles from raw bytes (framework-agnostic).
        
        Args:
            file_data: Raw image bytes
            
        Returns:
            Tuple[Dict[level, Dict[tile_coords, tile_data]], original_width, original_height]
        """
        try:
            # Use BytesIO to work with image bytes
            image = Image.open(io.BytesIO(file_data))

            # FIXED: Gestione formato basata su immagine originale + trasparenza
            original_format = image.format.lower() if image.format else 'jpg'
            original_has_transparency = image.mode in ('RGBA', 'LA') or 'transparency' in image.info
            
            # Determina formato tiles basato su formato originale E trasparenza
            if original_format == 'png' or original_has_transparency:
                # Per PNG originali o immagini con trasparenza, usa PNG
                self.format = 'png'
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                logger.info(f"🖼️ Using PNG format for tiles (original: {original_format}, transparency: {original_has_transparency})")
            else:
                # Per JPEG e altri formati senza trasparenza, usa JPEG per efficienza
                self.format = 'jpg'
                if image.mode == 'RGBA':
                    # Solo se non ha trasparenza reale, converti in RGB con sfondo bianco
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                logger.info(f"📷 Using JPG format for tiles (original: {original_format}, transparency: {original_has_transparency})")

            original_width = image.width
            original_height = image.height

            # Calcola livelli deep zoom (OpenSeadragon convention: level 0 is lowest resolution)
            max_dimension = max(image.size)
            levels = math.ceil(math.log2(max_dimension)) + 1

            tiles_data = {}

            # Genera tiles per ogni livello
            for level in range(levels):
                level_tiles = {}

                # Calcola dimensione per questo livello (level 0 = lowest resolution)
                scale = 2 ** (levels - 1 - level)
                level_width = max(1, image.width // scale)
                level_height = max(1, image.height // scale)

                # Crea immagine ridimensionata per questo livello
                level_image = image.resize((level_width, level_height), Image.Resampling.LANCZOS)

                # Genera tiles per questo livello
                for y in range(0, level_height, self.tile_size):
                    for x in range(0, level_width, self.tile_size):
                        # Estrai tile
                        tile_box = (x, y, min(x + self.tile_size, level_width), min(y + self.tile_size, level_height))
                        tile = level_image.crop(tile_box)

                        # Pad tile to tile_size if smaller, preservando la trasparenza
                        if tile.size[0] < self.tile_size or tile.size[1] < self.tile_size:
                            if original_has_transparency:
                                # Usa sfondo trasparente per PNG
                                padded_tile = Image.new('RGBA', (self.tile_size, self.tile_size), (255, 255, 255, 0))
                                padded_tile.paste(tile, (0, 0), tile if tile.mode == 'RGBA' else None)
                            else:
                                # Usa sfondo bianco per JPEG
                                padded_tile = Image.new('RGB', (self.tile_size, self.tile_size), (255, 255, 255))
                                padded_tile.paste(tile, (0, 0))
                            tile = padded_tile

                        # Converti in bytes con formato appropriato
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

                        # Salva con coordinate
                        tile_coords = f"{x//self.tile_size}_{y//self.tile_size}"
                        level_tiles[tile_coords] = tile_data

                tiles_data[level] = level_tiles
                logger.info(f"Generated {len(level_tiles)} tiles for level {level}")

            return tiles_data, original_width, original_height

        except Exception as e:
            logger.error(f"Tile generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Tile generation failed: {str(e)}")

    async def _upload_single_tile_with_metadata(
        self,
        object_name: str,
        tile_data: bytes,
        metadata: Dict[str, Any]
    ) -> Optional[str]:
        """Upload singolo tile con metadati archeologici"""
        try:
            # Validate tile_data
            if tile_data is None:
                logger.error(f"Tile data is None for {object_name}")
                return None
            
            if not isinstance(tile_data, bytes):
                logger.error(f"Tile data is not bytes for {object_name}: {type(tile_data)}")
                return None

            # Prepare metadata with string conversion for safety
            tile_metadata = {
                'x-amz-meta-photo-id': str(metadata.get('photo_id', '')),
                'x-amz-meta-site-id': str(metadata.get('site_id', '')),
                'x-amz-meta-level': str(metadata.get('level', '')),
                'x-amz-meta-tile-coords': str(metadata.get('tile_coords', '')),
                'x-amz-meta-tile-size': str(metadata.get('tile_size', '')),
                'x-amz-meta-inventory-number': str(metadata.get('inventory_number', '')),
                'x-amz-meta-excavation-area': str(metadata.get('excavation_area', '')),
                'x-amz-meta-material': str(metadata.get('material', ''))
            }

            # Upload usando storage service centralizzato
            result = await self.storage.upload_bytes(
                bucket=self.storage.buckets['tiles'],
                object_name=object_name,
                data=tile_data,
                content_type='image/png' if self.format == 'png' else 'image/jpeg',
                metadata=tile_metadata
            )

            logger.debug(f"Tile uploaded: {object_name}")
            return result

        except Exception as e:
            logger.error(f"Tile upload error {object_name}: {e}")
            return None

    async def _create_and_upload_metadata(
        self,
        photo_id: str,
        site_id: str,
        tiles_data: Dict[int, Dict[str, bytes]],
        archaeological_metadata: Optional[Dict[str, Any]] = None,
        width: int = 0,
        height: int = 0
    ) -> str:
        """Crea e carica metadata.json per i tiles"""

        metadata = {
            "photo_id": photo_id,
            "site_id": site_id,
            "width": width,
            "height": height,
            "levels": len(tiles_data),
            "tile_size": self.tile_size,
            "overlap": self.overlap,
            "format": self.format,
            "tile_format": self.format,  # FIXED: Aggiunto per compatibilità OpenSeadragon
            "total_tiles": self._count_total_tiles(tiles_data),
            "created": datetime.now().isoformat(),
            "archaeological_metadata": archaeological_metadata or {}
        }

        # Aggiungi informazioni per livello
        level_info = {}
        for level, tiles_level in tiles_data.items():
            level_info[level] = {
                "tile_count": len(tiles_level),
                "tiles": list(tiles_level.keys())
            }

        metadata["level_info"] = level_info

        # Upload metadata tramite storage service centralizzato
        metadata_object_name = f"{site_id}/tiles/{photo_id}/metadata.json"

        try:
            result = await self.storage.upload_json(
                bucket=self.storage.buckets['tiles'],
                object_name=metadata_object_name,
                data=metadata
            )

            logger.info(f"Deep zoom metadata uploaded: {metadata_object_name}")
            return result

        except Exception as e:
            logger.error(f"Metadata upload failed: {e}")
            raise HTTPException(status_code=500, detail="Metadata upload failed")

    def _count_total_tiles(self, tiles_data: Dict[int, Dict[str, bytes]]) -> int:
        """Conta totale tiles in tutti i livelli"""
        return sum(len(tiles_level) for tiles_level in tiles_data.values())

    async def get_tile_url(self, site_id: str, photo_id: str, level: int, x: int, y: int) -> Optional[str]:
        """Genera URL presigned per singolo tile usando storage service"""
        tile_coords = f"{x}_{y}"
        # FIXED: Determina il formato dei tiles leggendo i metadati
        try:
            metadata_info = await self.get_deep_zoom_info(site_id, photo_id)
            tile_format = metadata_info.get('tile_format', 'jpg') if metadata_info else 'jpg'
            extension = 'png' if tile_format == 'png' else 'jpg'
            logger.debug(f"🔍 Tile format detection: {tile_format} → .{extension} for photo {photo_id}")
        except Exception as e:
            logger.warning(f"⚠️ Could not determine tile format for {photo_id}: {e}, using JPG fallback")
            extension = 'jpg'  # fallback
            
        object_name = f"{site_id}/tiles/{photo_id}/{level}/{tile_coords}.{extension}"

        try:
            # Usa storage service per generare URL presigned
            from datetime import timedelta
            url = await self.storage._generate_presigned_url(
                bucket_name=self.storage.buckets['tiles'],
                object_name=object_name,
                expires_hours=24,
                operation_name=f"tile URL generation for {photo_id}"
            )
            
            if url is None:
                # Prova l'altro formato se il primo non esiste
                alternative_extension = 'png' if extension == 'jpg' else 'jpg'
                alternative_object_name = f"{site_id}/tiles/{photo_id}/{level}/{tile_coords}.{alternative_extension}"
                
                alternative_url = await self.storage._generate_presigned_url(
                    bucket_name=self.storage.buckets['tiles'],
                    object_name=alternative_object_name,
                    expires_hours=24,
                    operation_name=f"alternative tile URL generation for {photo_id}"
                )
                
                if alternative_url is not None:
                    logger.info(f"✅ Found tile with alternative format: .{alternative_extension} for photo {photo_id}")
                    return alternative_url
                else:
                    logger.error(f"❌ Tile not found in both formats (.{extension} and .{alternative_extension}) for photo {photo_id}")
                    return None
            else:
                logger.debug(f"Generated tile URL: {object_name}")
                return url
            
        except Exception as e:
            logger.error(f"Error generating tile URL for {object_name}: {e}")
            return None

    async def get_tile_content(self, site_id: str, photo_id: str, level: int, x: int, y: int) -> Optional[bytes]:
        """
        Ottieni contenuto diretto del tile invece di URL presigned.
        OTTIMIZZATO PER PERFORMANCE: Rimosso ogni controllo di metadati o listing file.
        Tenta direttamente il recupero del file supportando JPG e PNG.
        """
        tile_coords = f"{x}_{y}"
        
        # Performance optimization: Don't excessively context log every single tile hit
        # Only log on error or if specifically debugging
        
        try:
            # Import locale per evitare circular import
            storage_service = self.storage
            import asyncio
            from minio.error import S3Error

            # Standard extensions to try
            # Optimization: could cache format per photo_id in a LRU cache if needed
            extensions_to_try = ['jpg', 'png']
            
            for extension in extensions_to_try:
                object_name = f"{site_id}/tiles/{photo_id}/{level}/{tile_coords}.{extension}"
                
                try:
                    # Direct MinIO access via thread pool for async compatibility
                    tile_data = await asyncio.to_thread(
                        storage_service._client.get_object,
                        bucket_name=storage_service.buckets['tiles'],
                        object_name=object_name
                    )
                    
                    try:
                        content = tile_data.read()
                        return content
                    finally:
                        tile_data.close()
                        tile_data.release_conn()

                except S3Error as e:
                    if e.code == 'NoSuchKey':
                        # Normal case if format doesn't match or tile missing
                        continue
                    else:
                        logger.warning(f"MinIO error retrieving tile {object_name}: {e}")
                        continue
                except Exception as e:
                    logger.warning(f"Error retrieving tile {object_name}: {e}")
                    continue

            # If we reach here, tile was not found in any format
            # Log only as debug to avoid flooding logs during zooming on missing areas
            logger.debug(f"Tile {tile_coords} at level {level} not found for photo {photo_id}")
            return None
            
        except Exception as e:
            logger.error(f"Critical error in get_tile_content for {photo_id}: {e}")
            return None

    async def get_deep_zoom_info(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni informazioni deep zoom per una foto"""
        try:
            # Scarica metadata dal bucket tiles usando storage service
            metadata_path = f"{site_id}/tiles/{photo_id}/metadata.json"

            # FIXED: Try direct MinIO access first to avoid path parsing issues
            try:
                # Import locale per evitare circular import
                # Use self.storage instead of direct import to avoid circular imports
                storage_service = self.storage
                import asyncio
                from minio.error import S3Error
                
                def _download_metadata():
                    return storage_service._client.get_object(
                        bucket_name=storage_service.buckets['tiles'],
                        object_name=metadata_path
                    )
                
                response = await asyncio.to_thread(_download_metadata)
                metadata_content = response.read()
                response.close()
                response.release_conn()
                
                logger.info(f"✅ Successfully retrieved metadata.json for photo {photo_id} via direct MinIO access")
                
            except S3Error as e:
                if e.code == 'NoSuchKey':
                    logger.info(f"Deep zoom metadata not accessible for photo {photo_id}: File non trovato: {metadata_path}")
                    
                    # NUOVO: Verifica se le tiles esistono anche senza metadata.json
                    tiles_exist = await self._check_tiles_existence(site_id, photo_id)
                    if tiles_exist:
                        logger.info(f"✅ Tiles found for photo {photo_id} but metadata.json missing - reconstructing info")
                        return await self._reconstruct_tiles_info(site_id, photo_id, tiles_exist)
                else:
                    logger.error(f"MinIO error accessing metadata for photo {photo_id}: {e}")
                    raise
            except Exception as e:
                logger.info(f"Deep zoom metadata not accessible for photo {photo_id}: {metadata_path} - {e}")
                
                # NUOVO: Verifica se le tiles esistono anche senza metadata.json
                tiles_exist = await self._check_tiles_existence(site_id, photo_id)
                if tiles_exist:
                    logger.info(f"✅ Tiles found for photo {photo_id} but metadata.json missing - reconstructing info")
                    return await self._reconstruct_tiles_info(site_id, photo_id, tiles_exist)
                
                # Try to check if there's a processing status instead
                try:
                    processing_status = await self.get_processing_status(site_id, photo_id)
                    if processing_status:
                        return {
                            'photo_id': photo_id,
                            'site_id': site_id,
                            'available': False,
                            'status': processing_status.get('status', 'unknown'),
                            'progress': processing_status.get('progress', 0),
                            'message': f"Deep zoom processing in progress: {processing_status.get('status', 'unknown')}",
                            'width': 0,
                            'height': 0,
                            'levels': 0,
                            'tile_size': self.tile_size,
                            'total_tiles': 0,
                            'processing_status': processing_status
                        }
                except Exception:
                    pass  # Ignore processing status check failures
                
                return {
                    'photo_id': photo_id,
                    'site_id': site_id,
                    'available': False,
                    'status': 'not_found',
                    'message': 'Deep zoom tiles not generated for this photo',
                    'width': 0,
                    'height': 0,
                    'levels': 0,
                    'tile_size': self.tile_size,
                    'total_tiles': 0
                }

            if isinstance(metadata_content, str) and metadata_content.startswith("Error"):
                logger.info(f"Deep zoom metadata error for photo {photo_id}: {metadata_content}")
                return {
                    'photo_id': photo_id,
                    'site_id': site_id,
                    'available': False,
                    'status': 'error',
                    'message': f"Deep zoom metadata error: {metadata_content}",
                    'width': 0,
                    'height': 0,
                    'levels': 0,
                    'tile_size': self.tile_size,
                    'total_tiles': 0
                }

            # Parse metadata JSON
            if isinstance(metadata_content, bytes):
                metadata_content = metadata_content.decode('utf-8')
            
            try:
                metadata = json.loads(metadata_content)
            except json.JSONDecodeError as e:
                logger.warning(f"Deep zoom metadata corrupted for photo {photo_id}: {e}")
                return {
                    'photo_id': photo_id,
                    'site_id': site_id,
                    'available': False,
                    'status': 'corrupted',
                    'message': f"Deep zoom metadata corrupted: {str(e)}",
                    'width': 0,
                    'height': 0,
                    'levels': 0,
                    'tile_size': self.tile_size,
                    'total_tiles': 0
                }

            # Validate essential fields
            if not all(key in metadata for key in ['width', 'height', 'levels', 'total_tiles']):
                logger.warning(f"Deep zoom metadata incomplete for photo {photo_id}")
                return {
                    'photo_id': photo_id,
                    'site_id': site_id,
                    'available': False,
                    'status': 'incomplete',
                    'message': 'Deep zoom metadata incomplete',
                    'width': metadata.get('width', 0),
                    'height': metadata.get('height', 0),
                    'levels': metadata.get('levels', 0),
                    'tile_size': metadata.get('tile_size', self.tile_size),
                    'total_tiles': metadata.get('total_tiles', 0),
                    'metadata_preview': metadata
                }
                
            if metadata.get('levels', 0) <= 0 or metadata.get('total_tiles', 0) <= 0:
                logger.warning(f"Deep zoom has no valid tiles for photo {photo_id}")
                return {
                    'photo_id': photo_id,
                    'site_id': site_id,
                    'available': False,
                    'status': 'invalid',
                    'message': 'Deep zoom has no valid tiles',
                    'width': metadata.get('width', 0),
                    'height': metadata.get('height', 0),
                    'levels': metadata.get('levels', 0),
                    'tile_size': metadata.get('tile_size', self.tile_size),
                    'total_tiles': metadata.get('total_tiles', 0)
                }

            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'width': metadata.get('width', 0),
                'height': metadata.get('height', 0),
                'levels': metadata.get('levels', 0),
                'tile_size': metadata.get('tile_size', self.tile_size),
                'overlap': metadata.get('overlap', self.overlap),
                'total_tiles': metadata.get('total_tiles', 0),
                'tile_format': metadata.get('format', self.format),
                'available': True,
                'metadata_url': f"minio://{self.storage.buckets['tiles']}/{metadata_path}",
                'created': metadata.get('created')
            }

        except HTTPException:
            # HTTPException indica che il file non esiste (404)
            logger.info(f"Deep zoom tiles not available for photo {photo_id} - file not found")
            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'available': False,
                'status': 'not_found',
                'message': 'Deep zoom tiles not available - file not found',
                'width': 0,
                'height': 0,
                'levels': 0,
                'tile_size': self.tile_size,
                'total_tiles': 0
            }
        except Exception as e:
            logger.warning(f"Deep zoom info unavailable for photo {photo_id}: {e}")
            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'available': False,
                'status': 'error',
                'message': f"Deep zoom info unavailable: {str(e)}",
                'width': 0,
                'height': 0,
                'levels': 0,
                'tile_size': self.tile_size,
                'total_tiles': 0
            }

    async def _generate_tiles_from_bytes(self, content: bytes, photo_id: str, site_id: str) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """
        Genera tiles deep zoom da bytes in memoria
        """
        try:
            # Usa BytesIO invece di UploadFile
            image = Image.open(io.BytesIO(content))
            
            # FIXED: Gestione formato basata su immagine originale + trasparenza
            original_format = image.format.lower() if image.format else 'jpg'
            original_has_transparency = image.mode in ('RGBA', 'LA') or 'transparency' in image.info
            
            # Determina formato tiles basato su formato originale E trasparenza
            if original_format == 'png' or original_has_transparency:
                # Per PNG originali o immagini con trasparenza, usa PNG
                self.format = 'png'
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                logger.info(f"🖼️ Using PNG format for tiles (original: {original_format}, transparency: {original_has_transparency})")
            else:
                # Per JPEG e altri formati senza trasparenza, usa JPEG per efficienza
                self.format = 'jpg'
                if image.mode == 'RGBA':
                    # Solo se non ha trasparenza reale, converti in RGB con sfondo bianco
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                logger.info(f"📷 Using JPG format for tiles (original: {original_format}, transparency: {original_has_transparency})")

            original_width = image.width
            original_height = image.height

            # Calcola livelli deep zoom (OpenSeadragon convention: level 0 is lowest resolution)
            max_dimension = max(image.size)
            levels = math.ceil(math.log2(max_dimension)) + 1

            tiles_data = {}

            # Genera tiles per ogni livello
            for level in range(levels):
                level_tiles = {}

                # Calcola dimensione per questo livello (level 0 = lowest resolution)
                scale = 2 ** (levels - 1 - level)
                level_width = max(1, image.width // scale)
                level_height = max(1, image.height // scale)

                # Crea immagine ridimensionata per questo livello
                level_image = image.resize((level_width, level_height), Image.Resampling.LANCZOS)

                # Genera tiles per questo livello
                for y in range(0, level_height, self.tile_size):
                    for x in range(0, level_width, self.tile_size):
                        # Estrai tile
                        tile_box = (x, y, min(x + self.tile_size, level_width), min(y + self.tile_size, level_height))
                        tile = level_image.crop(tile_box)

                        # Pad tile to tile_size if smaller, preservando la trasparenza
                        if tile.size[0] < self.tile_size or tile.size[1] < self.tile_size:
                            if original_has_transparency:
                                # Usa sfondo trasparente per PNG
                                padded_tile = Image.new('RGBA', (self.tile_size, self.tile_size), (255, 255, 255, 0))
                                padded_tile.paste(tile, (0, 0), tile if tile.mode == 'RGBA' else None)
                            else:
                                # Usa sfondo bianco per JPEG
                                padded_tile = Image.new('RGB', (self.tile_size, self.tile_size), (255, 255, 255))
                                padded_tile.paste(tile, (0, 0))
                            tile = padded_tile

                        # Converti in bytes con formato appropriato
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

                        # Salva con coordinate
                        tile_coords = f"{x//self.tile_size}_{y//self.tile_size}"
                        level_tiles[tile_coords] = tile_data

                tiles_data[level] = level_tiles
                logger.info(f"Generated {len(level_tiles)} tiles for level {level}")

            return tiles_data, original_width, original_height

        except Exception as e:
            logger.error(f"Tile generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Tile generation failed: {str(e)}")

    async def _update_processing_status(
        self,
        photo_id: str,
        site_id: str,
        status: str,
        progress: int,
        total_tiles: int = 0,
        levels: int = 0,
        completed_tiles: int = 0,
        error: str = None
    ):
        """Aggiorna status di processing"""
        try:
            status_data = {
                "photo_id": photo_id,
                "site_id": site_id,
                "status": status,
                "progress": progress,
                "total_tiles": total_tiles,
                "completed_tiles": completed_tiles,
                "levels": levels,
                "tile_size": self.tile_size,
                "updated": datetime.now().isoformat()
            }
            
            if error:
                status_data["error"] = error
                
            status_object_name = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
            await self.storage.upload_json(
                bucket=self.storage.buckets['tiles'],
                object_name=status_object_name,
                data=status_data
            )
            
        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")
            
    async def _update_processing_status_full(
        self,
        photo_id: str,
        site_id: str,
        full_status: Dict[str, Any]
    ):
        """Aggiorna status completo"""
        try:
            status_object_name = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
            await self.storage.upload_json(
                bucket=self.storage.buckets['tiles'],
                object_name=status_object_name,
                data=full_status
            )
            
        except Exception as e:
            logger.error(f"Failed to update full processing status: {e}")

    async def get_processing_status(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni status di processing per una foto"""
        try:
            status_path = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
            # Ottieni contenuto usando storage service
            try:
                status_content = await self.storage.get_file(
                    bucket=self.storage.buckets['tiles'],
                    object_name=status_path
                )
            except Exception as e:
                logger.info(f"Processing status not found for photo {photo_id}: File non trovato: {status_path}")
                return None
                
            if isinstance(status_content, bytes):
                status_content = status_content.decode('utf-8')
                
            return json.loads(status_content)
            
        except Exception as e:
            logger.warning(f"Failed to get processing status for photo {photo_id}: {e}")
            return None

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
            from app.database.session import get_async_session
            from app.models import Photo
            from sqlalchemy import select
            from datetime import datetime
            import uuid
            
            # Use proper async session handling
            # Import from centralized database engine
            from app.database.engine import AsyncSessionLocal as async_session_maker
            
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
                    # Get photo record using proper UUID
                    photo_query = select(Photo).where(Photo.id == photo_uuid)
                    result = await db.execute(photo_query)
                    photo = result.scalar_one_or_none()
                    
                    if photo:
                        # Update status
                        photo.deepzoom_status = status
                        
                        if status == DeepZoomStatus.COMPLETED.value:
                            photo.has_deep_zoom = True
                            photo.deep_zoom_processed_at = datetime.now()
                            if tile_count is not None:
                                photo.tile_count = tile_count
                            if levels is not None:
                                photo.max_zoom_level = levels
                        elif status in [DeepZoomStatus.FAILED.value, DeepZoomStatus.ERROR.value]:
                            photo.has_deep_zoom = False
                            photo.deep_zoom_processed_at = datetime.now()
                        elif status == DeepZoomStatus.PROCESSING.value:
                            # Set processing status
                            photo.deepzoom_status = DeepZoomStatus.PROCESSING.value
                        
                        await db.commit()
                        logger.info(f"Updated photo {photo_id} deep zoom status to: {status}")
                    else:
                        logger.warning(f"Photo {photo_id} not found for status update")
                except Exception as e:
                    logger.error(f"Database error in status update: {e}")
                    await db.rollback()
                    
        except Exception as e:
            logger.error(f"Failed to update photo database status for {photo_id}: {e}")

    async def _check_tiles_existence(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """
        Verifica se le tiles esistono fisicamente in MinIO anche senza metadata.json
        Returns dict with tiles info if found, None if not found
        """
        try:
            import asyncio
            from minio.error import S3Error
            
            # Import locale per evitare circular import
            # Use self.storage instead of direct import to avoid circular imports
            storage_service = self.storage
            
            # Cerca tiles nei formati jpg e png
            formats_to_check = ['jpg', 'png']
            found_tiles = {}
            max_level_found = -1
            total_tiles = 0
            
            for format_ext in formats_to_check:
                # Lista gli oggetti nel percorso delle tiles per questo formato
                prefix = f"{site_id}/tiles/{photo_id}/"
                
                try:
                    # Usa asyncio.to_thread per operazioni sincrone MinIO
                    objects = await asyncio.to_thread(
                        storage_service._client.list_objects,
                        bucket_name=storage_service.buckets['tiles'],
                        prefix=prefix,
                        recursive=True
                    )
                    
                    # Filtra solo i file tile con questo formato
                    tile_objects = [
                        obj for obj in objects
                        if obj.object_name.endswith(f'.{format_ext}') and
                        '/' in obj.object_name.replace(prefix, '') and
                        len(obj.object_name.replace(prefix, '').split('/')) == 2  # level/tile_coords.format
                    ]
                    
                    if tile_objects:
                        logger.info(f"Found {len(tile_objects)} tiles with format .{format_ext} for photo {photo_id}")
                        
                        # Analizza i tile per determinare livelli e totale
                        for obj in tile_objects:
                            # Estrai livello e coordinate dal path: site_id/tiles/photo_id/level/x_y.format
                            path_parts = obj.object_name.replace(prefix, '').split('/')
                            if len(path_parts) == 2:
                                level_str, tile_coords = path_parts
                                try:
                                    level = int(level_str)
                                    max_level_found = max(max_level_found, level)
                                    
                                    if level not in found_tiles:
                                        found_tiles[level] = []
                                    found_tiles[level].append(tile_coords)
                                    total_tiles += 1
                                except ValueError:
                                    continue
                        
                        # Se abbiamo trovato tiles in questo formato, fermati
                        if found_tiles:
                            break
                            
                except S3Error as e:
                    logger.debug(f"No tiles found with format .{format_ext} for photo {photo_id}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error checking tiles format .{format_ext} for photo {photo_id}: {e}")
                    continue
            
            if found_tiles and max_level_found >= 0:
                # Determina il formato rilevato
                # Fix: tile_objects might not be defined in this scope
                # Use a safe default if tile_objects is not available
                detected_format = 'png' if 'tile_objects' in locals() and any(obj.object_name.endswith('.png') for obj in tile_objects) else 'jpg'
                
                return {
                    'found_tiles': found_tiles,
                    'max_level': max_level_found,
                    'total_tiles': total_tiles,
                    'format': detected_format,
                    'tile_size': self.tile_size  # Default tile size
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking tiles existence for photo {photo_id}: {e}")
            return None

    async def _reconstruct_tiles_info(self, site_id: str, photo_id: str, tiles_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ricostruisce le informazioni delle tiles basandosi sull'analisi dei file esistenti
        """
        try:
            # Calcola il numero di livelli (max_level + 1 perché i livelli partono da 0)
            levels = tiles_data['max_level'] + 1
            
            # Crea informazioni per ogni livello
            level_info = {}
            for level, tiles_list in tiles_data['found_tiles'].items():
                level_info[level] = {
                    "tile_count": len(tiles_list),
                    "tiles": tiles_list
                }
            
            # Tenta di ottenere dimensioni originali dal database
            width, height = 0, 0
            try:
                # Import locali per evitare circular import
                from app.database.engine import AsyncSessionLocal as async_session_maker
                from app.models import Photo
                from sqlalchemy import select
                import uuid
                
                # Convert string photo_id to UUID if needed
                if isinstance(photo_id, str):
                    try:
                        photo_uuid = uuid.UUID(photo_id)
                    except ValueError:
                        photo_uuid = photo_id
                else:
                    photo_uuid = photo_id
                
                async with async_session_maker() as db:
                    photo_query = select(Photo).where(Photo.id == photo_uuid)
                    result = await db.execute(photo_query)
                    photo = result.scalar_one_or_none()
                    
                    if photo:
                        width = photo.width or 0
                        height = photo.height or 0
                        
            except Exception as e:
                logger.warning(f"Could not get photo dimensions from database for {photo_id}: {e}")
            
            # Se non abbiamo dimensioni, prova a stimarle dal livello più alto
            if width == 0 or height == 0:
                # Stima dimensioni basandosi sul numero di tiles al livello più alto
                max_level_tiles = tiles_data['found_tiles'].get(tiles_data['max_level'], [])
                if max_level_tiles:
                    # Analizza le coordinate per stimare dimensioni
                    max_x = max_y = 0
                    for tile_coord in max_level_tiles:
                        try:
                            x, y = map(int, tile_coord.replace('.jpg', '').replace('.png', '').split('_'))
                            max_x = max(max_x, x)
                            max_y = max(max_y, y)
                        except:
                            continue
                    
                    # Aggiungi 1 perché le coordinate partono da 0
                    estimated_width = (max_x + 1) * tiles_data['tile_size']
                    estimated_height = (max_y + 1) * tiles_data['tile_size']
                    
                    # Scala per il livello massimo (2^max_level)
                    width = estimated_width * (2 ** tiles_data['max_level'])
                    height = estimated_height * (2 ** tiles_data['max_level'])
                    
                    logger.info(f"Estimated dimensions for photo {photo_id}: {width}x{height}")
            
            # Crea e salva il metadata.json mancante
            metadata = {
                "photo_id": photo_id,
                "site_id": site_id,
                "width": width,
                "height": height,
                "levels": levels,
                "tile_size": tiles_data['tile_size'],
                "overlap": self.overlap,
                "format": tiles_data['format'],
                "tile_format": tiles_data['format'],
                "total_tiles": tiles_data['total_tiles'],
                "created": datetime.now().isoformat(),
                "reconstructed": True,  # Indica che è stato ricostruito
                "level_info": level_info
            }
            
            # Salva il metadata.json in MinIO
            try:
                metadata_object_name = f"{site_id}/tiles/{photo_id}/metadata.json"
                await self.storage.upload_json(
                    bucket=self.storage.buckets['tiles'],
                    object_name=metadata_object_name,
                    data=metadata
                )
                logger.info(f"✅ Reconstructed and saved metadata.json for photo {photo_id}")
            except Exception as e:
                logger.warning(f"Failed to save reconstructed metadata for photo {photo_id}: {e}")
            
            # Aggiorna anche il database
            try:
                await self._update_photo_database_status(
                    photo_id,
                    DeepZoomStatus.COMPLETED.value,
                    tile_count=tiles_data['total_tiles'],
                    levels=levels
                )
                logger.info(f"✅ Updated database status for photo {photo_id}")
            except Exception as e:
                logger.warning(f"Failed to update database status for photo {photo_id}: {e}")
            
            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'width': width,
                'height': height,
                'levels': levels,
                'tile_size': tiles_data['tile_size'],
                'overlap': self.overlap,
                'total_tiles': tiles_data['total_tiles'],
                'tile_format': tiles_data['format'],
                'available': True,
                'metadata_url': f"minio://{self.storage.buckets['tiles']}/{site_id}/tiles/{photo_id}/metadata.json",
                'created': metadata['created'],
                'reconstructed': True,
                'message': 'Deep zoom tiles info reconstructed from existing files'
            }
            
        except Exception as e:
            logger.error(f"Error reconstructing tiles info for photo {photo_id}: {e}")
            return {
                'photo_id': photo_id,
                'site_id': site_id,
                'available': False,
                'status': 'reconstruction_failed',
                'message': f'Failed to reconstruct tiles info: {str(e)}',
                'width': 0,
                'height': 0,
                'levels': 0,
                'tile_size': self.tile_size,
                'total_tiles': 0
            }


# Istanza globale - verrà aggiornata con dependency injection
deep_zoom_minio_service = None

def get_deep_zoom_minio_service(archaeological_minio_service=None):
    """Factory function per ottenere istanza con dependency injection"""
    global deep_zoom_minio_service
    if deep_zoom_minio_service is None:
        if archaeological_minio_service is None:
            from app.services.archaeological_minio_service import archaeological_minio_service as default_service
            archaeological_minio_service = default_service
        deep_zoom_minio_service = DeepZoomMinIOService(archaeological_minio_service)
    return deep_zoom_minio_service