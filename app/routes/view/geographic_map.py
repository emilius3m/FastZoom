# app/routes/view/geographic_map.py - Route per mappa geografica
from loguru import logger
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Dict, Any, List, Tuple

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.templates import templates

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_read_access


geographic_map_router = APIRouter(prefix="/view", tags=["geographic-map"])


@geographic_map_router.get("/{site_id}/geographic-map", response_class=HTMLResponse)
async def geographic_map_view(
    request: Request,
    site_id: UUID,
    site_access: Tuple = Depends(get_site_read_access),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza mappa geografica con coordinate lat/lng per un sito"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, current_user, is_superuser = site_access
    
    # Determina permessi
    can_read = is_superuser or permission.can_read()
    can_write = is_superuser or permission.can_write()
    
    return templates.TemplateResponse("sites/geographic_map.html", {
        "request": request,
        "site": site,
        "is_superuser": is_superuser,
        "can_read": can_read,
        "can_write": can_write,
        "user_id": str(current_user.id) if current_user else None,
        "user": current_user,
        "current_user": current_user,  # Add current_user for profile modal
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None
    })