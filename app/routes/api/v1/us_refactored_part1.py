"""
API v1 - US/USM Units Management
Endpoints per gestione Unità Stratigrafiche e Murarie.
Thin wrappers delegating to USService for business logic.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError
from loguru import logger

from app.database.db import get_async_session
from app.core.dependencies import get_database_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.schemas.us import (
    USCreate, USUpdate, USOut,
    USMCreate, USMUpdate, USMOut
)
from app.routes.api.v1.ocr_us_import import router as ocr_us_import_router
from app.services.us_service import USService
from app.core.domain_exceptions import (
    DomainValidationError,
    ResourceNotFoundError,
    InsufficientPermissionsError
)

router = APIRouter()

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    """Verify user has access to site"""
    return any(s["site_id"] == str(site_id) for s in user_sites)

# ------- US CRUD - V1 ENDPOINTS -------

@router.post("/sites/{site_id}/us", response_model=USOut, status_code=status.HTTP_201_CREATED, summary="Create US", tags=["US/USM Units"])
async def v1_create_us(
    site_id: UUID,
    request: Request,
    payload: USCreate,
    db: AsyncSession = Depends(get_database_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Create a new US (Unità Stratigrafica) for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us
    """
    try:
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Delegate to service
        us = await USService.create_us(db, payload, site_id, user_id)
        return us
        
    except DomainValidationError as e:
        logger.error(f"Validation error creating US: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating US: {e}")
        raise HTTPException(status_code=500, detail=f"Errore interno del server: {str(e)}")

@router.get("/sites/{site_id}/us/{us_id}", response_model=USOut, summary="Get US by ID", tags=["US/USM Units"])
async def v1_get_us(
    site_id: UUID,
    us_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Get a specific US by ID for the specified site."""
    try:
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        us = await USService.get_us(db, us_id, site_id)
        return us
        
    except DomainValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"US not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sites/{site_id}/us", response_model=List[USOut], summary="List US for site", tags=["US/USM Units"])
async def v1_list_us(
    site_id: UUID,
    search: Optional[str] = Query(None, description="Ricerca testuale generica"),
    da: Optional[str] = Query(None, description="Data rilevamento DA (YYYY-MM-DD)"),
    a: Optional[str] = Query(None, description="Data rilevamento A (YYYY-MM-DD)"),
    us_code: Optional[str] = Query(None, description="Codice US (es: US001)"),
    tipo: Optional[str] = Query(None, description="Tipo US: positiva o negativa"),
    periodo: Optional[str] = Query(None, description="Periodo cronologico"),
    fase: Optional[str] = Query(None, description="Fase stratigrafica"),
    definizione: Optional[str] = Query(None, description="Definizione US"),
    localita: Optional[str] = Query(None, description="Località"),
    area_struttura: Optional[str] = Query(None, description="Area/Struttura"),
    affidabilita: Optional[str] = Query(None, description="Affidabilità stratigrafica"),
    responsabile: Optional[str] = Query(None, description="Responsabile compilazione"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """List US units for the specified site with optional filtering."""
    try:
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        rows = await USService.list_us(
            db, site_id, search=search, da=da, a=a,
            us_code=us_code, tipo=tipo, periodo=periodo, fase=fase,
            definizione=definizione, localita=localita, area_struttura=area_struttura,
            affidabilita=affidabilita, responsabile=responsabile,
            skip=skip, limit=limit
        )
        return rows
        
    except Exception as e:
        logger.error(f"Error listing US: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/sites/{site_id}/us/{us_id}", response_model=USOut, summary="Update US", tags=["US/USM Units"])
async def v1_update_us(
    site_id: UUID,
    us_id: str,
    payload: USUpdate,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Update a specific US for the specified site."""
    try:
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        us = await USService.update_us(db, us_id, payload, site_id)
        return us
        
    except DomainValidationError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except ResourceNotFoundError as e:
        logger.error(f"US not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sites/{site_id}/us/{us_id}", status_code=204, summary="Delete US", tags=["US/USM Units"])
async def v1_delete_us(
    site_id: UUID,
    us_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Delete a specific US for the specified site."""
    try:
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        await USService.delete_us(db, us_id, site_id)
        return
        
    except ResourceNotFoundError as e:
        logger.error(f"US not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ------- USM CRUD - V1 ENDPOINTS -------

# NOTE: USM endpoints follow similar pattern - delegating to US Service
# Keeping the rest of the file temporarily for USM endpoints and bulk operations
# These will be refactored in the next step
