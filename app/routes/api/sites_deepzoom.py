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
from app.routes.api.service_dependencies import get_deep_zoom_minio_service

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
    """FIXED: Ottieni singolo tile deep zoom con supporto formato dinamico (jpg/png) e logging dettagliato"""
    import time
    request_start_time = time.time()
    
    with logger.contextualize(
        operation="get_deep_zoom_tile_legacy",
        site_id=str(site_id),
        photo_id=str(photo_id),
        level=level,
        x=x,
        y=y,
        format=format,
        endpoint="sites_deepzoom_tile"
    ):
        logger.info(
            "🔍 LEGACY TILE REQUEST RECEIVED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "level": level,
                "coordinates": f"{x}_{y}",
                "format": format,
                "request_timestamp": datetime.now().isoformat(),
                "endpoint": "/site/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.{format}",
                "legacy_endpoint": True
            }
        )

        site, permission = site_access
        
        # Log site access verification
        access_check_start = time.time()
        logger.info(
            "🔐 SITE ACCESS VERIFICATION",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "permission_level": str(permission),
                "can_read": permission.can_read(),
                "coordinates": f"{x}_{y}",
                "level": level
            }
        )

        if not permission.can_read():
            access_check_time = time.time() - access_check_start
            logger.warning(
                "⚠️ LEGACY TILE ACCESS PERMISSION DENIED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "permission_level": str(permission),
                    "coordinates": f"{x}_{y}",
                    "level": level,
                    "access_check_time_ms": round(access_check_time * 1000, 2),
                    "reason": "insufficient_permissions"
                }
            )
            raise HTTPException(status_code=403, detail="Permessi richiesti")
        
        access_check_time = time.time() - access_check_start
        logger.debug(
            "✅ LEGACY TILE ACCESS PERMISSION VERIFIED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "permission_level": str(permission),
                "access_check_time_ms": round(access_check_time * 1000, 2)
            }
        )

        # Validate format
        format_validation_start = time.time()
        if format not in ['jpg', 'png', 'jpeg']:
            format_validation_time = time.time() - format_validation_start
            logger.error(
                "❌ LEGACY TILE INVALID FORMAT",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "requested_format": format,
                    "supported_formats": ['jpg', 'png', 'jpeg'],
                    "coordinates": f"{x}_{y}",
                    "level": level,
                    "format_validation_time_ms": round(format_validation_time * 1000, 2),
                    "endpoint_type": "legacy"
                }
            )
            raise HTTPException(status_code=400, detail="Formato tile non supportato")
        
        format_validation_time = time.time() - format_validation_start
        logger.debug(
            "✅ LEGACY TILE FORMAT VALIDATED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "format": format,
                "format_validation_time_ms": round(format_validation_time * 1000, 2)
            }
        )

        # Ottieni URL del tile
        url_generation_start = time.time()
        try:
            logger.info(
                "🔗 GENERATING TILE URL",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "level": level,
                    "coordinates": f"{x}_{y}",
                    "format": format,
                    "method": "get_tile_url"
                }
            )
            
            tile_url = await archaeological_minio_service.get_tile_url(str(site_id), str(photo_id), level, x, y)
            url_generation_time = time.time() - url_generation_start
            
            if not tile_url:
                total_time = time.time() - request_start_time
                logger.error(
                    "❌ LEGACY TILE URL GENERATION FAILED",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "level": level,
                        "coordinates": f"{x}_{y}",
                        "format": format,
                        "url_generation_time_ms": round(url_generation_time * 1000, 2),
                        "total_time_ms": round(total_time * 1000, 2),
                        "result": "null_url",
                        "http_status": 404
                    }
                )
                raise HTTPException(status_code=404, detail="Tile non trovato")
            
            logger.info(
                "✅ LEGACY TILE URL GENERATED SUCCESSFULLY",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "level": level,
                    "coordinates": f"{x}_{y}",
                    "format": format,
                    "tile_url": tile_url,
                    "url_generation_time_ms": round(url_generation_time * 1000, 2),
                    "url_length": len(tile_url) if tile_url else 0
                }
            )

        except Exception as url_error:
            url_generation_time = time.time() - url_generation_start
            total_time = time.time() - request_start_time
            logger.error(
                "💥 LEGACY TILE URL GENERATION ERROR",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "level": level,
                    "coordinates": f"{x}_{y}",
                    "format": format,
                    "error": str(url_error),
                    "error_type": type(url_error).__name__,
                    "url_generation_time_ms": round(url_generation_time * 1000, 2),
                    "total_time_ms": round(total_time * 1000, 2)
                }
            )
            import traceback
            logger.error(
                "📋 LEGACY TILE URL ERROR TRACEBACK",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "coordinates": f"{x}_{y}",
                    "traceback": traceback.format_exc()
                }
            )
            raise HTTPException(status_code=500, detail="Errore generazione URL tile")

        # Redirect al tile
        redirect_preparation_start = time.time()
        total_time = time.time() - request_start_time
        
        logger.info(
            "🔄 LEGACY TILE REDIRECT PREPARED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "level": level,
                "coordinates": f"{x}_{y}",
                "format": format,
                "tile_url": tile_url,
                "redirect_status": 302,
                "redirect_preparation_time_ms": round((time.time() - redirect_preparation_start) * 1000, 2),
                "total_time_ms": round(total_time * 1000, 2),
                "endpoint_type": "legacy_redirect"
            }
        )
        
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
    """Processa foto esistente per generare deep zoom tiles con logging dettagliato"""
    import time
    request_start_time = time.time()
    
    with logger.contextualize(
        operation="process_deep_zoom",
        site_id=str(site_id),
        photo_id=str(photo_id),
        endpoint="sites_deepzoom_process"
    ):
        logger.info(
            "🔄 DEEP ZOOM PROCESSING REQUEST RECEIVED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "request_timestamp": datetime.now().isoformat(),
                "endpoint": "/site/{site_id}/photos/{photo_id}/deepzoom/process",
                "endpoint_type": "legacy_processing"
            }
        )

        site, permission = site_access
        
        # Log site access verification
        access_check_start = time.time()
        logger.info(
            "🔐 PROCESSING SITE ACCESS VERIFICATION",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "permission_level": str(permission),
                "can_write": permission.can_write(),
                "operation": "deep_zoom_processing"
            }
        )

        if not permission.can_write():
            access_check_time = time.time() - access_check_start
            logger.warning(
                "⚠️ DEEP ZOOM PROCESSING PERMISSION DENIED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "permission_level": str(permission),
                    "access_check_time_ms": round(access_check_time * 1000, 2),
                    "reason": "insufficient_write_permissions"
                }
            )
            raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
        
        access_check_time = time.time() - access_check_start
        logger.debug(
            "✅ DEEP ZOOM PROCESSING ACCESS VERIFIED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "permission_level": str(permission),
                "access_check_time_ms": round(access_check_time * 1000, 2)
            }
        )

        # Trova foto nel database
        photo_lookup_start = time.time()
        try:
            logger.info(
                "🔍 PHOTO DATABASE LOOKUP",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "operation": "photo_retrieval_for_processing"
                }
            )
            
            photo = await db.execute(
                select(Photo).where(
                    and_(Photo.id == photo_id, Photo.site_id == site_id)
                )
            )
            photo = photo.scalar_one_or_none()
            photo_lookup_time = time.time() - photo_lookup_start

            if not photo:
                total_time = time.time() - request_start_time
                logger.error(
                    "❌ PHOTO NOT FOUND FOR PROCESSING",
                    extra={
                        "site_id": str(site_id),
                        "photo_id": str(photo_id),
                        "photo_lookup_time_ms": round(photo_lookup_time * 1000, 2),
                        "total_time_ms": round(total_time * 1000, 2),
                        "http_status": 404
                    }
                )
                raise HTTPException(status_code=404, detail="Foto non trovata")
            
            logger.info(
                "✅ PHOTO FOUND FOR PROCESSING",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "filepath": photo.filepath,
                    "width": photo.width,
                    "height": photo.height,
                    "has_deep_zoom": photo.has_deep_zoom,
                    "deepzoom_status": photo.deepzoom_status,
                    "photo_lookup_time_ms": round(photo_lookup_time * 1000, 2)
                }
            )

        except Exception as photo_error:
            photo_lookup_time = time.time() - photo_lookup_start
            total_time = time.time() - request_start_time
            logger.error(
                "💥 PHOTO DATABASE LOOKUP ERROR",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "error": str(photo_error),
                    "error_type": type(photo_error).__name__,
                    "photo_lookup_time_ms": round(photo_lookup_time * 1000, 2),
                    "total_time_ms": round(total_time * 1000, 2)
                }
            )
            import traceback
            logger.error(
                "📋 PHOTO LOOKUP ERROR TRACEBACK",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "traceback": traceback.format_exc()
                }
            )
            raise HTTPException(status_code=500, detail="Errore ricerca foto")

        # Scarica foto da MinIO per processamento
        minio_download_start = time.time()
        try:
            logger.info(
                "📥 MINIO PHOTO DOWNLOAD STARTED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "filepath": photo.filepath,
                    "operation": "download_for_deepzoom_processing"
                }
            )
            
            photo_data = await archaeological_minio_service.get_file(photo.filepath)
            minio_download_time = time.time() - minio_download_start
            
            logger.info(
                "✅ MINIO PHOTO DOWNLOAD COMPLETED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "filepath": photo.filepath,
                    "download_size_bytes": len(photo_data) if photo_data else 0,
                    "minio_download_time_ms": round(minio_download_time * 1000, 2)
                }
            )

        except Exception as download_error:
            minio_download_time = time.time() - minio_download_start
            total_time = time.time() - request_start_time
            logger.error(
                "💥 MINIO PHOTO DOWNLOAD ERROR",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "filepath": photo.filepath,
                    "error": str(download_error),
                    "error_type": type(download_error).__name__,
                    "minio_download_time_ms": round(minio_download_time * 1000, 2),
                    "total_time_ms": round(total_time * 1000, 2)
                }
            )
            import traceback
            logger.error(
                "📋 MINIO DOWNLOAD ERROR TRACEBACK",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filepath": photo.filepath,
                    "traceback": traceback.format_exc()
                }
            )
            raise HTTPException(status_code=500, detail=f"Download foto fallito: {str(download_error)}")

        # Processa con deep zoom
        processing_start = time.time()
        try:
            from fastapi import UploadFile
            import io

            logger.info(
                "🔄 DEEP ZOOM PROCESSING STARTED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "original_size_bytes": len(photo_data),
                    "dimensions": f"{photo.width}x{photo.height}",
                    "operation": "tile_generation"
                }
            )

            temp_file = UploadFile(
                filename=photo.filename,
                file=io.BytesIO(photo_data)
            )

            deep_zoom_service = get_deep_zoom_minio_service()
            result = await deep_zoom_service.process_and_upload_tiles(
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
            processing_time = time.time() - processing_start
            
            logger.success(
                "✅ DEEP ZOOM PROCESSING COMPLETED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "tiles_generated": result.get('total_tiles', 0),
                    "levels": result.get('levels', 0),
                    "processing_time_ms": round(processing_time * 1000, 2),
                    "metadata_url": result.get('metadata_url', ''),
                    "result_status": "success"
                }
            )

        except Exception as processing_error:
            processing_time = time.time() - processing_start
            total_time = time.time() - request_start_time
            logger.error(
                "💥 DEEP ZOOM PROCESSING ERROR",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "error": str(processing_error),
                    "error_type": type(processing_error).__name__,
                    "processing_time_ms": round(processing_time * 1000, 2),
                    "total_time_ms": round(total_time * 1000, 2)
                }
            )
            import traceback
            logger.error(
                "📋 DEEP ZOOM PROCESSING ERROR TRACEBACK",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "traceback": traceback.format_exc()
                }
            )
            raise HTTPException(status_code=500, detail=f"Deep zoom processing failed: {str(processing_error)}")

        # Aggiorna database con info deep zoom
        db_update_start = time.time()
        try:
            logger.info(
                "💾 DATABASE UPDATE STARTED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "tiles_generated": result.get('total_tiles', 0),
                    "levels": result.get('levels', 0),
                    "operation": "update_photo_deepzoom_info"
                }
            )

            # Aggiorna database con info deep zoom
            photo.has_deep_zoom = True
            photo.max_zoom_level = result['levels']
            photo.tile_count = result['total_tiles']
            await db.commit()
            db_update_time = time.time() - db_update_start
            total_time = time.time() - request_start_time
            
            logger.success(
                "✅ DATABASE UPDATE COMPLETED",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "filename": photo.filename,
                    "has_deep_zoom": True,
                    "max_zoom_level": result['levels'],
                    "tile_count": result['total_tiles'],
                    "db_update_time_ms": round(db_update_time * 1000, 2),
                    "total_time_ms": round(total_time * 1000, 2)
                }
            )

        except Exception as db_error:
            db_update_time = time.time() - db_update_start
            total_time = time.time() - request_start_time
            logger.error(
                "💥 DATABASE UPDATE ERROR",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "error": str(db_error),
                    "error_type": type(db_error).__name__,
                    "db_update_time_ms": round(db_update_time * 1000, 2),
                    "total_time_ms": round(total_time * 1000, 2)
                }
            )
            await db.rollback()
            import traceback
            logger.error(
                "📋 DATABASE UPDATE ERROR TRACEBACK",
                extra={
                    "site_id": str(site_id),
                    "photo_id": str(photo_id),
                    "traceback": traceback.format_exc()
                }
            )
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(db_error)}")

        total_time = time.time() - request_start_time
        
        logger.success(
            "🎉 DEEP ZOOM PROCESSING REQUEST COMPLETED",
            extra={
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "filename": photo.filename,
                "tiles_generated": result['total_tiles'],
                "levels": result['levels'],
                "metadata_url": result['metadata_url'],
                "total_time_ms": round(total_time * 1000, 2),
                "minio_download_time_ms": round(minio_download_time * 1000, 2),
                "processing_time_ms": round(processing_time * 1000, 2),
                "db_update_time_ms": round(db_update_time * 1000, 2)
            }
        )

        return JSONResponse({
            "message": "Deep zoom processing completato",
            "photo_id": str(photo_id),
            "tiles_generated": result['total_tiles'],
            "levels": result['levels'],
            "metadata_url": result['metadata_url']
        })


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
    deep_zoom_service = get_deep_zoom_minio_service()
    minio_status = await deep_zoom_service.get_processing_status(str(site_id), str(photo_id))

    return JSONResponse({
        "photo_id": str(photo_id),
        "site_id": str(site_id),
        "status": photo.deepzoom_status,
        "has_deep_zoom": photo.has_deep_zoom,
        "levels": photo.max_zoom_level,
        "tile_count": photo.tile_count,
        "processed_at": photo.deepzoom_processed_at.isoformat() if photo.deepzoom_processed_at else None,
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
            Photo.deepzoom_status.in_(['scheduled', 'processing'])
        )
    ).order_by(Photo.created_at.desc())
    
    processing_photos = await db.execute(processing_query)
    processing_photos = processing_photos.scalars().all()

    # Ottieni foto completate recentemente (ultime 24 ore)
    recent_completed_query = select(Photo).where(
        and_(
            Photo.site_id == site_id,
            Photo.deepzoom_status == 'completed',
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
                "status": photo.deepzoom_status,
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
                "status": photo.deepzoom_status,
                "completed_at": photo.deepzoom_processed_at.isoformat() if photo.deepzoom_processed_at else None,
                "tile_count": photo.tile_count,
                "levels": photo.max_zoom_level
            }
            for photo in completed_photos
        ],
        "queue_length": len(processing_photos),
        "completed_today": len(completed_photos)
    })