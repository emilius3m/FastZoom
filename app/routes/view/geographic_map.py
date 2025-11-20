# app/routes/view/geographic_map.py - Route per mappa geografica
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Dict, Any, List

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.templates import templates

logger = logging.getLogger(__name__)

geographic_map_router = APIRouter(prefix="/view", tags=["geographic-map"])


async def get_current_user_with_context(current_user_id: UUID, db: AsyncSession):
    """Recupera informazioni utente corrente"""
    user_query = select(User).where(User.id == str(current_user_id))  # Convert UUID to string like geographic_map.py
    user = await db.execute(user_query)
    return user.scalar_one_or_none()

@geographic_map_router.get("/{site_id}/geographic-map", response_class=HTMLResponse)
async def geographic_map_view(
    request: Request,
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza mappa geografica con coordinate lat/lng per un sito"""
    
    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()
    current_user = await get_current_user_with_context(current_user_id, db)
    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")
    

    
    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        UserSitePermission.user_id == str(current_user_id),
        UserSitePermission.site_id == str(site_id),
        UserSitePermission.is_active == True
    )
    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )
    
    # Determina permessi
    can_read = permission.can_read()
    can_write = permission.can_write()
    
    return templates.TemplateResponse("sites/geographic_map.html", {
        "request": request,
        "site": site,
        "can_read": can_read,
        "can_write": can_write,
        "user_id": str(current_user_id),
        "user": current_user,
        "current_user": current_user,  # Add current_user for profile modal
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None
    })