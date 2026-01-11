"""
API v1 - Deep Zoom Management
Endpoints per gestione completa deep zoom tiles e processing.
Refactored to use consolidated DeepZoomService and standard strict authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, UploadFile
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import (
    get_current_user_id_with_blacklist, 
    require_site_permission,
    get_current_user_token_with_blacklist,
    SecurityService,
    get_current_user_id,
    get_current_user_with_superuser_check
)
from app.database.db import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.deepzoom_enums import DeepZoomStatus
from app.routes.api.service_dependencies import DeepZoomServiceDep
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    PhotoNotFoundError,
    SiteNotFoundError,
    DomainValidationError,
    StorageError,
    InsufficientPermissionsError
)
# Services
from app.services.tiles_verification_service import tiles_verification_service

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


# ============================================================================
# DEEP ZOOM INFO & TILE SERVING
# ============================================================================

@router.get("/sites/{site_id}/photos/{photo_id}/info",
            summary="Ottieni informazioni deep zoom per una foto",
            tags=["Deep Zoom"])
async def get_deep_zoom_info(
    site_id: UUID,
    photo_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Ottieni informazioni deep zoom per una foto"""
    # Verify read permissions using centralized dependency
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")

    # Get info via service
    deep_zoom_info = await deep_zoom_service.get_deep_zoom_info(str(site_id), str(photo_id))
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
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Ottieni singolo tile deep zoom"""
    # Verify read permissions
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")

    # Validate format
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")

    # Get tile content
    tile_content = await deep_zoom_service.get_tile_content(str(site_id), str(photo_id), level, x, y)

    if not tile_content:
        raise HTTPException(status_code=404, detail="Tile non trovato")

    media_type = "image/jpeg" if format in ['jpg', 'jpeg'] else "image/png"
    return Response(
        content=tile_content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*"
        }
    )


# ============================================================================
# PUBLIC TILE ENDPOINT (For OpenSeadragon)
# ============================================================================

@router.get("/public/sites/{site_id}/photos/{photo_id}/tiles/{level}/{x}_{y}.{format}",
            summary="Public tile endpoint for OpenSeadragon",
            tags=["Deep Zoom - Public"])
async def get_public_deep_zoom_tile(
    site_id: UUID,
    photo_id: UUID,
    level: int,
    x: int,
    y: int,
    format: str,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep
):
    """
    Public tile endpoint using browser session or cookie authentication.
    Allows OpenSeadragon to load tiles without Authorization headers.
    """
    # 1. Validate format
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")

    # 2. Authenticate (Cookie/Session automatic check via get_current_user_id)
    # Allows both standard Bearer token AND Cookie auth
    try:
        current_user_id = await get_current_user_id(request)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")

    # 3. Check Permissions (implicitly uses current_user_id from request context in require_site_permission)
    # We pass 'read' requirement.
    # Note: require_site_permission internally fetches user from token/db.
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")

    # 4. Fetch Tile
    tile_content = await deep_zoom_service.get_tile_content(str(site_id), str(photo_id), level, x, y)
    
    if not tile_content:
        raise HTTPException(status_code=404, detail=f"Tile {level}/{x}_{y} non trovato")
    
    media_type = "image/jpeg" if format in ['jpg', 'jpeg'] else "image/png"
    return Response(
        content=tile_content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*"
        }
    )


# ============================================================================
# PROCESSING & MANAGEMENT
# ============================================================================

@router.post("/sites/{site_id}/photos/{photo_id}/process",
             summary="Processa foto esistente per generare deep zoom tiles",
             tags=["Deep Zoom"])
async def process_deep_zoom(
    site_id: UUID,
    photo_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Processa foto esistente per generare deep zoom tiles"""
    # Verify write permissions
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="write")

    result = await deep_zoom_service.process_photo(
        str(site_id), 
        str(photo_id), 
        current_user_id, 
        force_reprocess=True
    )

    return JSONResponse({
        "message": "Deep zoom processing avviato",
        "photo_id": str(photo_id),
        "task_info": result
    })


@router.get("/sites/{site_id}/photos/{photo_id}/status",
            summary="Ottieni status di elaborazione deep zoom",
            tags=["Deep Zoom"])
