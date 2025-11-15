"""
API v1 - Deep Zoom Management
Endpoints per gestione completa deep zoom tiles e processing.
Consolidamento di sites_deepzoom.py e deepzoom_tiles.py
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, UploadFile
from fastapi.responses import JSONResponse, Response, RedirectResponse
from fastapi.security import HTTPBearer
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from loguru import logger
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import io
import asyncio

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session
from app.models import Photo, PhotoType, MaterialType, ConservationStatus, UserActivity

# Services
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.deep_zoom_background_service import deep_zoom_background_service

# Schemas
class DeepZoomConfig(BaseModel):
    max_levels: Optional[int] = None
    tile_size: Optional[int] = 256
    tile_overlap: Optional[int] = 1
    quality: Optional[int] = 90
    format: Optional[str] = "jpg"

class BatchProcessRequest(BaseModel):
    photo_ids: List[UUID]
    force_reprocess: bool = False
    priority: Optional[str] = "normal"

class VerificationConfig(BaseModel):
    verification_interval_hours: Optional[int] = 24
    batch_size: Optional[int] = 50
    max_concurrent_verifications: Optional[int] = 3
    auto_repair_enabled: Optional[bool] = True

router = APIRouter()


def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint


def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )

    if not site_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )

    return site_info


# ============================================================================
# CONSOLIDATED ENDPOINTS FROM sites_deepzoom.py
# ============================================================================

@router.get("/sites/{site_id}/photos/{photo_id}/info", 
            summary="Ottieni informazioni deep zoom per una foto", 
            tags=["Deep Zoom"])
async def get_deep_zoom_info(
    site_id: UUID,
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni informazioni deep zoom per una foto"""
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify read permissions
    if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Ottieni info deep zoom
    deep_zoom_info = await deep_zoom_minio_service.get_deep_zoom_info(str(site_id), str(photo_id))

    if not deep_zoom_info:
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


@router.get("/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}", 
            summary="Ottieni singolo tile deep zoom", 
            tags=["Deep Zoom"])
