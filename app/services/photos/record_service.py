# app/services/photos/record_service.py - Photo record creation service

"""
Service for creating and managing Photo database records.
Handles record creation, enum conversion, and field validation.
"""

from typing import Dict, Any, Optional, Union
from uuid import UUID
from pathlib import Path

from loguru import logger

from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.core.domain_exceptions import PhotoServiceError
from .config import get_mime_type


class PhotoRecordService:
    """Service for creating Photo database records"""

    async def create_photo_record(
        self,
        filename: str,
        original_filename: str,
        file_path: str,
        file_size: int,
        site_id: Union[str, UUID],
        uploaded_by: Union[str, UUID],
        metadata: Optional[Dict[str, Any]] = None,
        archaeological_metadata: Optional[Dict[str, Any]] = None,
        thumbnail_path: Optional[str] = None
    ) -> Photo:
        """
        Create Photo model instance with extracted metadata.
        
        Args:
            filename: Unique filename for storage
            original_filename: Original uploaded filename
            file_path: Path/URL to stored file
            file_size: File size in bytes
            site_id: Site identifier
            uploaded_by: User identifier
            metadata: Technical metadata from image
            archaeological_metadata: Archaeological form data
            thumbnail_path: Path to thumbnail
            
        Returns:
            Photo model instance (not yet persisted)
            
        Raises:
            PhotoServiceError: If record creation fails
        """
        if metadata is None:
            metadata = {}
        if archaeological_metadata is None:
            archaeological_metadata = {}

        # Ensure UUIDs are strings for SQLite compatibility
        if not isinstance(site_id, str):
            site_id = str(site_id)
        if not isinstance(uploaded_by, str):
            uploaded_by = str(uploaded_by)

        # Build photo data dictionary
        photo_data = {
            "filename": filename,
            "original_filename": original_filename,
            "filepath": file_path,
            "thumbnail_path": thumbnail_path,
            "file_size": file_size,
            "mime_type": get_mime_type(filename),
            "site_id": site_id,
            "uploaded_by": uploaded_by,
            "created_by": uploaded_by,

            # Technical metadata
            "width": metadata.get('width'),
            "height": metadata.get('height'),

            # EXIF metadata
            "photo_date": metadata.get('photo_date'),
            "camera_model": metadata.get('camera_model'),
            "lens": metadata.get('lens'),
            "photographer": (
                archaeological_metadata.get('photographer') or 
                metadata.get('photographer')
            ),

            # Archaeological metadata
            "inventory_number": archaeological_metadata.get('inventory_number'),
            "excavation_area": archaeological_metadata.get('excavation_area'),
            "stratigraphic_unit": archaeological_metadata.get('stratigraphic_unit'),
            "find_date": archaeological_metadata.get('find_date'),
            "material": self._convert_to_enum(
                MaterialType, 
                archaeological_metadata.get('material')
            ),
            "object_type": archaeological_metadata.get('object_type'),
            "chronology_period": archaeological_metadata.get('chronology_period'),
            "conservation_status": self._convert_to_enum(
                ConservationStatus, 
                archaeological_metadata.get('conservation_status')
            ),
            "photo_type": self._convert_to_enum(
                PhotoType, 
                archaeological_metadata.get('photo_type')
            ),
            "description": archaeological_metadata.get('description'),
            "keywords": self._convert_keywords_to_string(
                archaeological_metadata.get('keywords')
            ),

            # Initial state
            "is_published": False,
            "is_validated": False
        }

        # Filter to only valid Photo model fields
        valid_photo_fields = {col.name for col in Photo.__table__.columns}
        
        filtered_photo_data = {}
        for key, value in photo_data.items():
            if key in valid_photo_fields:
                filtered_photo_data[key] = value
            else:
                logger.debug(f"Excluding '{key}' field from Photo model (not in model)")

        # Remove None values to avoid errors
        filtered_photo_data = {
            k: v for k, v in filtered_photo_data.items() if v is not None
        }

        try:
            photo = Photo(**filtered_photo_data)
            logger.debug(
                f"Photo record created successfully with "
                f"{len(filtered_photo_data)} fields"
            )
            return photo
            
        except Exception as e:
            logger.error(f"Error creating Photo record: {e}")
            logger.error(f"Photo data fields: {list(filtered_photo_data.keys())}")
            
            # Try with minimal fields as fallback
            return await self._create_minimal_photo_record(
                filename, original_filename, file_path, thumbnail_path,
                file_size, site_id, uploaded_by
            )

    async def _create_minimal_photo_record(
        self,
        filename: str,
        original_filename: str,
        file_path: str,
        thumbnail_path: Optional[str],
        file_size: int,
        site_id: str,
        uploaded_by: str
    ) -> Photo:
        """Create photo record with minimal required fields"""
        try:
            minimal_data = {
                "filename": filename,
                "original_filename": original_filename,
                "filepath": file_path,
                "thumbnail_path": thumbnail_path,
                "file_size": file_size,
                "site_id": site_id,
                "uploaded_by": uploaded_by,
                "created_by": uploaded_by,
                "mime_type": get_mime_type(filename),
            }
            photo = Photo(**minimal_data)
            logger.warning("Photo record created with minimal fields due to error")
            return photo
            
        except Exception as fallback_error:
            logger.error(f"Even minimal Photo creation failed: {fallback_error}")
            raise PhotoServiceError(f"Failed to create Photo record: {fallback_error}")

    def _convert_to_enum(self, enum_class, value):
        """
        Convert string to enum using centralized converter.
        
        Args:
            enum_class: Target enum class
            value: Value to convert (Italian or English)
            
        Returns:
            Enum instance or None if conversion fails
        """
        if value is None:
            return None
            
        if isinstance(value, enum_class):
            return value
            
        try:
            from app.utils.enum_mappings import enum_converter, log_conversion_attempt
            
            converted_value = enum_converter.convert_to_enum(enum_class, value)
            
            success = converted_value is not None
            log_conversion_attempt(enum_class, str(value), converted_value, success)
            
            return converted_value
            
        except ImportError:
            # Fallback to basic conversion
            logger.warning("enum_mappings not available, using basic conversion")
            try:
                return enum_class(value)
            except ValueError:
                logger.warning(f"Invalid value for {enum_class.__name__}: {value}")
                return None
        except Exception as e:
            logger.error(f"Error converting '{value}' to {enum_class.__name__}: {e}")
            return None

    def _convert_keywords_to_string(self, keywords) -> Optional[str]:
        """
        Convert keywords from list to string for SQLite database.
        
        Args:
            keywords: Keywords (list, string, or None)
            
        Returns:
            Comma-separated string or None
        """
        if keywords is None:
            return None
        
        if isinstance(keywords, str):
            return keywords.strip() if keywords.strip() else None
        
        if isinstance(keywords, list):
            valid_keywords = [
                str(k).strip() for k in keywords 
                if k and str(k).strip()
            ]
            return ", ".join(valid_keywords) if valid_keywords else None
        
        # Other types: convert to string
        try:
            keyword_str = str(keywords)
            return keyword_str if keyword_str.strip() else None
        except Exception:
            return None


# Global instance
photo_record_service = PhotoRecordService()

__all__ = ['PhotoRecordService', 'photo_record_service']
