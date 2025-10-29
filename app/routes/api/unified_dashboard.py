from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger
from typing import List, Dict, Any
from uuid import UUID

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models import Photo, User, UserSitePermission, UserActivity

router = APIRouter()

@router.get("/activities/recent")
async def get_recent_activities(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get recent activities for the unified dashboard
    """
    try:
        # For now, return mock data since we don't have a dedicated activity table
        # In a real implementation, this would query from UserActivity or similar
        mock_activities = [
            {
                "id": 1,
                "type": "sites",
                "title": "Nuovo sito aggiunto",
                "description": "Nuovo sito archeologico aggiunto al sistema",
                "timestamp": "2023-10-23T10:30:00Z",
                "user": "Mario Rossi",
                "site": "Foro Romano",
                "actions": [
                    {"label": "Visualizza", "icon": "fa-eye", "action": "view"}
                ]
            },
            {
                "id": 2,
                "type": "giornale",
                "title": "Giornale creato",
                "description": "Nuovo giornale di cantiere creato",
                "timestamp": "2023-10-23T08:15:00Z",
                "user": "Giulia Bianchi",
                "site": "Scavo A",
                "actions": [
                    {"label": "Modifica", "icon": "fa-edit", "action": "edit"}
                ]
            },
            {
                "id": 3,
                "type": "photos",
                "title": "Fotografie caricate",
                "description": "Nuove fotografie caricate nel sistema",
                "timestamp": "2023-10-23T07:45:00Z",
                "user": "Paolo Verdi",
                "site": "Area B",
                "actions": [
                    {"label": "Visualizza", "icon": "fa-images", "action": "view_photos"}
                ]
            }
        ]
        
        return {
            "activities": mock_activities,
            "has_more": False
        }
        
    except Exception as e:
        logger.error(f"Error getting recent activities: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel caricamento delle attività")

@router.get("/sites/list")
async def get_sites_list(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get sites list for the unified dashboard
    """
    try:
        # Return user sites with additional information
        return {
            "sites": user_sites,
            "total": len(user_sites)
        }
        
    except Exception as e:
        logger.error(f"Error getting sites list: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel caricamento dei siti")

@router.get("/documents/count")
async def get_documents_count(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get documents count for the unified dashboard
    """
    try:
        # For now, return mock count since we don't have documents table
        # In a real implementation, this would count from documents table
        return {
            "count": 0
        }
        
    except Exception as e:
        logger.error(f"Error getting documents count: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel conteggio dei documenti")

@router.get("/stats/overview")
async def get_overview_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get overview statistics for the unified dashboard
    """
    try:
        if not user_sites:
            return {
                "sites_count": 0,
                "photos_count": 0,
                "us_usm_count": 0,
                "users_count": 0
            }
        
        site_ids = [UUID(site['id']) for site in user_sites]
        
        # Count photos
        photos_result = await db.execute(
            select(func.count(Photo.id)).where(Photo.site_id.in_(site_ids))
        )
        photos_count = photos_result.scalar() or 0
        
        # Count unique users
        users_result = await db.execute(
            select(func.count(User.id.distinct())).join(
                UserSitePermission, UserSitePermission.user_id == User.id
            ).where(
                UserSitePermission.site_id.in_(site_ids)
            )
        )
        users_count = users_result.scalar() or 0
        
        # Count US/USM (Unità Stratigrafiche e Unità Stratigrafiche Murarie)
        from app.models import UnitaStratigrafica, UnitaStratigraficaMuraria
        
        us_result = await db.execute(
            select(func.count(UnitaStratigrafica.id)).where(UnitaStratigrafica.site_id.in_(site_ids))
        )
        us_count = us_result.scalar() or 0
        
        usm_result = await db.execute(
            select(func.count(UnitaStratigraficaMuraria.id)).where(UnitaStratigraficaMuraria.site_id.in_(site_ids))
        )
        usm_count = usm_result.scalar() or 0
        
        us_usm_count = us_count + usm_count
        
        return {
            "sites_count": len(user_sites),
            "photos_count": photos_count,
            "us_usm_count": us_usm_count,
            "users_count": users_count
        }
        
    except Exception as e:
        logger.error(f"Error getting overview stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel caricamento delle statistiche")

@router.get("/system/status")
async def get_system_status(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get real system status for database, storage, and backup
    """
    try:
        import asyncio
        from datetime import datetime, timedelta
        import os
        import psutil
        
        # Database status check
        database_status = "online"
        database_status_text = "Online"
        database_status_class = "text-green-600 dark:text-green-400"
        database_icon = "fa-check-circle"
        
        try:
            # Test database connection
            await db.execute("SELECT 1")
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            database_status = "offline"
            database_status_text = "Offline"
            database_status_class = "text-red-600 dark:text-red-400"
            database_icon = "fa-times-circle"
        
        # Storage status check
        storage_status = "operational"
        storage_status_text = "Operativo"
        storage_status_class = "text-green-600 dark:text-green-400"
        storage_icon = "fa-check-circle"
        
        try:
            # Check disk space
            disk_usage = psutil.disk_usage('/')
            free_space_gb = disk_usage.free / (1024**3)
            total_space_gb = disk_usage.total / (1024**3)
            used_percentage = (disk_usage.used / disk_usage.total) * 100
            
            if free_space_gb < 1:  # Less than 1GB free
                storage_status = "critical"
                storage_status_text = f"Critico: {free_space_gb:.1f}GB liberi"
                storage_status_class = "text-red-600 dark:text-red-400"
                storage_icon = "fa-exclamation-triangle"
            elif used_percentage > 90:  # More than 90% used
                storage_status = "warning"
                storage_status_text = f"Attenzione: {used_percentage:.0f}% usato"
                storage_status_class = "text-yellow-600 dark:text-yellow-400"
                storage_icon = "fa-exclamation-circle"
            elif used_percentage > 75:  # More than 75% used
                storage_status = "moderate"
                storage_status_text = f"{used_percentage:.0f}% usato"
                storage_status_class = "text-yellow-600 dark:text-yellow-400"
                storage_icon = "fa-exclamation-circle"
            else:
                storage_status = "good"
                storage_status_text = f"{free_space_gb:.0f}GB liberi ({used_percentage:.0f}% usato)"
                storage_status_class = "text-green-600 dark:text-green-400"
                storage_icon = "fa-check-circle"
                
        except Exception as e:
            logger.error(f"Storage check failed: {str(e)}")
            storage_status = "error"
            storage_status_text = "Errore lettura"
            storage_status_class = "text-red-600 dark:text-red-400"
            storage_icon = "fa-times-circle"
        
        # Backup status check
        backup_status = "recent"
        backup_status_text = "Recente"
        backup_status_class = "text-green-600 dark:text-green-400"
        backup_icon = "fa-check-circle"
        
        try:
            # Check for recent backup files (mock implementation - adjust based on your backup system)
            backup_dir = "backups"  # Adjust this path to your backup directory
            if os.path.exists(backup_dir):
                backup_files = [f for f in os.listdir(backup_dir) if f.endswith(('.sql', '.backup', '.zip'))]
                if backup_files:
                    # Get the most recent backup file
                    latest_backup = max([os.path.join(backup_dir, f) for f in backup_files],
                                      key=os.path.getmtime)
                    backup_time = datetime.fromtimestamp(os.path.getmtime(latest_backup))
                    time_since_backup = datetime.now() - backup_time
                    
                    if time_since_backup > timedelta(days=1):
                        backup_status = "old"
                        backup_status_text = f"{time_since_backup.days} giorni fa"
                        backup_status_class = "text-yellow-600 dark:text-yellow-400"
                        backup_icon = "fa-clock"
                    elif time_since_backup > timedelta(hours=24):
                        hours_ago = int(time_since_backup.total_seconds() / 3600)
                        backup_status_text = f"{hours_ago} ore fa"
                        backup_status_class = "text-yellow-600 dark:text-yellow-400"
                        backup_icon = "fa-clock"
                    else:
                        backup_status_text = "Oggi"
                else:
                    backup_status = "none"
                    backup_status_text = "Nessun backup"
                    backup_status_class = "text-red-600 dark:text-red-400"
                    backup_icon = "fa-times-circle"
            else:
                backup_status = "unknown"
                backup_status_text = "Non configurato"
                backup_status_class = "text-gray-600 dark:text-gray-400"
                backup_icon = "fa-question-circle"
                
        except Exception as e:
            logger.error(f"Backup check failed: {str(e)}")
            backup_status = "error"
            backup_status_text = "Errore"
            backup_status_class = "text-red-600 dark:text-red-400"
            backup_icon = "fa-times-circle"
        
        return {
            "database": {
                "status": database_status,
                "text": database_status_text,
                "class": database_status_class,
                "icon": database_icon
            },
            "storage": {
                "status": storage_status,
                "text": storage_status_text,
                "class": storage_status_class,
                "icon": storage_icon
            },
            "backup": {
                "status": backup_status,
                "text": backup_status_text,
                "class": backup_status_class,
                "icon": backup_icon
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel caricamento dello stato del sistema")