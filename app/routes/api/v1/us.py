"""
API v1 - US/USM Units Management
Endpoints per gestione Unità Stratigrafiche e Murarie.
Implementa backward compatibility con avvisi di deprecazione.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload
from pydantic import ValidationError
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.schemas.us import (
    USCreate, USUpdate, USOut,
    USMCreate, USMUpdate, USMOut
)

router = APIRouter()

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    return any(s["site_id"] == str(site_id) for s in user_sites)

# ------- US CRUD - V1 ENDPOINTS -------

@router.post("/sites/{site_id}/us", response_model=USOut, status_code=status.HTTP_201_CREATED, summary="Create US", tags=["US/USM Units"])
async def v1_create_us(
    site_id: UUID,
    request: Request,
    payload: USCreate,
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Create a new US (Unità Stratigrafica) for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us
    """
    try:
        logger.info(f"Creating US with payload: {payload.model_dump()}")
        
        # Override site_id from URL parameter
        payload_dict = payload.model_dump(exclude_unset=True)
        payload_dict['site_id'] = site_id
        
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and isinstance(payload_dict[field], str):
                try:
                    from datetime import datetime
                    payload_dict[field] = datetime.strptime(payload_dict[field], '%Y-%m-%d').date()
                except ValueError:
                    pass  # Keep original value if parsing fails
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        # Ensure site_id is a valid UUID and convert to string for SQLite compatibility
        if 'site_id' in payload_dict:
            if isinstance(payload_dict['site_id'], str):
                try:
                    # Validate UUID format but keep as string for SQLite
                    UUID(payload_dict['site_id'])
                except (ValueError, TypeError):
                    raise HTTPException(status_code=422, detail="site_id non è un UUID valido")
            elif isinstance(payload_dict['site_id'], UUID):
                # Convert UUID object to string for SQLite compatibility
                payload_dict['site_id'] = str(payload_dict['site_id'])
        
        # Validate us_code format
        if 'us_code' in payload_dict:
            import re
            us_code_pattern = re.compile(r'^US\d{3,4}$')
            if not us_code_pattern.match(payload_dict['us_code']):
                raise HTTPException(
                    status_code=422,
                    detail=f"us_code '{payload_dict['us_code']}' non è valido. Deve essere nel formato US seguito da 3-4 cifre (es: US001, US0001)"
                )
        
        # Validate date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                if isinstance(payload_dict[field], str):
                    if not payload_dict[field].strip():
                        # Empty string is OK, just set to None
                        payload_dict[field] = None
                    else:
                        try:
                            from datetime import datetime
                            payload_dict[field] = datetime.strptime(payload_dict[field], '%Y-%m-%d').date()
                        except ValueError:
                            raise HTTPException(
                                status_code=422,
                                detail=f"Campo '{field}': '{payload_dict[field]}' non è una data valida. Usare formato YYYY-MM-DD (es: 2025-01-15)"
                            )
        
        # Add user_id for created_by field (convert UUID to string for SQLite compatibility)
        payload_dict['created_by'] = str(user_id)
        payload_dict['updated_by'] = str(user_id)
        
        us = UnitaStratigrafica(**payload_dict)
        db.add(us)
        await db.commit()
        await db.refresh(us)
        return us
        
    except ValidationError as e:
        logger.error(f"Validation error creating US: {e}")
        raise HTTPException(status_code=422, detail=f"Errore di validazione: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating US: {e}")
        raise HTTPException(status_code=500, detail=f"Errore interno del server: {str(e)}")

