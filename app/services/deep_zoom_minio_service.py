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

# Import diretto evitato per evitare circular import
# Il servizio archeologico verrà passato come parametro o usato tramite import locale


class DeepZoomMinIOService:
    """Deep zoom ottimizzato per MinIO con supporto archeologico"""

    def __init__(self):
        self.tile_size = 256  # Standard deep zoom tile size
        self.overlap = 0      # Tile overlap for seamless viewing
        self.format = 'jpg'   # Tile format

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
        try:
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            # Crea status metadata iniziale
            status = {
                "photo_id": photo_id,
                "site_id": site_id,
                "status": "processing",
                "progress": 0,
                "total_tiles": 0,
                "completed_tiles": 0,
                "levels": 0,
                "tile_size": self.tile_size,
                "started": datetime.now().isoformat(),
                "archaeological_metadata": archaeological_metadata or {}
            }
            
            # Upload status iniziale
            status_json = json.dumps(status, indent=2, ensure_ascii=False)
            status_bytes = status_json.encode('utf-8')
            
            status_object_name = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
            await asyncio.to_thread(
                archaeological_minio_service.client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=status_object_name,
                data=io.BytesIO(status_bytes),
                length=len(status_bytes),
                content_type='application/json',
                metadata={
                    'x-amz-meta-photo-id': photo_id,
                    'x-amz-meta-site-id': site_id,
                    'x-amz-meta-status': 'processing',
                    'x-amz-meta-created': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Deep zoom processing status created for photo {photo_id}")
            return status
            
        except Exception as e:
            logger.error(f"Failed to create processing status for {photo_id}: {e}")
            raise

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
        
        # Aggiungi task in background
        background_tasks.add_task(
            self._process_tiles_background,
            photo_id,
            original_file_content,
            site_id,
            archaeological_metadata
        )
        
        logger.info(f"Deep zoom tiles generation scheduled in background for photo {photo_id}")
        
        return {
            'photo_id': photo_id,
            'site_id': site_id,
            'status': 'scheduled',
            'message': 'Deep zoom tiles generation scheduled in background',
            'scheduled_at': datetime.now().isoformat()
        }

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
        
        # FIXED: Usa asyncio.create_task per esecuzione veramente asincrona
        asyncio.create_task(
            self._process_tiles_background(
                photo_id,
                original_file_content,
                site_id,
                archaeological_metadata
            )
        )
        
        logger.info(f"✅ Deep zoom tiles generation scheduled asynchronously for photo {photo_id}")
        
        return {
            'photo_id': photo_id,
            'site_id': site_id,
            'status': 'scheduled',
            'message': 'Deep zoom tiles generation scheduled asynchronously',
            'scheduled_at': datetime.now().isoformat()
        }

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
        total_photos = len(photos_list)
        logger.info(f"🚀 BATCH PROCESSING STARTED: {total_photos} foto da processare sequenzialmente")
        
        # Import notification manager
        try:
            from app.routes.api.notifications_ws import notification_manager
            has_websocket = True
        except ImportError:
            logger.warning("Notification manager not available")
            has_websocket = False
        
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
            
            try:
                logger.info(f"🔄 [{idx}/{total_photos}] Processing tiles for photo {photo_id} ({width}x{height})")
                
                # Invia notifica inizio processing
                if has_websocket:
                    await notification_manager.broadcast_tiles_progress(
                        site_id=site_id,
                        photo_id=photo_id,
                        status='processing',
                        progress=0,
                        photo_filename=filename,
                        current_photo=idx,
                        total_photos=total_photos
                    )
                
                # Carica file da MinIO
                from app.services.archaeological_minio_service import archaeological_minio_service
                original_file_content = await archaeological_minio_service.get_file(file_path)
                
                # Processa tiles per questa foto
                await self._process_tiles_background(
                    photo_id,
                    original_file_content,
                    site_id,
                    archaeological_metadata
                )
                
                completed_count += 1
                logger.info(f"✅ [{idx}/{total_photos}] Tiles completati per photo {photo_id} - Progresso: {completed_count}/{total_photos}")
                
                # Ottieni info finali sui tiles
                tile_info = await self.get_deep_zoom_info(site_id, photo_id)
                tile_count = tile_info.get('total_tiles', 0) if tile_info else 0
                levels = tile_info.get('levels', 0) if tile_info else 0
                
                # Invia notifica completamento
                if has_websocket:
                    await notification_manager.broadcast_tiles_progress(
                        site_id=site_id,
                        photo_id=photo_id,
                        status='completed',
                        progress=100,
                        photo_filename=filename,
                        tile_count=tile_count,
                        levels=levels,
                        current_photo=idx,
                        total_photos=total_photos
                    )
                
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ [{idx}/{total_photos}] Tiles falliti per photo {photo_id}: {e}")
                
                # Update database with failed status
                await self._update_photo_database_status(photo_id, "failed")
                await self._update_processing_status(
                    photo_id, site_id, "failed", 0, error=str(e)
                )
                
                # Invia notifica errore
                if has_websocket:
                    await notification_manager.broadcast_tiles_progress(
                        site_id=site_id,
                        photo_id=photo_id,
                        status='failed',
                        progress=0,
                        photo_filename=filename,
                        current_photo=idx,
                        total_photos=total_photos,
                        error=str(e)
                    )
        
        logger.info(
            f"🎉 BATCH PROCESSING COMPLETED: {completed_count} successi, {failed_count} fallimenti su {total_photos} foto totali"
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
            
            # Carica file da MinIO in background
            from app.services.archaeological_minio_service import archaeological_minio_service
            original_file_content = await archaeological_minio_service.get_file(file_path)
            
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
            await self._update_photo_database_status(photo_id, "failed")
            await self._update_processing_status(
                photo_id, site_id, "failed", 0, error=f"File loading failed: {str(e)}"
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
        try:
            logger.info(f"🚀 Starting background tiles generation for photo {photo_id} (site: {site_id})")
            
            # 1. Update database status to "processing"
            await self._update_photo_database_status(photo_id, "processing")
            
            # 2. Aggiorna status a "processing"
            await self._update_processing_status(photo_id, site_id, "processing", 0)
            
            # 2. Genera tiles in memoria
            tiles_data, original_width, original_height = await self._generate_tiles_from_bytes(
                original_file_content, photo_id, site_id
            )
            
            total_tiles = self._count_total_tiles(tiles_data)
            await self._update_processing_status(photo_id, site_id, "uploading", 10, total_tiles, len(tiles_data))
            
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
                    photo_id, site_id, "uploading", progress, total_tiles, len(tiles_data), completed_tiles
                )
                
                logger.info(f"Uploaded {completed_tiles}/{total_tiles} tiles for photo {photo_id}")
            
            if failed_uploads:
                logger.warning(f"Some tile uploads failed for photo {photo_id}: {len(failed_uploads)} errors")

            # 4. Crea metadata finale
            await self._update_processing_status(photo_id, site_id, "finalizing", 90)
            
            metadata_url = await self._create_and_upload_metadata(
                photo_id, site_id, tiles_data, archaeological_metadata, original_width, original_height
            )
            
            # 5. Completa con successo
            final_status = {
                "photo_id": photo_id,
                "site_id": site_id,
                "status": "completed",
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
                "completed",
                tile_count=len(successful_uploads),
                levels=len(tiles_data)
            )
            
            logger.info(f"🎉 Background tiles generation completed for photo {photo_id}: {len(successful_uploads)} tiles uploaded in {len(tiles_data)} levels")

        except Exception as e:
            logger.error(f"❌ Background tiles generation failed for photo {photo_id}: {e}")
            
            # Update database with failed status
            await self._update_photo_database_status(photo_id, "failed")
            
            # Aggiorna status a "failed"
            try:
                await self._update_processing_status(
                    photo_id, site_id, "failed", 0, error=str(e)
                )
            except Exception as status_error:
                logger.error(f"Failed to update error status for photo {photo_id}: {status_error}")

    async def process_and_upload_tiles(
        self,
        photo_id: str,
        original_file: UploadFile,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Mantiene compatibilità per chiamate esistenti
        Usa schedule_tiles_generation_background invece per performance
        """
        logger.warning("Using deprecated synchronous tile processing. Consider using background processing.")
        
        try:
            # Leggi contenuto file
            content = await original_file.read()
            await original_file.seek(0)
            
            # Processa in background (ma aspetta per compatibilità)
            return await self._process_tiles_background(photo_id, content, site_id, archaeological_metadata)
            
        except Exception as e:
            logger.error(f"Deep zoom processing failed for {photo_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Deep zoom processing failed: {str(e)}")

    async def generate_tiles_in_memory(self, original_file: UploadFile) -> Tuple[Dict[int, Dict[str, bytes]], int, int]:
        """
        Genera tiles deep zoom in memoria senza salvare su disco

        Returns:
            Tuple[Dict[level, Dict[tile_coords, tile_data]], original_width, original_height]
        """
        try:
            # Carica immagine in memoria
            content = await original_file.read()
            await original_file.seek(0)  # Reset per altri usi

            # Usa BytesIO invece di file temporaneo per evitare problemi di permessi
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

    async def _upload_single_tile_with_metadata(
        self,
        object_name: str,
        tile_data: bytes,
        metadata: Dict[str, Any],
        archaeological_minio_service = None
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

            # Import locale per evitare circular import
            if archaeological_minio_service is None:
                from app.services.archaeological_minio_service import archaeological_minio_service

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

            # Upload usando asyncio.to_thread per chiamate sincrone MinIO
            result = await asyncio.to_thread(
                archaeological_minio_service.client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=object_name,
                data=io.BytesIO(tile_data),
                length=len(tile_data),
                content_type='image/png' if self.format == 'png' else 'image/jpeg',
                metadata=tile_metadata
            )

            logger.debug(f"Tile uploaded: {object_name}")
            return object_name

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
            "archeological_metadata": archaeological_metadata or {}
        }

        # Aggiungi informazioni per livello
        level_info = {}
        for level, tiles_level in tiles_data.items():
            level_info[level] = {
                "tile_count": len(tiles_level),
                "tiles": list(tiles_level.keys())
            }

        metadata["level_info"] = level_info

        # Upload metadata come JSON
        metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
        metadata_bytes = metadata_json.encode('utf-8')

        # Upload metadata direttamente nel bucket tiles
        metadata_object_name = f"{site_id}/tiles/{photo_id}/metadata.json"

        try:
            # Import locale per evitare circular import
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            # Upload direttamente nel bucket tiles invece di usare upload_document
            result = await asyncio.to_thread(
                archaeological_minio_service.client.put_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=metadata_object_name,
                data=io.BytesIO(metadata_bytes),
                length=len(metadata_bytes),
                content_type='application/json',
                metadata={
                    'x-amz-meta-photo-id': photo_id,
                    'x-amz-meta-site-id': site_id,
                    'x-amz-meta-document-type': 'deep_zoom_metadata',
                    'x-amz-meta-created': datetime.now().isoformat()
                }
            )

            logger.info(f"Deep zoom metadata uploaded: {metadata_object_name}")
            return f"minio://{archaeological_minio_service.buckets['tiles']}/{metadata_object_name}"

        except Exception as e:
            logger.error(f"Metadata upload failed: {e}")
            raise HTTPException(status_code=500, detail="Metadata upload failed")

    def _count_total_tiles(self, tiles_data: Dict[int, Dict[str, bytes]]) -> int:
        """Conta totale tiles in tutti i livelli"""
        return sum(len(tiles_level) for tiles_level in tiles_data.values())

    async def get_tile_url(self, site_id: str, photo_id: str, level: int, x: int, y: int) -> Optional[str]:
        """Genera URL presigned per singolo tile"""
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
            # Import locale per evitare circular import
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            # Verifica esistenza tile prima di generare URL
            import asyncio
            from minio.error import S3Error
            
            try:
                # Controlla se il tile esiste
                await asyncio.to_thread(
                    archaeological_minio_service.client.stat_object,
                    bucket_name=archaeological_minio_service.buckets['tiles'],
                    object_name=object_name
                )
            except S3Error:
                logger.warning(f"Tile not found: {object_name}")
                
                # FIXED: Prova l'altro formato se il primo non esiste
                alternative_extension = 'png' if extension == 'jpg' else 'jpg'
                alternative_object_name = f"{site_id}/tiles/{photo_id}/{level}/{tile_coords}.{alternative_extension}"
                
                try:
                    await asyncio.to_thread(
                        archaeological_minio_service.client.stat_object,
                        bucket_name=archaeological_minio_service.buckets['tiles'],
                        object_name=alternative_object_name
                    )
                    logger.info(f"✅ Found tile with alternative format: .{alternative_extension} for photo {photo_id}")
                    object_name = alternative_object_name
                except S3Error:
                    logger.error(f"❌ Tile not found in both formats (.{extension} and .{alternative_extension}) for photo {photo_id}")
                    return None
            
            # Genera URL presigned specifico per il tile
            from datetime import timedelta
            url = await asyncio.to_thread(
                archaeological_minio_service.client.presigned_get_object,
                bucket_name=archaeological_minio_service.buckets['tiles'],
                object_name=object_name,
                expires=timedelta(hours=24)
            )
            
            logger.debug(f"Generated tile URL: {object_name}")
            return url
            
        except Exception as e:
            logger.error(f"Error generating tile URL for {object_name}: {e}")
            return None

    async def get_deep_zoom_info(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni informazioni deep zoom per una foto"""
        try:
            # Import locale per evitare circular import
            from app.services.archaeological_minio_service import archaeological_minio_service
            import asyncio
            from minio.error import S3Error
            
            # Scarica metadata dal bucket tiles
            metadata_path = f"{site_id}/tiles/{photo_id}/metadata.json"

            # Prima verifica se il file metadata.json esiste
            try:
                await asyncio.to_thread(
                    archaeological_minio_service.client.stat_object,
                    bucket_name=archaeological_minio_service.buckets['tiles'],
                    object_name=metadata_path
                )
            except S3Error as e:
                logger.info(f"Deep zoom metadata not found for photo {photo_id} - tiles not generated: {e}")
                return None

            # Usa il servizio archeologico per ottenere il file
            try:
                metadata_content = await archaeological_minio_service.get_file(
                    f"minio://{archaeological_minio_service.buckets['tiles']}/{metadata_path}"
                )
            except HTTPException:
                logger.info(f"Deep zoom metadata not accessible for photo {photo_id}")
                return None

            if isinstance(metadata_content, str) and metadata_content.startswith("Error"):
                logger.info(f"Deep zoom metadata error for photo {photo_id}: {metadata_content}")
                return None

            # Parse metadata JSON
            if isinstance(metadata_content, bytes):
                metadata_content = metadata_content.decode('utf-8')
            
            metadata = json.loads(metadata_content)

            # Validate essential fields
            if not all(key in metadata for key in ['width', 'height', 'levels', 'total_tiles']):
                logger.warning(f"Deep zoom metadata incomplete for photo {photo_id}")
                return None
                
            if metadata.get('levels', 0) <= 0 or metadata.get('total_tiles', 0) <= 0:
                logger.warning(f"Deep zoom has no valid tiles for photo {photo_id}")
                return None

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
                'metadata_url': f"minio://{archaeological_minio_service.buckets['tiles']}/{metadata_path}",
                'created': metadata.get('created')
            }

        except HTTPException:
            # HTTPException indica che il file non esiste (404)
            logger.info(f"Deep zoom tiles not available for photo {photo_id} - file not found")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Deep zoom metadata corrupted for photo {photo_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Deep zoom info unavailable for photo {photo_id}: {e}")
            return None

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
            from app.services.archaeological_minio_service import archaeological_minio_service
            
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
                
            status_json = json.dumps(status_data, indent=2, ensure_ascii=False)
            status_bytes = status_json.encode('utf-8')
            
            status_object_name = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
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
        photo_id: str,
        site_id: str,
        full_status: Dict[str, Any]
    ):
        """Aggiorna status completo"""
        try:
            from app.services.archaeological_minio_service import archaeological_minio_service
            
            status_json = json.dumps(full_status, indent=2, ensure_ascii=False)
            status_bytes = status_json.encode('utf-8')
            
            status_object_name = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
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

    async def get_processing_status(self, site_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
        """Ottieni status di processing per una foto"""
        try:
            from app.services.archaeological_minio_service import archaeological_minio_service
            import asyncio
            from minio.error import S3Error
            
            status_path = f"{site_id}/tiles/{photo_id}/processing_status.json"
            
            # Verifica esistenza
            try:
                await asyncio.to_thread(
                    archaeological_minio_service.client.stat_object,
                    bucket_name=archaeological_minio_service.buckets['tiles'],
                    object_name=status_path
                )
            except S3Error:
                logger.info(f"Processing status not found for photo {photo_id}")
                return None
                
            # Ottieni contenuto
            try:
                status_content = await archaeological_minio_service.get_file(
                    f"minio://{archaeological_minio_service.buckets['tiles']}/{status_path}"
                )
            except HTTPException:
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
            from app.database.base import async_session_maker
            
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
                            # Set processing status
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


# Istanza globale
deep_zoom_minio_service = DeepZoomMinIOService()