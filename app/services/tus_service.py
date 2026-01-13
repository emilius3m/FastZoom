"""
TusPy Service for Resumable File Uploads
Handles chunked uploads using the TUS protocol
"""
import os
import shutil
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4
import aiofiles
from loguru import logger

from app.core.config import get_settings
from app.core.domain_exceptions import (
    FileUploadError,
    ValidationError,
    StorageError
)


class TusUploadService:
    """Service for handling TUS protocol resumable uploads"""
    
    def __init__(self):
        self.settings = get_settings()
        self.upload_dir = Path(self.settings.tus_upload_dir)
        self.metadata_dir = self.upload_dir / ".metadata"
        self.max_size = self.settings.tus_max_size
        self.chunk_size = self.settings.tus_chunk_size
        self.expiration_hours = self.settings.tus_expiration_hours
        self.allowed_extensions = set(
            ext.strip().lower() 
            for ext in self.settings.tus_allowed_extensions.split(",")
        )
        
        # Ensure directories exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"TUS Upload Service initialized: {self.upload_dir}")
    
    def _validate_extension(self, filename: str) -> None:
        """Validate file extension"""
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in self.allowed_extensions:
            raise ValidationError(
                f"File extension .{ext} not allowed. "
                f"Allowed: {', '.join(self.allowed_extensions)}"
            )
    
    def _validate_size(self, size: int) -> None:
        """Validate file size"""
        if size > self.max_size:
            max_mb = self.max_size / (1024 * 1024)
            raise ValidationError(
                f"File size {size / (1024*1024):.2f}MB exceeds "
                f"maximum allowed size {max_mb:.2f}MB"
            )
    
    async def create_upload(
        self,
        filename: str,
        upload_length: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new TUS upload session
        
        Args:
            filename: Original filename
            upload_length: Total file size in bytes
            metadata: Optional metadata dict
            
        Returns:
            Upload ID (UUID)
        """
        try:
            # Validate
            self._validate_extension(filename)
            self._validate_size(upload_length)
            
            # Generate upload ID
            upload_id = str(uuid4())
            
            # Create upload file path
            upload_path = self.upload_dir / upload_id
            metadata_path = self.metadata_dir / f"{upload_id}.json"
            
            # Prepare metadata
            upload_metadata = {
                "id": upload_id,
                "filename": filename,
                "upload_length": upload_length,
                "offset": 0,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (
                    datetime.utcnow() + timedelta(hours=self.expiration_hours)
                ).isoformat(),
                "custom_metadata": metadata or {}
            }
            
            # Save metadata
            async with aiofiles.open(metadata_path, "w") as f:
                import json
                await f.write(json.dumps(upload_metadata, indent=2))
            
            # Create empty upload file
            async with aiofiles.open(upload_path, "wb") as f:
                pass
            
            logger.info(
                f"TUS upload created: {upload_id} | "
                f"file={filename} | size={upload_length}"
            )
            
            return upload_id
            
        except (ValidationError, FileUploadError):
            raise
        except Exception as e:
            logger.error(f"Error creating TUS upload: {e}", exc_info=True)
            raise FileUploadError(f"Failed to create upload: {str(e)}")
    
    async def get_upload_metadata(self, upload_id: str) -> Dict[str, Any]:
        """Get metadata for an upload session"""
        metadata_path = self.metadata_dir / f"{upload_id}.json"
        
        if not metadata_path.exists():
            raise ValidationError(f"Upload {upload_id} not found")
        
        try:
            async with aiofiles.open(metadata_path, "r") as f:
                import json
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"Error reading metadata for {upload_id}: {e}")
            raise StorageError(f"Failed to read upload metadata: {str(e)}")
    
    async def append_chunk(
        self,
        upload_id: str,
        chunk_data: bytes,
        offset: int
    ) -> int:
        """
        Append a chunk to an upload
        
        Args:
            upload_id: Upload session ID
            chunk_data: Chunk bytes
            offset: Byte offset in file
            
        Returns:
            New offset after append
        """
        try:
            # Get metadata
            metadata = await self.get_upload_metadata(upload_id)
            
            # Validate offset
            if offset != metadata["offset"]:
                raise ValidationError(
                    f"Offset mismatch. Expected {metadata['offset']}, got {offset}"
                )
            
            # Validate total size
            new_offset = offset + len(chunk_data)
            if new_offset > metadata["upload_length"]:
                raise ValidationError(
                    f"Upload would exceed declared size {metadata['upload_length']}"
                )
            
            # Append chunk
            upload_path = self.upload_dir / upload_id
            async with aiofiles.open(upload_path, "ab") as f:
                await f.write(chunk_data)
            
            # Update metadata
            metadata["offset"] = new_offset
            metadata_path = self.metadata_dir / f"{upload_id}.json"
            async with aiofiles.open(metadata_path, "w") as f:
                import json
                await f.write(json.dumps(metadata, indent=2))
            
            logger.debug(
                f"TUS chunk appended: {upload_id} | "
                f"offset={offset} | size={len(chunk_data)} | "
                f"progress={new_offset}/{metadata['upload_length']}"
            )
            
            return new_offset
            
        except (ValidationError, StorageError):
            raise
        except Exception as e:
            logger.error(f"Error appending chunk to {upload_id}: {e}", exc_info=True)
            raise FileUploadError(f"Failed to append chunk: {str(e)}")
    
    async def is_upload_complete(self, upload_id: str) -> bool:
        """Check if upload is complete"""
        metadata = await self.get_upload_metadata(upload_id)
        return metadata["offset"] == metadata["upload_length"]
    
    async def get_upload_file_path(self, upload_id: str) -> Path:
        """Get the file path for a completed upload"""
        if not await self.is_upload_complete(upload_id):
            raise ValidationError(f"Upload {upload_id} is not complete")
        
        return self.upload_dir / upload_id
    
    async def delete_upload(self, upload_id: str) -> None:
        """Delete an upload and its metadata"""
        try:
            upload_path = self.upload_dir / upload_id
            metadata_path = self.metadata_dir / f"{upload_id}.json"
            
            # On Windows, file handles may not be released immediately
            # Retry deletion with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if upload_path.exists():
                        upload_path.unlink()
                    break
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5 * (attempt + 1))  # 0.5s, 1s, 1.5s
                        logger.debug(f"Retry {attempt + 1}/{max_retries} deleting {upload_id}")
                    else:
                        logger.warning(f"Could not delete TUS file after {max_retries} attempts: {upload_id}")
                        # Continue anyway - file will be cleaned up by expiration
            
            if metadata_path.exists():
                metadata_path.unlink()
            
            logger.info(f"TUS upload deleted: {upload_id}")
            
        except Exception as e:
            logger.error(f"Error deleting upload {upload_id}: {e}")
            # Don't raise - allow processing to continue even if temp file cleanup fails
            logger.warning(f"Upload processing will continue, temp file {upload_id} will be cleaned up later")
    
    async def cleanup_expired_uploads(self) -> int:
        """
        Clean up expired incomplete uploads
        
        Returns:
            Number of uploads cleaned up
        """
        try:
            cleaned = 0
            now = datetime.utcnow()
            
            # Iterate through all metadata files
            for metadata_file in self.metadata_dir.glob("*.json"):
                try:
                    async with aiofiles.open(metadata_file, "r") as f:
                        import json
                        content = await f.read()
                        metadata = json.loads(content)
                    
                    # Check if expired
                    expires_at = datetime.fromisoformat(metadata["expires_at"])
                    if now > expires_at:
                        upload_id = metadata["id"]
                        await self.delete_upload(upload_id)
                        cleaned += 1
                        logger.info(f"Cleaned expired upload: {upload_id}")
                        
                except Exception as e:
                    logger.error(f"Error processing {metadata_file}: {e}")
            
            if cleaned > 0:
                logger.info(f"TUS cleanup: removed {cleaned} expired uploads")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error during TUS cleanup: {e}", exc_info=True)
            return 0
    
    async def get_upload_progress(self, upload_id: str) -> Dict[str, Any]:
        """Get upload progress information"""
        metadata = await self.get_upload_metadata(upload_id)
        
        progress_pct = (
            (metadata["offset"] / metadata["upload_length"]) * 100
            if metadata["upload_length"] > 0
            else 0
        )
        
        return {
            "upload_id": upload_id,
            "filename": metadata["filename"],
            "offset": metadata["offset"],
            "upload_length": metadata["upload_length"],
            "progress_percent": round(progress_pct, 2),
            "is_complete": metadata["offset"] == metadata["upload_length"],
            "created_at": metadata["created_at"],
            "expires_at": metadata["expires_at"]
        }


# Singleton instance
tus_upload_service = TusUploadService()