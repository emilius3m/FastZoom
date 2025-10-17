# app/routes/api/sites_deepzoom.py - Deep zoom image processing API endpoints

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from datetime import datetime, timedelta

from app.database.session import get_async_session
from app.models import Photo
from app.routes.api.dependencies import get_site_access
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service

deepzoom_router = APIRouter()


@deepzoom_router.get("/site/{site_id}/photos/{photo_id}/deepzoom/info")
async def get_deep_zoom_info(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni informazioni deep zoom per una foto"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Ottieni info deep zoom
    deep_zoom_info = await archaeological_minio_service.get_deep_zoom_info(str(site_id), str(photo_id))

    if not deep_zoom_info:
        # Return a proper JSON response indicating deep zoom is not available
        return JSONResponse({
            "photo_id": str(photo_id),
            "site_id": str(site_id),
            "available": False,
            "message": "Deep zoom tiles not generated for this photo",
            "width": 0,
            "height": 0,
            "levels": 0,
            "tile_size": 256,
            "total_tiles": 0
        })

    return JSONResponse(deep_zoom_info)


@deepzoom_router.get("/site/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.{format}")
async def get_deep_zoom_tile(
        site_id: UUID,
        photo_id: UUID,
        level: int,
        x: int,
        y: int,
        format: str,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """FIXED: Ottieni singolo tile deep zoom con supporto formato dinamico (jpg/png)"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Validate format
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")

    # Ottieni URL del tile
    tile_url = await archaeological_minio_service.get_tile_url(str(site_id), str(photo_id), level, x, y)

    if not tile_url:
        raise HTTPException(status_code=404, detail="Tile non trovato")

    # Redirect al tile
    return RedirectResponse(url=tile_url, status_code=302)


# FIXED: Aggiungi endpoint legacy per backward compatibility
@deepzoom_router.get("/site/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.jpg")
async def get_deep_zoom_tile_jpg(
        site_id: UUID,
        photo_id: UUID,
        level: int,
        x: int,
        y: int,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Legacy endpoint per tile JPG - redirect al nuovo endpoint dinamico"""
    return await get_deep_zoom_tile(site_id, photo_id, level, x, y, "jpg", site_access, db)


@deepzoom_router.get("/site/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.png")
async def get_deep_zoom_tile_png(
        site_id: UUID,
        photo_id: UUID,
        level: int,
        x: int,
        y: int,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Legacy endpoint per tile PNG - redirect al nuovo endpoint dinamico"""
    return await get_deep_zoom_tile(site_id, photo_id, level, x, y, "png", site_access, db)


@deepzoom_router.post("/site/{site_id}/photos/{photo_id}/deepzoom/process")
async def process_deep_zoom(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Processa foto esistente per generare deep zoom tiles"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Scarica foto da MinIO per processamento
    try:
        photo_data = await archaeological_minio_service.get_file(photo.file_path)

        # Processa con deep zoom
        from fastapi import UploadFile
        import io

        temp_file = UploadFile(
            filename=photo.filename,
            file=io.BytesIO(photo_data)
        )

        result = await deep_zoom_minio_service.process_and_upload_tiles(
            photo_id=str(photo_id),
            original_file=temp_file,
            site_id=str(site_id),
            archaeological_metadata={
                'inventory_number': photo.inventory_number,
                'excavation_area': photo.excavation_area,
                'material': photo.material,
                'chronology_period': photo.chronology_period
            }
        )

        # Aggiorna database con info deep zoom
        photo.has_deep_zoom = True
        photo.deep_zoom_levels = result['levels']
        photo.deep_zoom_tile_count = result['total_tiles']
        await db.commit()

        return JSONResponse({
            "message": "Deep zoom processing completato",
            "photo_id": str(photo_id),
            "tiles_generated": result['total_tiles'],
            "levels": result['levels'],
            "metadata_url": result['metadata_url']
        })

    except Exception as e:
        logger.error(f"Deep zoom processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Deep zoom processing failed: {str(e)}")


@deepzoom_router.get("/site/{site_id}/photos/{photo_id}/deepzoom/status")
async def get_deep_zoom_processing_status(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni status di elaborazione deep zoom per una foto"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Ottieni status da MinIO se disponibile
    minio_status = await deep_zoom_minio_service.get_processing_status(str(site_id), str(photo_id))

    return JSONResponse({
        "photo_id": str(photo_id),
        "site_id": str(site_id),
        "status": photo.deep_zoom_status,
        "has_deep_zoom": photo.has_deep_zoom,
        "levels": photo.deep_zoom_levels,
        "tile_count": photo.deep_zoom_tile_count,
        "processed_at": photo.deep_zoom_processed_at.isoformat() if photo.deep_zoom_processed_at else None,
        "minio_status": minio_status
    })


@deepzoom_router.get("/site/{site_id}/photos/processing-queue")
async def get_processing_queue_status(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """
    FIXED: Endpoint per controllare lo stato della coda di processamento
    Utile per verificare che il background processing non blocchi gli upload
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Ottieni foto in processing o scheduled
    processing_query = select(Photo).where(
        and_(
            Photo.site_id == site_id,
            Photo.deep_zoom_status.in_(['scheduled', 'processing'])
        )
    ).order_by(Photo.created_at.desc())
    
    processing_photos = await db.execute(processing_query)
    processing_photos = processing_photos.scalars().all()

    # Ottieni foto completate recentemente (ultime 24 ore)
    recent_completed_query = select(Photo).where(
        and_(
            Photo.site_id == site_id,
            Photo.deep_zoom_status == 'completed',
            Photo.deep_zoom_processed_at >= datetime.now() - timedelta(hours=24)
        )
    ).order_by(Photo.deep_zoom_processed_at.desc()).limit(10)
    
    completed_photos = await db.execute(recent_completed_query)
    completed_photos = completed_photos.scalars().all()

    return JSONResponse({
        "site_id": str(site_id),
        "processing_queue": [
            {
                "photo_id": str(photo.id),
                "filename": photo.filename,
                "status": photo.deep_zoom_status,
                "created_at": photo.created_at.isoformat(),
                "width": photo.width,
                "height": photo.height
            }
            for photo in processing_photos
        ],
        "recent_completed": [
            {
                "photo_id": str(photo.id),
                "filename": photo.filename,
                "status": photo.deep_zoom_status,
                "completed_at": photo.deep_zoom_processed_at.isoformat() if photo.deep_zoom_processed_at else None,
                "tile_count": photo.deep_zoom_tile_count,
                "levels": photo.deep_zoom_levels
            }
            for photo in completed_photos
        ],
        "queue_length": len(processing_photos),
        "completed_today": len(completed_photos)
    })