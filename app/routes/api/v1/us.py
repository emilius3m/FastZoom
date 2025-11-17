"""
API v1 - US/USM Units Management
Endpoints per gestione Unità Stratigrafiche e Murarie.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )
    
    return site_info

# NUOVI ENDPOINTS V1 - STUB IMPLEMENTATION

@router.get("/sites/{site_id}/us", summary="Lista US sito", tags=["US/USM Units"])
async def v1_get_site_us(
    site_id: UUID,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera lista Unità Stratigrafiche del sito.
    
    TODO: Implementare con logica completa da app/routes/api/us.py
    """
    site_info = verify_site_access(site_id, user_sites)
    
    return {
        "site_id": str(site_id),
        "us_units": [],
        "count": 0,
        "site_info": site_info,
        "filters": {"search": search, "limit": limit, "offset": offset}
    }

@router.get("/sites/{site_id}/usm", summary="Lista USM sito", tags=["US/USM Units"])
async def v1_get_site_usm(
    site_id: UUID,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera lista Unità Stratigrafiche Murarie del sito.
    
    TODO: Implementare con logica completa da app/routes/api/us.py
    """
    site_info = verify_site_access(site_id, user_sites)
    
    return {
        "site_id": str(site_id),
        "usm_units": [],
        "count": 0,
        "site_info": site_info,
        "filters": {"search": search, "limit": limit, "offset": offset}
    }

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API US/USM", tags=["US/USM Units - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per US/USM.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/us": "/api/v1/us/sites/{site_id}/us",
                "/api/usm": "/api/v1/us/sites/{site_id}/usm",
                "/api/us/{us_id}": "/api/v1/us/sites/{site_id}/us/{us_id}",
                "/api/usm/{usm_id}": "/api/v1/us/sites/{site_id}/usm/{usm_id}"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Separazione endpoints US/USM in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints US/USM"
        }
    }