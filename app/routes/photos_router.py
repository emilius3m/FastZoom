# app/routes/photos_router.py - CONSOLIDATED PHOTO ENDPOINTS
"""
Consolidated photo serving endpoints using shared photo serving service.
Eliminates duplication with sites_photos API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.services.photo_serving_service import photo_serving_service
from app.routes.api.dependencies import get_site_access, get_photo_site_access

photos_router = APIRouter(prefix="/photos", tags=["photos"])


@photos_router.get("/{photo_id}/thumbnail")
async def get_photo_thumbnail(
        photo_id: UUID,
        site_access: tuple = Depends(get_photo_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Serve thumbnail foto - CONSOLIDATED"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")
        
    return await photo_serving_service.serve_photo_thumbnail(photo_id, db)


@photos_router.get("/{photo_id}/full")
async def get_photo_full(
        photo_id: UUID,
        site_access: tuple = Depends(get_photo_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Serve immagine completa - CONSOLIDATED"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")
        
    return await photo_serving_service.serve_photo_full(photo_id, db)


@photos_router.get("/{photo_id}/download")
async def download_photo(
        photo_id: UUID,
        site_access: tuple = Depends(get_photo_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Scarica file originale foto - CONSOLIDATED"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")
        
    return await photo_serving_service.serve_photo_download(photo_id, db)
