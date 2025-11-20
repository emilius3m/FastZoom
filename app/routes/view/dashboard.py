# app/routes/view/dashboard.py - Dashboard view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models import Photo, UserSitePermission, Document
from app.models import UserActivity, User
from app.models.sites import ArchaeologicalSite
from app.templates import templates

# Import helper functions unificati
from app.services.view_helpers import (
    get_current_user_with_profile,
    get_site_statistics,
    get_recent_activities,
    get_recent_photos,
    get_team_members,
    get_base_template_context
)

dashboard_router = APIRouter(prefix="/view", tags=["dashboard"])

# Le funzioni helper sono state spostate in app/services/view_helpers.py


@dashboard_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza dashboard del sito archeologico"""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site_result = await db.execute(site_query)
    site = site_result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Get current user information
    user = await get_current_user_with_profile(current_user_id, db)

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == str(current_user_id),
            UserSitePermission.site_id == str(site_id),
            UserSitePermission.is_active == True
        )
    )
    permission_result = await db.execute(permission_query)
    permission = permission_result.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )

    # Raccogli tutti i dati necessari per il template
    stats = await get_site_statistics(db, site_id)
    recent_photos = await get_recent_photos(db, site_id)
    team_members = await get_team_members(db, site_id)
    recent_activities = await get_recent_activities(db, site_id)

    # Prepara context per il template con user_sites corretti
    context = await get_base_template_context(
        request, current_user_id, user_sites, db, site, permission, "dashboard"
    )
    context.update({
        "stats": stats,
        "recent_photos": recent_photos,
        "team_members": team_members,
        "recent_activities": recent_activities,
        "user": user,
    })

    return templates.TemplateResponse("sites/dashboard.html", context)