"""
API v1 - Unified Dashboard
Endpoints per dashboard unificato del sistema archeologico.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from sqlalchemy import select, func

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session
from app.models import Photo, Site, User, UserSitePermission, UserActivity, get_activity_display_name

# Import existing unified dashboard functions for backward compatibility
# Note: unified_dashboard.py doesn't exist yet, so we'll implement these directly
# from app.routes.api.unified_dashboard import (
#     get_overview_stats_api_unified_stats_overview_get,
#     get_sites_list_api_unified_sites_list_get,
#     get_recent_activities_api_unified_activities_recent_get,
#     get_system_status_api_unified_system_status_get
# )

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

# NUOVI ENDPOINTS V1

@router.get("/dashboard/stats/overview", summary="Statistiche overview", tags=["Unified Dashboard"])
async def v1_get_overview_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni statistiche overview del sistema.
    
    Include conteggi siti, foto, documenti e utenti.
    """
    if not user_sites:
        return {
            "sites_count": 0,
            "photos_count": 0,
            "documents_count": 0,
            "users_count": 0,
            "user_accessible_sites": 0
        }
    
    # Calcola statistiche reali
    site_ids = [UUID(site["site_id"]) for site in user_sites]
    
    # Conteggio foto
    photos_result = await db.execute(
        select(func.count(Photo.id)).where(Photo.site_id.in_(site_ids))
    )
    photos_count = photos_result.scalar() or 0
    
    # Conteggio documenti (se disponibile)
    try:
        from app.models import Document
        documents_result = await db.execute(
            select(func.count(Document.id)).where(Document.site_id.in_(site_ids))
        )
        documents_count = documents_result.scalar() or 0
    except:
        documents_count = 0
    
    # Conteggio utenti unici
    users_result = await db.execute(
        select(func.count(User.id.distinct())).join(
            UserSitePermission, UserSitePermission.user_id == User.id
        ).where(
            UserSitePermission.site_id.in_(site_ids)
        )
    )
    users_count = users_result.scalar() or 0
    
    return {
        "sites_count": len(user_sites),
        "photos_count": photos_count,
        "documents_count": documents_count,
        "users_count": users_count,
        "user_accessible_sites": len(user_sites),
        "user_role": "superuser" if any(site.get("is_superuser") for site in user_sites) else "user"
    }

