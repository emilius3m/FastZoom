"""Repository layer for FastAPI application."""

from .base import BaseRepository
from .geographic_maps import GeographicMapRepository
from .iccd_records import ICCDRecordRepository

__all__ = [
    "BaseRepository",
    "GeographicMapRepository", 
    "ICCDRecordRepository"
]