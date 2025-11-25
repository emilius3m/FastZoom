# app/routes/api/service_dependencies.py - Dependency Injection for Refactored Services

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.services.archaeological_minio_service import ArchaeologicalMinIOService
from app.services.photo_service import PhotoService
from app.services.deep_zoom_minio_service import DeepZoomMinIOService
from app.core.exceptions import (
    StorageError, StorageFullError, StorageTemporaryError,
    StorageConnectionError, StorageNotFoundError, StorageValidationError
)


# Singleton instances for dependency injection
@lru_cache()
def get_archaeological_minio_service() -> ArchaeologicalMinIOService:
    """Get singleton instance of ArchaeologicalMinIOService"""
    return ArchaeologicalMinIOService()


def get_photo_service(
    storage: Annotated[ArchaeologicalMinIOService, Depends(get_archaeological_minio_service)]
) -> PhotoService:
    """Get PhotoService with injected storage dependency"""
    return PhotoService(archaeological_minio_service=storage)


def get_deep_zoom_minio_service(
    storage: Annotated[ArchaeologicalMinIOService, Depends(get_archaeological_minio_service)]
) -> DeepZoomMinIOService:
    """Get DeepZoomMinIOService with injected storage dependency"""
    return DeepZoomMinIOService(archaeological_minio_service=storage)


# Error handling wrapper for storage operations
async def handle_storage_errors(operation_name: str = "storage operation"):
    """Decorator to handle storage errors and convert to HTTP responses"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except StorageFullError as e:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=507,  # Insufficient Storage
                    detail=f"Storage full. Cleaned {e.freed_space_mb}MB but insufficient"
                )
            except StorageTemporaryError as e:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,  # Service Unavailable
                    detail="Storage temporarily unavailable, retry later"
                )
            except StorageConnectionError as e:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=502,  # Bad Gateway
                    detail="Cannot connect to storage backend"
                )
            except StorageNotFoundError as e:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=404,  # Not Found
                    detail=f"Storage object not found: {str(e)}"
                )
            except StorageValidationError as e:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,  # Bad Request
                    detail=f"Storage validation error: {str(e)}"
                )
            except StorageError as e:
                from fastapi import HTTPException
                from loguru import logger
                logger.error(f"Storage error during {operation_name}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Storage error during {operation_name}"
                )
            except Exception as e:
                from fastapi import HTTPException
                from loguru import logger
                logger.error(f"Unexpected error during {operation_name}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Unexpected error during {operation_name}"
                )
        return wrapper
    return decorator


# Non-decorator version for route-level error handling
async def convert_storage_error_to_http_exception(error: Exception, operation_name: str = "storage operation"):
    """Convert domain storage exceptions to HTTP exceptions for use in route handlers"""
    from fastapi import HTTPException
    from loguru import logger
    
    if isinstance(error, StorageFullError):
        raise HTTPException(
            status_code=507,  # Insufficient Storage
            detail=f"Storage full. Cleaned {error.freed_space_mb}MB but insufficient"
        )
    elif isinstance(error, StorageTemporaryError):
        raise HTTPException(
            status_code=503,  # Service Unavailable
            detail="Storage temporarily unavailable, retry later"
        )
    elif isinstance(error, StorageConnectionError):
        raise HTTPException(
            status_code=502,  # Bad Gateway
            detail="Cannot connect to storage backend"
        )
    elif isinstance(error, StorageNotFoundError):
        raise HTTPException(
            status_code=404,  # Not Found
            detail=f"Storage object not found: {str(error)}"
        )
    elif isinstance(error, StorageValidationError):
        raise HTTPException(
            status_code=400,  # Bad Request
            detail=f"Storage validation error: {str(error)}"
        )
    elif isinstance(error, StorageError):
        logger.error(f"Storage error during {operation_name}: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Storage error during {operation_name}"
        )
    else:
        logger.error(f"Unexpected error during {operation_name}: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during {operation_name}"
        )


# Type aliases for cleaner dependency annotations
ArchaeologicalMinIOServiceDep = Annotated[ArchaeologicalMinIOService, Depends(get_archaeological_minio_service)]
PhotoServiceDep = Annotated[PhotoService, Depends(get_photo_service)]
DeepZoomMinIOServiceDep = Annotated[DeepZoomMinIOService, Depends(get_deep_zoom_minio_service)]