async def get_deep_zoom_tile(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    format: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni singolo tile deep zoom con supporto formato dinamico (jpg/png)"""
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify read permissions
    if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Validate format
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")

    # Ottieni URL del tile
    tile_url = await deep_zoom_minio_service.get_tile_url(str(site_id), str(photo_id), level, x, y)

    if not tile_url:
        raise HTTPException(status_code=404, detail="Tile non trovato")

    # Redirect al tile
    return RedirectResponse(url=tile_url, status_code=302)


@router.get("/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.jpg", 
            summary="Legacy endpoint per tile JPG", 
            tags=["Deep Zoom"])
async def get_deep_zoom_tile_jpg(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Legacy endpoint per tile JPG"""
    return await get_deep_zoom_tile(site_id, photo_id, level, x, y, "jpg", current_user_id, user_sites, db)


@router.get("/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.png", 
            summary="Legacy endpoint per tile PNG", 
            tags=["Deep Zoom"])
async def get_deep_zoom_tile_png(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Legacy endpoint per tile PNG"""
    return await get_deep_zoom_tile(site_id, photo_id, level, x, y, "png", current_user_id, user_sites, db)


# ============================================================================
# PUBLIC TILE ENDPOINT (OPTION 1 - RECOMMENDED)
# ============================================================================

@router.get("/public/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}",
            summary="Public tile endpoint for OpenSeadragon (no auth headers required)",
            tags=["Deep Zoom - Public"])
async def get_public_deep_zoom_tile(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    format: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Public tile endpoint that uses browser session context instead of JWT headers.
    This allows OpenSeadragon to load tiles without sending authentication headers.
    """
    # Validate format
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")

    # Check if user has valid session (browser session authentication)
    session = request.session
    if not session.get("user_id"):
        raise HTTPException(
            status_code=401,
            detail="Sessione non valida. Effettua il login per accedere alle tiles."
        )

    current_user_id = UUID(session.get("user_id"))
    
    # Verify user has access to this site by checking database
    from app.core.security import get_user_sites_by_id
    try:
        user_sites = await get_user_sites_by_id(current_user_id, db)
        site_info = verify_site_access(site_id, user_sites)
        
        # Verify read permissions
        if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
            raise HTTPException(status_code=403, detail="Permessi richiesti")
            
    except Exception as e:
        logger.error(f"Public tile access denied for user {current_user_id}, site {site_id}: {e}")
        raise HTTPException(status_code=403, detail="Accesso al sito negato")

    # Verify photo exists and belongs to site
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == str(photo_id), Photo.site_id == str(site_id))
        )
    )
    photo = photo.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Get tile URL from MinIO
    try:
        tile_url = await deep_zoom_minio_service.get_tile_url(str(site_id), str(photo_id), level, x, y)

        if not tile_url:
            raise HTTPException(status_code=404, detail="Tile non trovato")

        # Log access for security monitoring
        logger.info(f"Public tile accessed: user={current_user_id}, site={site_id}, photo={photo_id}, tile={level}/{x}_{y}.{format}")

        # Redirect to tile (this preserves the 302 redirect behavior)
        return RedirectResponse(url=tile_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Error getting public tile {level}/{x}_{y}.{format} for photo {photo_id}: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il caricamento del tile")


@router.post("/sites/{site_id}/photos/{photo_id}/process",
             summary="Processa foto esistente per generare deep zoom tiles", 
             tags=["Deep Zoom"])
async def process_deep_zoom(
    site_id: UUID,
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Processa foto esistente per generare deep zoom tiles"""
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify write permissions
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == str(photo_id), Photo.site_id == str(site_id))
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Scarica foto da MinIO per processamento
    try:
        photo_data = await archaeological_minio_service.get_file(photo.filepath)

        # Processa con deep zoom
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
                'material': photo.material.value if photo.material else None,
                'chronology_period': photo.chronology_period
            }
        )

        # Aggiorna database con info deep zoom
        photo.has_deep_zoom = True
        photo.max_zoom_level = result['levels']
        photo.tile_count = result['total_tiles']
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


@router.get("/sites/{site_id}/photos/{photo_id}/status", 
            summary="Ottieni status di elaborazione deep zoom per una foto", 
            tags=["Deep Zoom"])
async def get_deep_zoom_processing_status(
    site_id: UUID,
    photo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni status di elaborazione deep zoom per una foto"""
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify read permissions
    if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == str(photo_id), Photo.site_id == str(site_id))
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
        "status": photo.deepzoom_status,
        "has_deep_zoom": photo.has_deep_zoom,
        "levels": photo.max_zoom_level,
        "tile_count": photo.tile_count,
        "processed_at": photo.deepzoom_processed_at.isoformat() if photo.deepzoom_processed_at else None,
        "minio_status": minio_status
    })


@router.get("/sites/{site_id}/processing-queue", 
            summary="Controlla lo stato della coda di processamento", 
            tags=["Deep Zoom"])