@router.get("/sites/{site_id}/us/{us_id}", response_model=USOut, summary="Get US by ID", tags=["US/USM Units"])
async def v1_get_us(
    site_id: UUID,
    us_id: str,  # Accept as string to handle both formats
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Get a specific US by ID for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us/{us_id}
    """
    # Normalize UUID - handle both with and without hyphens
    try:
        # If us_id doesn't have hyphens, try to format it as a proper UUID
        if '-' not in us_id and len(us_id) == 32:
            # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
            normalized_us_id = f"{us_id[0:8]}-{us_id[8:12]}-{us_id[12:16]}-{us_id[16:20]}-{us_id[20:32]}"
            us_id_uuid = UUID(normalized_us_id)
            logger.info(f"🔧 [US_GET] Normalized UUID from {us_id} to {normalized_us_id}")
        else:
            # Try to parse as-is (with hyphens)
            us_id_uuid = UUID(us_id)
            normalized_us_id = str(us_id_uuid)
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [US_GET] Invalid UUID format: {us_id} - Error: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid UUID format",
                "message": f"L'ID US '{us_id}' non è un UUID valido",
                "us_id": us_id,
                "debug_info": "UUID must be in standard format (with or without hyphens)"
            }
        )
    
    # DEBUG LOGGING: Log request details
    logger.info(f"🔍 [US_GET] Request received - Site ID: {site_id}, US ID: {normalized_us_id}")
    logger.info(f"🔍 [US_GET] User has access to {len(user_sites)} sites")
    
    # Log user accessible sites for debugging
    if user_sites:
        logger.debug(f"🔍 [US_GET] Accessible sites: {[s['site_id'] for s in user_sites]}")
    else:
        logger.warning(f"⚠️  [US_GET] User has NO accessible sites - this is likely the root cause of 404 errors")
    
    # Check site access first (before database query for better performance)
    site_access = await verify_site_access(site_id, user_sites)
    logger.info(f"🔍 [US_GET] Site access check result: {site_access}")
    
    if not site_access:
        logger.error(f"❌ [US_GET] ACCESS DENIED - User does not have access to site {site_id}")
        logger.error(f"❌ [US_GET] Available sites: {[s['site_id'] for s in user_sites]}")
        logger.error(f"❌ [US_GET] Requested site: {site_id}")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Access denied",
                "message": f"Non hai i permessi per accedere al sito {site_id}",
                "site_id": str(site_id),
                "accessible_sites": [s["site_id"] for s in user_sites],
                "debug_info": "User lacks site permissions - contact administrator"
            }
        )
    
    # Query US from database
    logger.info(f"🔍 [US_GET] Querying US {normalized_us_id} from database...")
    result = await db.execute(
        select(UnitaStratigrafica).where(UnitaStratigrafica.id == str(us_id_uuid))
    )
    us = result.scalar_one_or_none()
    
    if not us:
        logger.error(f"❌ [US_GET] US NOT FOUND - US {normalized_us_id} does not exist in database")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "US not found",
                "message": f"L'Unità Stratigrafica {normalized_us_id} non esiste nel database",
                "us_id": normalized_us_id,
                "debug_info": "US ID not found in database"
            }
        )
    
    logger.info(f"🔍 [US_GET] US found - Site ID: {us.site_id}, US Code: {us.us_code}")
    
    # Check if US belongs to requested site
    if us.site_id != str(site_id):
        logger.error(f"❌ [US_GET] SITE MISMATCH - US {normalized_us_id} belongs to site {us.site_id}, not {site_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "US not found for this site",
                "message": f"L'US {normalized_us_id} appartiene al sito {us.site_id}, non al sito {site_id}",
                "us_id": normalized_us_id,
                "requested_site_id": str(site_id),
                "actual_site_id": us.site_id,
                "debug_info": "US exists but belongs to different site"
            }
        )
    
    logger.success(f"✅ [US_GET] SUCCESS - US {normalized_us_id} retrieved successfully")
    return us

@router.get("/sites/{site_id}/us", response_model=List[USOut], summary="List US for site", tags=["US/USM Units"])
async def v1_list_us(
    site_id: UUID,
    search: Optional[str] = Query(None),
    da: Optional[str] = Query(None),
    a: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    List US units for the specified site with optional filtering.
    
    Endpoint: /api/v1/us/sites/{site_id}/us
    """
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    q = select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == str(site_id))
    if search:
        like = f"%{search}%"
        q = q.where(UnitaStratigrafica.descrizione.ilike(like))
    q = q.order_by(desc(UnitaStratigrafica.created_at)).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows

