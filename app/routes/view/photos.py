# app/routes/view/photos.py
# Foto archeologiche view route

import asyncio
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from uuid import UUID
from typing import List, Dict, Any, Tuple, Optional

from app.database.session import get_async_session
from app.core.security import get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.models.documentation_and_field import Photo
from app.templates import templates

# Import centralized permission dependency
from app.routes.view.view_dependencies import get_site_read_access


photos_view_router = APIRouter(prefix="/view", tags=["photos"])


@photos_view_router.get("/{site_id}/photos", response_class=HTMLResponse)
async def site_photos(
        request: Request,
        site_id: UUID,
        page: int = 1,
        per_page: int = 20,
        category: Optional[str] = None,
        mode: Optional[str] = None,
        giornale_id: Optional[UUID] = None,
        site_access: Tuple[ArchaeologicalSite, Optional[UserSitePermission], User, bool] = Depends(get_site_read_access),
        user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione collezione fotografica del sito"""
    
    # Unpack site access tuple (site, permission, user, is_superuser)
    site, permission, current_user, is_superuser = site_access
    
    # Compute permissions
    can_read = is_superuser or (permission.can_read() if permission else False)
    can_write = is_superuser or (permission.can_write() if permission else False)
    can_admin = is_superuser or (permission.can_admin() if permission else False)

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

    # Prepara context per il template - gestisce superuser con permission None
    can_read = is_superuser or (permission.can_read() if permission else False)
    can_write = is_superuser or (permission.can_write() if permission else False)
    can_admin = is_superuser or (permission.can_admin() if permission else False)
    
    is_giornale_linker = mode == "giornale_linker" and giornale_id is not None

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "user": current_user,  # Add user for profile modal compatibility
        "is_superuser": is_superuser,
        "can_read": can_read,
        "can_write": can_write,
        "can_admin": can_admin,
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if is_superuser else "user",
        "user_role": permission.permission_level if permission else ("admin" if is_superuser else "none"),
        "current_page": "photos",
        "photos": [photo.to_dict() for photo in photos],
        "current_page_num": page,
        "per_page": per_page,
        "total_photos": total_photos,
        "total_pages": (total_photos + per_page - 1) // per_page,
        "current_photo_type": category,
        "categories": categories,
        "photos_mode": mode,
        "giornale_id": str(giornale_id) if giornale_id else None,
        "is_giornale_linker": is_giornale_linker,
    }

    return templates.TemplateResponse("sites/photos.html", context)
