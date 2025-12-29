# app/routes/view/team.py - Team management view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any, Tuple

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.templates import templates

# Import team API functions
from app.routes.api.sites_team import get_site_team

# Import helper functions unificati
from app.services.view_helpers import (
    get_current_user_with_profile,
    get_base_template_context
)

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_admin_access

team_router = APIRouter(prefix="/view", tags=["team"])

# Le funzioni helper sono state spostate in app/services/view_helpers.py


@team_router.get("/{site_id}/team", response_class=HTMLResponse)
async def site_team_management(
        # Dependencies for admin-only site team management
        request: Request,
        site_id: UUID,
        site_access: Tuple = Depends(get_site_admin_access),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione team del sito (solo per admin sito)"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, current_user, is_superuser = site_access

    # Team completo del sito
    team_members = await get_site_team(db, site_id)

    # Prepara context per il template
    context = await get_base_template_context(
        request, current_user.id, user_sites, db, site, permission, "team"
    )
    context.update({
        "team_members": team_members,
        "is_superuser": is_superuser
    })

    return templates.TemplateResponse("sites/teams.html", context)