@router.put("/sites/{site_id}/us/{us_id}", response_model=USOut, summary="Update US", tags=["US/USM Units"])
async def v1_update_us(
    site_id: UUID,
    us_id: str,  # Accept as string to handle both formats
    payload: USUpdate,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Update a specific US for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us/{us_id}
    """
    # Normalize UUID - handle both with and without hyphens
    try:
        # If us_id doesn't have hyphens, try to format it as a proper UUID
        if '-' not in us_id and len(us_id) == 32:
            # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
            normalized_us_id = f"{us_id[0:8]}-{us_id[8:12]}-{us_id[12:16]}-{us_id[16:20]}-{us_id[20:32]}"
            us_id_uuid = UUID(normalized_us_id)
            logger.info(f"🔧 [US_UPDATE] Normalized UUID from {us_id} to {normalized_us_id}")
        else:
            # Try to parse as-is (with hyphens)
            us_id_uuid = UUID(us_id)
            normalized_us_id = str(us_id_uuid)
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [US_UPDATE] Invalid UUID format: {us_id} - Error: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid UUID format",
                "message": f"L'ID US '{us_id}' non è un UUID valido",
                "us_id": us_id,
                "debug_info": "UUID must be in standard format (with or without hyphens)"
            }
        )
    
    try:
        logger.info(f"Updating US {normalized_us_id} with payload: {payload.model_dump()}")
        
        result = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == str(us_id_uuid)))
        us = result.scalar_one_or_none()
        if not us:
            raise HTTPException(status_code=404, detail="US non trovata")
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        if us.site_id != str(site_id):
            raise HTTPException(status_code=404, detail="US non trovata per questo sito")
        
        # Process payload to ensure proper data types
        payload_dict = payload.model_dump(exclude_unset=True)
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                if isinstance(payload_dict[field], str):
                    if not payload_dict[field].strip():
                        payload_dict[field] = None
                    else:
                        try:
                            from datetime import datetime
                            payload_dict[field] = datetime.strptime(payload_dict[field], '%Y-%m-%d').date()
                        except ValueError:
                            raise HTTPException(
                                status_code=422,
                                detail=f"Campo '{field}': '{payload_dict[field]}' non è una data valida. Usare formato YYYY-MM-DD (es: 2025-01-15)"
                            )
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        # Update all fields
        for k, v in payload_dict.items():
            setattr(us, k, v)
        
        await db.commit()
        await db.refresh(us)
        logger.info(f"US {us_id} updated successfully")
        return us
        
    except ValidationError as e:
        logger.error(f"Validation error updating US: {e}")
        raise HTTPException(status_code=422, detail=f"Errore di validazione: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating US: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Errore interno del server: {str(e)}")

@router.delete("/sites/{site_id}/us/{us_id}", status_code=204, summary="Delete US", tags=["US/USM Units"])
async def v1_delete_us(
    site_id: UUID,
    us_id: str,  # Accept as string to handle both formats
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Delete a specific US for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us/{us_id}
    """
    # Normalize UUID - handle both with and without hyphens
    try:
        # If us_id doesn't have hyphens, try to format it as a proper UUID
        if '-' not in us_id and len(us_id) == 32:
            # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
            normalized_us_id = f"{us_id[0:8]}-{us_id[8:12]}-{us_id[12:16]}-{us_id[16:20]}-{us_id[20:32]}"
            us_id_uuid = UUID(normalized_us_id)
            logger.info(f"🔧 [US_DELETE] Normalized UUID from {us_id} to {normalized_us_id}")
        else:
            # Try to parse as-is (with hyphens)
            us_id_uuid = UUID(us_id)
            normalized_us_id = str(us_id_uuid)
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [US_DELETE] Invalid UUID format: {us_id} - Error: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid UUID format",
                "message": f"L'ID US '{us_id}' non è un UUID valido",
                "us_id": us_id,
                "debug_info": "UUID must be in standard format (with or without hyphens)"
            }
        )
    
    result = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == str(us_id_uuid)))
    us = result.scalar_one_or_none()
    if not us:
        raise HTTPException(status_code=404, detail="US non trovata")
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    if us.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="US non trovata per questo sito")
    await db.delete(us)
    await db.commit()
    return

# ------- USM CRUD - V1 ENDPOINTS -------

