# app/routes/view/us.py - US/USM view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any, Tuple

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

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_read_access

us_view_router = APIRouter(prefix="/view", tags=["us-usm"])




@us_view_router.get("/{site_id}/us", response_class=HTMLResponse)
async def us_usm_view(
    request: Request,
    site_id: UUID,
    site_access: Tuple = Depends(get_site_read_access),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza pagina di gestione US/USM"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, current_user, is_superuser = site_access

    # Prepara context per il template usando la funzione helper unificata
    context = await get_base_template_context(
        request, current_user.id, user_sites, db, site, permission, "us"
    )
    context.update({
        "site_id": str(site_id),
        "user_role": permission.permission_level if hasattr(permission, 'permission_level') else ("admin" if is_superuser else "none"),
        "is_superuser": is_superuser
    })

    return templates.TemplateResponse("pages/us/index.html", context)
