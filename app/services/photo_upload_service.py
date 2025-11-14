# app/services/photo_upload_service.py - Nuovo Service per Upload Foto
"""
Photo Upload Service - Estrazione della logica business dall'endpoint upload_photo

Questo service implementa il refactoring della tecnica #1 (Estrazione logica business)
e #2 (Introduzione Service Layer).
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from fastapi import HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import Photo
from app.services.photo_service import photo_metadata_service
from app.services.storage_service import storage_service
from app.services.photo_serving_service import photo_serving_service
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.repositories.photo_repository import PhotoRepository


class PhotoUploadResult:
    """Risultato upload singola foto"""
    def __init__(self, photo_id: UUID, filename: str, file_size: int, metadata: Dict[str, Any]):
        self.photo_id = photo_id
        self.filename = filename
        self.file_size = file_size
        self.metadata = metadata


class PhotoUploadService:
    """
    Service per gestione upload foto - Centralizza tutta la logica di business
    precedentemente distribuita nell'endpoint upload_photo (632 righe).
    """

    def __init__(
        self,
        db: AsyncSession,
        storage_service,
        metadata_service,
        photo_repo: PhotoRepository
    ):
        self.db = db
        self.storage = storage_service
        self.metadata = metadata_service
        self.photo_repo = photo_repo

    async def upload_photos(
        self,
        site_id: UUID,
        files: List[UploadFile],
        user_id: UUID,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload multiplo foto con processamento completo

        Args:
            site_id: ID del sito archeologico
            files: Lista file da uploadare
            user_id: ID utente che effettua upload
            archaeological_metadata: Metadati archeologici comuni

        Returns:
            Dict con risultati upload
        """
        # 🔍 DIAGNOSTIC: Track service-level upload timing
        service_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting batch upload service at {service_start_time}")
        logger.info(f"Starting batch upload: {len(files)} photos for site {site_id}")
        logger.info(f"🔍 [SERVICE DEBUG] File details: {[{ 'name': f.filename, 'size': f.size, 'type': f.content_type } for f in files]}")
        logger.info(f"🔍 [SERVICE DEBUG] Archaeological metadata: {archaeological_metadata}")

        uploaded_photos = []
        errors = []

        # Processa ogni foto
        for file_index, file in enumerate(files):
            try:
                file_start_time = asyncio.get_event_loop().time()
                logger.info(f"🔍 [SERVICE DEBUG] Processing file {file_index + 1}/{len(files)}: {file.filename}")
                
                result = await self._upload_single_photo(
                    site_id, file, user_id, archaeological_metadata
                )
                
                file_end_time = asyncio.get_event_loop().time()
                file_duration = file_end_time - file_start_time
                logger.info(f"🔍 [SERVICE DEBUG] File {file.filename} processed in {file_duration:.2f}s")
                
                uploaded_photos.append(result)
            except Exception as e:
                file_end_time = asyncio.get_event_loop().time()
                logger.error(f"🔍 [SERVICE DEBUG] File {file.filename} failed after {file_end_time - file_start_time:.2f}s: {e}")
                logger.error(f"🔍 [SERVICE DEBUG] Error details: {type(e).__name__}: {str(e)}")
                errors.append({
                    "filename": file.filename,
                    "error": str(e)
                })

        # 🔍 DIAGNOSTIC: Track deep zoom preparation
        deep_zoom_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting deep zoom preparation at {deep_zoom_start_time}")
        
        photos_needing_tiles = await self._prepare_deep_zoom_processing(
            uploaded_photos, site_id
        )
        
        deep_zoom_end_time = asyncio.get_event_loop().time()
        deep_zoom_duration = deep_zoom_end_time - deep_zoom_start_time
        logger.info(f"🔍 [SERVICE DEBUG] Deep zoom preparation completed in {deep_zoom_duration:.2f}s for {len(photos_needing_tiles)} photos")

        # Avvia processamento in background se necessario
        if photos_needing_tiles:
            background_start_time = asyncio.get_event_loop().time()
            logger.info(f"🔍 [SERVICE DEBUG] Starting background tiles processing at {background_start_time}")
            
            # 🔧 FIX: Ensure background processor is running
            if not deep_zoom_background_service._running:
                await deep_zoom_background_service.start_background_processor()
                logger.info('🚀 Auto-started background processor for tiles generation')

            asyncio.create_task(
                self._process_tiles_batch_background(photos_needing_tiles, site_id)
            )
            
            logger.info(f"🔍 [SERVICE DEBUG] Background tiles task created at {asyncio.get_event_loop().time()}")

        # 🔍 DIAGNOSTIC: Track service completion
        service_end_time = asyncio.get_event_loop().time()
        total_service_duration = service_end_time - service_start_time
        
        response = {
            "message": f"Successfully uploaded {len(uploaded_photos)} photos",
            "uploaded_photos": [
                {
                    "photo_id": str(result.photo_id),
                    "filename": result.filename,
                    "file_size": result.file_size,
                    "metadata": result.metadata
                }
                for result in uploaded_photos
            ],
            "total_uploaded": len(uploaded_photos),
            "errors": errors,
            "photos_needing_tiles": len(photos_needing_tiles)
        }

        logger.info(f"🔍 [SERVICE DEBUG] Service-level upload completed in {total_service_duration:.2f}s at {service_end_time}")
        logger.info(f"Batch upload completed: {len(uploaded_photos)} success, {len(errors)} errors")
        return response

    async def _upload_single_photo(
        self,
        site_id: UUID,
        file: UploadFile,
        user_id: UUID,
        archaeological_metadata: Optional[Dict[str, Any]] = None
    ) -> PhotoUploadResult:
        """
        Upload singola foto con processamento completo

        Fasi:
        1. Validazione file
        2. Upload storage
        3. Estrazione metadati
        4. Creazione record DB
        5. Generazione thumbnail
        """
        single_photo_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting single photo upload: {file.filename} at {single_photo_start_time}")
        logger.info(f"🔍 [SERVICE DEBUG] File info: size={file.size}, type={file.content_type}")

        # 1. Validazione file
        validation_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting file validation at {validation_start_time}")
        
        is_valid, validation_message = await self.metadata.validate_image_file(file)
        
        validation_end_time = asyncio.get_event_loop().time()
        validation_duration = validation_end_time - validation_start_time
        logger.info(f"🔍 [SERVICE DEBUG] File validation completed in {validation_duration:.2f}s: valid={is_valid}")
        
        if not is_valid:
            logger.error(f"🔍 [SERVICE DEBUG] Validation failed: {validation_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file {file.filename}: {validation_message}"
            )

        # 2. Upload storage
        storage_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting storage upload at {storage_start_time}")
        
        try:
            filename, file_path, file_size = await self.storage.save_upload_file(
                file, str(site_id), str(user_id)
            )
            storage_end_time = asyncio.get_event_loop().time()
            storage_duration = storage_end_time - storage_start_time
            logger.info(f"🔍 [SERVICE DEBUG] Storage upload completed in {storage_duration:.2f}s: {filename} ({file_size} bytes)")
        except Exception as e:
            storage_end_time = asyncio.get_event_loop().time()
            storage_duration = storage_end_time - storage_start_time
            logger.error(f"🔍 [SERVICE DEBUG] Storage upload failed after {storage_duration:.2f}s for {file.filename}: {e}")
            logger.error(f"🔍 [SERVICE DEBUG] Storage error details: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storage upload failed: {str(e)}"
            )

        # 3. Estrazione metadati
        metadata_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting metadata extraction at {metadata_start_time}")
        
        await file.seek(0)  # Reset file pointer
        try:
            exif_data, metadata = await self.metadata.extract_metadata_from_file(
                file, filename
            )
            metadata_end_time = asyncio.get_event_loop().time()
            metadata_duration = metadata_end_time - metadata_start_time
            logger.info(f"🔍 [SERVICE DEBUG] Metadata extracted in {metadata_duration:.2f}s for {filename}")
            logger.info(f"🔍 [SERVICE DEBUG] Extracted metadata keys: {list(metadata.keys())}")
        except Exception as e:
            metadata_end_time = asyncio.get_event_loop().time()
            metadata_duration = metadata_end_time - metadata_start_time
            logger.warning(f"🔍 [SERVICE DEBUG] Metadata extraction failed after {metadata_duration:.2f}s for {filename}: {e}")
            exif_data, metadata = {}, {}

        # 4. Creazione record DB
        db_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting database record creation at {db_start_time}")
        
        try:
            photo_record = await self.metadata.create_photo_record(
                filename=filename,
                original_filename=file.filename,
                file_path=file_path,
                file_size=file_size,
                site_id=str(site_id),
                uploaded_by=str(user_id),
                metadata=metadata,
                archaeological_metadata=archaeological_metadata
            )

            self.db.add(photo_record)
            
            # 🔍 DIAGNOSTIC: Track database transaction timing
            db_commit_start_time = asyncio.get_event_loop().time()
            await self.db.commit()
            db_commit_end_time = asyncio.get_event_loop().time()
            db_commit_duration = db_commit_end_time - db_commit_start_time
            logger.info(f"🔍 [SERVICE DEBUG] Database commit completed in {db_commit_duration:.2f}s")
            
            await self.db.refresh(photo_record)
            db_end_time = asyncio.get_event_loop().time()
            db_total_duration = db_end_time - db_start_time
            logger.info(f"🔍 [SERVICE DEBUG] Database operations completed in {db_total_duration:.2f}s, photo_id: {photo_record.id}")

        except Exception as e:
            db_end_time = asyncio.get_event_loop().time()
            db_total_duration = db_end_time - db_start_time
            logger.error(f"🔍 [SERVICE DEBUG] Database operations failed after {db_total_duration:.2f}s: {e}")
            logger.error(f"🔍 [SERVICE DEBUG] Database error details: {type(e).__name__}: {str(e)}")
            
            # Cleanup storage se DB fallisce
            try:
                cleanup_start_time = asyncio.get_event_loop().time()
                await self.storage.delete_file(file_path)
                cleanup_end_time = asyncio.get_event_loop().time()
                logger.info(f"🔍 [SERVICE DEBUG] Storage cleanup completed in {cleanup_end_time - cleanup_start_time:.2f}s")
            except Exception as cleanup_e:
                logger.error(f"🔍 [SERVICE DEBUG] Storage cleanup failed: {cleanup_e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

        # 5. Generazione thumbnail
        thumbnail_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting thumbnail generation at {thumbnail_start_time}")
        
        await file.seek(0)  # Reset file pointer
        try:
            thumbnail_path = await self.metadata.generate_thumbnail_from_file(
                file, str(photo_record.id)
            )

            if thumbnail_path:
                photo_record.thumbnail_path = thumbnail_path
                await self.db.commit()
                thumbnail_end_time = asyncio.get_event_loop().time()
                thumbnail_duration = thumbnail_end_time - thumbnail_start_time
                logger.info(f"🔍 [SERVICE DEBUG] Thumbnail generated in {thumbnail_duration:.2f}s: {thumbnail_path}")
            else:
                thumbnail_end_time = asyncio.get_event_loop().time()
                thumbnail_duration = thumbnail_end_time - thumbnail_start_time
                logger.warning(f"🔍 [SERVICE DEBUG] Thumbnail generation failed after {thumbnail_duration:.2f}s for photo {photo_record.id}")

        except Exception as e:
            thumbnail_end_time = asyncio.get_event_loop().time()
            thumbnail_duration = thumbnail_end_time - thumbnail_start_time
            logger.warning(f"🔍 [SERVICE DEBUG] Thumbnail generation error after {thumbnail_duration:.2f}s for {photo_record.id}: {e}")
            logger.warning(f"🔍 [SERVICE DEBUG] Thumbnail error details: {type(e).__name__}: {str(e)}")
            # Non bloccare upload se thumbnail fallisce

        # 6. Log attività
        activity_start_time = asyncio.get_event_loop().time()
        logger.info(f"🔍 [SERVICE DEBUG] Starting activity logging at {activity_start_time}")
        
        try:
            await self._log_upload_activity(site_id, user_id, photo_record.id, filename, file_size)
            activity_end_time = asyncio.get_event_loop().time()
            activity_duration = activity_end_time - activity_start_time
            logger.info(f"🔍 [SERVICE DEBUG] Activity logging completed in {activity_duration:.2f}s")
        except Exception as e:
            activity_end_time = asyncio.get_event_loop().time()
            activity_duration = activity_end_time - activity_start_time
            logger.warning(f"🔍 [SERVICE DEBUG] Activity logging failed after {activity_duration:.2f}s: {e}")

        # 🔍 DIAGNOSTIC: Track single photo completion
        single_photo_end_time = asyncio.get_event_loop().time()
        total_single_photo_duration = single_photo_end_time - single_photo_start_time
        logger.info(f"🔍 [SERVICE DEBUG] Single photo upload completed in {total_single_photo_duration:.2f}s for {file.filename}")

        return PhotoUploadResult(
            photo_id=photo_record.id,
            filename=filename,
            file_size=file_size,
            metadata={
                "width": photo_record.width,
                "height": photo_record.height,
                "photo_date": photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                "camera_model": photo_record.camera_model
            }
        )

    async def _prepare_deep_zoom_processing(
        self,
        uploaded_results: List[PhotoUploadResult],
        site_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Prepara lista foto che necessitano processamento deep zoom

        Returns:
            Lista foto che necessitano tiles
        """
        photos_needing_tiles = []

        for result in uploaded_results:
            try:
                # Recupera dimensioni dalla metadata
                width = result.metadata.get("width", 0)
                height = result.metadata.get("height", 0)
                max_dimension = max(width, height)

                if max_dimension > 2000:  # Threshold per deep zoom
                    logger.info(f"Photo {result.photo_id} needs deep zoom tiles ({width}x{height})")

                    # Recupera record completo per metadati archeologici
                    photo_record = await self.photo_repo.get(result.photo_id)
                    if photo_record:
                        photos_needing_tiles.append({
                            'photo_id': str(result.photo_id),
                            'file_path': photo_record.filepath,
                            'width': width,
                            'height': height,
                            'archaeological_metadata': {
                                'inventory_number': photo_record.inventory_number,
                                'excavation_area': photo_record.excavation_area,
                                'material': photo_record.material if photo_record.material else None,
                                'chronology_period': photo_record.chronology_period,
                                'photo_type': photo_record.photo_type if photo_record.photo_type else None,
                                'photographer': photo_record.photographer,
                                'description': photo_record.description,
                                'keywords': photo_record.keywords
                            }
                        })

                        # Aggiorna status deep zoom
                        photo_record.deepzoom_status = 'scheduled'
                        await self.db.commit()

            except Exception as e:
                logger.error(f"Error checking tile requirements for photo {result.photo_id}: {e}")

        return photos_needing_tiles

    async def _process_tiles_batch_background(
        self,
        photos_list: List[Dict[str, Any]],
        site_id: UUID
    ):
        """
        Processa tiles in background per multiple foto

        Args:
            photos_list: Lista foto da processare
            site_id: ID sito
        """
        try:
            logger.info(f"Starting background tiles processing for {len(photos_list)} photos")

            # Import qui per evitare circular imports
            from app.services.deep_zoom_minio_service import deep_zoom_minio_service

            # Processa sequenzialmente per evitare sovraccarico
            await deep_zoom_minio_service.process_tiles_batch_sequential(
                photos_list=photos_list,
                site_id=str(site_id)
            )

            logger.info(f"Background tiles processing completed for {len(photos_list)} photos")

        except Exception as e:
            logger.error(f"Background tiles processing failed: {e}")

    async def _log_upload_activity(
        self,
        site_id: UUID,
        user_id: UUID,
        photo_id: UUID,
        filename: str,
        file_size: int
    ):
        """Log attività upload"""
        try:
            from app.models import UserActivity

            activity = UserActivity(
                id=str(uuid4()),  # Convert UUID to string for SQLite compatibility
                user_id=str(user_id),  # Convert UUID to string for SQLite compatibility
                site_id=str(site_id),  # Convert UUID to string for SQLite compatibility
                activity_type="UPLOAD",
                activity_desc=f"Caricata foto: {filename}",
                extra_data={
                    "photo_id": str(photo_id),
                    "filename": filename,
                    "file_size": file_size
                }
            )

            self.db.add(activity)
            await self.db.commit()

        except Exception as e:
            logger.warning(f"Failed to log upload activity: {e}")


# Dependency injection function
def get_photo_upload_service(
    db: AsyncSession,
    photo_repo: PhotoRepository,
    metadata_service=photo_metadata_service,
    storage_service=storage_service
):
    """Factory function per dependency injection"""
    return PhotoUploadService(db, storage_service, metadata_service, photo_repo)