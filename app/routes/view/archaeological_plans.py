# app/routes/view/archaeological_plans.py - Archaeological plans view route

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
from app.models import User
from app.templates import templates

archaeological_plans_view_router = APIRouter(prefix="/view/archaeological-plan", tags=["Archaeological Plans View"])

async def get_current_user_with_context(current_user_id: UUID, db: AsyncSession):
    """Recupera informazioni utente corrente"""
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    return user.scalar_one_or_none()


@archaeological_plans_view_router.get("/{site_id}/archaeological-plans", response_class=HTMLResponse)
async def site_archaeological_plans(
        request: Request,
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione piante archeologiche e griglie di scavo"""

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

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    current_user = await get_current_user_with_context(current_user_id, db)

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
        "current_page": "archaeological_plans",
        # Informazioni specifiche per piante archeologiche
        "archaeological_plans": [],  # Placeholder per piante future
        "grid_systems": [],  # Placeholder per sistemi di griglia
    }

    return templates.TemplateResponse("sites/archaeological_plans.html", context)