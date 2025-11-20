# app/routes/view/photos.py - Photos view route

import asyncio
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from uuid import UUID
from typing import List, Dict, Any

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites_with_blacklist
from app.models import Photo
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.templates import templates

logger = logging.getLogger(__name__)

photos_view_router = APIRouter(prefix="/view", tags=["photos"])

async def get_current_user_with_context(current_user_id: UUID, db: AsyncSession):
    """Recupera informazioni utente corrente"""
    user_query = select(User).where(User.id == str(current_user_id))  # Convert UUID to string like geographic_map.py
    user = await db.execute(user_query)
    return user.scalar_one_or_none()


@photos_view_router.get("/{site_id}/photos", response_class=HTMLResponse)
async def site_photos(
        # Query parameters for filtering and pagination
        request: Request,
        site_id: UUID,
        page: int = 1,
        per_page: int = 24,
        category: str = None,
        current_user_id: UUID = Depends(get_current_user_id),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione collezione fotografica del sito"""

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
    


    # Query foto con paginazione e categorie
    photos_query = select(Photo).where(Photo.site_id == str(site_id))
    total_query = select(func.count(Photo.id)).where(Photo.site_id == str(site_id))

    if category:
        photos_query = photos_query.where(Photo.photo_type == category)
        total_query = total_query.where(Photo.photo_type == category)

    # Esegui query in parallelo per ottimizzazione
    total_photos_result, photos_result, categories_result = await asyncio.gather(
        db.execute(total_query),
        db.execute(photos_query.offset((page - 1) * per_page).limit(per_page)),
        db.execute(
            select(Photo.photo_type, func.count(Photo.id))
            .where(Photo.site_id == str(site_id))
            .group_by(Photo.photo_type)
        )
    )

    total_photos = total_photos_result.scalar()
    photos = photos_result.scalars().all()
    categories = categories_result.all()

    # Prepara context per il template
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "user": current_user,  # Add user for profile modal compatibility
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin(),
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "user_role": permission.permission_level if permission else "none",
        "current_page": "photos",
        "photos": [photo.to_dict() for photo in photos],
        "current_page_num": page,
        "per_page": per_page,
        "total_photos": total_photos,
        "total_pages": (total_photos + per_page - 1) // per_page,
        "current_photo_type": category,
        "categories": categories
    }

    return templates.TemplateResponse("sites/photos.html", context)