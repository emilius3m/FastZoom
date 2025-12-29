# app/routes/view/archaeological_plans.py - Archaeological plans view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any, Tuple

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models import User
from app.templates import templates

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_read_access

archaeological_plans_view_router = APIRouter(prefix="/view/archaeological-plan", tags=["Archaeological Plans View"])


@archaeological_plans_view_router.get("/{site_id}/archaeological-plans", response_class=HTMLResponse)
async def site_archaeological_plans(
        request: Request,
        site_id: UUID,
        site_access: Tuple = Depends(get_site_read_access),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione piante archeologiche e griglie di scavo"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, current_user, is_superuser = site_access
    
    # Compute permissions
    can_read = is_superuser or permission.can_read()
    can_write = is_superuser or permission.can_write()
    can_admin = is_superuser or permission.can_admin()

    # Prepara context per il template
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "is_superuser": is_superuser,
        "can_read": can_read,
        "can_write": can_write,
        "can_admin": can_admin,
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if is_superuser else "user",
        "current_page": "archaeological_plans",
        # Informazioni specifiche per piante archeologiche
        "archaeological_plans": [],  # Placeholder per piante future
        "grid_systems": [],  # Placeholder per sistemi di griglia
    }

    return templates.TemplateResponse("sites/archaeological_plans.html", context)