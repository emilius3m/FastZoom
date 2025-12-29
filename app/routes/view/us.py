# app/routes/view/us.py - US/USM view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any

from app.database.session import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.templates import templates

# Import helper functions unificati
from app.services.view_helpers import (
    get_current_user_with_profile,
    get_base_template_context
)

us_view_router = APIRouter(prefix="/view", tags=["us-usm"])




@us_view_router.get("/{site_id}/us", response_class=HTMLResponse)
async def us_usm_view(
    request: Request,
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza pagina di gestione US/USM"""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Get user first to check superuser status
    user = await get_current_user_with_profile(current_user_id, db)
    is_superuser = user and user.is_superuser

    # Verifica permessi utente - superuser bypassa il controllo
    permission = None
    if not is_superuser:
        permission_query = select(UserSitePermission).where(
            and_(
                UserSitePermission.user_id == str(current_user_id),
                UserSitePermission.site_id == str(site_id),
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

    # Prepara context per il template usando la funzione helper unificata
    context = await get_base_template_context(
        request, current_user_id, user_sites, db, site, permission, "us"
    )
    context.update({
        "site_id": str(site_id),
        "user_role": permission.permission_level if permission else ("admin" if is_superuser else "none")
    })

    return templates.TemplateResponse("pages/us/index.html", context)
