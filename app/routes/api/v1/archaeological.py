"""
API v1 - Archaeological Plans Management
Endpoints per gestione piante e dati archeologici.
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
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)

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
        (site for site in user_sites if site["site_id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise SiteNotFoundError(str(site_id))
    
    return site_info

# NUOVI ENDPOINTS V1 - STUB IMPLEMENTATION

@router.get("/sites/{site_id}/plans", summary="Lista piante archeologiche", tags=["Archaeological Plans"])
async def v1_get_site_archaeological_plans(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera tutte le piante archeologiche di un sito.
    
    TODO: Implementare con logica completa da app/routes/api/archaeological_plans.py
    """
    site_info = verify_site_access(site_id, user_sites)
    
    return {
        "site_id": str(site_id),
        "plans": [],
        "count": 0,
        "site_info": site_info
    }

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API archaeological plans", tags=["Archaeological Plans - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per archaeological plans.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/archaeological-plan/site/{site_id}/plans": "/api/v1/archaeological/sites/{site_id}/plans",
                "/api/archaeological-plan/site/{site_id}/plan/{plan_id}": "/api/v1/archaeological/sites/{site_id}/plans/{plan_id}"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints archaeological plans in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints archaeological plans"
        }
    }