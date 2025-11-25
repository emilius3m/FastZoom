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
import logging

logger = logging.getLogger(__name__)

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
    return any(s["id"] == str(site_id) for s in user_sites)

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
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Get a specific US by ID for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us/{us_id}
    """
    result = await db.execute(
        select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id)
    )
    us = result.scalar_one_or_none()
    if not us:
        raise HTTPException(status_code=404, detail="US non trovata")
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    if us.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="US non trovata per questo sito")
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
    us_id: UUID,
    payload: USUpdate,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Update a specific US for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us/{us_id}
    """
    try:
        logger.info(f"Updating US {us_id} with payload: {payload.model_dump()}")
        
        result = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id))
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
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Delete a specific US for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/us/{us_id}
    """
    result = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id))
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
    usm_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Get a specific USM by ID for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm/{usm_id}
    """
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
    )
    usm = result.scalar_one_or_none()
    if not usm:
        raise HTTPException(status_code=404, detail="USM non trovata")
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    if usm.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="USM non trovata per questo sito")
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
    usm_id: UUID,
    payload: USMUpdate,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Update a specific USM for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm/{usm_id}
    """
    try:
        print(f"\n{'='*80}")
        print(f"[UPDATE USM] Updating USM {usm_id}")
        print(f"[UPDATE USM] Payload received: {payload.model_dump()}")
        print(f"{'='*80}\n")
        
        result = await db.execute(
            select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
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
        
        print(f"\n[UPDATE USM] USM {usm_id} updated successfully")
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
    usm_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Delete a specific USM for the specified site.
    
    Endpoint: /api/v1/us/sites/{site_id}/usm/{usm_id}
    """
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
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