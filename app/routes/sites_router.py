# app/routes/sites_router.py - DASHBOARD GESTIONE SITO ARCHEOLOGICO (REFACTORED)

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from uuid import UUID
from typing import List, Dict, Any
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
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
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist, SecurityService

# Include refactored API sub-routers
sites_router.include_router(dashboard_router, tags=["dashboard"])
sites_router.include_router(photos_router, tags=["photos"])
sites_router.include_router(storage_router, tags=["storage"])
sites_router.include_router(deepzoom_router, tags=["deepzoom"])
sites_router.include_router(team_router, tags=["team"])


# === SHARED DEPENDENCY ===

async def get_site_access(
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito e restituisce sito e permessi"""

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
            UserSitePermission.is_active == True,
            or_(
                UserSitePermission.expires_at.is_(None),
                UserSitePermission.expires_at > func.now()
            )
        )
    )

    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )

    return site, permission


# === HTML VIEW ENDPOINTS ===

@sites_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def site_dashboard(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Dashboard principale per gestione sito archeologico"""
    site, permission = site_access

    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()

    # Statistiche del sito
    stats = await get_site_statistics(db, site_id)

    # Attività recenti
    recent_activities = await get_recent_activities(db, site_id, limit=10)

    # Foto recenti
    recent_photos = await get_recent_photos(db, site_id, limit=6)

    # Team del sito
    team_members = await get_site_team(db, site_id)

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "stats": stats,
        "recent_activities": recent_activities,
        "recent_photos": recent_photos,
        "team_members": team_members,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user"

    }



    return templates.TemplateResponse("sites/dashboard.html", context)


@sites_router.get("/{site_id}/photos", response_class=HTMLResponse)
async def site_photos(
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
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    from app.models.photos import Photo
    
    # Query foto con paginazione
    photos_query = select(Photo).where(Photo.site_id == site_id)

    if category:
        photos_query = photos_query.where(Photo.photo_type == category)

    # Conta totale
    total_query = select(func.count(Photo.id)).where(Photo.site_id == site_id)
    if category:
        total_query = total_query.where(Photo.photo_type == category)

    total_photos = await db.execute(total_query)
    total_photos = total_photos.scalar()

    # Foto paginate
    photos_query = photos_query.offset((page - 1) * per_page).limit(per_page)
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    # Categorie disponibili
    categories_query = select(Photo.photo_type, func.count(Photo.id)).where(
        Photo.site_id == site_id
    ).group_by(Photo.photo_type)
    categories = await db.execute(categories_query)
    categories = categories.all()

    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "user_role": permission.permission_level.value,
        "photos": [photo.to_dict() for photo in photos],
        "current_page": page,
        "per_page": per_page,
        "total_photos": total_photos,
        "total_pages": (total_photos + per_page - 1) // per_page,
        "current_photo_type": category,
        "categories": categories,
        "can_write": permission.can_write(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user"
    }

    return templates.TemplateResponse("sites/photos.html", context)


@sites_router.get("/{site_id}/documentation", response_class=HTMLResponse)
async def site_documentation(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione documentazione e rapporti del sito"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Documenti del sito
    documents = []
    
    # Form schemas del sito
    form_schemas_query = select(FormSchema).where(
        and_(FormSchema.site_id == site_id, FormSchema.is_active == True)
    ).order_by(FormSchema.created_at.desc())
    
    form_schemas = await db.execute(form_schemas_query)
    form_schemas = form_schemas.scalars().all()
    
    # Prepara i form schema per il template
    import json
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

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "documents": documents,
        "form_schemas": schemas_list,
        "can_write": permission.can_write()
    }

    return templates.TemplateResponse("sites/documentation.html", context)


@sites_router.get("/{site_id}/team", response_class=HTMLResponse)
async def site_team_management(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione team del sito (solo per admin sito)"""
    site, permission = site_access

    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Solo amministratori del sito")

    # Team completo del sito
    team_members = await get_site_team(db, site_id)

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "team_members": team_members
    }

    return templates.TemplateResponse("sites/teams.html", context)


@sites_router.get("/{site_id}/archaeological-plans", response_class=HTMLResponse)
async def site_archaeological_plans(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione piante archeologiche e griglie di scavo"""
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
        "can_admin": permission.can_admin()
    }
    
    return templates.TemplateResponse("sites/archaeological_plans.html", context)


# === ROUTES ICCD - CATALOGAZIONE ARCHEOLOGICA STANDARDIZZATA ===

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
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Sistema gerarchico ICCD completo del sito archeologico."""
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
        "can_admin": permission.can_admin()
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
