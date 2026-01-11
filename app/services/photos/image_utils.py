# app/services/photos/image_utils.py - Image and file utility classes

"""
Utility classes for image processing and file operations.
These are stateless helper functions used by photo services.
"""

import os
import io
import tempfile
from pathlib import Path
from typing import Tuple, Optional

from PIL import Image
from fastapi import UploadFile
from loguru import logger

# ORIENTATION constant - handle different PIL versions
try:
    from PIL.ExifTags import ORIENTATION
except ImportError:
    # Fallback for older PIL versions
    ORIENTATION = 274

from app.core.domain_exceptions import ImageProcessingError
from .config import THUMBNAIL_MAX_SIZE, THUMBNAIL_QUALITY, THUMBNAIL_OPTIMIZE


class ImageUtils:
    """Utility class for common image processing operations"""

    @staticmethod
    def calculate_thumbnail_dimensions(
        original_size: Tuple[int, int], 
        max_size: int = THUMBNAIL_MAX_SIZE
    ) -> Tuple[int, int]:
        """
        Calculate thumbnail dimensions maintaining aspect ratio.
        
        Args:
            original_size: Tuple of (width, height)
            max_size: Maximum dimension for thumbnail
            
        Returns:
            Tuple of (new_width, new_height)
        """
        width, height = original_size

        if width > height:
            new_width = max_size
            new_height = int((height * max_size) / width)
        else:
            new_height = max_size
            new_width = int((width * max_size) / height)

        return new_width, new_height

    @staticmethod
    def correct_image_orientation(image: Image.Image) -> Image.Image:
        """
        Correct image orientation based on EXIF data.
        
        Args:
            image: PIL Image object
            
        Returns:
            Rotated image if needed, otherwise original
        """
        try:
            exif = image.getexif()
            if exif and ORIENTATION in exif:
                orientation = exif[ORIENTATION]

                if orientation == 3:
                    return image.rotate(180, expand=True)
                elif orientation == 6:
                    return image.rotate(270, expand=True)
                elif orientation == 8:
                    return image.rotate(90, expand=True)
        except Exception as e:
            logger.warning(f"Error correcting image orientation: {e}")

        return image

    @staticmethod
    def prepare_image_for_thumbnail(image: Image.Image) -> Image.Image:
        """
        Prepare image for thumbnail generation.
        Corrects orientation and converts to RGB if needed.
        
        Args:
            image: PIL Image object
            
        Returns:
            Prepared image ready for thumbnail generation
        """
        # Correct orientation
        image = ImageUtils.correct_image_orientation(image)

        # Convert to RGB if necessary (handles RGBA, P, LA modes)
        if image.mode in ("RGBA", "P", "LA"):
            image = image.convert("RGB")

        return image

    @staticmethod
    def create_thumbnail(
        image: Image.Image, 
        max_size: int = THUMBNAIL_MAX_SIZE
    ) -> Image.Image:
        """
        Create thumbnail from image.
        
        Args:
            image: PIL Image object
            max_size: Maximum dimension
            
        Returns:
            Thumbnail image
        """
        original_size = image.size
        new_size = ImageUtils.calculate_thumbnail_dimensions(original_size, max_size)
        return image.resize(new_size, Image.Resampling.LANCZOS)

    @staticmethod
    def generate_thumbnail_bytes(
        image_data: bytes,
        max_size: int = THUMBNAIL_MAX_SIZE,
        quality: int = THUMBNAIL_QUALITY,
        optimize: bool = THUMBNAIL_OPTIMIZE
    ) -> bytes:
        """
        Generate thumbnail bytes from image data.
        
        Args:
            image_data: Raw image bytes
            max_size: Maximum thumbnail dimension
            quality: JPEG quality (1-100)
            optimize: Whether to optimize file size
            
        Returns:
            Thumbnail as JPEG bytes
            
        Raises:
            ImageProcessingError: If thumbnail generation fails
        """
        try:
            # Load image from bytes
            image = Image.open(io.BytesIO(image_data))
            
            # Prepare image for thumbnail
            image = ImageUtils.prepare_image_for_thumbnail(image)
            
            # Create thumbnail
            thumbnail = ImageUtils.create_thumbnail(image, max_size)
            
            # Save to bytes
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(
                thumbnail_buffer, 
                'JPEG', 
                quality=quality, 
                optimize=optimize
            )
            thumbnail_buffer.seek(0)
            
            return thumbnail_buffer.read()
            
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            raise ImageProcessingError(f"Thumbnail generation failed: {e}")


class FileUtils:
    """Utility class for common file operations"""

    @staticmethod
    def create_temp_file_from_bytes(file_data: bytes, filename: str) -> str:
        """
        Create temporary file from bytes.
        
        Args:
            file_data: Raw file bytes
            filename: Original filename (for extension)
            
        Returns:
            Path to temporary file
            
        Raises:
            ImageProcessingError: If file is empty or filename missing
        """
        if not filename:
            raise ImageProcessingError("Nome file mancante")
        
        if len(file_data) == 0:
            raise ImageProcessingError("Contenuto file vuoto")

        with tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=Path(filename).suffix
        ) as tmp_file:
            tmp_file.write(file_data)
            return tmp_file.name

    @staticmethod
    async def create_temp_file_from_upload(file: UploadFile) -> str:
        """
        Create temporary file from FastAPI UploadFile.
        
        Args:
            file: FastAPI UploadFile object
            
        Returns:
            Path to temporary file
            
        Raises:
            ImageProcessingError: If file is empty
        """
        content = await file.read()
        await file.seek(0)  # Reset pointer for potential reuse
        
        if len(content) == 0:
            raise ImageProcessingError("File vuoto")
        
        suffix = Path(file.filename).suffix if file.filename else '.tmp'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(content)
            return tmp_file.name

    @staticmethod
    def cleanup_temp_file(file_path: str) -> bool:
        """
        Clean up temporary file.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if deleted, False if error
        """
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                return True
        except Exception as e:
            logger.warning(f"Error cleaning up temp file {file_path}: {e}")
        return False

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """
        Get lowercase file extension from filename.
        
        Args:
            filename: Name of file
            
        Returns:
            Lowercase extension including dot (e.g., '.jpg')
        """
        return Path(filename).suffix.lower() if filename else ''

    @staticmethod
    def get_file_size(file_path: str) -> Optional[int]:
        """
        Get file size in bytes.
        
        Args:
            file_path: Path to file
            
        Returns:
            File size in bytes, or None if error
        """
        try:
            return os.path.getsize(file_path)
        except Exception:
            return None


# Convenience exports
__all__ = ['ImageUtils', 'FileUtils']
