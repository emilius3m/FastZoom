# app/routes/view/dashboard.py - Dashboard view route

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import Photo, UserSitePermission
from app.models import UserActivity, User
from app.models.sites import ArchaeologicalSite
from app.templates import templates

dashboard_router = APIRouter(prefix="/view", tags=["dashboard"])

async def get_site_statistics(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """Calcola statistiche del sito"""

    # Conta foto
    photos_count = await db.execute(
        select(func.count(Photo.id)).where(Photo.site_id == site_id)
    )
    photos_count = photos_count.scalar() or 0

    # Conta utenti autorizzati
    users_count = await db.execute(
        select(func.count(UserSitePermission.id)).where(
            and_(
                UserSitePermission.site_id == site_id,
                UserSitePermission.is_active == True
            )
        )
    )
    users_count = users_count.scalar() or 0

    # Foto caricate nell'ultimo mese
    last_month = datetime.now() - timedelta(days=30)
    recent_photos = await db.execute(
        select(func.count(Photo.id)).where(
            and_(
                Photo.site_id == site_id,
                Photo.created_at >= last_month
            )
        )
    )
    recent_photos = recent_photos.scalar() or 0

    # Storage utilizzato (MB)
    storage_query = await db.execute(
        select(func.sum(Photo.file_size)).where(Photo.site_id == site_id)
    )
    storage_mb = (storage_query.scalar() or 0) / (1024 * 1024)

    return {
        "photos_count": photos_count,
        "users_count": users_count,
        "recent_photos": recent_photos,
        "storage_mb": round(storage_mb, 2),
        "last_updated": datetime.now().isoformat()
    }


async def get_recent_activities(db: AsyncSession, site_id: UUID, limit: int = 10) -> List[Dict]:
    """Recupera attività recenti del sito"""
    activities_query = (
        select(UserActivity, User)
        .outerjoin(User, UserActivity.user_id == User.id)
        .options(selectinload(User.profile))
        .where(UserActivity.site_id == site_id)
        .order_by(UserActivity.activity_date.desc())
        .limit(limit)
    )

    activities_result = await db.execute(activities_query)
    activities = activities_result.all()

    return [
        {
            "id": str(activity.id),
            "type": activity.activity_type,
            "description": activity.activity_desc,
            "user": user.email if user else "Sistema",
            "date": activity.activity_date.isoformat(),
            "metadata": activity.get_extra_data() if hasattr(activity, 'get_extra_data') else {}
        }
        for activity, user in activities
    ]


async def get_recent_photos(db: AsyncSession, site_id: UUID, limit: int = 6) -> List[Dict]:
    """Recupera foto recenti del sito"""
    photos_query = select(Photo).where(
        Photo.site_id == site_id
    ).order_by(Photo.created_at.desc()).limit(limit)

    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    return [
        {
            "id": str(photo.id),
            "filename": photo.filename,
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "full_url": f"/photos/{photo.id}/full",
            "photo_type": photo.photo_type.value if photo.photo_type else None,
            "created_at": photo.created_at.isoformat(),
            "category": getattr(photo, 'category', None)  # Aggiunto per compatibilità template
        }
        for photo in photos
    ]


async def get_team_members(db: AsyncSession, site_id: UUID, limit: int = 10) -> List[Dict]:
    """Recupera membri del team del sito"""
    team_query = (
        select(User, UserSitePermission)
        .join(UserSitePermission, User.id == UserSitePermission.user_id)
        .options(selectinload(User.profile))
        .where(
            and_(
                UserSitePermission.site_id == site_id,
                UserSitePermission.is_active == True
            )
        )
        .order_by(UserSitePermission.permission_level.desc())
        .limit(limit)
    )

    team = await db.execute(team_query)
    team = team.all()

    return [
        {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "permission_level": permission.permission_level,
            "permission_display": permission.permission_level.replace('_', ' ').title(),
            "granted_at": permission.created_at.isoformat()
        }
        for user, permission in team
    ]


@dashboard_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Visualizza dashboard del sito archeologico"""

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

    # Determina permessi
    can_read = permission.can_read()
    can_write = permission.can_write()
    can_admin = permission.can_admin()

    # Raccogli tutti i dati necessari per il template
    stats = await get_site_statistics(db, site_id)
    recent_photos = await get_recent_photos(db, site_id)
    team_members = await get_team_members(db, site_id)
    recent_activities = await get_recent_activities(db, site_id)

    # Prepara context per il template
    context = {
        "request": request,
        "site": site,
        "stats": stats,
        "recent_photos": recent_photos,
        "team_members": team_members,
        "recent_activities": recent_activities,
        "can_read": can_read,
        "can_write": can_write,
        "can_admin": can_admin,
        "user_permission": permission,
        "current_page": "dashboard"
    }

    return templates.TemplateResponse("sites/dashboard.html", context)