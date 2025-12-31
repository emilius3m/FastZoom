# app/routes/api/v1/sites.py - Sites API v1 endpoints

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger

from app.core.dependencies import get_database_session, get_site_stats_service
from app.core.security import get_current_user_id_with_blacklist
from app.services.site_stats_service import SiteStatsService
from app.routes.api.dependencies import get_site_access
from app.core.domain_exceptions import SiteNotFoundError, InsufficientPermissionsError

router = APIRouter()


@router.get("/sites/{site_id}/dashboard/stats", summary="Statistiche dashboard sito", tags=["Sites"])
async def v1_get_site_dashboard_stats(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_database_session),
        site_stats_service: SiteStatsService = Depends(get_site_stats_service)
):
    """
    API v1 per statistiche del sito (per aggiornamenti real-time).
    
    Args:
        site_id: Site UUID
        site_access: Site access validation
        db: Database session
        site_stats_service: Site statistics service
        
    Returns:
        Site statistics as JSON
        
    Raises:
        InsufficientPermissionsError: If user lacks read permissions
        SiteNotFoundError: If site doesn't exist
    """
    site, permission = site_access
    
    if not permission.can_read():
        raise InsufficientPermissionsError("Permessi di lettura richiesti")
    
    # Use service layer for business logic
    stats = await site_stats_service.get_site_statistics(db, site_id)
    return JSONResponse(stats)


# Helper functions have been moved to SiteStatsService for better separation of concerns
# Use site_stats_service.get_site_statistics(), get_recent_activities(), get_recent_photos()