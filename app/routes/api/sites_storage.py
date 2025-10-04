# app/routes/api/sites_storage.py - Storage management API endpoints

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database.session import get_async_session
from app.routes.api.dependencies import get_site_access
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.storage_management_service import storage_management_service

storage_router = APIRouter()


@storage_router.get("/{site_id}/api/storage/stats")
async def get_site_storage_stats(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni statistiche storage del sito con gestione avanzata"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    try:
        # Ottieni statistiche da MinIO archeologico
        site_stats = await archaeological_minio_service.get_storage_stats(str(site_id))
        
        # Ottieni statistiche globali storage
        global_stats = await storage_management_service.get_storage_usage()
        
        # Controlla se storage è quasi pieno (>85%)
        storage_warning = False
        storage_usage_percent = 0
        if global_stats.get('total_size_gb', 0) > 0:
            # Assumiamo un limite di 10GB per MinIO locale
            storage_usage_percent = (global_stats['total_size_gb'] / 10.0) * 100
            storage_warning = storage_usage_percent > 85
        
        combined_stats = {
            **site_stats,
            'global_storage': global_stats,
            'storage_warning': storage_warning,
            'storage_usage_percent': min(100, storage_usage_percent)
        }
        
        return JSONResponse(combined_stats)
        
    except Exception as e:
        logger.error(f"Error getting storage stats: {e}")
        return JSONResponse({
            'site_id': str(site_id),
            'total_size_mb': 0,
            'photo_count': 0,
            'document_count': 0,
            'total_files': 0,
            'storage_warning': True,
            'error': str(e)
        })


@storage_router.post("/{site_id}/api/storage/cleanup")
async def emergency_storage_cleanup(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Cleanup di emergenza dello storage MinIO"""
    site, permission = site_access

    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Solo gli amministratori possono eseguire il cleanup")

    try:
        # Assicurati che tutti i bucket esistano
        bucket_check = await storage_management_service.ensure_buckets_exist()
        logger.info(f"Bucket check result: {bucket_check}")
        
        # Esegui cleanup di emergenza
        cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=500)
        
        return JSONResponse({
            'success': cleanup_result['success'],
            'total_freed_mb': cleanup_result['total_freed_mb'],
            'cleanup_actions': cleanup_result['cleanup_actions'],
            'bucket_check': bucket_check,
            'message': f"Cleanup completato: {cleanup_result['total_freed_mb']}MB liberati"
        })
        
    except Exception as e:
        logger.error(f"Emergency cleanup failed: {e}")
        return JSONResponse({
            'success': False,
            'total_freed_mb': 0,
            'cleanup_actions': [],
            'error': str(e),
            'message': f"Cleanup fallito: {str(e)}"
        }, status_code=500)


@storage_router.get("/{site_id}/api/storage/health")
async def check_storage_health(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Controlla lo stato di salute dello storage MinIO"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    try:
        # Controlla i bucket
        bucket_status = await storage_management_service.ensure_buckets_exist()
        
        # Controlla l'utilizzo dello storage
        storage_usage = await storage_management_service.get_storage_usage()
        
        # Determina lo stato di salute
        health_status = "healthy"
        issues = []
        
        if bucket_status['errors']:
            health_status = "warning"
            issues.append(f"{len(bucket_status['errors'])} bucket errors")
        
        if storage_usage.get('total_size_gb', 0) > 8:  # >80% di 10GB
            health_status = "critical"
            issues.append("Storage usage critical (>80%)")
        elif storage_usage.get('total_size_gb', 0) > 6:  # >60% di 10GB
            if health_status == "healthy":
                health_status = "warning"
            issues.append("Storage usage high (>60%)")
        
        return JSONResponse({
            'status': health_status,
            'issues': issues,
            'bucket_status': bucket_status,
            'storage_usage': storage_usage,
            'recommendations': [
                "Run emergency cleanup if storage >85%",
                "Check for orphaned files",
                "Consider archiving old photos"
            ] if health_status != "healthy" else []
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse({
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'bucket_status': {},
            'storage_usage': {},
            'recommendations': ["Contact system administrator"]
        }, status_code=500)