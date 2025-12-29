# app/routes/view/dashboard.py - Dashboard view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Dict, Any, List, Tuple
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

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_read_access

dashboard_router = APIRouter(prefix="/view", tags=["dashboard"])

# Le funzioni helper sono state spostate in app/services/view_helpers.py


@dashboard_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    site_id: UUID,
    site_access: Tuple = Depends(get_site_read_access),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza dashboard del sito archeologico"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, user, is_superuser = site_access

    # Raccogli tutti i dati necessari per il template
    stats = await get_site_statistics(db, site_id)
    recent_photos = await get_recent_photos(db, site_id)
    team_members = await get_team_members(db, site_id)
    recent_activities = await get_recent_activities(db, site_id)

    # Prepara context per il template usando la funzione helper
    context = await get_base_template_context(
        request, user.id, user_sites, db, site, permission, "dashboard"
    )
    context.update({
        "stats": stats,
        "recent_photos": recent_photos,
        "team_members": team_members,
        "recent_activities": recent_activities,
        "is_superuser": is_superuser
    })

    return templates.TemplateResponse("sites/dashboard.html", context)