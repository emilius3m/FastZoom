"""
API v1 - ICCD Cataloging
Endpoints per gestione schede ICCD standard.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session

# Import existing ICCD functions for backward compatibility
from app.routes.api.iccd_records import (
    get_iccd_hierarchy_api__site_id__api_iccd_hierarchy_get,
    create_iccd_record_api__site_id__api_iccd_records_post,
    get_authority_files_api__site_id__api_iccd_authority_files_get,
    create_authority_file_api__site_id__api_iccd_authority_files_post
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
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )
    
    return site_info

# NUOVI ENDPOINTS V1

@router.get("/sites/{site_id}/hierarchy", summary="Gerarchia ICCD", tags=["ICCD Cataloging"])
async def v1_get_iccd_hierarchy(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera gerarchia completa ICCD per sito.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    return await get_iccd_hierarchy_api__site_id__api_iccd_hierarchy_get(site_id, db)

@router.post("/sites/{site_id}/records", summary="Crea scheda ICCD", tags=["ICCD Cataloging"])
async def v1_create_iccd_record(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea nuova scheda ICCD con gestione gerarchia.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di creazione
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permessi insufficienti per creare schede ICCD"
        )
    
    return await create_iccd_record_api__site_id__api_iccd_records_post(
        site_id, request, current_user_id, user_sites, db
    )

@router.get("/sites/{site_id}/authority-files", summary="Authority files", tags=["ICCD Cataloging"])
async def v1_get_authority_files(
    site_id: UUID,
    authority_type: Optional[str] = None,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Recupera authority files per un sito.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    return await get_authority_files_api__site_id__api_iccd_authority_files_get(
        site_id, authority_type, db
    )

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/iccd/{site_id}/hierarchy", summary="[DEPRECATED] Gerarchia ICCD legacy", tags=["ICCD Cataloging - Legacy"])
async def legacy_get_iccd_hierarchy(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session)
):
    """
    ⚠️ DEPRECATED: Gerarchia ICCD endpoint legacy.
    
    Usa /api/v1/iccd/sites/{site_id}/hierarchy invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning(f"Legacy ICCD hierarchy endpoint used for site {site_id} - deprecated")
    response = await get_iccd_hierarchy_api__site_id__api_iccd_hierarchy_get(site_id, db)
    if hasattr(response, 'headers'):
        add_deprecation_headers(response, f"/api/v1/iccd/sites/{site_id}/hierarchy")
    return response

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API ICCD", tags=["ICCD Cataloging - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per ICCD.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/{site_id}/api/iccd/hierarchy": "/api/v1/iccd/sites/{site_id}/hierarchy",
                "/api/{site_id}/api/iccd/records": "/api/v1/iccd/sites/{site_id}/records",
                "/api/{site_id}/api/iccd/authority-files": "/api/v1/iccd/sites/{site_id}/authority-files"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints ICCD in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints ICCD"
        }
    }