@router.post("/sites/{site_id}/usm", response_model=USMOut, status_code=status.HTTP_201_CREATED, summary="Create USM", tags=["US/USM Units"])
async def v1_create_usm(
    site_id: UUID,
    request: Request,
    payload: USMCreate,
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Create a new USM (Unità Stratigrafica Muraria) for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm
    """
    try:
        # Get raw request body for debugging
        body = await request.body()
        logger.info(f"Raw request body: {body.decode('utf-8')}")
        logger.info(f"Creating USM with payload: {payload.model_dump()}")
        
        # Override site_id from URL parameter
        payload_dict = payload.model_dump(exclude_unset=True)
        payload_dict['site_id'] = site_id
        
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and isinstance(payload_dict[field], str):
                try:
                    from datetime import datetime
                    payload_dict[field] = datetime.strptime(payload_dict[field], '%Y-%m-%d').date()
                except ValueError:
                    pass  # Keep original value if parsing fails
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        if 'superficie_analizzata' in payload_dict and payload_dict['superficie_analizzata'] is not None:
            try:
                payload_dict['superficie_analizzata'] = float(payload_dict['superficie_analizzata'])
            except (ValueError, TypeError):
                pass
        
        # Ensure site_id is a valid UUID and convert to string for SQLite compatibility
        if 'site_id' in payload_dict:
            if isinstance(payload_dict['site_id'], str):
                try:
                    # Validate UUID format but keep as string for SQLite
                    UUID(payload_dict['site_id'])
                except (ValueError, TypeError):
                    raise HTTPException(status_code=422, detail="site_id non è un UUID valido")
            elif isinstance(payload_dict['site_id'], UUID):
                # Convert UUID object to string for SQLite compatibility
                payload_dict['site_id'] = str(payload_dict['site_id'])
        
        # Validate usm_code format
        if 'usm_code' in payload_dict:
            import re
            usm_code_pattern = re.compile(r'^USM\d{3,4}$')
            if not usm_code_pattern.match(payload_dict['usm_code']):
                raise HTTPException(
                    status_code=422,
                    detail=f"usm_code '{payload_dict['usm_code']}' non è valido. Deve essere nel formato USM seguito da 3-4 cifre (es: USM001, USM0001)"
                )
        
        # Validate date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                if isinstance(payload_dict[field], str):
                    if not payload_dict[field].strip():
                        # Empty string is OK, just set to None
                        payload_dict[field] = None
                    else:
                        try:
                            from datetime import datetime
                            payload_dict[field] = datetime.strptime(payload_dict[field], '%Y-%m-%d').date()
                        except ValueError:
                            raise HTTPException(
                                status_code=422,
                                detail=f"Campo '{field}': '{payload_dict[field]}' non è una data valida. Usare formato YYYY-MM-DD (es: 2025-01-15)"
                            )
        
        # Add user_id for created_by field (convert UUID to string for SQLite compatibility)
        payload_dict['created_by'] = str(user_id)
        payload_dict['updated_by'] = str(user_id)
        
        usm = UnitaStratigraficaMuraria(**payload_dict)
        db.add(usm)
        await db.commit()
        await db.refresh(usm)
        return usm
        
    except ValidationError as e:
        logger.error(f"Validation error creating USM: {e}")
        logger.error(f"Validation error details: {e.errors()}")
        # Format validation errors in a more readable way
        error_messages = []
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error['loc'])
            msg = error['msg']
            error_messages.append(f"Campo '{field}': {msg}")
        raise HTTPException(status_code=422, detail=" | ".join(error_messages))
    except Exception as e:
        logger.error(f"Unexpected error creating USM: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Errore interno del server: {str(e)}")

@router.get("/sites/{site_id}/usm/{usm_id}", response_model=USMOut, summary="Get USM by ID", tags=["US/USM Units"])
async def v1_get_usm(
    site_id: UUID,
    usm_id: str,  # Accept as string to handle both formats
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Get a specific USM by ID for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm/{usm_id}
    """
    # Normalize UUID - handle both with and without hyphens
    try:
        # If usm_id doesn't have hyphens, try to format it as a proper UUID
        if '-' not in usm_id and len(usm_id) == 32:
            # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
            normalized_usm_id = f"{usm_id[0:8]}-{usm_id[8:12]}-{usm_id[12:16]}-{usm_id[16:20]}-{usm_id[20:32]}"
            usm_id_uuid = UUID(normalized_usm_id)
            logger.info(f"🔧 [USM_GET] Normalized UUID from {usm_id} to {normalized_usm_id}")
        else:
            # Try to parse as-is (with hyphens)
            usm_id_uuid = UUID(usm_id)
            normalized_usm_id = str(usm_id_uuid)
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [USM_GET] Invalid UUID format: {usm_id} - Error: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid UUID format",
                "message": f"L'ID USM '{usm_id}' non è un UUID valido",
                "usm_id": usm_id,
                "debug_info": "UUID must be in standard format (with or without hyphens)"
            }
        )
    
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == str(usm_id_uuid))
    )
    usm = result.scalar_one_or_none()
    if not usm:
        logger.error(f"❌ [USM_GET] USM NOT FOUND - USM {normalized_usm_id} does not exist in database")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "USM not found",
                "message": f"L'Unità Stratigrafica Muraria {normalized_usm_id} non esiste nel database",
                "usm_id": normalized_usm_id,
                "debug_info": "USM ID not found in database"
            }
        )
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    if usm.site_id != str(site_id):
        logger.error(f"❌ [USM_GET] SITE MISMATCH - USM {normalized_usm_id} belongs to site {usm.site_id}, not {site_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "USM not found for this site",
                "message": f"L'USM {normalized_usm_id} appartiene al sito {usm.site_id}, non al sito {site_id}",
                "usm_id": normalized_usm_id,
                "requested_site_id": str(site_id),
                "actual_site_id": usm.site_id,
                "debug_info": "USM exists but belongs to different site"
            }
        )
    return usm

