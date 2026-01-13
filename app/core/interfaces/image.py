from abc import ABC, abstractmethod
from typing import Tuple, Optional, Any, Dict

class ImageProcessorInterface(ABC):
    """
    Interface for image processing operations.
    Abstracts dependencies on PIL or other image libraries.
    """

    @abstractmethod
    def open_image(self, file_content: bytes) -> Any:
        """Open an image from bytes"""
        pass

    @abstractmethod
    def get_dimensions(self, image: Any) -> Tuple[int, int]:
        """Get image dimensions (width, height)"""
        pass

    @abstractmethod
    def resize_for_tile(self, image: Any, tile_size: int, overlap: int, 
                       level: int, col: int, row: int) -> Optional[bytes]:
        """
        Process a specific tile from the image.
        Returns the tile data as bytes or None if tile is invalid/empty.
        """
        pass
    
    @abstractmethod
    def validate_image(self, file_content: bytes) -> bool:
        """Validate if content is a valid image"""
        pass
