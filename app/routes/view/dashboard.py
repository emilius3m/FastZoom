# app/routes/view/dashboard.py - Dashboard view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List, Tuple

from app.core.dependencies import get_database_session, get_dashboard_service
from app.core.security import get_current_user_sites_with_blacklist
from app.services.dashboard_service import DashboardService
from app.templates import templates

# Import helper functions for context preparation
from app.services.view_helpers import get_base_template_context

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_read_access

dashboard_router = APIRouter(prefix="/view", tags=["dashboard"])


@dashboard_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    site_id: UUID,
    site_access: Tuple = Depends(get_site_read_access),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session),
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """Visualizza dashboard del sito archeologico"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, user, is_superuser = site_access

    # Get all dashboard data using the service
    dashboard_data = await dashboard_service.get_dashboard_data(db, site_id)

    # Prepare context for template using helper
    context = await get_base_template_context(
        request, user.id, user_sites, db, site, permission, "dashboard"
    )
    
    # Add dashboard data to context
    context.update({
        "stats": dashboard_data["stats"],
        "recent_photos": dashboard_data["recent_photos"],
        "team_members": dashboard_data["team_members"],
        "recent_activities": dashboard_data["recent_activities"],
        "is_superuser": is_superuser
    })

    return templates.TemplateResponse("sites/dashboard.html", context)
