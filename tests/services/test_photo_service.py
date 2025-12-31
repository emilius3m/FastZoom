"""
Tests for PhotoService.
"""

import pytest
import io
from PIL import Image

from app.services.photo_service import PhotoMetadataService


@pytest.mark.unit
def test_extract_metadata_from_bytes():
    """Test extracting metadata from image bytes."""
    # Arrange
    metadata_service = PhotoMetadataService()
    
    # Create a simple test image in memory
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    image_data = img_bytes.getvalue()
    
    # Save to temporary file for extraction
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
        tmp_file.write(image_data)
        tmp_file_path = tmp_file.name
    
    try:
        # Act
        exif_data, photo_metadata = metadata_service.extract_metadata(
            file_path=tmp_file_path,
            filename="test_image.jpg"
        )
        
        # Assert
        assert photo_metadata is not None
        assert "width" in photo_metadata
        assert "height" in photo_metadata
        assert photo_metadata["width"] == 100
        assert photo_metadata["height"] == 100
        assert photo_metadata["format"] == "JPEG"
        
    finally:
        # Cleanup
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
