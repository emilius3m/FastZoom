# app/routes/view/iccd.py - ICCD cataloging view routes

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import List, Dict, Any

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.templates import templates

iccd_router = APIRouter(tags=["iccd"])

@iccd_router.get("/sites/{site_id}/iccd")
async def site_iccd_redirect(site_id: UUID):
    """Redirect to hierarchical ICCD system."""
    return RedirectResponse(url=f"/sites/{site_id}/iccd/hierarchy", status_code=302)


async def get_current_user_with_context(current_user_id: UUID, db: AsyncSession):
    """Recupera informazioni utente corrente"""
    user_query = select(User).where(User.id == str(current_user_id))
    user = await db.execute(user_query)
    return user.scalar_one_or_none()


@iccd_router.get("/sites/{site_id}/iccd/hierarchy", response_class=HTMLResponse)
async def site_iccd_hierarchy(
        request: Request,
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Sistema gerarchico ICCD completo del sito archeologico."""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
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
        "can_delete": permission.can_admin(),  # Only admins can delete
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "current_page": "iccd_hierarchy",
        # Informazioni specifiche per il template ICCD hierarchy
        "hierarchy_data": None,  # Placeholder per dati gerarchici futuri
        "schema_types": ["RA", "SI", "MI", "MA"],  # Tipologie schemi ICCD
        "regions": ["12"],  # Regione Lazio per default
    }

    return templates.TemplateResponse("sites/iccd_hierarchy.html", context)


@iccd_router.get("/sites/{site_id}/iccd/records", response_class=HTMLResponse)
async def site_iccd_records_list(
        request: Request,
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Lista schede ICCD del sito archeologico."""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
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
        "current_page": "iccd_records",
    }

    return templates.TemplateResponse("sites/iccd_records.html", context)


@iccd_router.get("/sites/{site_id}/iccd/new/{schema_type}", response_class=HTMLResponse)
async def new_iccd_record(
        request: Request,
        site_id: UUID,
        schema_type: str,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Form per creare nuova scheda ICCD."""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
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

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    current_user = await get_current_user_with_context(current_user_id, db)

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

    # Prepara context per il template
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
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "current_page": "iccd_new",
    }

    return templates.TemplateResponse("iccd/form_universal.html", context)


@iccd_router.get("/sites/{site_id}/iccd/{record_id}", response_class=HTMLResponse)
async def view_iccd_record(
        request: Request,
        site_id: UUID,
        record_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Visualizza scheda ICCD specifica."""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
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

    current_user = await get_current_user_with_context(current_user_id, db)

    # Recupera record ICCD dal database
    try:
        from app.models.iccd_records import ICCDBaseRecord

        record_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == str(record_id),
                ICCDBaseRecord.site_id == str(site_id)
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
        from loguru import logger
        logger.error(f"Error loading ICCD record {record_id}: {e}")
        raise HTTPException(status_code=500, detail="Errore caricamento scheda ICCD")

    # Prepara context per il template
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "record": record_data,
        "record_id": str(record_id),
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "current_page": "iccd_view",
    }

    return templates.TemplateResponse("sites/iccd_view.html", context)


@iccd_router.get("/sites/{site_id}/iccd/{record_id}/edit", response_class=HTMLResponse)
async def edit_iccd_record(
        request: Request,
        site_id: UUID,
        record_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Form per modificare scheda ICCD esistente."""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
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

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    current_user = await get_current_user_with_context(current_user_id, db)

    # Recupera record ICCD dal database
    try:
        from app.models.iccd_records import ICCDBaseRecord

        record_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == str(record_id),
                ICCDBaseRecord.site_id == str(site_id)
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
        from loguru import logger
        logger.error(f"Error loading ICCD record {record_id} for edit: {e}")
        raise HTTPException(status_code=500, detail="Errore caricamento scheda ICCD")

    # Prepara context per il template
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
        "can_delete": permission.can_admin(),  # Only admins can delete
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "current_page": "iccd_edit",
    }

    return templates.TemplateResponse("iccd/form_universal.html", context)