@router.get("/sites/{site_id}/usm", response_model=List[USMOut], summary="List USM for site", tags=["US/USM Units"])
async def v1_list_usm(
    site_id: UUID,
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    List USM units for the specified site with optional filtering.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm
    """
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    q = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.site_id == str(site_id))
    if search:
        like = f"%{search}%"
        q = q.where(UnitaStratigraficaMuraria.descrizione.ilike(like))
    q = q.order_by(desc(UnitaStratigraficaMuraria.created_at)).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows

@router.put("/sites/{site_id}/usm/{usm_id}", response_model=USMOut, summary="Update USM", tags=["US/USM Units"])
async def v1_update_usm(
    site_id: UUID,
    usm_id: str,  # Accept as string to handle both formats
    payload: USMUpdate,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Update a specific USM for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm/{usm_id}
    """
    # Normalize UUID - handle both with and without hyphens
    try:
        # If usm_id doesn't have hyphens, try to format it as a proper UUID
        if '-' not in usm_id and len(usm_id) == 32:
            # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
            normalized_usm_id = f"{usm_id[0:8]}-{usm_id[8:12]}-{usm_id[12:16]}-{usm_id[16:20]}-{usm_id[20:32]}"
            usm_id_uuid = UUID(normalized_usm_id)
            logger.info(f"🔧 [USM_UPDATE] Normalized UUID from {usm_id} to {normalized_usm_id}")
        else:
            # Try to parse as-is (with hyphens)
            usm_id_uuid = UUID(usm_id)
            normalized_usm_id = str(usm_id_uuid)
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [USM_UPDATE] Invalid UUID format: {usm_id} - Error: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid UUID format",
                "message": f"L'ID USM '{usm_id}' non è un UUID valido",
                "usm_id": usm_id,
                "debug_info": "UUID must be in standard format (with or without hyphens)"
            }
        )
    
    try:
        print(f"\n{'='*80}")
        print(f"[UPDATE USM] Updating USM {normalized_usm_id}")
        print(f"[UPDATE USM] Payload received: {payload.model_dump()}")
        print(f"{'='*80}\n")
        
        result = await db.execute(
            select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == str(usm_id_uuid))
        )
        usm = result.scalar_one_or_none()
        if not usm:
            raise HTTPException(status_code=404, detail="USM non trovata")
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        if usm.site_id != str(site_id):
            raise HTTPException(status_code=404, detail="USM non trovata per questo sito")
        
        # Process payload to ensure proper data types
        payload_dict = payload.model_dump(exclude_unset=True)
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                if isinstance(payload_dict[field], str):
                    if not payload_dict[field].strip():
                        payload_dict[field] = None
                    else:
                        try:
                            from datetime import datetime
                            payload_dict[field] = datetime.strptime(payload_dict[field], '%Y-%m-%d').date()
                        except ValueError:
                            raise HTTPException(
                                status_code=422,
                                detail=f"Campo '{field}': '{payload_dict[field]}' non è una data valida. Usare formato YYYY-MM-DD (es: 2025-01-15)"
                            )
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        if 'superficie_analizzata' in payload_dict and payload_dict['superficie_analizzata'] is not None:
            try:
                payload_dict['superficie_analizzata'] = float(payload_dict['superficie_analizzata'])
            except (ValueError, TypeError):
                pass
        
        # Update all fields
        print(f"\n[UPDATE USM] Updating fields:")
        for k, v in payload_dict.items():
            setattr(usm, k, v)
            print(f"  - {k} = {v}")
        
        # Force flush to ensure changes are written
        await db.flush()
        await db.commit()
        await db.refresh(usm)
        
        print(f"\n[UPDATE USM] USM {normalized_usm_id} updated successfully")
        print(f"[UPDATE USM] data_rilevamento after save: {usm.data_rilevamento}")
        print(f"[UPDATE USM] data_rielaborazione after save: {usm.data_rielaborazione}")
        print(f"{'='*80}\n")
        return usm
        
    except ValidationError as e:
        logger.error(f"Validation error updating USM: {e}")
        logger.error(f"Validation error details: {e.errors()}")
        error_messages = []
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error['loc'])
            msg = error['msg']
            error_messages.append(f"Campo '{field}': {msg}")
        raise HTTPException(status_code=422, detail=" | ".join(error_messages))
    except Exception as e:
        logger.error(f"Unexpected error updating USM: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Errore interno del server: {str(e)}")

