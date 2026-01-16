"""
Voice Database Functions

Functions that can be called by the LLM to query the FastZoom database.
Each function returns structured data that can be formatted into natural language responses.
"""

from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.documentation_and_field import Photo
from app.models.giornale_cantiere import GiornaleCantiere
from app.models import UnitaStratigrafica
from app.models.sites import ArchaeologicalSite


# ============================================================================
# Function Definitions for LLM
# ============================================================================

VOICE_FUNCTIONS = [
    {
        "name": "get_site_stats",
        "description": "Ottiene statistiche generali del sito corrente: numero di foto, giornali, unità stratigrafiche",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_photos_count",
        "description": "Conta le foto nel sito corrente, opzionalmente filtrate per periodo temporale",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "this_week", "this_month", "all"],
                    "description": "Periodo temporale per filtrare le foto"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_recent_photos",
        "description": "Ottiene le foto più recenti del sito",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Numero massimo di foto da restituire (default 5)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_giornali_count",
        "description": "Conta i giornali di cantiere nel sito corrente",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "this_week", "this_month", "all"],
                    "description": "Periodo temporale"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_recent_giornali",
        "description": "Ottiene gli ultimi giornali di cantiere",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Numero massimo di giornali (default 5)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_us_count",
        "description": "Conta le unità stratigrafiche nel sito corrente",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


# ============================================================================
# Helper Functions
# ============================================================================

def _get_date_filter(period: str) -> Optional[date]:
    """Convert period string to date filter."""
    today = date.today()
    if period == "today":
        return today
    elif period == "yesterday":
        return today - timedelta(days=1)
    elif period == "this_week":
        return today - timedelta(days=7)
    elif period == "this_month":
        return today - timedelta(days=30)
    return None  # "all" or None


# ============================================================================
# Function Implementations
# ============================================================================

async def get_site_stats(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """Get general site statistics."""
    try:
        # Count photos
        photos_result = await db.execute(
            select(func.count(Photo.id)).where(Photo.site_id == site_id)
        )
        photos_count = photos_result.scalar() or 0
        
        # Count giornali
        giornali_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == site_id)
        )
        giornali_count = giornali_result.scalar() or 0
        
        # Count US
        us_result = await db.execute(
            select(func.count(UnitaStratigrafica.id)).where(UnitaStratigrafica.site_id == site_id)
        )
        us_count = us_result.scalar() or 0
        
        # Get site name
        site_result = await db.execute(select(ArchaeologicalSite.name).where(ArchaeologicalSite.id == str(site_id)))
        site_name = site_result.scalar() or "Sito"
        
        return {
            "success": True,
            "data": {
                "site_name": site_name,
                "photos": photos_count,
                "giornali": giornali_count,
                "us": us_count
            },
            "message": f"Il sito '{site_name}' contiene {photos_count} foto, {giornali_count} giornali di cantiere e {us_count} unità stratigrafiche."
        }
    except Exception as e:
        logger.error(f"Error getting site stats: {e}")
        return {"success": False, "message": "Errore nel recupero delle statistiche."}


async def get_photos_count(db: AsyncSession, site_id: UUID, period: str = "all") -> Dict[str, Any]:
    """Count photos with optional date filter."""
    try:
        query = select(func.count(Photo.id)).where(Photo.site_id == site_id)
        
        date_filter = _get_date_filter(period)
        if date_filter:
            query = query.where(func.date(Photo.created_at) >= date_filter)
        
        result = await db.execute(query)
        count = result.scalar() or 0
        
        period_text = {
            "today": "oggi",
            "yesterday": "ieri",
            "this_week": "questa settimana",
            "this_month": "questo mese",
            "all": "in totale"
        }.get(period, "in totale")
        
        return {
            "success": True,
            "data": {"count": count, "period": period},
            "message": f"{period_text.capitalize()}, ci sono {count} foto nel sito."
        }
    except Exception as e:
        logger.error(f"Error counting photos: {e}")
        return {"success": False, "message": "Errore nel conteggio delle foto."}


