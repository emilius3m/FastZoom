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
from app.services.photo_serving_service import photo_serving_service

photos_router = APIRouter(prefix="/photos", tags=["photos"])


@photos_router.get("/{photo_id}/thumbnail")
async def get_photo_thumbnail(
        photo_id: UUID,
        db: AsyncSession = Depends(get_async_session)
):
    """Serve thumbnail foto (endpoint senza prefisso /sites/) - CONSOLIDATED"""
    return await photo_serving_service.serve_photo_thumbnail(photo_id, db)


@photos_router.get("/{photo_id}/full")
async def get_photo_full(
        photo_id: UUID,
        db: AsyncSession = Depends(get_async_session)
):
    """Serve immagine completa - CONSOLIDATED"""
    return await photo_serving_service.serve_photo_full(photo_id, db)


@photos_router.get("/{photo_id}/download")
async def download_photo(
        photo_id: UUID,
        db: AsyncSession = Depends(get_async_session)
):
    """Scarica file originale foto - CONSOLIDATED"""
    return await photo_serving_service.serve_photo_download(photo_id, db)
