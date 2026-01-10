"""
TUS Protocol API Routes
Handles resumable file uploads using TUS protocol
"""
from fastapi import APIRouter, Request, Response, Header, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Optional
from uuid import UUID
from loguru import logger

from app.services.tus_service import tus_upload_service
from app.core.security import get_current_user_id_with_blacklist
from app.core.domain_exceptions import (
    FileUploadError,
    ValidationError,
    StorageError
)
from app.database.db import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/tus", tags=["TUS Uploads"])


@router.post("/uploads")
async def create_tus_upload(
    request: Request,
    upload_length: int = Header(..., alias="Upload-Length"),
    upload_metadata: Optional[str] = Header(None, alias="Upload-Metadata"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new TUS upload session
    
    Headers:
        Upload-Length: Total file size in bytes
        Upload-Metadata: Base64 encoded metadata (optional)
    
    Returns:
        201: Upload created with Location header containing upload URL
    """
    try:
        # Parse metadata if provided
        metadata = {}
        if upload_metadata:
            # Parse TUS metadata format: "key1 value1,key2 value2"
            import base64
            pairs = upload_metadata.split(",")
            for pair in pairs:
                pair = pair.strip()
                if not pair:
                    continue
                    
                if " " in pair:
                    parts = pair.split(" ", 1)
                    if len(parts) != 2:
                        continue
                        
                    key, encoded_value = parts
                    try:
                        value = base64.b64decode(encoded_value).decode("utf-8")
                        metadata[key] = value
                    except Exception as e:
                        logger.warning(f"Failed to decode metadata pair {pair}: {e}")
        
        # Get filename from metadata or use default
        filename = metadata.get("filename", f"upload_{current_user_id}.bin")
        
        # Add user context to metadata
        metadata["user_id"] = str(current_user_id)
        
        # Create upload session
        upload_id = await tus_upload_service.create_upload(
            filename=filename,
            upload_length=upload_length,
            metadata=metadata
        )
        
        # Build upload URL
        upload_url = f"{request.base_url}api/v1/tus/uploads/{upload_id}"
        
        # Return TUS creation response
        return Response(
            status_code=201,
            headers={
                "Location": upload_url,
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": "0"
            }
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileUploadError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating TUS upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create upload")


@router.head("/uploads/{upload_id}")
async def get_tus_upload_offset(
    upload_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Get current upload offset (HEAD request)
    
    Returns:
        200: Current offset in Upload-Offset header
        404: Upload not found
    """
    try:
        metadata = await tus_upload_service.get_upload_metadata(upload_id)
        
        # Verify user owns this upload
        if metadata.get("custom_metadata", {}).get("user_id") != str(current_user_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return Response(
            status_code=200,
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": str(metadata["offset"]),
                "Upload-Length": str(metadata["upload_length"]),
                "Cache-Control": "no-store"
            }
        )
        
    except ValidationError:
        raise HTTPException(status_code=404, detail="Upload not found")
    except Exception as e:
        logger.error(f"Error getting upload offset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get upload info")


@router.patch("/uploads/{upload_id}")
async def append_tus_chunk(
    upload_id: str,
    request: Request,
    upload_offset: int = Header(..., alias="Upload-Offset"),
    content_type: str = Header(..., alias="Content-Type"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Append a chunk to an upload (PATCH request)
    
    Headers:
        Upload-Offset: Current byte offset
        Content-Type: application/offset+octet-stream
    
    Body:
        Raw chunk bytes
    
    Returns:
        204: Chunk appended successfully with new Upload-Offset
        409: Offset conflict
        404: Upload not found
    """
    try:
        # Validate content type
        if content_type != "application/offset+octet-stream":
            raise HTTPException(
                status_code=400,
                detail="Content-Type must be application/offset+octet-stream"
            )
        
        # Get metadata and verify ownership
        metadata = await tus_upload_service.get_upload_metadata(upload_id)
        if metadata.get("custom_metadata", {}).get("user_id") != str(current_user_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Read chunk data
        chunk_data = await request.body()
        
        if not chunk_data:
            raise HTTPException(status_code=400, detail="No data provided")
        
        # Append chunk
        new_offset = await tus_upload_service.append_chunk(
            upload_id=upload_id,
            chunk_data=chunk_data,
            offset=upload_offset
        )
        
        # Check if upload is complete
        is_complete = await tus_upload_service.is_upload_complete(upload_id)
        
        headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": str(new_offset)
        }
        
        if is_complete:
            headers["Upload-Complete"] = "true"
        
        return Response(
            status_code=204,
            headers=headers
        )
        
    except ValidationError as e:
        if "Offset mismatch" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except FileUploadError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error appending chunk: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to append chunk")


@router.get("/uploads/{upload_id}/progress")
async def get_upload_progress(
    upload_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Get upload progress information (non-TUS endpoint for convenience)
    
    Returns:
        Upload progress details including percentage
    """
    try:
        metadata = await tus_upload_service.get_upload_metadata(upload_id)
        
        # Verify user owns this upload
        if metadata.get("custom_metadata", {}).get("user_id") != str(current_user_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        progress = await tus_upload_service.get_upload_progress(upload_id)
        
        return JSONResponse(content=progress)
        
    except ValidationError:
        raise HTTPException(status_code=404, detail="Upload not found")
    except Exception as e:
        logger.error(f"Error getting progress: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get progress")


@router.delete("/uploads/{upload_id}")
async def delete_tus_upload(
    upload_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """
    Delete an upload session
    
    Returns:
        204: Upload deleted successfully
        404: Upload not found
    """
    try:
        metadata = await tus_upload_service.get_upload_metadata(upload_id)
        
        # Verify user owns this upload
        if metadata.get("custom_metadata", {}).get("user_id") != str(current_user_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        await tus_upload_service.delete_upload(upload_id)
        
        return Response(status_code=204)
        
    except ValidationError:
        raise HTTPException(status_code=404, detail="Upload not found")
    except StorageError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete upload")


@router.options("/uploads")
@router.options("/uploads/{upload_id}")
async def tus_options(upload_id: Optional[str] = None):
    """
    TUS OPTIONS request - declare supported extensions
    
    Returns:
        TUS protocol capabilities
    """
    return Response(
        status_code=204,
        headers={
            "Tus-Resumable": "1.0.0",
            "Tus-Version": "1.0.0",
            "Tus-Extension": "creation,termination",
            "Tus-Max-Size": str(tus_upload_service.max_size)
        }
    )


@router.post("/cleanup")
async def cleanup_expired_uploads(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Cleanup expired uploads (admin/maintenance endpoint)
    
    Returns:
        Number of uploads cleaned up
    """
    try:
        # You might want to add admin-only check here
        cleaned = await tus_upload_service.cleanup_expired_uploads()
        
        return JSONResponse(content={
            "success": True,
            "cleaned_uploads": cleaned
        })
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Cleanup failed")