async def get_recent_photos(db: AsyncSession, site_id: UUID, limit: int = 5) -> Dict[str, Any]:
    """Get most recent photos."""
    try:
        result = await db.execute(
            select(Photo.id, Photo.filename, Photo.created_at)
            .where(Photo.site_id == site_id)
            .order_by(Photo.created_at.desc())
            .limit(limit)
        )
        photos = result.all()
        
        if not photos:
            return {"success": True, "data": [], "message": "Non ci sono foto nel sito."}
        
        photo_list = [
            {"id": str(p.id), "filename": p.filename, "date": p.created_at.strftime("%d/%m/%Y")}
            for p in photos
        ]
        
        return {
            "success": True,
            "data": photo_list,
            "message": f"Le ultime {len(photos)} foto sono: " + ", ".join([p["filename"] for p in photo_list])
        }
    except Exception as e:
        logger.error(f"Error getting recent photos: {e}")
        return {"success": False, "message": "Errore nel recupero delle foto recenti."}


async def get_giornali_count(db: AsyncSession, site_id: UUID, period: str = "all") -> Dict[str, Any]:
    """Count giornali with optional date filter."""
    try:
        query = select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == site_id)
        
        date_filter = _get_date_filter(period)
        if date_filter:
            query = query.where(GiornaleCantiere.data_giornale >= date_filter)
        
        result = await db.execute(query)
        count = result.scalar() or 0
        
        period_text = {
            "today": "oggi",
            "yesterday": "ieri",
            "this_week": "questa settimana",
            "this_month": "questo mese",
            "all": "in totale"
        }.get(period, "in totale")
        
        return {
            "success": True,
            "data": {"count": count, "period": period},
            "message": f"{period_text.capitalize()}, ci sono {count} giornali di cantiere."
        }
    except Exception as e:
        logger.error(f"Error counting giornali: {e}")
        return {"success": False, "message": "Errore nel conteggio dei giornali."}


async def get_recent_giornali(db: AsyncSession, site_id: UUID, limit: int = 5) -> Dict[str, Any]:
    """Get most recent giornali."""
    try:
        result = await db.execute(
            select(GiornaleCantiere.id, GiornaleCantiere.data)
            .where(GiornaleCantiere.site_id == str(site_id))
            .order_by(GiornaleCantiere.data.desc())
            .limit(limit)
        )
        giornali = result.all()
        
        if not giornali:
            return {"success": True, "data": [], "message": "Non ci sono giornali di cantiere nel sito."}
        
        giornali_list = [
            {"id": str(g.id), "nome": f"Giornale del {g.data.strftime('%d/%m/%Y')}", "data": g.data.strftime("%d/%m/%Y")}
            for g in giornali
        ]
        
        return {
            "success": True,
            "data": giornali_list,
            "message": f"Gli ultimi {len(giornali)} giornali sono: " + ", ".join([f"{g['nome']} ({g['data']})" for g in giornali_list])
        }
    except Exception as e:
        logger.error(f"Error getting recent giornali: {e}")
        return {"success": False, "message": "Errore nel recupero dei giornali recenti."}


async def get_us_count(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """Count unità stratigrafiche."""
    try:
        result = await db.execute(
            select(func.count(UnitaStratigrafica.id)).where(UnitaStratigrafica.site_id == site_id)
        )
        count = result.scalar() or 0
        
        return {
            "success": True,
            "data": {"count": count},
            "message": f"Il sito contiene {count} unità stratigrafiche."
        }
    except Exception as e:
        logger.error(f"Error counting US: {e}")
        return {"success": False, "message": "Errore nel conteggio delle unità stratigrafiche."}


# ============================================================================
# Function Dispatcher
# ============================================================================

FUNCTION_MAP = {
    "get_site_stats": get_site_stats,
    "get_photos_count": get_photos_count,
    "get_recent_photos": get_recent_photos,
    "get_giornali_count": get_giornali_count,
    "get_recent_giornali": get_recent_giornali,
    "get_us_count": get_us_count,
}


async def execute_voice_db_function(
    function_name: str,
    parameters: Dict[str, Any],
    db: AsyncSession,
    site_id: UUID
) -> Dict[str, Any]:
    """
    Execute a voice function by name.
    
    Args:
        function_name: Name of the function to call
        parameters: Function parameters
        db: Database session
        site_id: Current site ID
        
    Returns:
        Function result dictionary with success, data, and message
    """
    func = FUNCTION_MAP.get(function_name)
    if not func:
        return {"success": False, "message": f"Funzione '{function_name}' non trovata."}
    
    try:
        # All functions require db and site_id, plus optional parameters
        return await func(db, site_id, **parameters)
    except TypeError as e:
        logger.error(f"Parameter error for {function_name}: {e}")
        return await func(db, site_id)
    except Exception as e:
        logger.error(f"Error executing {function_name}: {e}")
        return {"success": False, "message": f"Errore nell'esecuzione della funzione."}
