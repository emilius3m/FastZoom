# app/services/photo_upload_service.py - Nuovo Service per Upload Foto
"""
Photo Upload Service - Estrazione della logica business dall'endpoint upload_photo

Questo service implementa il refactoring della tecnica #1 (Estrazione logica business)
e #2 (Introduzione Service Layer).
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from fastapi import HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import Photo
from app.services.photo_service import photo_metadata_service
from app.services.storage_service import storage_service
from app.services.photo_serving_service import photo_serving_service
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
        logger.info(f"Starting batch upload: {len(files)} photos for site {site_id}")

        uploaded_photos = []
        errors = []

        # Processa ogni foto
        for file in files:
            try:
                result = await self._upload_single_photo(
                    site_id, file, user_id, archaeological_metadata
                )
                uploaded_photos.append(result)
            except Exception as e:
                logger.error(f"Failed to upload {file.filename}: {e}")
                errors.append({
                    "filename": file.filename,
                    "error": str(e)
                })

        # Prepara processamento deep zoom se necessario
        photos_needing_tiles = await self._prepare_deep_zoom_processing(
            uploaded_photos, site_id
        )

        # Avvia processamento in background se necessario
        if photos_needing_tiles:
            asyncio.create_task(
                self._process_tiles_batch_background(photos_needing_tiles, site_id)
            )

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
        logger.info(f"Uploading photo: {file.filename} for site {site_id}")

        # 1. Validazione file
        is_valid, validation_message = await self.metadata.validate_image_file(file)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file {file.filename}: {validation_message}"
            )

        # 2. Upload storage
        try:
            filename, file_path, file_size = await self.storage.save_upload_file(
                file, str(site_id), str(user_id)
            )
            logger.info(f"File saved to storage: {filename}")
        except Exception as e:
            logger.error(f"Storage upload failed for {file.filename}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storage upload failed: {str(e)}"
            )

        # 3. Estrazione metadati
        await file.seek(0)  # Reset file pointer
        try:
            exif_data, metadata = await self.metadata.extract_metadata_from_file(
                file, filename
            )
            logger.info(f"Metadata extracted for {filename}")
        except Exception as e:
            logger.warning(f"Metadata extraction failed for {filename}: {e}")
            exif_data, metadata = {}, {}

        # 4. Creazione record DB
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
            await self.db.commit()
            await self.db.refresh(photo_record)

            logger.info(f"Photo record created: {photo_record.id}")

        except Exception as e:
            logger.error(f"Database record creation failed: {e}")
            # Cleanup storage se DB fallisce
            try:
                await self.storage.delete_file(file_path)
            except Exception:
                pass  # Ignore cleanup errors
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

        # 5. Generazione thumbnail
        await file.seek(0)  # Reset file pointer
        try:
            thumbnail_path = await self.metadata.generate_thumbnail_from_file(
                file, str(photo_record.id)
            )

            if thumbnail_path:
                photo_record.thumbnail_path = thumbnail_path
                await self.db.commit()
                logger.info(f"Thumbnail generated: {thumbnail_path}")
            else:
                logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")

        except Exception as e:
            logger.warning(f"Thumbnail generation error for {photo_record.id}: {e}")
            # Non bloccare upload se thumbnail fallisce

        # 6. Log attività
        await self._log_upload_activity(site_id, user_id, photo_record.id, filename, file_size)

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
                user_id=user_id,
                site_id=site_id,
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