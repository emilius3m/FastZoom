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
                "description": "Sito 'Foro Romano' è stato aggiunto al sistema",
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
                "description": "Nuovo giornale di cantiere per il giorno 2023-10-23",
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
                "description": "15 nuove fotografie sono state caricate",
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
                "documents_count": 0,
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
        
        return {
            "sites_count": len(user_sites),
            "photos_count": photos_count,
            "documents_count": 0,  # Mock count
            "users_count": users_count
        }
        
    except Exception as e:
        logger.error(f"Error getting overview stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Errore nel caricamento delle statistiche")