# app/routes/sites_router.py - DASHBOARD GESTIONE SITO ARCHEOLOGICO (REFACTORED)
#
# Main router for archaeological site management with optimized endpoints.
# Features:
# - Centralized context management for consistent template data
# - Helper functions to reduce code duplication
# - Comprehensive error handling with localized messages
# - Optimized database queries with parallel execution where beneficial
# - Full ICCD cataloging system integration
#
# Endpoints are organized by functionality:
# - Dashboard: Main site overview with statistics and recent activity
# - Photos: Photographic collection management with pagination
# - Documentation: Site documentation and form schemas
# - Team: Site team management (admin only)
# - Archaeological Plans: Excavation grids and site mapping
# - ICCD: Hierarchical archaeological cataloging system

import asyncio
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from uuid import UUID
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist, SecurityService
from app.models.users import User
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.form_schemas import FormSchema
from app.templates import templates

# Import API sub-routers
from app.routes.api.iccd_hierarchy import iccd_hierarchy_router
from app.routes.api.sites_dashboard import dashboard_router, get_site_statistics, get_recent_activities, get_recent_photos
from app.routes.api.sites_photos import photos_router
from app.routes.api.sites_storage import storage_router
from app.routes.api.sites_deepzoom import deepzoom_router
from app.routes.api.sites_team import team_router, get_site_team

sites_router = APIRouter(prefix="/sites", tags=["sites"])

# Include hierarchical ICCD API endpoints
sites_router.include_router(iccd_hierarchy_router, prefix="/{site_id}")

# Include refactored API sub-routers
sites_router.include_router(dashboard_router, tags=["dashboard"])
sites_router.include_router(photos_router, tags=["photos"])
sites_router.include_router(storage_router, tags=["storage"])
sites_router.include_router(deepzoom_router, tags=["deepzoom"])
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
    handle_resource_not_found,
    get_site_access
)


# === HTML VIEW ENDPOINTS ===
# Main site management endpoints with optimized context handling
# All endpoints use centralized helper functions for consistency and maintainability

