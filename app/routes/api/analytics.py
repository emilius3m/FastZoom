"""
Analytics API Routes
Provides analytics data for the unified dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from uuid import UUID
from typing import List, Dict, Any
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models import Photo, Document, UserActivity, User, UserSitePermission
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.models.giornale_cantiere import GiornaleCantiere

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview")
async def get_analytics_overview(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get analytics overview for the dashboard.
    Returns aggregated statistics across all accessible sites.
    """
    try:
        # Get site IDs accessible by user
        site_ids = [site['site_id'] for site in user_sites]
        
        if not site_ids:
            return {
                "total_documents": 0,
                "total_photos": 0,
                "total_us": 0,
                "total_activities_week": 0,
                "productivity_change": 0,
                "documents_by_site": [],
                "activities_by_day": [],
                "photos_trend": 0
            }
        
        # Calculate date ranges
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        two_months_ago = now - timedelta(days=60)
        
        # Total documents
        docs_result = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.site_id.in_(site_ids),
                    Document.is_deleted == False
                )
            )
        )
        total_documents = docs_result.scalar() or 0
        
        # Total photos
        photos_result = await db.execute(
            select(func.count(Photo.id)).where(Photo.site_id.in_(site_ids))
        )
        total_photos = photos_result.scalar() or 0
        
        # Photos this month vs last month (for productivity trend)
        photos_this_month = await db.execute(
            select(func.count(Photo.id)).where(
                and_(
                    Photo.site_id.in_(site_ids),
                    Photo.created_at >= month_ago
                )
            )
        )
        photos_this_month = photos_this_month.scalar() or 0
        
        photos_last_month = await db.execute(
            select(func.count(Photo.id)).where(
                and_(
                    Photo.site_id.in_(site_ids),
                    Photo.created_at >= two_months_ago,
                    Photo.created_at < month_ago
                )
            )
        )
        photos_last_month = photos_last_month.scalar() or 0
        
        # Calculate productivity change percentage
        if photos_last_month > 0:
            productivity_change = round(((photos_this_month - photos_last_month) / photos_last_month) * 100)
        elif photos_this_month > 0:
            productivity_change = 100
        else:
            productivity_change = 0
        
        # Total US + USM
        us_result = await db.execute(
            select(func.count(UnitaStratigrafica.id)).where(
                UnitaStratigrafica.site_id.in_(site_ids)
            )
        )
        total_us = us_result.scalar() or 0
        
        usm_result = await db.execute(
            select(func.count(UnitaStratigraficaMuraria.id)).where(
                UnitaStratigraficaMuraria.site_id.in_(site_ids)
            )
        )
        total_usm = usm_result.scalar() or 0
        
        # Activities in the last week
        activities_result = await db.execute(
            select(func.count(UserActivity.id)).where(
                and_(
                    UserActivity.site_id.in_(site_ids),
                    UserActivity.activity_date >= week_ago
                )
            )
        )
        total_activities_week = activities_result.scalar() or 0
        
        # Documents by site (for chart)
        documents_by_site = []
        for site in user_sites[:5]:  # Limit to 5 sites for chart
            site_docs = await db.execute(
                select(func.count(Document.id)).where(
                    and_(
                        Document.site_id == site['site_id'],
                        Document.is_deleted == False
                    )
                )
            )
            documents_by_site.append({
                "site_name": site.get('site_name', 'N/A'),
                "count": site_docs.scalar() or 0
            })
        
        # Activities by day (last 7 days)
        activities_by_day = []
        for i in range(7):
            day_start = now - timedelta(days=i+1)
            day_end = now - timedelta(days=i)
            
            day_activities = await db.execute(
                select(func.count(UserActivity.id)).where(
                    and_(
                        UserActivity.site_id.in_(site_ids),
                        UserActivity.activity_date >= day_start,
                        UserActivity.activity_date < day_end
                    )
                )
            )
            activities_by_day.append({
                "day": day_start.strftime("%d/%m"),
                "count": day_activities.scalar() or 0
            })
        
        activities_by_day.reverse()  # Oldest first
        
        # Giornali count
        giornali_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                GiornaleCantiere.site_id.in_(site_ids)
            )
        )
        total_giornali = giornali_result.scalar() or 0
        
        return {
            "total_documents": total_documents,
            "total_photos": total_photos,
            "total_us": total_us + total_usm,
            "total_giornali": total_giornali,
            "total_activities_week": total_activities_week,
            "productivity_change": productivity_change,
            "documents_by_site": documents_by_site,
            "activities_by_day": activities_by_day,
            "photos_trend": productivity_change
        }
        
    except Exception as e:
        logger.error(f"Error fetching analytics overview: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Errore nel recupero delle statistiche"
        )
