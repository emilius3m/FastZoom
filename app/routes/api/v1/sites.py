# app/routes/api/v1/sites.py - Sites API v1 endpoints

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import Photo, Document
from app.models import UserSitePermission
from app.models import UserActivity, User
from app.routes.api.dependencies import get_site_access
from sqlalchemy import select, func, and_

router = APIRouter()


@router.get("/sites/{site_id}/dashboard/stats", summary="Statistiche dashboard sito", tags=["Sites"])
async def v1_get_site_dashboard_stats(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """API v1 per statistiche del sito (per aggiornamenti real-time)"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    stats = await _get_site_statistics(db, site_id)
    return JSONResponse(stats)


async def _get_site_statistics(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """Calcola statistiche del sito"""

    # Conta foto
    photos_count = await db.execute(
        select(func.count(Photo.id)).where(Photo.site_id == str(site_id))
    )
    photos_count = photos_count.scalar() or 0

    # 🔥 NUOVO: Conta giornali di cantiere
    from app.models.giornale_cantiere import GiornaleCantiere
    
    giornali_totali_result = await db.execute(
        select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == str(site_id))
    )
    giornali_totali = giornali_totali_result.scalar() or 0

    # Conta giornali validati
    giornali_validati_result = await db.execute(
        select(func.count(GiornaleCantiere.id)).where(
            and_(
                GiornaleCantiere.site_id == str(site_id),
                GiornaleCantiere.validato.is_(True)
            )
        )
    )
    giornali_validati = giornali_validati_result.scalar() or 0

    # Conta utenti autorizzati
    users_count = await db.execute(
        select(func.count(UserSitePermission.id)).where(
            and_(
                UserSitePermission.site_id == str(site_id),
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
                Photo.site_id == str(site_id),
                Photo.created_at >= last_month
            )
        )
    )
    recent_photos = recent_photos.scalar() or 0

    # Storage utilizzato (MB)
    storage_query = await db.execute(
        select(func.sum(Photo.file_size)).where(Photo.site_id == str(site_id))
    )
    storage_mb = (storage_query.scalar() or 0) / (1024 * 1024)

    # Conta documenti
    documents_count = await db.execute(
        select(func.count(Document.id)).where(
            and_(
                Document.site_id == str(site_id),
                Document.is_deleted == False
            )
        )
    )
    documents_count = documents_count.scalar() or 0

    # Conta US/USM (Unità Stratigrafiche e Unità Stratigrafiche Murarie)
    from app.models import UnitaStratigrafica, UnitaStratigraficaMuraria
    
    us_count = await db.execute(
        select(func.count(UnitaStratigrafica.id)).where(UnitaStratigrafica.site_id == str(site_id))
    )
    us_count = us_count.scalar() or 0
    
    usm_count = await db.execute(
        select(func.count(UnitaStratigraficaMuraria.id)).where(UnitaStratigraficaMuraria.site_id == str(site_id))
    )
    usm_count = usm_count.scalar() or 0
    
    us_usm_count = us_count + usm_count

    return {
        "photos_count": photos_count,
        "documents_count": documents_count,
        "us_usm_count": us_usm_count,
        "us_count": us_count,
        "usm_count": usm_count,
        "giornali_totali": giornali_totali,  # 🔥 NUOVO
        "giornali_validati": giornali_validati,  # 🔥 NUOVO
        "giornali_pendenti": giornali_totali - giornali_validati,  # 🔥 NUOVO
        "users_count": users_count,
        "recent_photos": recent_photos,
        "storage_mb": round(storage_mb, 2),
        "last_updated": datetime.now().isoformat()
    }


async def _get_recent_activities(db: AsyncSession, site_id: UUID, limit: int = 10) -> List[Dict]:
    """Recupera attività recenti del sito"""
    activities_query = (
        select(UserActivity, User)
        .outerjoin(User, UserActivity.user_id == User.id)
        .where(UserActivity.site_id == str(site_id))
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


async def _get_recent_photos(db: AsyncSession, site_id: UUID, limit: int = 6) -> List[Dict]:
    """Recupera foto recenti del sito"""
    photos_query = select(Photo).where(
        Photo.site_id == str(site_id)
    ).order_by(Photo.created_at.desc()).limit(limit)

    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    return [
        {
            "id": str(photo.id),
            "filename": photo.filename,
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "full_url": f"/photos/{photo.id}/full",
            "photo_type": photo.photo_type if photo.photo_type else None,
            "created_at": photo.created_at.isoformat(),
            "category": getattr(photo, 'category', None)  # Aggiunto per compatibilità template
        }
        for photo in photos
    ]