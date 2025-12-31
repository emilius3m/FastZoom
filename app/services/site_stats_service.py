"""
Site Statistics Service

Handles business logic for site statistics, activities, and photo retrieval.
Moved from route handlers to follow clean architecture principles.
"""

from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from loguru import logger

from app.models import Photo, Document, UserActivity, User, UserSitePermission
from app.models.giornale_cantiere import GiornaleCantiere
from app.models import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.core.domain_exceptions import SiteNotFoundError, ResourceNotFoundError


class SiteStatsService:
    """Service for site statistics and activity tracking"""
    
    @staticmethod
    async def get_site_statistics(
        db: AsyncSession, 
        site_id: UUID
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive statistics for a site.
        
        Args:
            db: Database session
            site_id: Site UUID
            
        Returns:
            Dictionary with site statistics
            
        Raises:
            SiteNotFoundError: If site doesn't exist
        """
        with logger.contextualize(
            operation="get_site_statistics",
            site_id=str(site_id)
        ):
            try:
                site_id_str = str(site_id)
                
                logger.debug(f"Calculating statistics for site {site_id_str}")
                
                # Conta foto
                photos_count = await db.execute(
                    select(func.count(Photo.id)).where(Photo.site_id == site_id_str)
                )
                photos_count = photos_count.scalar() or 0
                
                # Conta giornali di cantiere
                giornali_totali_result = await db.execute(
                    select(func.count(GiornaleCantiere.id)).where(
                        GiornaleCantiere.site_id == site_id_str
                    )
                )
                giornali_totali = giornali_totali_result.scalar() or 0
                
                # Conta giornali validati
                giornali_validati_result = await db.execute(
                    select(func.count(GiornaleCantiere.id)).where(
                        and_(
                            GiornaleCantiere.site_id == site_id_str,
                            GiornaleCantiere.validato.is_(True)
                        )
                    )
                )
                giornali_validati = giornali_validati_result.scalar() or 0
                
                # Conta utenti autorizzati
                users_count = await db.execute(
                    select(func.count(UserSitePermission.id)).where(
                        and_(
                            UserSitePermission.site_id == site_id_str,
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
                            Photo.site_id == site_id_str,
                            Photo.created_at >= last_month
                        )
                    )
                )
                recent_photos = recent_photos.scalar() or 0
                
                # Storage utilizzato (MB)
                storage_query = await db.execute(
                    select(func.sum(Photo.file_size)).where(Photo.site_id == site_id_str)
                )
                storage_mb = (storage_query.scalar() or 0) / (1024 * 1024)
                
                # Conta documenti
                documents_count = await db.execute(
                    select(func.count(Document.id)).where(
                        and_(
                            Document.site_id == site_id_str,
                            Document.is_deleted == False
                        )
                    )
                )
                documents_count = documents_count.scalar() or 0
                
                # Conta US (Unità Stratigrafiche)
                us_count = await db.execute(
                    select(func.count(UnitaStratigrafica.id)).where(
                        UnitaStratigrafica.site_id == site_id_str
                    )
                )
                us_count = us_count.scalar() or 0
                
                # Conta US positive
                us_positive = await db.execute(
                    select(func.count(UnitaStratigrafica.id)).where(
                        and_(
                            UnitaStratigrafica.site_id == site_id_str,
                            UnitaStratigrafica.tipo == 'positiva'
                        )
                    )
                )
                us_positive = us_positive.scalar() or 0
                
                # Conta US negative
                us_negative = await db.execute(
                    select(func.count(UnitaStratigrafica.id)).where(
                        and_(
                            UnitaStratigrafica.site_id == site_id_str,
                            UnitaStratigrafica.tipo == 'negativa'
                        )
                    )
                )
                us_negative = us_negative.scalar() or 0
                
                # Conta USM (Unità Stratigrafiche Murarie)
                usm_count = await db.execute(
                    select(func.count(UnitaStratigraficaMuraria.id)).where(
                        UnitaStratigraficaMuraria.site_id == site_id_str
                    )
                )
                usm_count = usm_count.scalar() or 0
                
                us_usm_count = us_count + usm_count
                
                stats = {
                    "photos_count": photos_count,
                    "documents_count": documents_count,
                    "us_usm_count": us_usm_count,
                    "us_count": us_count,
                    "us_positive": us_positive,
                    "us_negative": us_negative,
                    "usm_count": usm_count,
                    "giornali_totali": giornali_totali,
                    "giornali_validati": giornali_validati,
                    "giornali_pendenti": giornali_totali - giornali_validati,
                    "users_count": users_count,
                    "recent_photos": recent_photos,
                    "storage_mb": round(storage_mb, 2),
                    "last_updated": datetime.now().isoformat()
                }
                
                logger.success(
                    "Site statistics calculated successfully",
                    extra={
                        "site_id": site_id_str,
                        "stats_keys": list(stats.keys()),
                        "photos_count": photos_count,
                        "users_count": users_count
                    }
                )
                
                return stats
                
            except Exception as e:
                logger.error(
                    "Error calculating site statistics",
                    extra={
                        "site_id": str(site_id),
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
    
    @staticmethod
    async def get_recent_activities(
        db: AsyncSession, 
        site_id: UUID, 
        limit: int = 10
    ) -> List[Dict]:
        """
        Get recent activities for a site.
        
        Args:
            db: Database session
            site_id: Site UUID
            limit: Maximum number of activities to return
            
        Returns:
            List of activity dictionaries
        """
        with logger.contextualize(
            operation="get_recent_activities",
            site_id=str(site_id),
            limit=limit
        ):
            try:
                site_id_str = str(site_id)
                
                activities_query = (
                    select(UserActivity, User)
                    .outerjoin(User, UserActivity.user_id == User.id)
                    .where(UserActivity.site_id == site_id_str)
                    .order_by(UserActivity.activity_date.desc())
                    .limit(limit)
                )
                
                activities_result = await db.execute(activities_query)
                activities = activities_result.all()
                
                activity_list = [
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
                
                logger.debug(
                    "Retrieved recent activities",
                    extra={
                        "site_id": site_id_str,
                        "activities_count": len(activity_list),
                        "limit": limit
                    }
                )
                
                return activity_list
                
            except Exception as e:
                logger.error(
                    "Error retrieving recent activities",
                    extra={
                        "site_id": str(site_id),
                        "limit": limit,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
    
    @staticmethod
    async def get_recent_photos(
        db: AsyncSession, 
        site_id: UUID, 
        limit: int = 6
    ) -> List[Dict]:
        """
        Get recent photos for a site.
        
        Args:
            db: Database session
            site_id: Site UUID
            limit: Maximum number of photos to return
            
        Returns:
            List of photo dictionaries
        """
        with logger.contextualize(
            operation="get_recent_photos",
            site_id=str(site_id),
            limit=limit
        ):
            try:
                site_id_str = str(site_id)
                
                photos_query = select(Photo).where(
                    Photo.site_id == site_id_str
                ).order_by(Photo.created_at.desc()).limit(limit)
                
                photos = await db.execute(photos_query)
                photos = photos.scalars().all()
                
                photo_list = [
                    {
                        "id": str(photo.id),
                        "filename": photo.filename,
                        "thumbnail_url": f"/photos/{photo.id}/thumbnail",
                        "full_url": f"/photos/{photo.id}/full",
                        "photo_type": photo.photo_type if photo.photo_type else None,
                        "created_at": photo.created_at.isoformat(),
                        "category": getattr(photo, 'category', None)
                    }
                    for photo in photos
                ]
                
                logger.debug(
                    "Retrieved recent photos",
                    extra={
                        "site_id": site_id_str,
                        "photos_count": len(photo_list),
                        "limit": limit
                    }
                )
                
                return photo_list
                
            except Exception as e:
                logger.error(
                    "Error retrieving recent photos",
                    extra={
                        "site_id": str(site_id),
                        "limit": limit,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
