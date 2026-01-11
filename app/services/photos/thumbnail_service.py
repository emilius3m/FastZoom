# app/services/photos/thumbnail_service.py - Thumbnail generation and upload service

"""
Service for generating and uploading photo thumbnails.
Handles thumbnail creation, sizing, and MinIO upload.
"""

import io
from typing import Optional

from PIL import Image
from loguru import logger

from app.core.domain_exceptions import ImageProcessingError, StorageError, StorageFullError
from .config import THUMBNAIL_MAX_SIZE, THUMBNAIL_QUALITY, THUMBNAIL_OPTIMIZE
from .image_utils import ImageUtils, FileUtils


class ThumbnailService:
    """Service for thumbnail generation and upload"""

    def __init__(self):
        self.max_size = THUMBNAIL_MAX_SIZE
        self.quality = THUMBNAIL_QUALITY
        self.optimize = THUMBNAIL_OPTIMIZE
        self._minio_service = None

    @property
    def minio_service(self):
        """Lazy load MinIO service to avoid circular imports"""
        if self._minio_service is None:
            try:
                from app.services.archaeological_minio_service import archaeological_minio_service
                self._minio_service = archaeological_minio_service
            except ImportError:
                logger.warning("MinIO service not available for thumbnails")
                self._minio_service = None
        return self._minio_service

    async def generate_thumbnail_bytes(
        self,
        image_data: bytes,
        max_size: Optional[int] = None,
        quality: Optional[int] = None
    ) -> bytes:
        """
        Generate thumbnail bytes from image data.
        
        Args:
            image_data: Raw image bytes
            max_size: Maximum thumbnail dimension (optional)
            quality: JPEG quality (optional)
            
        Returns:
            Thumbnail as JPEG bytes
            
        Raises:
            ImageProcessingError: If thumbnail generation fails
        """
        max_size = max_size or self.max_size
        quality = quality or self.quality
        
        try:
            return ImageUtils.generate_thumbnail_bytes(
                image_data,
                max_size=max_size,
                quality=quality,
                optimize=self.optimize
            )
        except Exception as e:
            logger.error(f"Error generating thumbnail bytes: {e}")
            raise ImageProcessingError(f"Thumbnail generation failed: {e}")

    async def generate_thumbnail_from_path(
        self,
        file_path: str,
        max_size: Optional[int] = None
    ) -> Image.Image:
        """
        Generate thumbnail from file path.
        
        Args:
            file_path: Path to image file
            max_size: Maximum thumbnail dimension
            
        Returns:
            PIL Image thumbnail
            
        Raises:
            ImageProcessingError: If thumbnail generation fails
        """
        max_size = max_size or self.max_size
        
        try:
            with Image.open(file_path) as img:
                # Prepare image (orientation, color mode)
                prepared_image = ImageUtils.prepare_image_for_thumbnail(img)
                
                # Create thumbnail
                return ImageUtils.create_thumbnail(prepared_image, max_size)
                
        except Exception as e:
            raise ImageProcessingError(f"Error preparing thumbnail: {e}")

    async def create_and_upload_thumbnail(
        self,
        photo_id: str,
        image_data: bytes,
        site_id: Optional[str] = None
    ) -> str:
        """
        Create thumbnail and upload to MinIO.
        
        Args:
            photo_id: Photo identifier
            image_data: Raw image bytes
            site_id: Site identifier (optional)
            
        Returns:
            URL/path of uploaded thumbnail
            
        Raises:
            ImageProcessingError: If thumbnail generation fails
            StorageFullError: If storage is full
            StorageError: If upload fails
        """
        try:
            # Generate thumbnail bytes
            thumbnail_bytes = await self.generate_thumbnail_bytes(image_data)

            # Upload via MinIO service
            if self.minio_service:
                thumbnail_url = await self.minio_service.upload_thumbnail(
                    thumbnail_bytes=thumbnail_bytes,
                    photo_id=photo_id,
                    site_id=site_id
                )
                logger.info(f"Thumbnail uploaded: {photo_id}")
                return thumbnail_url
            else:
                logger.warning("MinIO not available, thumbnail upload skipped")
                return f"temp_thumbnail_{photo_id}.jpg"

        except StorageFullError:
            logger.error(f"Cannot upload thumbnail, storage full: {photo_id}")
            raise
        except StorageError:
            logger.error(f"Storage error uploading thumbnail: {photo_id}")
            raise
        except Exception as e:
            logger.error(f"Error creating/uploading thumbnail for {photo_id}: {e}")
            raise ImageProcessingError(f"Thumbnail creation failed: {e}")

    async def save_thumbnail_to_bytes(
        self,
        thumbnail: Image.Image,
        quality: Optional[int] = None
    ) -> bytes:
        """
        Save PIL thumbnail image to bytes.
        
        Args:
            thumbnail: PIL Image thumbnail
            quality: JPEG quality (optional)
            
        Returns:
            Thumbnail as JPEG bytes
        """
        quality = quality or self.quality
        
        try:
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(
                thumbnail_buffer, 
                'JPEG', 
                quality=quality, 
                optimize=self.optimize
            )
            return thumbnail_buffer.getvalue()
            
        except Exception as e:
            raise ImageProcessingError(f"Error saving thumbnail to bytes: {e}")

    async def upload_thumbnail_bytes(
        self,
        thumbnail_bytes: bytes,
        photo_id: str,
        site_id: Optional[str] = None
    ) -> str:
        """
        Upload raw thumbnail bytes to MinIO.
        
        Args:
            thumbnail_bytes: Thumbnail JPEG bytes
            photo_id: Photo identifier
            site_id: Site identifier (optional)
            
        Returns:
            URL/path of uploaded thumbnail
        """
        try:
            if self.minio_service:
                thumbnail_url = await self.minio_service.upload_thumbnail(
                    thumbnail_bytes=thumbnail_bytes,
                    photo_id=photo_id,
                    site_id=site_id
                )
                logger.info(f"Thumbnail uploaded successfully: {photo_id}")
                return thumbnail_url
            else:
                logger.warning("MinIO not available, thumbnail upload skipped")
                return f"temp_thumbnail_{photo_id}.jpg"
                
        except Exception as e:
            logger.error(f"Error uploading thumbnail for {photo_id}: {e}")
            raise ImageProcessingError(f"Thumbnail upload failed: {e}")


# Global instance
thumbnail_service = ThumbnailService()

__all__ = ['ThumbnailService', 'thumbnail_service']