@router.delete("/sites/{site_id}/usm/{usm_id}", status_code=204, summary="Delete USM", tags=["US/USM Units"])
async def v1_delete_usm(
    site_id: UUID,
    usm_id: str,  # Accept as string to handle both formats
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Delete a specific USM for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm/{usm_id}
    """
    # Normalize UUID - handle both with and without hyphens
    try:
        # If usm_id doesn't have hyphens, try to format it as a proper UUID
        if '-' not in usm_id and len(usm_id) == 32:
            # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
            normalized_usm_id = f"{usm_id[0:8]}-{usm_id[8:12]}-{usm_id[12:16]}-{usm_id[16:20]}-{usm_id[20:32]}"
            usm_id_uuid = UUID(normalized_usm_id)
            logger.info(f"🔧 [USM_DELETE] Normalized UUID from {usm_id} to {normalized_usm_id}")
        else:
            # Try to parse as-is (with hyphens)
            usm_id_uuid = UUID(usm_id)
            normalized_usm_id = str(usm_id_uuid)
    except (ValueError, TypeError) as e:
        logger.error(f"❌ [USM_DELETE] Invalid UUID format: {usm_id} - Error: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid UUID format",
                "message": f"L'ID USM '{usm_id}' non è un UUID valido",
                "usm_id": usm_id,
                "debug_info": "UUID must be in standard format (with or without hyphens)"
            }
        )
    
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == str(usm_id_uuid))
    )
    usm = result.scalar_one_or_none()
    if not usm:
        raise HTTPException(status_code=404, detail="USM non trovata")
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    if usm.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="USM non trovata per questo sito")
    await db.delete(usm)
    await db.commit()
    return

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


@router.post(
    "/sites/{site_id}/harris-matrix/bulk-create",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk create US/USM from Harris Matrix editor",
    tags=["Harris Matrix Editor"]
)
async def bulk_create_from_matrix(
    site_id: UUID,
    payload: Dict[str, Any],  # nodes e edges dal frontend
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Create US/USM units and relationships in bulk from Harris Matrix editor.

    Input format:
    {
        "nodes": [
            {
                "temp_id": "temp_1",
                "type": "us",  # "us" or "usm"
                "tipo": "positiva",  # solo per US
                "periodo": "Medievale",
                "fase": "Fase 1",
                "definition": "Strato di terra",
                "datazione": "XII sec.",
                "localita": "Area A"
            }
        ],
        "edges": [
            {
                "from": "temp_1",
                "to": "temp_2",
                "relationship": "copre"  # copre, taglia, riempie, etc.
            }
        ]
    }
    """
    try:
        # Verifica accesso al sito
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")

        nodes = payload.get("nodes", [])
        edges = payload.get("edges", [])

        if not nodes:
            raise HTTPException(status_code=422, detail="Almeno un nodo è richiesto")

        # Genera codici sequenziali per US e USM
        us_nodes = [n for n in nodes if n.get("type") == "us"]
        usm_nodes = [n for n in nodes if n.get("type") == "usm"]

        # Trova il prossimo numero disponibile per US
        us_count_result = await db.execute(
            select(UnitaStratigrafica)
            .where(UnitaStratigrafica.site_id == str(site_id))
        )
        existing_us = us_count_result.scalars().all()
        next_us_num = len(existing_us) + 1

        # Trova il prossimo numero disponibile per USM
        usm_count_result = await db.execute(
            select(UnitaStratigraficaMuraria)
            .where(UnitaStratigraficaMuraria.site_id == str(site_id))
        )
        existing_usm = usm_count_result.scalars().all()
        next_usm_num = len(existing_usm) + 1

        # Mapping temp_id -> codice reale
        temp_id_mapping = {}
        created_units = {}

        # Crea US
        for i, node in enumerate(us_nodes):
            us_code = f"US{next_us_num + i:03d}"  # US001, US002, etc.
            temp_id_mapping[node["temp_id"]] = us_code

            us_data = {
                "site_id": str(site_id),
                "us_code": us_code,
                "tipo": node.get("tipo", "positiva"),
                "definizione": node.get("definition", ""),
                "periodo": node.get("periodo"),
                "fase": node.get("fase"),
                "datazione": node.get("datazione"),
                "localita": node.get("localita"),
                "sequenza_fisica": {},  # Sarà popolato dopo con le relazioni
                "created_by": str(user_id),
                "updated_by": str(user_id)
            }

            us = UnitaStratigrafica(**us_data)
            db.add(us)
            created_units[node["temp_id"]] = us

        # Crea USM
        for i, node in enumerate(usm_nodes):
            usm_code = f"USM{next_usm_num + i:03d}"  # USM001, USM002, etc.
            temp_id_mapping[node["temp_id"]] = usm_code

            usm_data = {
                "site_id": str(site_id),
                "usm_code": usm_code,
                "definizione": node.get("definition", ""),
                "periodo": node.get("periodo"),
                "fase": node.get("fase"),
                "datazione": node.get("datazione"),
                "localita": node.get("localita"),
                "sequenza_fisica": {},
                "created_by": str(user_id),
                "updated_by": str(user_id)
            }

            usm = UnitaStratigraficaMuraria(**usm_data)
            db.add(usm)
            created_units[node["temp_id"]] = usm

        # Flush per ottenere gli ID prima di aggiornare le relazioni
        await db.flush()

        # Costruisci sequenza_fisica per ogni unità
        for edge in edges:
            from_temp_id = edge["from"]
            to_temp_id = edge["to"]
            relationship = edge["relationship"]  # copre, taglia, etc.

            if from_temp_id not in created_units or to_temp_id not in created_units:
                logger.warning(f"Edge skipped: {from_temp_id} -> {to_temp_id} (unit not found)")
                continue

            from_unit = created_units[from_temp_id]
            to_code = temp_id_mapping[to_temp_id]

            # Aggiungi relazione a sequenza_fisica
            if not from_unit.sequenza_fisica:
                from_unit.sequenza_fisica = {}

            if relationship not in from_unit.sequenza_fisica:
                from_unit.sequenza_fisica[relationship] = []

            # Aggiungi suffisso "usm" se il target è USM
            to_node_type = next(n["type"] for n in nodes if n["temp_id"] == to_temp_id)
            target_ref = f"{to_code}usm" if to_node_type == "usm" else to_code

            if target_ref not in from_unit.sequenza_fisica[relationship]:
                from_unit.sequenza_fisica[relationship].append(target_ref)

        # Commit finale
        await db.commit()

        # Refresh per ottenere dati completi
        for unit in created_units.values():
            await db.refresh(unit)

        return {
            "success": True,
            "created": {
                "us": len(us_nodes),
                "usm": len(usm_nodes)
            },
            "mapping": temp_id_mapping,
            "message": f"Creati {len(us_nodes)} US e {len(usm_nodes)} USM con {len(edges)} relazioni"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk_create_from_matrix: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la creazione: {str(e)}"
        )
