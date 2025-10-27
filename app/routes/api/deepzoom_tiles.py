# app/routes/api/deepzoom_tiles.py - API endpoints for deep zoom tiles management

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import asyncio

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.models import UserActivity
from app.routes.api.dependencies import get_site_access
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.archaeological_minio_service import archaeological_minio_service

deepzoom_router = APIRouter()


@deepzoom_router.post("/deepzoom/process-missing")
async def process_missing_tiles(
    photo_id: UUID,
    site_id: UUID,
    background_tasks: BackgroundTasks,
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
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
    site, permission = site_access
    
    if not permission.can_write():
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


@deepzoom_router.post("/deepzoom/verify-and-repair")
async def verify_and_repair_tiles(
    photo_id: UUID,
    site_id: UUID,
    auto_repair: bool = True,
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
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
    site, permission = site_access
    
    if not permission.can_read():
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
        if auto_repair and repair_needed and permission.can_write():
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


@deepzoom_router.get("/deepzoom/batch-status")
async def get_batch_tiles_status(
    site_id: UUID,
    photo_ids: Optional[List[UUID]] = None,
    limit: int = 100,
    offset: int = 0,
    site_access: tuple = Depends(get_site_access),
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
    site, permission = site_access
    
    if not permission.can_read():
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
                "deep_zoom_processed_at": photo.deep_zoom_processed_at.isoformat() if photo.deep_zoom_processed_at else None,
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


@deepzoom_router.get("/deepzoom/verification/status")
async def get_verification_status(
    site_access: tuple = Depends(get_site_access)
):
    """
    Ottieni lo stato del servizio di verifica periodica dei tiles
    
    Returns:
        Stato completo del servizio di verifica
    """
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
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


@deepzoom_router.post("/deepzoom/verification/trigger")
async def trigger_manual_verification(
    site_id: Optional[UUID] = None,
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Avvia manualmente la verifica dei tiles per un sito specifico o per tutti i siti
    
    Args:
        site_id: ID del sito da verificare (opzionale, se None verifica tutti i siti)
        
    Returns:
        Risultato dell'avvio della verifica manuale
    """
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        from app.services.tiles_verification_service import tiles_verification_service
        
        # Se è specificato un site_id, verifica che l'utente abbia accesso
        if site_id:
            site_access_result = await get_site_access(site_id, current_user_id, db)
            target_site, target_permission = site_access_result
            
            if not target_permission.can_read():
                raise HTTPException(status_code=403, detail="Permessi insufficienti per il sito specificato")
        
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


@deepzoom_router.put("/deepzoom/verification/configure")
async def configure_verification_service(
    verification_interval_hours: Optional[int] = None,
    batch_size: Optional[int] = None,
    max_concurrent_verifications: Optional[int] = None,
    auto_repair_enabled: Optional[bool] = None,
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
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
    site, permission = site_access
    
    # Solo gli amministratori possono configurare il servizio
    if not permission.can_admin():
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
            site_id=site.id,
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


@deepzoom_router.post("/deepzoom/verification/start")
async def start_verification_service(
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Avvia il servizio di verifica periodica dei tiles
    
    Returns:
        Stato del servizio dopo l'avvio
    """
    site, permission = site_access
    
    # Solo gli amministratori possono avviare il servizio
    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Permessi di amministrazione richiesti")
    
    try:
        from app.services.tiles_verification_service import tiles_verification_service
        
        # Avvia il servizio
        await tiles_verification_service.start_periodic_verification()
        
        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site.id,
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


@deepzoom_router.post("/deepzoom/verification/stop")
async def stop_verification_service(
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ferma il servizio di verifica periodica dei tiles
    
    Returns:
        Stato del servizio dopo l'arresto
    """
    site, permission = site_access
    
    # Solo gli amministratori possono fermare il servizio
    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Permessi di amministrazione richiesti")
    
    try:
        from app.services.tiles_verification_service import tiles_verification_service
        
        # Ferma il servizio
        await tiles_verification_service.stop_periodic_verification()
        
        # Log attività
        activity = UserActivity(
            user_id=current_user_id,
            site_id=site.id,
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


@deepzoom_router.post("/deepzoom/batch-repair")
async def batch_repair_tiles(
    site_id: UUID,
    photo_ids: List[UUID],
    force_repair: bool = False,
    site_access: tuple = Depends(get_site_access),
    current_user_id: UUID = Depends(get_current_user_id),
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
    site, permission = site_access
    
    if not permission.can_write():
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