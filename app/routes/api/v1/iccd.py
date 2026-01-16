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
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)

# Import existing ICCD functions for backward compatibility
from app.routes.api.iccd_records import (
    get_iccd_hierarchy_api__site_id__api_iccd_hierarchy_get,
    create_iccd_record_api__site_id__api_iccd_records_post,
    get_authority_files_api__site_id__api_iccd_authority_files_get,
    create_authority_file_api__site_id__api_iccd_authority_files_post
)

router = APIRouter()



def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["site_id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise SiteNotFoundError(str(site_id))
    
    return site_info

# NUOVI ENDPOINTS V1

@router.get("/sites/{site_id}/hierarchy", summary="Gerarchia ICCD", tags=["ICCD Cataloging"])
async def v1_get_iccd_hierarchy(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
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
    db: AsyncSession = Depends(get_database_session)
):
    """
    Crea nuova scheda ICCD con gestione gerarchia.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di creazione
    if site_info.get("permission_level") not in ["admin", "editor"]:
        raise InsufficientPermissionsError("Creazione schede ICCD richiede permessi editor o admin")
    
    return await create_iccd_record_api__site_id__api_iccd_records_post(
        site_id, request, current_user_id, user_sites, db
    )

@router.get("/sites/{site_id}/authority-files", summary="Authority files", tags=["ICCD Cataloging"])
async def v1_get_authority_files(
    site_id: UUID,
    authority_type: Optional[str] = None,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera authority files per un sito.
    """
    # Verifica accesso al sito
    site_info = verify_site_access(site_id, user_sites)
    
    return await get_authority_files_api__site_id__api_iccd_authority_files_get(
        site_id, authority_type, db
    )

