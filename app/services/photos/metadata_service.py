# app/services/photos/metadata_service.py - Photo metadata extraction service

"""
Service for extracting metadata from images.
Handles EXIF data, technical metadata, and GPS information.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from loguru import logger

from app.core.domain_exceptions import ImageProcessingError
from .config import MAX_IMAGE_PIXELS, SUPPORTED_IMAGE_FORMATS
from .image_utils import FileUtils


class PhotoMetadataExtractor:
    """Service for extracting metadata from images"""

    def __init__(self):
        self.supported_formats = SUPPORTED_IMAGE_FORMATS
        self._configure_pil_limits()

    def _configure_pil_limits(self):
        """Configure PIL/Pillow limits for handling large images safely"""
        try:
            old_limit = getattr(Image, 'MAX_IMAGE_PIXELS', None)
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            
            if hasattr(Image, 'preinit'):
                Image.preinit()

            logger.debug(
                f"PIL limits configured: MAX_IMAGE_PIXELS increased from "
                f"{old_limit} to {Image.MAX_IMAGE_PIXELS}"
            )
        except Exception as e:
            logger.warning(f"Could not configure PIL limits: {e}")

    async def extract_metadata(
        self,
        file_path: str,
        filename: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extract technical and EXIF metadata from image.
        
        Args:
            file_path: Path to image file
            filename: Original filename
            
        Returns:
            Tuple of (exif_data, combined_metadata)
        """
        try:
            image_path = Path(file_path)

            # Extract technical metadata
            technical_metadata = await self._extract_technical_metadata(
                image_path, filename
            )

            # Extract EXIF metadata
            exif_data = await self._extract_exif_data(image_path)

            # Combine metadata
            photo_metadata = {
                **technical_metadata,
                **exif_data
            }

            logger.info(f"Metadata extracted for {filename}")
            return exif_data, photo_metadata

        except ImageProcessingError:
            raise
        except Exception as e:
            logger.error(f"Error extracting metadata from {filename}: {e}")
            return {}, {}

    async def extract_metadata_from_bytes(
        self,
        file_data: bytes,
        filename: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extract metadata from image bytes.
        
        Args:
            file_data: Raw image bytes
            filename: Original filename
            
        Returns:
            Tuple of (exif_data, combined_metadata)
        """
        temp_file_path = None
        try:
            temp_file_path = FileUtils.create_temp_file_from_bytes(file_data, filename)
            exif_data, metadata = await self.extract_metadata(temp_file_path, filename)
            return exif_data, metadata

        except ImageProcessingError:
            raise
        except Exception as e:
            logger.error(f"Error extracting metadata from bytes {filename}: {e}")
            return {}, {}
        finally:
            if temp_file_path:
                FileUtils.cleanup_temp_file(temp_file_path)

    async def _extract_technical_metadata(
        self,
        image_path: Path,
        filename: str
    ) -> Dict[str, Any]:
        """Extract basic technical metadata from image"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size

                return {
                    "width": width,
                    "height": height,
                    "dpi": self._extract_dpi(img),
                    "color_profile": self._extract_color_profile(img),
                    "image_format": img.format,
                    "image_mode": img.mode
                }

        except Exception as e:
            logger.warning(f"Could not extract technical metadata for {filename}: {e}")
            return {}

    def _extract_dpi(self, image: Image.Image) -> Optional[float]:
        """Extract DPI from image"""
        try:
            if hasattr(image, 'info') and 'dpi' in image.info:
                dpi = image.info['dpi']
                return dpi[0] if isinstance(dpi, tuple) else dpi
        except Exception as e:
            logger.warning(f"Error extracting DPI: {e}")
        return None

    def _extract_color_profile(self, image: Image.Image) -> Optional[str]:
        """Extract color profile from image"""
        try:
            if image.mode in ['RGB', 'CMYK', 'LAB']:
                return image.mode
        except Exception as e:
            logger.warning(f"Error extracting color profile: {e}")
        return None

    async def _extract_exif_data(self, image_path: Path) -> Dict[str, Any]:
        """Extract EXIF metadata from image"""
        try:
            with Image.open(image_path) as img:
                exif_dict = await self._extract_exif_dictionary(img)
                extracted_data = await self._extract_specific_exif_data(exif_dict)

                # Create JSON-serializable EXIF data
                extracted_data['exif_data'] = self._make_exif_serializable(exif_dict)

                return extracted_data

        except Exception as e:
            logger.warning(f"Could not extract EXIF data: {e}")
            return {}

    async def _extract_exif_dictionary(self, image: Image.Image) -> Dict[str, Any]:
        """Extract EXIF dictionary from image"""
        exif_dict = {}

        # Try modern getexif() method
        try:
            exif_data = image.getexif()
            if exif_data:
                exif_dict = self._process_exif_tags(exif_data)
        except Exception:
            # Fallback to legacy method
            if hasattr(image, '_getexif') and image._getexif() is not None:
                exif_info = image._getexif()
                exif_dict = self._process_exif_tags(exif_info)

        return exif_dict

    def _process_exif_tags(self, exif_data) -> Dict[str, Any]:
        """Process EXIF tags and handle different types"""
        processed_dict = {}

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)

            # Handle bytes values
            if isinstance(value, bytes):
                try:
                    value = value.decode('utf-8')
                except UnicodeDecodeError:
                    value = str(value)

            processed_dict[tag] = value

        return processed_dict

    async def _extract_specific_exif_data(
        self, 
        exif_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract specific fields from EXIF dictionary"""
        extracted_data = {}

        # Photo date
        extracted_data['photo_date'] = self._extract_photo_date(exif_dict)

        # Camera info
        if 'Model' in exif_dict:
            extracted_data['camera_model'] = str(exif_dict['Model']).strip()

        if 'Make' in exif_dict:
            extracted_data['camera_make'] = str(exif_dict['Make']).strip()

        # Lens
        if 'LensModel' in exif_dict:
            extracted_data['lens'] = str(exif_dict['LensModel']).strip()

        # Software
        if 'Software' in exif_dict:
            extracted_data['software'] = str(exif_dict['Software']).strip()

        # Orientation
        if 'Orientation' in exif_dict:
            extracted_data['orientation'] = exif_dict['Orientation']

        # GPS data
        gps_data = self._extract_gps_data(exif_dict)
        if gps_data:
            extracted_data['gps_data'] = gps_data

        return extracted_data

    def _extract_photo_date(self, exif_dict: Dict[str, Any]) -> Optional[datetime]:
        """Extract photo date from EXIF dictionary"""
        for date_field in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
            if date_field in exif_dict:
                try:
                    return datetime.strptime(
                        exif_dict[date_field], 
                        '%Y:%m:%d %H:%M:%S'
                    )
                except (ValueError, TypeError):
                    continue
        return None

    def _make_exif_serializable(self, exif_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Make EXIF dictionary JSON serializable"""
        serializable_exif = {}

        for key, value in exif_dict.items():
            try:
                # Handle IFDRational from PIL
                if hasattr(value, '__class__') and 'IFDRational' in value.__class__.__name__:
                    try:
                        serializable_exif[key] = float(value)
                    except (ValueError, TypeError):
                        serializable_exif[key] = str(value)
                else:
                    # Test normal serialization
                    json.dumps(value)
                    serializable_exif[key] = value
            except (TypeError, ValueError):
                # Fallback to string for any non-serializable type
                serializable_exif[key] = str(value)

        return serializable_exif

    def _extract_gps_data(self, exif_dict: Dict) -> Optional[Dict[str, Any]]:
        """Extract GPS data from EXIF dictionary"""
        try:
            gps_info = {}

            # Look for GPSInfo tag
            if 'GPSInfo' in exif_dict:
                gps_raw = exif_dict['GPSInfo']
                if isinstance(gps_raw, dict):
                    for tag_id, value in gps_raw.items():
                        gps_tag = GPSTAGS.get(tag_id, tag_id)
                        gps_info[gps_tag] = value

            # Look for individual GPS tags
            for tag_id, value in exif_dict.items():
                tag = TAGS.get(tag_id, tag_id)
                if isinstance(tag, str) and tag.startswith('GPS'):
                    gps_tag = GPSTAGS.get(tag_id, tag_id)
                    gps_info[gps_tag] = value

            return gps_info if gps_info else None

        except Exception as e:
            logger.warning(f"Could not extract GPS data: {e}")
            return None


# Global instance
photo_metadata_extractor = PhotoMetadataExtractor()

__all__ = ['PhotoMetadataExtractor', 'photo_metadata_extractor']
