# app/services/photos/__init__.py - Photo services package

"""
Photo services package providing modular photo processing functionality.

This package contains specialized services for different aspects of photo handling:
- config: Centralized configuration and constants
- image_utils: Image and file utility functions
- metadata_service: EXIF and technical metadata extraction
- thumbnail_service: Thumbnail generation and upload
- record_service: Photo database record management
- processing_service: Main orchestration service
- upload_service: Standard photo upload handling
- bulk_service: Bulk operations (update, delete)
- deletion_service: Photo deletion with storage cleanup
- query_service: Photo querying and filtering
- deepzoom_service: Deep zoom tile generation
"""

# Configuration
from .config import (
    MAX_IMAGE_PIXELS,
    THUMBNAIL_MAX_SIZE,
    THUMBNAIL_QUALITY,
    MIN_DIMENSION_FOR_TILES,
    SUPPORTED_IMAGE_FORMATS,
    MIME_TYPES,
    get_mime_type,
    is_supported_format,
)

# Utilities
from .image_utils import ImageUtils, FileUtils

# New refactored services
from .metadata_service import PhotoMetadataExtractor, photo_metadata_extractor
from .thumbnail_service import ThumbnailService, thumbnail_service
from .record_service import PhotoRecordService, photo_record_service
from .processing_service import PhotoProcessingService, photo_processing_service

# Existing services (classes only - some don't have global instances)
from .upload_service import PhotoUploadService, photo_upload_service
from .bulk_service import PhotoBulkService  # No global instance
from .deletion_service import PhotoDeletionService, photo_deletion_service
from .query_service import PhotoQueryService, photo_query_service
from .deepzoom_service import PhotoDeepZoomService, photo_deepzoom_service


__all__ = [
    # Configuration
    'MAX_IMAGE_PIXELS',
    'THUMBNAIL_MAX_SIZE',
    'THUMBNAIL_QUALITY',
    'MIN_DIMENSION_FOR_TILES',
    'SUPPORTED_IMAGE_FORMATS',
    'MIME_TYPES',
    'get_mime_type',
    'is_supported_format',
    
    # Utilities
    'ImageUtils',
    'FileUtils',
    
    # New services
    'PhotoMetadataExtractor',
    'photo_metadata_extractor',
    'ThumbnailService',
    'thumbnail_service',
    'PhotoRecordService',
    'photo_record_service',
    'PhotoProcessingService',
    'photo_processing_service',
    
    # Existing services
    'PhotoUploadService',
    'photo_upload_service',
    'PhotoBulkService',
    'PhotoDeletionService',
    'photo_deletion_service',
    'PhotoQueryService',
    'photo_query_service',
    'PhotoDeepZoomService',
    'photo_deepzoom_service',
]