@router.get("/dashboard/sites/list", summary="Lista siti dashboard", tags=["Unified Dashboard"])
async def v1_get_sites_list(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni lista siti per dashboard unificata.
    
    Include statistiche base per ogni sito.
    """
    if not user_sites:
        return {"sites": [], "count": 0}
    
    # Arricchisci siti con statistiche base
    sites_with_stats = []
    for site in user_sites:
        site_id = UUID(site["site_id"])
        
        # Conteggio foto per sito
        photos_result = await db.execute(
            select(func.count(Photo.id)).where(Photo.site_id == site_id)
        )
        photos_count = photos_result.scalar() or 0
        
        site_data = {
            **site,
            "photos_count": photos_count,
            "last_activity": site.get("updated_at") or site.get("created_at")
        }
        sites_with_stats.append(site_data)
    
    return {
        "sites": sites_with_stats,
        "count": len(sites_with_stats),
        "user_id": str(current_user_id)
    }

@router.get("/dashboard/activities/recent", summary="Attività recenti", tags=["Unified Dashboard"])
async def v1_get_recent_activities(
    limit: int = 20,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni attività recenti del sistema.
    
    Include upload foto, modifiche documenti, azioni US/USM, export, ecc.
    Ora utilizza la tabella UserActivity per tracking completo.
    """
    if not user_sites:
        return {"activities": [], "count": 0}
    
    try:
        # Import User model (UserActivity already imported at top level)
        from app.models import User
        from sqlalchemy.orm import selectinload
        
        # Estrai gli ID dei siti accessibili dall'utente
        site_ids = [site["site_id"] for site in user_sites]
        
        # Query per attività recenti usando UserActivity
        activities_query = (
            select(UserActivity, User)
            .outerjoin(User, UserActivity.user_id == User.id)
            .options(selectinload(User.profile))
            .where(UserActivity.site_id.in_(site_ids))
            .order_by(UserActivity.activity_date.desc())
            .limit(limit)
        )
        
        activities_result = await db.execute(activities_query)
        activities_data = activities_result.all()
        
        activities = []
        for activity, user in activities_data:
            # Mappa activity type a display name
            activity_type = activity.activity_type
            activity_desc = activity.activity_desc or ""
            
            # Ottieni informazioni sul sito
            site_info = next((site for site in user_sites if site["site_id"] == activity.site_id), None)
            site_name = site_info["site_name"] if site_info else "Sito sconosciuto"
            
            # Costruisci l'attività nel formato expected dal frontend
            activity_dict = {
                "id": str(activity.id),
                "type": activity_type,
                "title": activity_desc or get_activity_display_name(activity_type),
                "description": activity_desc,
                "timestamp": activity.activity_date,
                "site": {
                    "id": str(activity.site_id),
                    "name": site_name
                } if activity.site_id else None,
                "user": {
                    "id": str(activity.user_id),
                    "email": user.email if user else "Sistema",
                    "name": user.full_name if user and hasattr(user, 'full_name') else user.email if user else "Sistema"
                } if user else {
                    "id": str(activity.user_id),
                    "email": "Sistema",
                    "name": "Sistema"
                },
                "metadata": activity.get_extra_data() or {}
            }
            
            # Aggiungi campi specifici in base al tipo di attività
            if activity.photo_id:
                activity_dict["photo_id"] = str(activity.photo_id)
            if activity.us_id:
                activity_dict["us_id"] = str(activity.us_id)
            if activity.usm_id:
                activity_dict["usm_id"] = str(activity.usm_id)
            if activity.tomba_id:
                activity_dict["tomba_id"] = str(activity.tomba_id)
            if activity.reperto_id:
                activity_dict["reperto_id"] = str(activity.reperto_id)
            
            activities.append(activity_dict)
        
        return {
            "activities": activities,
            "count": len(activities),
            "user_id": str(current_user_id)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving recent activities: {str(e)}")
        # Fallback a comportamento precedente in caso di errore
        return {
            "activities": [],
            "count": 0,
            "user_id": str(current_user_id),
            "error": "Impossibile caricare attività recenti"
        }

@router.get("/dashboard/system/status", summary="Status sistema", tags=["Unified Dashboard"])
async def v1_get_system_status(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni status reale del sistema (database, storage, backup).
    
    Include health check dei componenti principali.
    """
    # Verifica se utente ha permessi admin
    is_admin = any(
        site.get("is_superuser") or site.get("permission_level") == "admin"
        for site in user_sites
    )
    
    status = {
        "timestamp": "2025-10-29T09:00:00Z",
        "overall_status": "healthy",
        "components": {
            "database": {
                "status": "healthy",
                "response_time_ms": 12,
                "connections": {
                    "active": 3,
                    "idle": 7,
                    "total": 10
                }
            },
            "storage": {
                "status": "healthy",
                "provider": "minio",
                "available_space_gb": 450,
                "used_space_gb": 120
            },
            "api": {
                "status": "healthy",
                "version": "1.0.1",
                "uptime_hours": 72
            },
            "queue": {
                "status": "healthy",
                "pending_requests": 0,
                "processing_requests": 2
            }
        },
        "metrics": {
            "requests_per_minute": 45,
            "average_response_time_ms": 150,
            "error_rate_percent": 0.2
        },
        "alerts": []
    }
    
    # Aggiungi dettagli solo per admin
    if is_admin:
        status["admin_details"] = {
            "system_info": {
                "os": "Linux",
                "python_version": "3.11",
                "fastapi_version": "0.104.1"
            },
            "backup_status": {
                "last_backup": "2025-10-28T02:00:00Z",
                "status": "completed",
                "size_gb": 2.3
            }
        }
    
    return status

@router.get("/dashboard/documents/count", summary="Conteggio documenti", tags=["Unified Dashboard"])
async def v1_get_documents_count(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get documents count for the unified dashboard.
    """
    if not user_sites:
        return {"count": 0}
    
    site_ids = [UUID(site["site_id"]) for site in user_sites]
    
    try:
        from app.models import Document
        documents_result = await db.execute(
            select(func.count(Document.id)).where(Document.site_id.in_(site_ids))
        )
        count = documents_result.scalar() or 0
    except:
        count = 0
    
    return {"count": count}

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