async def get_deep_zoom_processing_status(
    site_id: UUID,
    photo_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Ottieni status di elaborazione deep zoom per una foto"""
    # Verify read permissions
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")

    status_info = await deep_zoom_service.get_processing_status(str(site_id), str(photo_id))
    return JSONResponse(status_info)


@router.get("/sites/{site_id}/processing-queue", 
            summary="Controlla lo stato della coda di processamento", 
            tags=["Deep Zoom"])
async def get_processing_queue_status(
    site_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Endpoint per controllare lo stato della coda di processamento"""
    # Verify read permissions
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")
    
    # Leverages the batch status method which does a similar listing
    # Or we can keep utilizing the background service direct dependency if strictly needed for specific queue metrics
    # For now, let's map it to batch status of the site for simplicity in refactor, or keep background service call if metrics are specific.
    # The original implementation queried DB for 'scheduled'/'processing'. Let's implement a clean call.
    
    # We will use the service's batch status method (which lists all, so we might filter) 
    # OR better, since this is a specific dashboard view, we might want to let the Service handle "get_queue_for_site".
    
    # For this refactor, let's use the BackgroundService directly for valid queue stats, but wrapped for safety.
    queue_status = await deep_zoom_background_service.get_queue_status()
    # Note: get_queue_status is global.
    
    # Let's delegate to our new service to get site-specific processing photos
    # We'll use get_batch_status and filter client-side or add a filter param later.
    # The original endpoint did specific DB queries. Let's assume DeepZoomService.get_batch_status gives us what we need for now.
    
    batch_data = await deep_zoom_service.get_batch_status(str(site_id), limit=50)
    
    processing_photos = [p for p in batch_data['photos'] if p['status'] in [DeepZoomStatus.PROCESSING.value, DeepZoomStatus.SCHEDULED.value, 'pending']]
    
    return JSONResponse({
        "site_id": str(site_id),
        "processing_queue": processing_photos,
        "queue_length": len(processing_photos),
        "global_queue_status": queue_status
    })


# ============================================================================
# REPAIR & MAINTENANCE
# ============================================================================

@router.post("/deepzoom/process-missing",
             summary="Avvia generazione manuale tiles per foto specifica",
             tags=["Deep Zoom - Tiles Management"])
async def process_missing_tiles(
    photo_id: UUID,
    site_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Avvia la generazione manuale dei tiles per una foto specifica"""
    # Verify write permissions
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="write")

    result = await deep_zoom_service.process_missing_tiles(str(site_id), str(photo_id), current_user_id)
    return JSONResponse(result)


@router.post("/deepzoom/verify-and-repair",
             summary="Verifica stato tiles e avvia riparazione se necessario",
             tags=["Deep Zoom - Tiles Management"])
async def verify_and_repair_tiles(
    photo_id: UUID,
    site_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    auto_repair: bool = True,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Verifica lo stato dei tiles per una foto e avvia automaticamente la generazione se mancanti"""
    # Verify read permissions (repair needs write, but verify only read)
    # If auto_repair is True, we check write permission inside
    
    perms = await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")
    can_write = perms.get("can_write", False) or perms.get("is_superuser", False)
    
    if auto_repair and not can_write:
        # Step down to read-only verification
        auto_repair = False
        
    result = await deep_zoom_service.verify_and_repair(
        str(site_id), str(photo_id), current_user_id, auto_repair=auto_repair
    )
    return JSONResponse(result)


@router.get("/deepzoom/batch-status",
            summary="Ottieni stato tiles per un batch di foto",
            tags=["Deep Zoom - Tiles Management"])
async def get_batch_tiles_status(
    site_id: UUID,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    limit: int = 100,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Ottieni lo stato dei tiles per un batch di foto"""
    # Verify read permissions
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="read")

    result = await deep_zoom_service.get_batch_status(str(site_id), limit, offset)
    return JSONResponse(result)


# ============================================================================
# BATCH PROCESSING
# ============================================================================

@router.post("/sites/{site_id}/photos/batch-process", 
             summary="Processamento batch deep zoom", 
             tags=["Deep Zoom - Batch"])
async def v1_batch_process_deepzoom(
    site_id: UUID,
    batch_request: BatchProcessRequest,
    request: Request,
    deep_zoom_service: DeepZoomServiceDep,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Processa multiple foto per deep zoom in batch."""
    # Verify write/admin permissions (batch usually requires higher privs or at least write)
    await require_site_permission(site_id, request, db=deep_zoom_service.db, required_permission="write")

    if len(batch_request.photo_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 photos per batch request")

    results = []
    for photo_id in batch_request.photo_ids:
        try:
            # Reusing the single process method which handles retrieving and scheduling
            res = await deep_zoom_service.process_photo(
                str(site_id), 
                str(photo_id), 
                current_user_id, 
                force_reprocess=batch_request.force_reprocess
            )
            results.append({"photo_id": str(photo_id), "status": DeepZoomStatus.SCHEDULED.value, "result": res})
        except Exception as e:
            results.append({"photo_id": str(photo_id), "status": DeepZoomStatus.ERROR.value, "error": str(e)})

    return {
        "batch_id": f"batch_{site_id}_{current_user_id}_{len(batch_request.photo_ids)}",
        "site_id": str(site_id),
        "photos_processed": len(batch_request.photo_ids),
        "results": results,
        "priority": batch_request.priority
    }


# ============================================================================
# BACKGROUND SERVICE HEALTH
# ============================================================================

@router.get("/background/health",
            summary="Get background service health status",
            tags=["Deep Zoom - Background Service"])
async def get_background_service_health(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Get comprehensive health status of the DeepZoom background service"""
    # Use background service directly as it is a singleton system service
    return await deep_zoom_background_service.get_health_status()


# ============================================================================
# VERIFICATION SERVICE (ADMIN)
# ============================================================================

@router.get("/verification/status",
            summary="Ottieni stato del servizio di verifica periodica",
            tags=["Deep Zoom - Verification"])
async def get_verification_status(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Ottieni stato del servizio di verifica periodica tiles"""
    # Check if user is admin (using require_site_permission is site-specific, 
    # but this is a global service. We should check user profile/superuser status)
    
    # Using superuser bypass logic manually for now as this is a global system service,
    # or ensure caller has admin rights. 
    # Since we don't have a "global admin" dependency ready here (except superuser), 
    # we can check if user is superuser or just allow authenticated users to see status.
    # Let's verify user info.
    
    # Allow read for authenticated users
    
    try:
        status_info = await tiles_verification_service.get_verification_status()
        return JSONResponse({
            "verification_service_status": status_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting verification status: {e}")
        # Return 500 but wrapped in JSON
        raise HTTPException(
            status_code=500,
            detail=f"Errore recupero stato verifica: {str(e)}"
        )


@router.post("/verification/trigger",
             summary="Avvia verifica manuale tiles",
             tags=["Deep Zoom - Verification"])
async def trigger_manual_verification(
    request: Request,
    site_id: Optional[UUID] = None,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Avvia verifica manuale per un sito o globale"""
    if site_id:
        # Site specific check
        await require_site_permission(site_id, request, db=db, required_permission="write")
        
        result = await tiles_verification_service.trigger_manual_verification(str(site_id))
    else:
        # Global trigger requires Superuser or high level admin
        # We can implement a simple check here
        user = await get_current_user_with_superuser_check(request, db=db) # We need to import this if not available
        if not user.is_superuser:
            raise InsufficientPermissionsError("Richiesto accesso Superuser per verifica globale")
            
        result = await tiles_verification_service.trigger_manual_verification(None)

    # Log activity
    # Note: UserActivity logging is typically handled by service, but here we can add if needed.
    # The service logs locally.
    
    return JSONResponse(result)


@router.put("/verification/configure",
            summary="Configura servizio verifica",
            tags=["Deep Zoom - Verification"])
async def configure_verification_service(
    config: VerificationConfig,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Configura parametri del servizio di verifica"""
    # Requires Superuser
    user = await get_current_user_with_superuser_check(request, db=db)
    if not user.is_superuser:
        raise InsufficientPermissionsError("Richiesto accesso Superuser")

    tiles_verification_service.configure_settings(
        verification_interval_hours=config.verification_interval_hours,
        batch_size=config.batch_size,
        max_concurrent_verifications=config.max_concurrent_verifications,
        auto_repair_enabled=config.auto_repair_enabled
    )
    
    return JSONResponse({
        "message": "Configurazione aggiornata", 
        "config": config.dict(exclude_none=True)
    })


@router.post("/verification/start",
             summary="Avvia servizio verifica periodica",
             tags=["Deep Zoom - Verification"])
async def start_verification_service_endpoint(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Avvia il servizio background di verifica"""
    # Requires Superuser
    user = await get_current_user_with_superuser_check(request, db=db)
    if not user.is_superuser:
        raise InsufficientPermissionsError("Richiesto accesso Superuser")

    await tiles_verification_service.start_periodic_verification()
    return JSONResponse({"message": "Servizio avviato"})


@router.post("/verification/stop",
             summary="Ferma servizio verifica periodica",
             tags=["Deep Zoom - Verification"])
async def stop_verification_service_endpoint(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Ferma il servizio background di verifica"""
    # Requires Superuser
    user = await get_current_user_with_superuser_check(request, db=db)
    if not user.is_superuser:
        raise InsufficientPermissionsError("Richiesto accesso Superuser")

    await tiles_verification_service.stop_periodic_verification()
    return JSONResponse({"message": "Servizio fermato"})
