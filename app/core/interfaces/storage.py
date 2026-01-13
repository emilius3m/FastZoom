from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class FileStorageInterface(ABC):
    """
    Interface for file storage operations.
    Abstracts direct dependencies on MinIO or other storage providers.
    """

    @abstractmethod
    async def upload_file(
        self, 
        data: bytes, 
        bucket: str, 
        object_name: str, 
        content_type: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Upload a file to storage"""
        pass

    @abstractmethod
    async def get_file(self, bucket: str, object_name: str) -> bytes:
        """Retrieve file content from storage"""
        pass
    
    @abstractmethod
    async def upload_deep_zoom_tile(
        self,
        tile_data: bytes,
        site_id: str,
        object_name: str,
        content_type: str,
        tile_metadata: Dict[str, Any]
    ) -> str:
        """Upload a deep zoom tile with specific optimization/retry logic"""
        pass