@sites_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def site_dashboard(
        # Main dependencies
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Dashboard principale per gestione sito archeologico"""
    site, permission = site_access
    current_user = await get_current_user_with_context(current_user_id, db)

    # Statistiche del sito
    stats = await get_site_statistics(db, site_id)

    # Attività recenti
    recent_activities = await get_recent_activities(db, site_id, limit=10)

    # Foto recenti
    recent_photos = await get_recent_photos(db, site_id, limit=6)

    # Team del sito
    team_members = await get_site_team(db, site_id)

    # Crea context ottimizzato
    user_context = create_user_context(current_user, user_sites)
    base_context = get_base_context(request, site, permission, current_user, user_sites)

    context = {
        **base_context,
        "stats": stats,
        "recent_activities": recent_activities,
        "recent_photos": recent_photos,
        "team_members": team_members
    }

    return templates.TemplateResponse("sites/dashboard.html", context)


@sites_router.get("/{site_id}/photos", response_class=HTMLResponse)
async def site_photos(
        # Query parameters for filtering and pagination
        request: Request,
        site_id: UUID,
        page: int = 1,
        per_page: int = 24,
        category: str = None,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione collezione fotografica del sito"""
    site, permission = site_access

    if not permission.can_read():
        raise handle_permission_denied("visualizzare le foto")

    from app.models.photos import Photo
    current_user = await get_current_user_with_context(current_user_id, db)

    # Query foto con paginazione e categorie
    photos_query = select(Photo).where(Photo.site_id == site_id)
    total_query = select(func.count(Photo.id)).where(Photo.site_id == site_id)

    if category:
        photos_query = photos_query.where(Photo.photo_type == category)
        total_query = total_query.where(Photo.photo_type == category)

    # Esegui query in parallelo per ottimizzazione
    total_photos_result, photos_result, categories_result = await asyncio.gather(
        db.execute(total_query),
        db.execute(photos_query.offset((page - 1) * per_page).limit(per_page)),
        db.execute(
            select(Photo.photo_type, func.count(Photo.id))
            .where(Photo.site_id == site_id)
            .group_by(Photo.photo_type)
        )
    )

    total_photos = total_photos_result.scalar()
    photos = photos_result.scalars().all()
    categories = categories_result.all()

    # Crea context ottimizzato
    base_context = get_base_context(request, site, permission, current_user, user_sites)

    context = {
        **base_context,
        "user_role": permission.permission_level.value,
        "photos": [photo.to_dict() for photo in photos],
        "current_page": page,
        "per_page": per_page,
        "total_photos": total_photos,
        "total_pages": (total_photos + per_page - 1) // per_page,
        "current_photo_type": category,
        "categories": categories
    }

    return templates.TemplateResponse("sites/photos.html", context)


@sites_router.get("/{site_id}/documentation", response_class=HTMLResponse)
async def site_documentation(
        # Dependencies for site access and user context
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione documentazione e rapporti del sito"""
    site, permission = site_access

    if not permission.can_read():
        raise handle_permission_denied("visualizzare la documentazione")

    current_user = await get_current_user_with_context(current_user_id, db)

    # Documenti del sito (placeholder per ora)
    documents = []

    # Form schemas del sito con gestione errori centralizzata
    form_schemas = await _get_form_schemas_safe(db, site_id)

    # Crea context ottimizzato
    base_context = get_base_context(request, site, permission, current_user, user_sites)

    context = {
        **base_context,
        "documents": documents,
        "form_schemas": form_schemas,
        "can_write": permission.can_write()
    }

    return templates.TemplateResponse("sites/documentation.html", context)


async def _get_form_schemas_safe(db: AsyncSession, site_id: UUID) -> List[Dict[str, Any]]:
    """Safely retrieve form schemas with centralized error handling.

    Args:
        db: Database session
        site_id: UUID of the archaeological site

    Returns:
        List of form schema dictionaries with safe error handling
    """
    """Recupera form schemas con gestione errori centralizzata"""
    try:
        import json

        form_schemas_query = select(FormSchema).where(
            and_(FormSchema.site_id == site_id, FormSchema.is_active == True)
        ).order_by(FormSchema.created_at.desc())

        form_schemas = await db.execute(form_schemas_query)
        form_schemas = form_schemas.scalars().all()

        schemas_list = []
        for schema in form_schemas:
            try:
                schema_json = json.loads(schema.schema_json)
                schemas_list.append({
                    "id": str(schema.id),
                    "name": schema.name,
                    "description": schema.description,
                    "category": schema.category,
                    "created_at": schema.created_at.isoformat(),
                    "updated_at": schema.updated_at.isoformat(),
                    "schema": schema_json
                })
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in schema {schema.id}")
                continue

        return schemas_list

    except Exception as e:
        logger.error(f"Error loading form schemas for site {site_id}: {e}")
        return []


@sites_router.get("/{site_id}/team", response_class=HTMLResponse)
async def site_team_management(
        # Dependencies for admin-only site team management
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione team del sito (solo per admin sito)"""
    site, permission = site_access

    if not permission.can_admin():
        raise handle_permission_denied("gestire il team del sito")

    current_user = await get_current_user_with_context(current_user_id, db)

    # Team completo del sito
    team_members = await get_site_team(db, site_id)

    # Crea context ottimizzato
    base_context = get_base_context(request, site, permission, current_user, user_sites)

    context = {
        **base_context,
        "team_members": team_members
    }

    return templates.TemplateResponse("sites/teams.html", context)


@sites_router.get("/{site_id}/archaeological-plans", response_class=HTMLResponse)
async def site_archaeological_plans(
        # Dependencies for archaeological plans management
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione piante archeologiche e griglie di scavo"""
    site, permission = site_access

    if not permission.can_read():
        raise handle_permission_denied("visualizzare le piante archeologiche")

    current_user = await get_current_user_with_context(current_user_id, db)

    # Crea context ottimizzato
    base_context = get_base_context(request, site, permission, current_user, user_sites)

    context = {
        **base_context,
        # Informazioni specifiche per piante archeologiche
        "archaeological_plans": [],  # Placeholder per piante future
        "grid_systems": [],  # Placeholder per sistemi di griglia
    }

    return templates.TemplateResponse("sites/archaeological_plans.html", context)


# === ICCD ROUTES - CATALOGAZIONE ARCHEOLOGICA STANDARDIZZATA ===
# Sistema di catalogazione archeologica secondo standard ICCD
# Archaeological cataloging system with hierarchical structure and legacy support

@sites_router.get("/{site_id}/iccd", response_class=HTMLResponse)
async def site_iccd_records(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Redirect to hierarchical ICCD system."""
    return RedirectResponse(url=f"/sites/{site_id}/iccd/hierarchy", status_code=302)


@sites_router.get("/{site_id}/iccd/hierarchy", response_class=HTMLResponse)
async def site_iccd_hierarchy(
        # Dependencies for hierarchical ICCD cataloging system
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Sistema gerarchico ICCD completo del sito archeologico."""
    site, permission = site_access

    if not permission.can_read():
        raise handle_permission_denied("accedere al sistema ICCD")

    current_user = await get_current_user_with_context(current_user_id, db)

    # Crea context ottimizzato con tutte le informazioni necessarie per ICCD
    base_context = get_base_context(request, site, permission, current_user, user_sites)

    context = {
        **base_context,
        # Informazioni specifiche per il template ICCD hierarchy
        "hierarchy_data": None,  # Placeholder per dati gerarchici futuri
        "schema_types": ["RA", "SI", "MI", "MA"],  # Tipologie schemi ICCD
        "regions": ["12"],  # Regione Lazio per default
    }

    return templates.TemplateResponse("sites/iccd_hierarchy.html", context)


@sites_router.get("/{site_id}/iccd/records", response_class=HTMLResponse)
async def site_iccd_records_list(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Lista schede ICCD del sito archeologico (legacy endpoint)."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
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
        "user_type": "superuser" if current_user and current_user.is_superuser else "user"
    }
    
    return templates.TemplateResponse("sites/iccd_records.html", context)


@sites_router.get("/{site_id}/iccd/new", response_class=HTMLResponse)
async def new_iccd_record(
        request: Request,
        site_id: UUID,
        schema_type: str = "RA",
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Form per creare nuova scheda ICCD."""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()

    # Initialize empty record data for new records
    record_data = {
        "id": None,
        "schema_type": schema_type,
        "nct_region": "12",
        "nct_number": "",
        "nct_suffix": "",
        "nct": "",
        "iccd_data": {
            "CD": {
                "TSK": schema_type,
                "LIR": "C",
                "NCT": {
                    "NCTR": "12",
                    "NCTN": "",
                    "NCTS": ""
                },
                "ESC": "",
                "ECP": ""
            }
        },
        "created_at": None,
        "updated_at": None
    }

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "record": record_data,
        "record_id": None,
        "edit_mode": False,
        "schema_type": schema_type,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }

    return templates.TemplateResponse("iccd/form_universal.html", context)


@sites_router.get("/{site_id}/iccd/{record_id}", response_class=HTMLResponse)
async def view_iccd_record(
        request: Request,
        site_id: UUID,
        record_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Visualizza scheda ICCD specifica."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    # Recupera record ICCD dal database
    try:
        from app.models.iccd_records import ICCDBaseRecord
        
        record_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == record_id,
                ICCDBaseRecord.site_id == site_id
            )
        )
        result = await db.execute(record_query)
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
        
        # Convert to dict for template
        record_data = {
            "id": str(record.id),
            "schema_type": record.schema_type,
            "nct_region": record.nct_region,
            "nct_number": record.nct_number,
            "nct_suffix": record.nct_suffix or "",
            "nct": f"{record.nct_region}{record.nct_number}{record.nct_suffix or ''}",
            "iccd_data": record.iccd_data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading ICCD record {record_id}: {e}")
        raise HTTPException(status_code=500, detail="Errore caricamento scheda ICCD")
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "record": record_data,
        "record_id": str(record_id),
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }
    
    return templates.TemplateResponse("sites/iccd_view.html", context)


@sites_router.get("/{site_id}/iccd/{record_id}/edit", response_class=HTMLResponse)
async def edit_iccd_record(
        request: Request,
        site_id: UUID,
        record_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Form per modificare scheda ICCD esistente."""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    # Recupera record ICCD dal database
    try:
        from app.models.iccd_records import ICCDBaseRecord
        
        record_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == record_id,
                ICCDBaseRecord.site_id == site_id
            )
        )
        result = await db.execute(record_query)
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
        
        # Convert to dict for template
        record_data = {
            "id": str(record.id),
            "schema_type": record.schema_type,
            "nct_region": record.nct_region,
            "nct_number": record.nct_number,
            "nct_suffix": record.nct_suffix or "",
            "nct": f"{record.nct_region}{record.nct_number}{record.nct_suffix or ''}",
            "iccd_data": record.iccd_data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading ICCD record {record_id} for edit: {e}")
        raise HTTPException(status_code=500, detail="Errore caricamento scheda ICCD")
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "record": record_data,
        "record_id": str(record_id),
        "edit_mode": True,
        "schema_type": record_data["schema_type"],
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user"
    }

    return templates.TemplateResponse("iccd/form_universal.html", context)
