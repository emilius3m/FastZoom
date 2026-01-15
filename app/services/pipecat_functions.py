"""
Pipecat Function Handlers

Implementation of function handlers that the LLM can invoke.
These bridge voice commands to FastZoom services.
"""

from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_async_session
from app.models.documentation_and_field import Photo
from app.models.sites import ArchaeologicalSite as Site
from app.models.users import User
from app.models.giornale_cantiere import GiornaleCantiere as Giornale
from app.services.pipecat_service import pipecat_service


async def search_photos_handler(
    arguments: dict,
    user_id: Optional[UUID] = None,
    site_id: Optional[UUID] = None,
    **kwargs
) -> dict:
    """
    Search for photos based on query and optional site filter.
    
    Args:
        arguments: {"query": str, "site_name": str (optional)}
        user_id: Current user ID
        site_id: Current site context
    """
    query = arguments.get("query", "")
    site_name = arguments.get("site_name")
    
    async for session in get_async_session():
        try:
            stmt = select(Photo).where(
                Photo.is_published == True
            )
            
            # Filter by search query in title, description, keywords
            if query:
                search_pattern = f"%{query}%"
                stmt = stmt.where(
                    (Photo.title.ilike(search_pattern)) |
                    (Photo.description.ilike(search_pattern)) |
                    (Photo.keywords.ilike(search_pattern))
                )
            
            # Filter by site name if provided
            if site_name:
                stmt = stmt.join(Site).where(Site.name.ilike(f"%{site_name}%"))
            
            # Limit results
            stmt = stmt.limit(10)
            
            result = await session.execute(stmt)
            photos = result.scalars().all()
            
            if not photos:
                return {
                    "success": True,
                    "message": f"Nessuna foto trovata per '{query}'",
                    "count": 0,
                    "photos": []
                }
            
            photo_list = [
                {
                    "id": str(photo.id),
                    "title": photo.title or photo.original_filename,
                    "description": photo.description[:100] if photo.description else None,
                }
                for photo in photos
            ]
            
            return {
                "success": True,
                "message": f"Trovate {len(photos)} foto per '{query}'",
                "count": len(photos),
                "photos": photo_list
            }
            
        except Exception as e:
            logger.error(f"Error searching photos: {e}")
            return {"error": True, "message": str(e)}