async def get_processing_queue_status(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Endpoint per controllare lo stato della coda di processamento
    Utile per verificare che il background processing non blocchi gli upload
    """
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify read permissions
    if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Ottieni foto in processing o scheduled
    processing_query = select(Photo).where(
        and_(
            Photo.site_id == str(site_id),
            Photo.deepzoom_status.in_(['scheduled', 'processing'])
        )
    ).order_by(Photo.created_at.desc())

    processing_photos = await db.execute(processing_query)
    processing_photos = processing_photos.scalars().all()

    # Ottieni foto completate recentemente (ultime 24 ore)
    recent_completed_query = select(Photo).where(
        and_(
            Photo.site_id == str(site_id),
            Photo.deepzoom_status == 'completed',
            Photo.deepzoom_processed_at >= datetime.now() - timedelta(hours=24)
        )
    ).order_by(Photo.deepzoom_processed_at.desc()).limit(10)

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


# ============================================================================
# CONSOLIDATED ENDPOINTS FROM deepzoom_tiles.py
# ============================================================================

@router.post("/deepzoom/process-missing", 
             summary="Avvia generazione manuale tiles per foto specifica", 
             tags=["Deep Zoom - Tiles Management"])
async def process_missing_tiles(
    photo_id: UUID,
    site_id: UUID,
    background_tasks: BackgroundTasks,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Avvia la generazione manuale dei tiles per una foto specifica

    Args:
        photo_id: ID della foto da processare
        site_id: ID del sito archeologico
        background_tasks: FastAPI BackgroundTasks per processing asincrono

    Returns:
        Stato immediato della richiesta di generazione tiles
    """
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify write permissions
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Verifica che la foto esista e appartenga al sito
        photo_query = select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
        photo_result = await db.execute(photo_query)
        photo = photo_result.scalar_one_or_none()

        if not photo:
            raise HTTPException(status_code=404, detail="Foto non trovata nel sito specificato")

        # Verifica se i tiles sono già stati generati
        existing_tiles = await deep_zoom_minio_service.get_deep_zoom_info(str(site_id), str(photo_id))

        if existing_tiles and existing_tiles.get('available', False):
            return JSONResponse({
                "photo_id": str(photo_id),
                "site_id": str(site_id),
                "status": "already_exists",
                "message": "I tiles per questa foto sono già stati generati",
                "tile_info": existing_tiles,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

        # Verifica se c'è già un processo in corso
        task_status = await deep_zoom_background_service.get_task_status(str(photo_id))

        if task_status and task_status['status'] in ['pending', 'processing', 'retrying']:
            return JSONResponse({
                "photo_id": str(photo_id),
                "site_id": str(site_id),
                "status": "already_processing",
                "message": f"Generazione tiles già in corso (stato: {task_status['status']})",
                "task_status": task_status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

        # Carica il contenuto del file originale
        try:
            original_file_content = await archaeological_minio_service.get_file(photo.filepath)
        except Exception as e:
            logger.error(f"Failed to load original file for photo {photo_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Impossibile caricare il file originale: {str(e)}"
            )

        # Prepara i metadati archeologici
        archaeological_metadata = {
            'inventory_number': photo.inventory_number,
            'excavation_area': photo.excavation_area,
            'material': photo.material.value if photo.material else None,
            'chronology_period': photo.chronology_period,
            'photo_type': photo.photo_type.value if photo.photo_type else None,
            'photographer': photo.photographer,
            'description': photo.description,
            'keywords': photo.keywords
        }

        # Avvia il processo di generazione tiles in background
        result = await deep_zoom_background_service.schedule_tile_processing(
            photo_id=str(photo_id),
            site_id=str(site_id),
            file_path=photo.filepath,
            original_file_content=original_file_content,
            archaeological_metadata=archaeological_metadata
        )

        # Aggiorna lo stato nel database
        photo.deepzoom_status = 'scheduled'
        await db.commit()

        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TILES_GENERATION",
            activity_desc=f"Avviata generazione tiles per foto: {photo.filename}",
            extra_data={
                "photo_id": str(photo_id),
                "filename": photo.filename,
                "action": "manual_tiles_generation"
            }
        )
        db.add(activity)
        await db.commit()

        logger.info(f"Manual tiles generation scheduled for photo {photo_id} by user {current_user_id}")

        return JSONResponse({
            "photo_id": str(photo_id),
            "site_id": str(site_id),
            "status": "scheduled",
            "message": "Generazione tiles avviata con successo",
            "task_info": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling tiles generation for photo {photo_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'avvio della generazione tiles: {str(e)}"
        )


@router.post("/deepzoom/verify-and-repair", 
             summary="Verifica stato tiles e avvia riparazione se necessario", 
             tags=["Deep Zoom - Tiles Management"])
async def verify_and_repair_tiles(
    photo_id: UUID,
    site_id: UUID,
    auto_repair: bool = True,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Verifica lo stato dei tiles per una foto e avvia automaticamente la generazione se mancanti

    Args:
        photo_id: ID della foto da verificare
        site_id: ID del sito archeologico
        auto_repair: Se True, avvia automaticamente la generazione se i tiles sono mancanti

    Returns:
        Stato completo della verifica e eventuale riparazione
    """
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify read permissions
    if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        # Verifica che la foto esista e appartenga al sito
        photo_query = select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
        photo_result = await db.execute(photo_query)
        photo = photo_result.scalar_one_or_none()

        if not photo:
            raise HTTPException(status_code=404, detail="Foto non trovata nel sito specificato")

        # Verifica lo stato dei tiles
        tile_info = await deep_zoom_minio_service.get_deep_zoom_info(str(site_id), str(photo_id))
        processing_status = await deep_zoom_minio_service.get_processing_status(str(site_id), str(photo_id))
        task_status = await deep_zoom_background_service.get_task_status(str(photo_id))

        # Determina lo stato attuale
        current_status = "unknown"
        status_message = ""
        repair_needed = False
        repair_action = None

        if task_status and task_status['status'] in ['pending', 'processing', 'retrying']:
            current_status = "processing"
            status_message = f"Generazione tiles già in corso (stato: {task_status['status']})"
        elif tile_info and tile_info.get('available', False):
            current_status = "complete"
            status_message = "Tiles già generati e disponibili"
        elif processing_status and processing_status.get('status') == 'failed':
            current_status = "failed"
            status_message = f"Generazione tiles fallita: {processing_status.get('error', 'Errore sconosciuto')}"
            repair_needed = True
        else:
            current_status = "missing"
            status_message = "Tiles non generati"
            repair_needed = True

        # Log attività di verifica
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TILES_VERIFICATION",
            activity_desc=f"Verificato stato tiles per foto: {photo.filename}",
            extra_data={
                "photo_id": str(photo_id),
                "filename": photo.filename,
                "status": current_status,
                "auto_repair": auto_repair
            }
        )
        db.add(activity)
        await db.commit()

        response_data = {
            "photo_id": str(photo_id),
            "site_id": str(site_id),
            "verification_status": current_status,
            "status_message": status_message,
            "tile_info": tile_info,
            "processing_status": processing_status,
            "task_status": task_status,
            "repair_needed": repair_needed,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Se è richiesta la riparazione automatica e i tiles sono mancanti/falliti
        if auto_repair and repair_needed and site_info.get("permission_level") in ["admin", "editor"]:
            try:
                # Carica il contenuto del file originale
                original_file_content = await archaeological_minio_service.get_file(photo.filepath)

                # Prepara i metadati archeologici
                archaeological_metadata = {
                    'inventory_number': photo.inventory_number,
                    'excavation_area': photo.excavation_area,
                    'material': photo.material.value if photo.material else None,
                    'chronology_period': photo.chronology_period,
                    'photo_type': photo.photo_type.value if photo.photo_type else None,
                    'photographer': photo.photographer,
                    'description': photo.description,
                    'keywords': photo.keywords
                }

                # Avvia il processo di generazione tiles
                repair_result = await deep_zoom_background_service.schedule_tile_processing(
                    photo_id=str(photo_id),
                    site_id=str(site_id),
                    file_path=photo.filepath,
                    original_file_content=original_file_content,
                    archaeological_metadata=archaeological_metadata
                )

                # Aggiorna lo stato nel database
                photo.deepzoom_status = 'scheduled'
                await db.commit()

                repair_action = {
                    "action": "auto_repair_scheduled",
                    "message": "Riparazione automatica avviata",
                    "repair_result": repair_result
                }
                response_data["repair_action"] = repair_action

                # Log attività di riparazione
                repair_activity = UserActivity(
                    user_id=current_user_id,
                    site_id=site_id,
                    activity_type="TILES_REPAIR",
                    activity_desc=f"Avviata riparazione tiles per foto: {photo.filename}",
                    extra_data={
                        "photo_id": str(photo_id),
                        "filename": photo.filename,
                        "action": "auto_repair"
                    }
                )
                db.add(repair_activity)
                await db.commit()

                logger.info(f"Auto-repair scheduled for photo {photo_id} by user {current_user_id}")

            except Exception as repair_error:
                logger.error(f"Failed to schedule auto-repair for photo {photo_id}: {repair_error}")
                repair_action = {
                    "action": "auto_repair_failed",
                    "message": f"Riparazione automatica fallita: {str(repair_error)}",
                    "error": str(repair_error)
                }
                response_data["repair_action"] = repair_action

        return JSONResponse(response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during tiles verification for photo {photo_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la verifica dei tiles: {str(e)}"
        )


@router.get("/deepzoom/batch-status", 
            summary="Ottieni stato tiles per un batch di foto", 
            tags=["Deep Zoom - Tiles Management"])
async def get_batch_tiles_status(
    site_id: UUID,
    photo_ids: Optional[List[UUID]] = None,
    limit: int = 100,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni lo stato dei tiles per un batch di foto

    Args:
        site_id: ID del sito archeologico
        photo_ids: Lista specifica di ID foto (opzionale)
        limit: Limite risultati per paginazione
        offset: Offset per paginazione

    Returns:
        Stato dei tiles per le foto richieste
    """
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify read permissions
    if not site_info.get("permission_level") or site_info.get("permission_level") == "viewer":
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        # Costruisci la query base
        photos_query = select(Photo).where(Photo.site_id == site_id)

        # Filtra per ID specifici se forniti
        if photo_ids:
            photos_query = photos_query.where(Photo.id.in_(photo_ids))

        # Applica paginazione
        photos_query = photos_query.offset(offset).limit(limit)

        # Esegui la query
        photos_result = await db.execute(photos_query)
        photos = photos_result.scalars().all()

        # Prepara i risultati
        batch_status = []
        for photo in photos:
            # Ottieni informazioni sui tiles
            tile_info = await deep_zoom_minio_service.get_deep_zoom_info(str(site_id), str(photo.id))
            processing_status = await deep_zoom_minio_service.get_processing_status(str(site_id), str(photo.id))
            task_status = await deep_zoom_background_service.get_task_status(str(photo.id))

            # Determina lo stato complessivo
            overall_status = "unknown"
            if task_status and task_status['status'] in ['pending', 'processing', 'retrying']:
                overall_status = "processing"
            elif tile_info and tile_info.get('available', False):
                overall_status = "complete"
            elif processing_status and processing_status.get('status') == 'failed':
                overall_status = "failed"
            elif photo.deepzoom_status:
                overall_status = photo.deepzoom_status
            else:
                overall_status = "missing"

            photo_status = {
                "photo_id": str(photo.id),
                "filename": photo.filename,
                "overall_status": overall_status,
                "database_status": photo.deepzoom_status,
                "has_deep_zoom": photo.has_deep_zoom,
                "tile_count": photo.tile_count,
                "max_zoom_level": photo.max_zoom_level,
                "deepzoom_processed_at": photo.deepzoom_processed_at.isoformat() if photo.deepzoom_processed_at else None,
                "tile_info": tile_info,
                "processing_status": processing_status,
                "task_status": task_status
            }
            batch_status.append(photo_status)

        # Calcola statistiche
        status_counts = {}
        for status_item in batch_status:
            status = status_item["overall_status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        return JSONResponse({
            "site_id": str(site_id),
            "batch_status": batch_status,
            "statistics": {
                "total_photos": len(batch_status),
                "status_counts": status_counts,
                "processing": status_counts.get("processing", 0),
                "complete": status_counts.get("complete", 0),
                "failed": status_counts.get("failed", 0),
                "missing": status_counts.get("missing", 0)
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(batch_status) == limit
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting batch tiles status for site {site_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante il recupero dello stato batch: {str(e)}"
        )


@router.post("/deepzoom/batch-repair", 
             summary="Avvia riparazione batch tiles per più foto", 
             tags=["Deep Zoom - Tiles Management"])
async def batch_repair_tiles(
    site_id: UUID,
    photo_ids: List[UUID],
    force_repair: bool = False,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Avvia la riparazione batch dei tiles per più foto

    Args:
        site_id: ID del sito archeologico
        photo_ids: Lista di ID foto da riparare
        force_repair: Se True, rigenera anche i tiles esistenti

    Returns:
        Risultati della riparazione batch
    """
    # Verify site access
    site_info = verify_site_access(site_id, user_sites)

    # Verify write permissions
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        # Verifica che le foto esistano e appartengano al sito
        photos_query = select(Photo).where(
            and_(Photo.id.in_(photo_ids), Photo.site_id == site_id)
        )
        photos_result = await db.execute(photos_query)
        photos = photos_result.scalars().all()

        if not photos:
            raise HTTPException(status_code=404, detail="Nessuna foto trovata con gli ID specificati")

        # Risultati della riparazione
        repair_results = {
            "total_requested": len(photo_ids),
            "found_photos": len(photos),
            "scheduled": 0,
            "skipped": 0,
            "failed": 0,
            "details": []
        }

        for photo in photos:
            try:
                # Verifica lo stato attuale
                tile_info = await deep_zoom_minio_service.get_deep_zoom_info(str(site_id), str(photo.id))
                task_status = await deep_zoom_background_service.get_task_status(str(photo.id))

                # Determina se la riparazione è necessaria
                needs_repair = False
                skip_reason = None

                if task_status and task_status['status'] in ['pending', 'processing', 'retrying']:
                    skip_reason = "Già in elaborazione"
                elif tile_info and tile_info.get('available', False) and not force_repair:
                    skip_reason = "Tiles già disponibili"
                else:
                    needs_repair = True

                photo_result = {
                    "photo_id": str(photo.id),
                    "filename": photo.filename,
                    "needs_repair": needs_repair,
                    "skip_reason": skip_reason
                }

                if needs_repair:
                    # Carica il contenuto del file originale
                    original_file_content = await archaeological_minio_service.get_file(photo.filepath)

                    # Prepara i metadati archeologici
                    archaeological_metadata = {
                        'inventory_number': photo.inventory_number,
                        'excavation_area': photo.excavation_area,
                        'material': photo.material.value if photo.material else None,
                        'chronology_period': photo.chronology_period,
                        'photo_type': photo.photo_type.value if photo.photo_type else None,
                        'photographer': photo.photographer,
                        'description': photo.description,
                        'keywords': photo.keywords
                    }

                    # Avvia il processo di generazione tiles
                    repair_result = await deep_zoom_background_service.schedule_tile_processing(
                        photo_id=str(photo.id),
                        site_id=str(site_id),
                        file_path=photo.filepath,
                        original_file_content=original_file_content,
                        archaeological_metadata=archaeological_metadata
                    )

                    # Aggiorna lo stato nel database
                    photo.deepzoom_status = 'scheduled'

                    photo_result.update({
                        "repair_scheduled": True,
                        "repair_result": repair_result
                    })
                    repair_results["scheduled"] += 1
                else:
                    repair_results["skipped"] += 1

                repair_results["details"].append(photo_result)

            except Exception as photo_error:
                logger.error(f"Failed to process photo {photo.id} in batch repair: {photo_error}")
                repair_results["details"].append({
                    "photo_id": str(photo.id),
                    "filename": photo.filename,
                    "error": str(photo_error)
                })
                repair_results["failed"] += 1

        # Commit delle modifiche al database
        await db.commit()

        # Log attività batch
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TILES_BATCH_REPAIR",
            activity_desc=f"Avviata riparazione batch tiles per {repair_results['scheduled']} foto",
            extra_data={
                "total_requested": repair_results["total_requested"],
                "scheduled": repair_results["scheduled"],
                "skipped": repair_results["skipped"],
                "failed": repair_results["failed"],
                "force_repair": force_repair
            }
        )
        db.add(activity)
        await db.commit()

        logger.info(f"Batch tiles repair scheduled for site {site_id} by user {current_user_id}: {repair_results['scheduled']} photos")

        return JSONResponse({
            "site_id": str(site_id),
            "batch_repair_results": repair_results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during batch tiles repair for site {site_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la riparazione batch: {str(e)}"
        )


# ============================================================================
# TILES VERIFICATION SERVICE ENDPOINTS
# ============================================================================

@router.get("/deepzoom/verification/status", 
            summary="Ottieni stato servizio di verifica periodica tiles", 
            tags=["Deep Zoom - Verification"])
async def get_verification_status(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni lo stato del servizio di verifica periodica dei tiles"""
    try:
        from app.services.tiles_verification_service import tiles_verification_service

        verification_status = await tiles_verification_service.get_verification_status()

        return JSONResponse({
            "verification_service_status": verification_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting verification service status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante il recupero dello stato del servizio di verifica: {str(e)}"
        )


@router.post("/deepzoom/verification/trigger", 
             summary="Avvia manualmente verifica tiles per sito", 
             tags=["Deep Zoom - Verification"])
async def trigger_manual_verification(
    site_id: Optional[UUID] = None,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Avvia manualmente la verifica dei tiles per un sito specifico o per tutti i siti

    Args:
        site_id: ID del sito da verificare (opzionale, se None verifica tutti i siti)

    Returns:
        Risultato dell'avvio della verifica manuale
    """
    # If site_id is specified, verify access
    if site_id:
        site_info = verify_site_access(site_id, user_sites)
        if site_info.get("permission_level") not in ["admin", "editor"]:
            raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        from app.services.tiles_verification_service import tiles_verification_service

        # Avvia la verifica manuale
        result = await tiles_verification_service.trigger_manual_verification(
            site_id=str(site_id) if site_id else None
        )

        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id if site_id else None,
            activity_type="MANUAL_TILES_VERIFICATION",
            activity_desc=f"Avviata verifica manuale tiles" + (f" per sito {site_id}" if site_id else " per tutti i siti"),
            extra_data={
                "site_id": str(site_id) if site_id else None,
                "action": "manual_verification_trigger"
            }
        )
        db.add(activity)
        await db.commit()

        logger.info(f"Manual tiles verification triggered by user {current_user_id}" +
                   (f" for site {site_id}" if site_id else " for all sites"))

        return JSONResponse({
            "verification_result": result,
            "triggered_by": str(current_user_id),
            "site_id": str(site_id) if site_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering manual verification: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'avvio della verifica manuale: {str(e)}"
        )


@router.put("/deepzoom/verification/configure", 
            summary="Configura impostazioni servizio di verifica periodica", 
            tags=["Deep Zoom - Verification"])
async def configure_verification_service(
    verification_interval_hours: Optional[int] = None,
    batch_size: Optional[int] = None,
    max_concurrent_verifications: Optional[int] = None,
    auto_repair_enabled: Optional[bool] = None,
    site_id: UUID = None,  # Required for permission check
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Configura le impostazioni del servizio di verifica periodica dei tiles

    Args:
        verification_interval_hours: Intervallo di verifica in ore (default: 24)
        batch_size: Dimensione del batch per elaborazione (default: 50)
        max_concurrent_verifications: Numero massimo di verifiche concorrenti (default: 3)
        auto_repair_enabled: Abilita riparazione automatica (default: True)

    Returns:
        Nuove configurazioni del servizio
    """
    # Verify site access and admin permissions
    if site_id:
        site_info = verify_site_access(site_id, user_sites)
        if site_info.get("permission_level") != "admin":
            raise HTTPException(status_code=403, detail="Permessi di amministrazione richiesti")

    try:
        from app.services.tiles_verification_service import tiles_verification_service

        # Configura il servizio
        tiles_verification_service.configure_settings(
            verification_interval_hours=verification_interval_hours,
            batch_size=batch_size,
            max_concurrent_verifications=max_concurrent_verifications,
            auto_repair_enabled=auto_repair_enabled
        )

        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id if site_id else None,
            activity_type="VERIFICATION_SERVICE_CONFIG",
            activity_desc="Configurato servizio di verifica periodica tiles",
            extra_data={
                "verification_interval_hours": verification_interval_hours,
                "batch_size": batch_size,
                "max_concurrent_verifications": max_concurrent_verifications,
                "auto_repair_enabled": auto_repair_enabled
            }
        )
        db.add(activity)
        await db.commit()

        logger.info(f"Verification service configured by user {current_user_id}")

        # Ottieni lo stato aggiornato
        verification_status = await tiles_verification_service.get_verification_status()

        return JSONResponse({
            "message": "Servizio di verifica configurato con successo",
            "configured_by": str(current_user_id),
            "new_configuration": {
                "verification_interval_hours": verification_interval_hours,
                "batch_size": batch_size,
                "max_concurrent_verifications": max_concurrent_verifications,
                "auto_repair_enabled": auto_repair_enabled
            },
            "updated_service_status": verification_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"Error configuring verification service: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la configurazione del servizio: {str(e)}"
        )


@router.post("/deepzoom/verification/start", 
             summary="Avvia servizio di verifica periodica tiles", 
             tags=["Deep Zoom - Verification"])
async def start_verification_service(
    site_id: UUID,  # Required for permission check
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Avvia il servizio di verifica periodica dei tiles"""
    # Verify site access and admin permissions
    site_info = verify_site_access(site_id, user_sites)
    if site_info.get("permission_level") != "admin":
        raise HTTPException(status_code=403, detail="Permessi di amministrazione richiesti")

    try:
        from app.services.tiles_verification_service import tiles_verification_service

        # Avvia il servizio
        await tiles_verification_service.start_periodic_verification()

        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id,
            activity_type="VERIFICATION_SERVICE_START",
            activity_desc="Avviato servizio di verifica periodica tiles",
            extra_data={"action": "start_verification_service"}
        )
        db.add(activity)
        await db.commit()

        logger.info(f"Verification service started by user {current_user_id}")

        # Ottieni lo stato del servizio
        verification_status = await tiles_verification_service.get_verification_status()

        return JSONResponse({
            "message": "Servizio di verifica periodica avviato con successo",
            "started_by": str(current_user_id),
            "service_status": verification_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"Error starting verification service: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'avvio del servizio: {str(e)}"
        )


@router.post("/deepzoom/verification/stop", 
             summary="Ferma servizio di verifica periodica tiles", 
             tags=["Deep Zoom - Verification"])
async def stop_verification_service(
    site_id: UUID,  # Required for permission check
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Ferma il servizio di verifica periodica dei tiles"""
    # Verify site access and admin permissions
    site_info = verify_site_access(site_id, user_sites)
    if site_info.get("permission_level") != "admin":
        raise HTTPException(status_code=403, detail="Permessi di amministrazione richiesti")

    try:
        from app.services.tiles_verification_service import tiles_verification_service

        # Ferma il servizio
        await tiles_verification_service.stop_periodic_verification()

        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site_id,
            activity_type="VERIFICATION_SERVICE_STOP",
            activity_desc="Fermato servizio di verifica periodica tiles",
            extra_data={"action": "stop_verification_service"}
        )
        db.add(activity)
        await db.commit()

        logger.info(f"Verification service stopped by user {current_user_id}")

        # Ottieni lo stato del servizio
        verification_status = await tiles_verification_service.get_verification_status()

        return JSONResponse({
            "message": "Servizio di verifica periodica fermato con successo",
            "stopped_by": str(current_user_id),
            "service_status": verification_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"Error stopping verification service: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'arresto del servizio: {str(e)}"
        )


# ============================================================================
# BATCH PROCESSING ENDPOINTS
# ============================================================================

@router.post("/sites/{site_id}/photos/batch-process", 
             summary="Processamento batch deep zoom", 
             tags=["Deep Zoom - Batch"])
async def v1_batch_process_deepzoom(
    site_id: UUID,
    batch_request: BatchProcessRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Processa multiple foto per deep zoom in batch.
    Supporta fino a 50 foto per richiesta con priorità personalizzabile.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)

    # Verifica permessi di processing
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per processare deep zoom in batch"
        )

    if len(batch_request.photo_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 photos per batch request"
        )

    # Verifica che tutte le foto appartengano al sito
    photos = await db.execute(
        select(Photo).where(Photo.id.in_(batch_request.photo_ids))
    )
    photos = photos.scalars().all()

    if len(photos) != len(batch_request.photo_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Una o più foto non trovate"
        )

    # Verifica che tutte le foto appartengano al sito
    for photo in photos:
        if str(photo.site_id) != str(site_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Foto {photo.id} non appartiene al sito {site_id}"
            )

    # Avvia processing batch
    results = []
    for photo_id in batch_request.photo_ids:
        try:
            result = await process_deep_zoom(site_id, photo_id, current_user_id, user_sites, db)
            results.append({
                "photo_id": str(photo_id),
                "status": "started",
                "result": result
            })
        except Exception as e:
            results.append({
                "photo_id": str(photo_id),
                "status": "error",
                "error": str(e)
            })

    return {
        "batch_id": f"batch_{site_id}_{current_user_id}_{len(batch_request.photo_ids)}",
        "site_id": str(site_id),
        "photos_processed": len(batch_request.photo_ids),
        "results": results,
        "priority": batch_request.priority,
        "force_reprocess": batch_request.force_reprocess
    }


# ============================================================================
# MIGRATION HELPER ENDPOINTS
# ============================================================================

@router.get("/migration/help", 
            summary="Aiuto migrazione API deep zoom", 
            tags=["Deep Zoom - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per deep zoom.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/site/{site_id}/photos/{photo_id}/deepzoom/process": "/api/v1/deepzoom/sites/{site_id}/photos/{photo_id}/process",
                "/api/site/{site_id}/photos/{photo_id}/deepzoom/status": "/api/v1/deepzoom/sites/{site_id}/photos/{photo_id}/status",
                "/api/site/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.{format}": "/api/v1/deepzoom/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}",
                "/api/site/{site_id}/photos/processing-queue": "/api/v1/deepzoom/sites/{site_id}/processing-queue",
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints deep zoom",
                "Nuovi endpoints batch processing",
                "Miglioramento gestione background processing",
                "Headers di deprecazione automatici",
                "Consolidamento da sites_deepzoom.py e deepzoom_tiles.py"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints deep zoom"
        }
    }
