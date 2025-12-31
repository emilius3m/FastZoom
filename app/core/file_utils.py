"""
app/core/file_utils.py
Utility functions and classes for file handling.
Provides framework-agnostic file handling to keep services independent from FastAPI.
"""

from typing import Dict, Any, BinaryIO, Tuple
from io import BytesIO
from fastapi import UploadFile
from loguru import logger


class FileAdapter:
    """
    Adapter for converting FastAPI UploadFile to framework-agnostic formats.
    Helps services stay independent from web framework details.
    """
    
    @staticmethod
    async def read_upload_file(file: UploadFile) -> bytes:
        """
        Read complete file content from UploadFile.
        
        Args:
            file: FastAPI UploadFile instance
            
        Returns:
            Complete file content as bytes
        """
        try:
            contents = await file.read()
            await file.seek(0)  # Reset file pointer for potential re-reads
            return contents
        except Exception as e:
            logger.error(f"Error reading upload file {file.filename}: {e}")
            raise
    
    @staticmethod
    async def get_file_info(file: UploadFile) -> Dict[str, Any]:
        """
        Extract metadata from UploadFile.
        
        Args:
            file: FastAPI UploadFile instance
            
        Returns:
            Dictionary containing:
                - filename: Original filename
                - content_type: MIME type
                - size: File size in bytes
        """
        try:
            # Read file to get size
            contents = await file.read()
            size = len(contents)
            await file.seek(0)  # Reset for subsequent reads
            
            return {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": size
            }
        except Exception as e:
            logger.error(f"Error extracting file info from {file.filename}: {e}")
            raise
    
    @staticmethod
    def bytes_to_binary_io(data: bytes) -> BinaryIO:
        """
        Convert bytes to BinaryIO stream.
        
        Args:
            data: File content as bytes
            
        Returns:
            BinaryIO stream
        """
        return BytesIO(data)
    
    @staticmethod
    async def adapt_upload_file(file: UploadFile) -> Tuple[bytes, str, str]:
        """
        Convert UploadFile to tuple format for service layer.
        
        Args:
            file: FastAPI UploadFile instance
            
        Returns:
            Tuple of (file_data, filename, content_type)
        """
        file_data = await FileAdapter.read_upload_file(file)
        return (file_data, file.filename, file.content_type or "application/octet-stream")
    
    @staticmethod
    async def adapt_multiple_upload_files(files: list[UploadFile]) -> list[Tuple[bytes, str, str]]:
        """
        Convert multiple UploadFiles to service layer format.
        
        Args:
            files: List of FastAPI UploadFile instances
            
        Returns:
            List of tuples (file_data, filename, content_type)
        """
        adapted_files = []
        for file in files:
            adapted = await FileAdapter.adapt_upload_file(file)
            adapted_files.append(adapted)
        return adapted_files


class FileValidator:
    """
    File validation utilities.
    Provides common validation functions for uploaded files.
    """
    
    # Common MIME types
    IMAGE_TYPES = {
        'image/jpeg', 'image/jpg', 'image/png', 
        'image/gif', 'image/webp', 'image/tiff', 'image/bmp'
    }
    
    PDF_TYPES = {'application/pdf'}
    
    DOCUMENT_TYPES = {
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    }
    
    @staticmethod
    def validate_file_size(file_size: int, max_size_mb: int = 50) -> bool:
        """
        Validate file size.
        
        Args:
            file_size: File size in bytes
            max_size_mb: Maximum allowed size in megabytes
            
        Returns:
            True if valid, False otherwise
        """
        max_bytes = max_size_mb * 1024 * 1024
        return file_size <= max_bytes
    
    @staticmethod
    def validate_content_type(content_type: str, allowed_types: set[str]) -> bool:
        """
        Validate file content type.
        
        Args:
            content_type: MIME type of the file
            allowed_types: Set of allowed MIME types
            
        Returns:
            True if valid, False otherwise
        """
        return content_type in allowed_types
    
    @staticmethod
    def validate_image_file(content_type: str, file_size: int, max_size_mb: int = 50) -> Tuple[bool, str]:
        """
        Validate image file.
        
        Args:
            content_type: MIME type
            file_size: Size in bytes
            max_size_mb: Maximum size limit
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not FileValidator.validate_content_type(content_type, FileValidator.IMAGE_TYPES):
            return False, f"Invalid file type: {content_type}. Must be an image."
        
        if not FileValidator.validate_file_size(file_size, max_size_mb):
            return False, f"File too large: {file_size / (1024*1024):.2f}MB. Maximum: {max_size_mb}MB"
        
        return True, ""
    
    @staticmethod
    def validate_pdf_file(content_type: str, file_size: int, max_size_mb: int = 100) -> Tuple[bool, str]:
        """
        Validate PDF file.
        
        Args:
            content_type: MIME type
            file_size: Size in bytes
            max_size_mb: Maximum size limit
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not FileValidator.validate_content_type(content_type, FileValidator.PDF_TYPES):
            return False, f"Invalid file type: {content_type}. Must be PDF."
        
        if not FileValidator.validate_file_size(file_size, max_size_mb):
            return False, f"File too large: {file_size / (1024*1024):.2f}MB. Maximum: {max_size_mb}MB"
        
        return True, ""
