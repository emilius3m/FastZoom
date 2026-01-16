# app/routes/sites_router.py - DASHBOARD GESTIONE SITO ARCHEOLOGICO (REFACTORED)
#


import asyncio
from fastapi import APIRouter, Depends, Request, HTTPException


from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist, SecurityService
from app.models import User
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models.form_schemas import FormSchema
from app.templates import templates
from app.routes.api.dependencies import get_site_access

# Import API sub-routers
from app.routes.api.iccd_hierarchy import iccd_hierarchy_router
from app.routes.api.v1.photos import router as photos_router
from app.routes.api.sites_storage import storage_router
from app.routes.api.sites_team import team_router, get_site_team

sites_router = APIRouter(prefix="/api", tags=["sites"])

# Include hierarchical ICCD API endpoints
sites_router.include_router(iccd_hierarchy_router, prefix="/{site_id}")
sites_router.include_router(photos_router, tags=["photos"])  # API v1 photos router
sites_router.include_router(storage_router, tags=["storage"])
sites_router.include_router(team_router, tags=["team"])

# === UTILITIES ===
# Helper functions to reduce code duplication and improve maintainability
# These functions centralize common operations used across multiple endpoints

# Import shared utilities for consolidated router patterns
from app.routes.shared.router_utils import (
    get_base_context,
    get_current_user_with_context,
    create_user_context,
    handle_permission_denied,
    handle_resource_not_found
)
