# app/routes/api/sites_dashboard.py - Dashboard and statistics API endpoints

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.database.session import get_async_session
from app.models.photos import Photo
from app.models.user_sites import UserSitePermission
from app.models.users import UserActivity, User
from sqlalchemy import select, func, and_

dashboard_router = APIRouter()


@dashboard_router.get("/{site_id}/api/stats")
async def get_site_stats_api(
        site_id: UUID,
        site_access: tuple,
        db: AsyncSession = Depends(get_async_session)
):
    """API per statistiche del sito (per aggiornamenti real-time)"""
    site, permission = site_access
    stats = await get_site_statistics(db, site_id)
    return JSONResponse(stats)


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
                Photo.created >= last_month
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
    ).order_by(Photo.created.desc()).limit(limit)

    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    return [
        {
            "id": str(photo.id),
            "filename": photo.filename,
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "full_url": f"/photos/{photo.id}/full",
            "photo_type": photo.photo_type.value if photo.photo_type else None,
            "created_at": photo.created.isoformat()
        }
        for photo in photos
    ]