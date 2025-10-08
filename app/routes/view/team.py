# app/routes/view/team.py - Team management view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.users import User
from app.templates import templates

# Import team API functions
from app.routes.api.sites_team import get_site_team

team_router = APIRouter(prefix="/view", tags=["team"])

async def get_current_user_with_context(current_user_id: UUID, db: AsyncSession):
    """Recupera informazioni utente corrente"""
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    return user.scalar_one_or_none()


@team_router.get("/{site_id}/team", response_class=HTMLResponse)
async def site_team_management(
        # Dependencies for admin-only site team management
        request: Request,
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione team del sito (solo per admin sito)"""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == current_user_id,
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        )
    )
    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )

    if not permission.can_admin():
        raise HTTPException(
            status_code=403,
            detail="Solo gli amministratori possono gestire il team del sito"
        )

    current_user = await get_current_user_with_context(current_user_id, db)

    # Team completo del sito
    team_members = await get_site_team(db, site_id)

    # Prepara context per il template
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "current_page": "team",
        "team_members": team_members
    }

    return templates.TemplateResponse("sites/teams.html", context)