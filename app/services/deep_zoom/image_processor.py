from typing import Tuple, Optional, Any
from PIL import Image
import io
import math
from loguru import logger
from app.core.interfaces.image import ImageProcessorInterface

class DeepZoomImageProcessor(ImageProcessorInterface):
    """
    Implementation of ImageProcessorInterface using PIL/Pillow.
    Handles all image manipulation logic for Deep Zoom tile generation.
    """
    
    def __init__(self):
        # Configure PIL limits
        Image.MAX_IMAGE_PIXELS = 933120000  # Large enough for archaeological photos
    
    def open_image(self, file_content: bytes) -> Any:
        """Open an image from bytes"""
        try:
            return Image.open(io.BytesIO(file_content))
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            raise ValueError(f"Invalid image content: {e}")

    def get_dimensions(self, image: Any) -> Tuple[int, int]:
        """Get image dimensions (width, height)"""
        return image.size

    def resize_for_tile(self, image: Any, tile_size: int, overlap: int, 
                       level: int, col: int, row: int) -> Optional[bytes]:
        """
        Process a specific tile from the image.
        Returns the tile data as bytes or None if tile is invalid/empty.
        """
        try:
            # Calculate the scale factor for this level
            max_dimension = max(image.size)
            scale = 1 / (2 ** level)
            
            # Tile coordinates in the original image space
            x = col * tile_size / scale
            y = row * tile_size / scale
            
            # Dimensions of the tile in the original image space
            w = tile_size / scale
            h = tile_size / scale
            
            # Add overlap
            if overlap > 0:
                x -= overlap / scale
                y -= overlap / scale
                w += (2 * overlap) / scale
                h += (2 * overlap) / scale
            
            # Crop the region from original image
            # Note: PIL crop expects (left, upper, right, lower)
            crop_box = (
                max(0, math.floor(x)),
                max(0, math.floor(y)),
                min(image.width, math.ceil(x + w)),
                min(image.height, math.ceil(y + h))
            )
            
            # If crop box has no area, skip
            if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                return None
                
            tile_image = image.crop(crop_box)
            
            # Resize locally to output size (usually 256x256 unless edge tile)
            target_w = math.ceil((crop_box[2] - crop_box[0]) * scale)
            target_h = math.ceil((crop_box[3] - crop_box[1]) * scale)
            
            # Use LANCZOS for high quality downsampling
            tile_image = tile_image.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            # Use RGB to ensure compatibility (remove alpha if present unless PNG requested)
            if tile_image.mode in ('RGBA', 'LA') and False: # Force format logic can go here
                background = Image.new('RGB', tile_image.size, (255, 255, 255))
                background.paste(tile_image, mask=tile_image.split()[-1])
                tile_image = background
            elif tile_image.mode != 'RGB':
                tile_image = tile_image.convert('RGB')
                
            tile_image.save(output, format='JPEG', quality=90, optimize=True)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error processing tile {level}/{col}_{row}: {e}")
            return None
    
    def validate_image(self, file_content: bytes) -> bool:
        """Validate if content is a valid image"""
        try:
            with Image.open(io.BytesIO(file_content)) as img:
                img.verify()
            return True
        except Exception:
            return False
