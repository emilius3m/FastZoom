"""
app/services/dashboard_service.py
Centralized service for dashboard data aggregation and business logic.
Consolidates logic previously in view_helpers.py.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from loguru import logger

from app.models import (
    Photo,
    UserSitePermission,
    Document,
    UserActivity,
    User,
)
from app.models.giornale_cantiere import GiornaleCantiere
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria


class DashboardService:
    """
    Service for dashboard data aggregation.
    Provides consolidated methods for retrieving dashboard statistics and data.
    """

    @staticmethod
    async def get_statistics(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
        """
        Calculate comprehensive site statistics.
        
        Args:
            db: Database session
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary containing:
                - photos_count: Total photos
                - documents_count: Total documents
                - us_usm_count: Total stratigraphic units
                - giornali_totali: Total site journals
                - giornali_validati: Validated journals
                - users_count: Authorized users
                - storage_mb: Storage used in MB
                - recent_photos: Photos uploaded in last 30 days
        """
        try:
            site_id_str = str(site_id)
            
            # Count photos
            photos_count = await db.scalar(
                select(func.count(Photo.id)).where(Photo.site_id == site_id_str)
            ) or 0

            # Count site journals
            giornali_totali = await db.scalar(
                select(func.count(GiornaleCantiere.id))
                .where(GiornaleCantiere.site_id == site_id_str)
            ) or 0

            # Count validated journals
            giornali_validati = await db.scalar(
                select(func.count(GiornaleCantiere.id)).where(
                    and_(
                        GiornaleCantiere.site_id == site_id_str,
                        GiornaleCantiere.validato.is_(True)
                    )
                )
            ) or 0

            # Count authorized users
            users_count = await db.scalar(
                select(func.count(UserSitePermission.id)).where(
                    and_(
                        UserSitePermission.site_id == site_id_str,
                        UserSitePermission.is_active == True
                    )
                )
            ) or 0

            # Recent photos (last 30 days)
            last_month = datetime.now() - timedelta(days=30)
            recent_photos = await db.scalar(
                select(func.count(Photo.id)).where(
                    and_(
                        Photo.site_id == site_id_str,
                        Photo.created_at >= last_month
                    )
                )
            ) or 0

            # Storage used in MB
            storage_bytes = await db.scalar(
                select(func.sum(Photo.file_size)).where(Photo.site_id == site_id_str)
            ) or 0
            storage_mb = storage_bytes / (1024 * 1024)

            # Count documents
            documents_count = await db.scalar(
                select(func.count(Document.id)).where(
                    and_(
                        Document.site_id == site_id_str,
                        Document.is_deleted == False
                    )
                )
            ) or 0

            # Count stratigraphic units (US + USM)
            us_count = await db.scalar(
                select(func.count(UnitaStratigrafica.id))
                .where(UnitaStratigrafica.site_id == site_id_str)
            ) or 0
            
            usm_count = await db.scalar(
                select(func.count(UnitaStratigraficaMuraria.id))
                .where(UnitaStratigraficaMuraria.site_id == site_id_str)
            ) or 0
            
            us_usm_count = us_count + usm_count

            return {
                "photos_count": photos_count,
                "documents_count": documents_count,
                "us_usm_count": us_usm_count,
                "us_count": us_count,
                "usm_count": usm_count,
                "giornali_totali": giornali_totali,
                "giornali_validati": giornali_validati,
                "giornali_pendenti": giornali_totali - giornali_validati,
                "users_count": users_count,
                "recent_photos": recent_photos,
                "storage_mb": round(storage_mb, 2),
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating site statistics for {site_id}: {str(e)}")
            # Return empty stats on error
            return {
                "photos_count": 0,
                "documents_count": 0,
                "us_usm_count": 0,
                "us_count": 0,
                "usm_count": 0,
                "giornali_totali": 0,
                "giornali_validati": 0,
                "giornali_pendenti": 0,
                "users_count": 0,
                "recent_photos": 0,
                "storage_mb": 0,
                "last_updated": datetime.now().isoformat()
            }

    @staticmethod
    async def get_recent_activities(
        db: AsyncSession,
        site_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent site activities.
        
        Args:
            db: Database session
            site_id: UUID of the site
            limit: Maximum number of activities to return
            
        Returns:
            List of activity dictionaries
        """
        try:
            from sqlalchemy.orm import selectinload
            
            stmt = (
                select(UserActivity, User)
                .outerjoin(User, UserActivity.user_id == User.id)
                .options(selectinload(User.profile))
                .where(UserActivity.site_id == str(site_id))
                .order_by(UserActivity.activity_date.desc())
                .limit(limit)
            )

            result = await db.execute(stmt)
            activities = result.all()

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
            
        except Exception as e:
            logger.error(f"Error retrieving recent activities for {site_id}: {str(e)}")
            return []

    @staticmethod
    async def get_recent_photos(
        db: AsyncSession,
        site_id: UUID,
        limit: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent site photos.
        
        Args:
            db: Database session
            site_id: UUID of the site
            limit: Maximum number of photos to return
            
        Returns:
            List of photo dictionaries
        """
        try:
            stmt = (
                select(Photo)
                .where(Photo.site_id == str(site_id))
                .order_by(Photo.created_at.desc())
                .limit(limit)
            )

            result = await db.execute(stmt)
            photos = result.scalars().all()

            return [
                {
                    "id": str(photo.id),
                    "filename": photo.filename,
                    "thumbnail_url": f"/api/v1/photos/{photo.id}/thumbnail",
                    "full_url": f"/api/v1/photos/{photo.id}/full",
                    "photo_type": photo.photo_type if photo.photo_type else None,
                    "created_at": photo.created_at.isoformat(),
                    "category": getattr(photo, 'category', None)
                }
                for photo in photos
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving recent photos for {site_id}: {str(e)}")
            return []

    @staticmethod
    async def get_team_members(
        db: AsyncSession,
        site_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve site team members.
        
        Args:
            db: Database session
            site_id: UUID of the site
            limit: Maximum number of members to return
            
        Returns:
            List of team member dictionaries
        """
        try:
            from sqlalchemy.orm import selectinload
            
            stmt = (
                select(User, UserSitePermission)
                .join(UserSitePermission, User.id == UserSitePermission.user_id)
                .options(selectinload(User.profile))
                .where(
                    and_(
                        UserSitePermission.site_id == str(site_id),
                        UserSitePermission.is_active == True
                    )
                )
                .order_by(UserSitePermission.permission_level.desc())
                .limit(limit)
            )

            result = await db.execute(stmt)
            team = result.all()

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
            
        except Exception as e:
            logger.error(f"Error retrieving team members for {site_id}: {str(e)}")
            return []

    @staticmethod
    async def get_dashboard_data(
        db: AsyncSession,
        site_id: UUID
    ) -> Dict[str, Any]:
        """
        Get all dashboard data in a single call.
        Consolidates statistics, activities, photos, and team data.
        
        Args:
            db: Database session
            site_id: UUID of the site
            
        Returns:
            Dictionary with all dashboard data
        """
        stats = await DashboardService.get_statistics(db, site_id)
        activities = await DashboardService.get_recent_activities(db, site_id)
        photos = await DashboardService.get_recent_photos(db, site_id)
        team = await DashboardService.get_team_members(db, site_id)
        
        return {
            "stats": stats,
            "recent_activities": activities,
            "recent_photos": photos,
            "team_members": team
        }
