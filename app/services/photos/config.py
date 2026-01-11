# app/services/photos/config.py - Photo service configuration constants

"""
Centralized configuration for photo processing services.
All magic numbers and constants should be defined here.
"""

# =============================================================================
# IMAGE PROCESSING LIMITS
# =============================================================================

# Maximum image pixels PIL/Pillow will process (prevents decompression bombs)
# Default is ~179M pixels, we increase to 400M pixels for large archaeological images
MAX_IMAGE_PIXELS = 400_000_000  # 400M pixels

# =============================================================================
# THUMBNAIL CONFIGURATION
# =============================================================================

# Maximum dimension (width or height) for thumbnails
THUMBNAIL_MAX_SIZE = 800  # pixels

# JPEG quality for thumbnail compression (1-100)
THUMBNAIL_QUALITY = 85

# Whether to optimize thumbnail file size
THUMBNAIL_OPTIMIZE = True

# =============================================================================
# DEEP ZOOM CONFIGURATION
# =============================================================================

# Minimum image dimension (max of width/height) to trigger deep zoom tile generation
# Images smaller than this will not have tiles generated
MIN_DIMENSION_FOR_TILES = 2000  # pixels

# =============================================================================
# SUPPORTED FORMATS
# =============================================================================

# File extensions that can be processed as images
SUPPORTED_IMAGE_FORMATS = frozenset({
    '.jpg', '.jpeg',  # JPEG
    '.png',           # PNG
    '.tiff', '.tif',  # TIFF
    '.bmp',           # Bitmap
    '.webp',          # WebP
    '.gif',           # GIF (single frame)
})

# Raw camera formats (read-only support via rawpy if available)
SUPPORTED_RAW_FORMATS = frozenset({
    '.raw',   # Generic RAW
    '.cr2',   # Canon RAW 2
    '.cr3',   # Canon RAW 3
    '.nef',   # Nikon Electronic Format
    '.arw',   # Sony Alpha RAW
    '.dng',   # Adobe Digital Negative
    '.orf',   # Olympus RAW
    '.rw2',   # Panasonic RAW
})

# All supported formats combined
ALL_SUPPORTED_FORMATS = SUPPORTED_IMAGE_FORMATS | SUPPORTED_RAW_FORMATS

# =============================================================================
# MIME TYPE MAPPINGS
# =============================================================================

MIME_TYPES = {
    # Standard image formats
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.tiff': 'image/tiff',
    '.tif': 'image/tiff',
    '.bmp': 'image/bmp',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    
    # RAW formats (vendor-specific MIME types)
    '.raw': 'image/x-raw',
    '.cr2': 'image/x-canon-cr2',
    '.cr3': 'image/x-canon-cr3',
    '.nef': 'image/x-nikon-nef',
    '.arw': 'image/x-sony-arw',
    '.dng': 'image/x-adobe-dng',
    '.orf': 'image/x-olympus-orf',
    '.rw2': 'image/x-panasonic-rw2',
}

# Default MIME type for unknown extensions
DEFAULT_MIME_TYPE = 'application/octet-stream'


def get_mime_type(filename: str) -> str:
    """
    Get MIME type for a filename based on its extension.
    
    Args:
        filename: Name of the file (with extension)
        
    Returns:
        MIME type string
    """
    from pathlib import Path
    extension = Path(filename).suffix.lower()
    return MIME_TYPES.get(extension, DEFAULT_MIME_TYPE)


def is_supported_format(filename: str) -> bool:
    """
    Check if a filename has a supported image format extension.
    
    Args:
        filename: Name of the file to check
        
    Returns:
        True if supported, False otherwise
    """
    from pathlib import Path
    extension = Path(filename).suffix.lower()
    return extension in ALL_SUPPORTED_FORMATS
