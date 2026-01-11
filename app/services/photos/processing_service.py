# app/services/photos/processing_service.py - Main photo processing orchestration service

"""
Main service for photo processing orchestration.
Coordinates metadata extraction, thumbnail generation, record creation,
and deep zoom tile scheduling.
"""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from uuid import uuid4

from PIL import Image
import io
import aiofiles
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from app.core.domain_exceptions import PhotoServiceError, ImageProcessingError
from app.models import Photo

from .config import (
    MIN_DIMENSION_FOR_TILES, 
    SUPPORTED_IMAGE_FORMATS,
    THUMBNAIL_MAX_SIZE
)
from .image_utils import ImageUtils, FileUtils
from .metadata_service import photo_metadata_extractor
from .thumbnail_service import thumbnail_service
from .record_service import photo_record_service


class PhotoProcessingService:
    """
    Main orchestration service for photo processing.
    Coordinates all photo-related operations.
    """

    def __init__(self):
        self.supported_formats = SUPPORTED_IMAGE_FORMATS
        self.min_dimension_for_tiles = MIN_DIMENSION_FOR_TILES
        self._tus_service = None
        self._minio_service = None
        self._deep_zoom_service = None

    # Lazy load services to avoid circular imports
    @property
    def tus_service(self):
        if self._tus_service is None:
            try:
                from app.services.tus_service import tus_upload_service
                self._tus_service = tus_upload_service
            except ImportError:
                logger.warning("TUS service not available")
        return self._tus_service

    @property
    def minio_service(self):
        if self._minio_service is None:
            try:
                from app.services.archaeological_minio_service import archaeological_minio_service
                self._minio_service = archaeological_minio_service
            except ImportError:
                logger.warning("MinIO service not available")
        return self._minio_service

    @property
    def deep_zoom_service(self):
        if self._deep_zoom_service is None:
            try:
                from app.services.deep_zoom_background_service import deep_zoom_background_service
                self._deep_zoom_service = deep_zoom_background_service
            except ImportError:
                logger.warning("Deep zoom service not available")
        return self._deep_zoom_service

    # =========================================================================
    # Metadata Extraction (delegated)
    # =========================================================================

    async def extract_metadata(
        self,
        file_path: str,
        filename: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Extract metadata from image file"""
        return await photo_metadata_extractor.extract_metadata(file_path, filename)

    async def extract_metadata_from_bytes(
        self,
        file_data: bytes,
        filename: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Extract metadata from image bytes"""
        return await photo_metadata_extractor.extract_metadata_from_bytes(
            file_data, filename
        )

    # =========================================================================
    # Thumbnail Generation (delegated)
    # =========================================================================

    async def create_and_upload_thumbnail(
        self,
        photo_id: str,
        image_data: bytes,
        site_id: Optional[str] = None
    ) -> str:
        """Create and upload thumbnail"""
        return await thumbnail_service.create_and_upload_thumbnail(
            photo_id, image_data, site_id
        )

    async def generate_thumbnail(
        self,
        original_path: str,
        photo_id: str,
        max_size: int = THUMBNAIL_MAX_SIZE
    ) -> Optional[str]:
        """Generate thumbnail from file path"""
        try:
            thumbnail = await thumbnail_service.generate_thumbnail_from_path(
                original_path, max_size
            )
            thumbnail_bytes = await thumbnail_service.save_thumbnail_to_bytes(thumbnail)
            return await thumbnail_service.upload_thumbnail_bytes(thumbnail_bytes, photo_id)
        except Exception as e:
            logger.error(f"Error generating thumbnail for {photo_id}: {e}")
            return None

    # =========================================================================
    # Record Creation (delegated)
    # =========================================================================

    async def create_photo_record(
        self,
        filename: str,
        original_filename: str,
        file_path: str,
        file_size: int,
        site_id: str,
        uploaded_by: str,
        metadata: Optional[Dict[str, Any]] = None,
        archaeological_metadata: Optional[Dict[str, Any]] = None,
        thumbnail_path: Optional[str] = None
    ) -> Photo:
        """Create Photo database record"""
        return await photo_record_service.create_photo_record(
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            site_id=site_id,
            uploaded_by=uploaded_by,
            metadata=metadata,
            archaeological_metadata=archaeological_metadata,
            thumbnail_path=thumbnail_path
        )

    # =========================================================================
    # TUS Upload Processing
    # =========================================================================

    async def process_tus_upload(
        self,
        db: AsyncSession,
        upload_id: str,
        site_id: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Photo:
        """
        Process a completed TUS upload.
        
        1. Retrieve file from TUS temp directory
        2. Upload to MinIO (original + thumbnail)
        3. Create database record
        4. Delete TUS temp file
        5. Schedule deep zoom if needed
        
        Args:
            db: Database session
            upload_id: TUS upload identifier
            site_id: Site identifier
            user_id: User identifier
            metadata: Upload metadata
            
        Returns:
            Photo model instance
            
        Raises:
            PhotoServiceError: If processing fails
        """
        if metadata is None:
            metadata = {}

        try:
            # 1. Get TUS file path
            if not self.tus_service:
                raise PhotoServiceError("TUS service not available")
                
            if not await self.tus_service.is_upload_complete(upload_id):
                raise PhotoServiceError(f"TUS upload {upload_id} not complete")
            
            temp_path = await self.tus_service.get_upload_file_path(upload_id)
            
            if not temp_path.exists():
                raise PhotoServiceError(f"TUS file not found: {upload_id}")
                
            file_size = temp_path.stat().st_size
            filename = metadata.get('filename', f"upload_{upload_id}.jpg")
            
            # Read file content
            async with aiofiles.open(temp_path, 'rb') as f:
                file_data = await f.read()

            # 2. Extract metadata
            arch_metadata = metadata.get('archaeological_metadata', {})
            exif_data, tech_metadata = await self.extract_metadata_from_bytes(
                file_data, filename
            )

            # 3. Upload to MinIO (thumbnail + original)
            photo_uuid = str(uuid4())
            
            # Generate and upload thumbnail
            thumbnail_url = None
            try:
                thumbnail_url = await self.create_and_upload_thumbnail(
                    photo_uuid, file_data, site_id
                )
            except Exception as e:
                logger.warning(f"Thumbnail creation failed for TUS {upload_id}: {e}")

            # Upload original photo
            if not self.minio_service:
                raise PhotoServiceError("MinIO service required for TUS processing")
                
            full_metadata = {**arch_metadata, **tech_metadata}
            minio_url = await self.minio_service.upload_photo_with_metadata(
                photo_data=file_data,
                photo_id=f"{photo_uuid}{Path(filename).suffix}",
                site_id=site_id,
                archaeological_metadata=full_metadata
            )
            file_path_db = minio_url

            # 4. Create database record
            photo = await self.create_photo_record(
                filename=f"{photo_uuid}{Path(filename).suffix}",
                original_filename=filename,
                file_path=file_path_db,
                file_size=file_size,
                site_id=site_id,
                uploaded_by=user_id,
                metadata=tech_metadata,
                archaeological_metadata=arch_metadata,
                thumbnail_path=thumbnail_url
            )
            
            db.add(photo)
            await db.commit()
            await db.refresh(photo)
            
            # 5. Cleanup TUS temp file
            await self.tus_service.delete_upload(upload_id)
            logger.info(f"TUS upload {upload_id} processed -> Photo {photo.id}")
            
            # 6. Schedule deep zoom if needed
            await self._schedule_deep_zoom_if_needed(
                photo=photo,
                site_id=site_id,
                file_path=file_path_db,
                width=tech_metadata.get('width', 0),
                height=tech_metadata.get('height', 0),
                filename=filename,
                file_size=file_size,
                arch_metadata=arch_metadata,
                db=db
            )
            
            return photo

        except PhotoServiceError:
            raise
        except Exception as e:
            logger.error(f"Error processing TUS upload {upload_id}: {e}")
            raise PhotoServiceError(f"Failed to process TUS upload: {str(e)}")

    # =========================================================================
    # Deep Zoom Scheduling (unified)
    # =========================================================================

    async def _schedule_deep_zoom_if_needed(
        self,
        photo: Photo,
        site_id: str,
        file_path: str,
        width: int,
        height: int,
        filename: str,
        file_size: int,
        arch_metadata: Dict[str, Any],
        db: AsyncSession
    ) -> bool:
        """
        Schedule deep zoom tile generation if image is large enough.
        
        Args:
            photo: Photo model instance
            site_id: Site identifier
            file_path: Path to image file
            width: Image width
            height: Image height
            filename: Image filename
            file_size: File size in bytes
            arch_metadata: Archaeological metadata
            db: Database session
            
        Returns:
            True if scheduled, False otherwise
        """
        try:
            max_dimension = max(width, height) if width and height else 0
            
            if max_dimension <= self.min_dimension_for_tiles:
                logger.debug(
                    f"Photo {photo.id}: Too small for deep zoom "
                    f"({max_dimension}px < {self.min_dimension_for_tiles}px)"
                )
                return False
            
            logger.info(
                f"Photo {photo.id}: Scheduling deep zoom tiles ({width}x{height})"
            )
            
            # Update status
            photo.deepzoom_status = 'scheduled'
            await db.commit()
            
            if not self.deep_zoom_service:
                logger.warning("Deep zoom service not available")
                return False
            
            # Create snapshot for background processing
            photo_snapshot = {
                'id': str(photo.id),
                'site_id': site_id,
                'file_path': file_path,
                'width': width,
                'height': height,
                'filename': filename,
                'file_size': file_size,
                'archaeological_metadata': arch_metadata,
                'needs_tiles': True
            }
            
            await self.deep_zoom_service.schedule_batch_processing_with_snapshots(
                photo_snapshots=[photo_snapshot],
                site_id=site_id
            )
            
            logger.info(f"Photo {photo.id}: Deep zoom tiles scheduled successfully")
            return True
            
        except Exception as e:
            logger.warning(f"Photo {photo.id}: Failed to schedule deep zoom: {e}")
            return False

    # =========================================================================
    # Validation
    # =========================================================================

    async def validate_image_bytes(
        self, 
        file_data: bytes, 
        filename: str
    ) -> Tuple[bool, str]:
        """
        Validate that bytes represent a supported image.
        
        Args:
            file_data: Raw image bytes
            filename: Filename with extension
            
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            if not filename:
                return False, "Nome file mancante"

            extension = Path(filename).suffix.lower()
            if extension not in self.supported_formats:
                return False, f"Formato {extension} non supportato"

            # Verify it's actually an image
            temp_file_path = None
            try:
                temp_file_path = FileUtils.create_temp_file_from_bytes(
                    file_data, filename
                )

                with Image.open(temp_file_path) as img:
                    width, height = img.size
                    if width < 1 or height < 1:
                        return False, "Dimensioni immagine non valide"
                    return True, "OK"

            except ImageProcessingError as e:
                return False, f"File corrotto o non valido: {str(e)}"
            finally:
                if temp_file_path:
                    FileUtils.cleanup_temp_file(temp_file_path)

        except Exception as e:
            return False, f"Errore validazione: {str(e)}"

    # =========================================================================
    # Deep Zoom Processing (for standard upload)
    # =========================================================================

    async def process_photo_with_deep_zoom(
        self,
        file: UploadFile,
        photo_id: str,
        site_id: str,
        archaeological_metadata: Optional[Dict[str, Any]] = None,
        generate_deep_zoom: bool = True
    ) -> Dict[str, Any]:
        """
        Process photo with deep zoom generation if needed.
        
        Args:
            file: FastAPI UploadFile
            photo_id: Photo identifier
            site_id: Site identifier
            archaeological_metadata: Archaeological form data
            generate_deep_zoom: Whether to attempt deep zoom generation
            
        Returns:
            Dict with processing results
        """
        try:
            should_generate = generate_deep_zoom

            if should_generate:
                content = await file.read()
                await file.seek(0)

                try:
                    with Image.open(io.BytesIO(content)) as img:
                        width, height = img.size
                        max_dimension = max(width, height)
                        should_generate = max_dimension > self.min_dimension_for_tiles
                except Exception as e:
                    logger.warning(f"Could not determine image dimensions: {e}")
                    should_generate = False

                if should_generate and self.minio_service:
                    logger.info(f"Generating deep zoom for image: {width}x{height}")

                    try:
                        result = await self.minio_service.process_photo_with_deep_zoom(
                            photo_data=content,
                            photo_id=photo_id,
                            site_id=site_id,
                            archaeological_metadata=archaeological_metadata,
                            generate_deep_zoom=True
                        )

                        logger.info(f"Deep zoom completed for {photo_id}")
                        return {
                            'photo_url': result['photo_url'],
                            'deep_zoom_available': result['deep_zoom_available'],
                            'tile_count': result.get('tile_count', 0),
                            'levels': result.get('levels', 0),
                            'metadata_url': result.get('metadata_url')
                        }
                    except Exception as e:
                        logger.error(f"Deep zoom failed for {photo_id}: {e}")
                        return {
                            'photo_url': None,
                            'deep_zoom_available': False,
                            'tile_count': 0,
                            'levels': 0,
                            'metadata_url': None,
                            'deep_zoom_error': str(e)
                        }

            # No deep zoom
            return {
                'photo_url': None,
                'deep_zoom_available': False,
                'tile_count': 0,
                'levels': 0,
                'metadata_url': None
            }

        except Exception as e:
            logger.error(f"Deep zoom processing failed: {e}")
            return {
                'photo_url': None,
                'deep_zoom_available': False,
                'tile_count': 0,
                'levels': 0,
                'metadata_url': None,
                'deep_zoom_error': str(e)
            }


# Global instance
photo_processing_service = PhotoProcessingService()

__all__ = ['PhotoProcessingService', 'photo_processing_service']