async def get_site_info_handler(
    arguments: dict,
    user_id: Optional[UUID] = None,
    site_id: Optional[UUID] = None,
    **kwargs
) -> dict:
    """
    Get information about an archaeological site.
    
    Args:
        arguments: {"site_name": str}
    """
    site_name = arguments.get("site_name", "")
    
    async for session in get_async_session():
        try:
            stmt = select(Site).where(
                Site.name.ilike(f"%{site_name}%")
            ).limit(1)
            
            result = await session.execute(stmt)
            site = result.scalar_one_or_none()
            
            if not site:
                return {
                    "success": False,
                    "message": f"Sito '{site_name}' non trovato"
                }
            
            # Count photos for this site
            photo_count_stmt = select(func.count(Photo.id)).where(Photo.site_id == site.id)
            photo_count = await session.execute(photo_count_stmt)
            
            return {
                "success": True,
                "site": {
                    "id": str(site.id),
                    "name": site.name,
                    "code": site.code,
                    "location": site.location,
                    "region": site.region,
                    "province": site.province,
                    "description": site.description[:200] if site.description else None,
                    "historical_period": site.historical_period,
                    "site_type": site.site_type,
                    "research_status": site.research_status,
                    "photo_count": photo_count.scalar() or 0,
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting site info: {e}")
            return {"error": True, "message": str(e)}


async def get_statistics_handler(
    arguments: dict,
    user_id: Optional[UUID] = None,
    site_id: Optional[UUID] = None,
    **kwargs
) -> dict:
    """
    Get statistics about photos, sites, or activities.
    
    Args:
        arguments: {"stat_type": str, "time_range": str}
    """
    stat_type = arguments.get("stat_type", "photos")
    time_range = arguments.get("time_range", "all")
    
    # Calculate date filter
    date_filter = None
    now = datetime.utcnow()
    if time_range == "today":
        date_filter = now - timedelta(days=1)
    elif time_range == "week":
        date_filter = now - timedelta(weeks=1)
    elif time_range == "month":
        date_filter = now - timedelta(days=30)
    elif time_range == "year":
        date_filter = now - timedelta(days=365)
    
    async for session in get_async_session():
        try:
            if stat_type == "photos":
                stmt = select(func.count(Photo.id))
                if date_filter:
                    stmt = stmt.where(Photo.created_at >= date_filter)
                result = await session.execute(stmt)
                count = result.scalar() or 0
                
                return {
                    "success": True,
                    "stat_type": "photos",
                    "time_range": time_range,
                    "count": count,
                    "message": f"Ci sono {count} foto nel periodo selezionato"
                }
                
            elif stat_type == "sites":
                stmt = select(func.count(Site.id))
                result = await session.execute(stmt)
                count = result.scalar() or 0
                
                return {
                    "success": True,
                    "stat_type": "sites",
                    "count": count,
                    "message": f"Ci sono {count} siti archeologici nel sistema"
                }
                
            elif stat_type == "users":
                stmt = select(func.count(User.id)).where(User.is_active == True)
                result = await session.execute(stmt)
                count = result.scalar() or 0
                
                return {
                    "success": True,
                    "stat_type": "users",
                    "count": count,
                    "message": f"Ci sono {count} utenti attivi"
                }
            
            else:
                return {
                    "success": False,
                    "message": f"Tipo di statistica '{stat_type}' non supportato"
                }
                
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {"error": True, "message": str(e)}


async def navigate_to_handler(
    arguments: dict,
    user_id: Optional[UUID] = None,
    site_id: Optional[UUID] = None,
    **kwargs
) -> dict:
    """
    Generate navigation instructions for the frontend.
    
    Args:
        arguments: {"page": str, "site_id": str (optional)}
    """
    page = arguments.get("page", "dashboard")
    target_site_id = arguments.get("site_id")
    
    # Map page names to URLs
    page_urls = {
        "dashboard": "/dashboard",
        "sites": "/sites",
        "photos": f"/sites/{target_site_id}/photos" if target_site_id else "/photos",
        "giornale": f"/sites/{target_site_id}/giornale" if target_site_id else "/giornale",
        "admin": "/admin",
        "profile": "/profile",
    }
    
    url = page_urls.get(page, "/dashboard")
    
    return {
        "success": True,
        "action": "navigate",
        "url": url,
        "page": page,
        "message": f"Navigo alla pagina {page}"
    }


async def create_giornale_handler(
    arguments: dict,
    user_id: Optional[UUID] = None,
    site_id: Optional[UUID] = None,
    **kwargs
) -> dict:
    """
    Prepare data for creating a new giornale di cantiere.
    
    Note: This returns data for the frontend to complete the action,
    as creating records requires proper authentication context.
    
    Args:
        arguments: {"site_id": str, "date": str, "description": str}
    """
    target_site_id = arguments.get("site_id") or (str(site_id) if site_id else None)
    date = arguments.get("date", datetime.now().strftime("%Y-%m-%d"))
    description = arguments.get("description", "")
    
    if not target_site_id:
        return {
            "success": False,
            "message": "È necessario specificare un sito archeologico"
        }
    
    return {
        "success": True,
        "action": "create_giornale",
        "data": {
            "site_id": target_site_id,
            "date": date,
            "description": description,
        },
        "message": f"Preparato nuovo giornale di cantiere per il {date}"
    }


def register_all_handlers():
    """Register all function handlers with the Pipecat service."""
    pipecat_service.register_function_handler("search_photos", search_photos_handler)
    pipecat_service.register_function_handler("get_site_info", get_site_info_handler)
    pipecat_service.register_function_handler("get_statistics", get_statistics_handler)
    pipecat_service.register_function_handler("navigate_to", navigate_to_handler)
    pipecat_service.register_function_handler("create_giornale", create_giornale_handler)
    logger.info("Registered all Pipecat function handlers")
