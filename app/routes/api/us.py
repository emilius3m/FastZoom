# app/routes/api/us.py
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
from app.models.us import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.schemas.us import (
    USCreate, USUpdate, USOut,
    USMCreate, USMUpdate, USMOut
)

us_router = APIRouter(prefix="/api", tags=["us-usm"])

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    return any(s["id"] == str(site_id) for s in user_sites)

# ------- US CRUD -------

@us_router.post("/us", response_model=USOut, status_code=status.HTTP_201_CREATED)
async def create_us(
    request: Request,
    payload: USCreate,
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    try:
        logger.info(f"Creating US with payload: {payload.model_dump()}")
        
        if not await verify_site_access(payload.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Process payload to ensure proper data types
        payload_dict = payload.model_dump(exclude_unset=True)
        
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
        
        # Ensure site_id is a valid UUID
        if 'site_id' in payload_dict and isinstance(payload_dict['site_id'], str):
            try:
                payload_dict['site_id'] = UUID(payload_dict['site_id'])
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="site_id non è un UUID valido")
        
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

@us_router.get("/us/{us_id}", response_model=USOut)
async def get_us(
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    result = await db.execute(
        select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id)
    )
    us = result.scalar_one_or_none()
    if not us:
        raise HTTPException(status_code=404, detail="US non trovata")
    if not await verify_site_access(us.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    return us

@us_router.get("/us", response_model=List[USOut])
async def list_us(
    site_id: UUID = Query(...),
    search: Optional[str] = Query(None),
    da: Optional[str] = Query(None),
    a: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    q = select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == site_id)
    if search:
        like = f"%{search}%"
        q = q.where(UnitaStratigrafica.descrizione.ilike(like))
    q = q.order_by(desc(UnitaStratigrafica.created_at)).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows

@us_router.put("/us/{us_id}", response_model=USOut)
async def update_us(
    us_id: UUID,
    payload: USUpdate,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    result = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id))
    us = result.scalar_one_or_none()
    if not us:
        raise HTTPException(status_code=404, detail="US non trovata")
    if not await verify_site_access(us.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(us, k, v)
    await db.commit()
    await db.refresh(us)
    return us

@us_router.delete("/us/{us_id}", status_code=204)
async def delete_us(
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    result = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id))
    us = result.scalar_one_or_none()
    if not us:
        raise HTTPException(status_code=404, detail="US non trovata")
    if not await verify_site_access(us.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    await db.delete(us)
    await db.commit()
    return

# ------- USM CRUD -------

@us_router.post("/usm", response_model=USMOut, status_code=status.HTTP_201_CREATED)
async def create_usm(
    request: Request,
    payload: USMCreate,
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    try:
        logger.info(f"Creating USM with payload: {payload.model_dump()}")
        
        if not await verify_site_access(payload.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Process payload to ensure proper data types
        payload_dict = payload.model_dump(exclude_unset=True)
        
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
        
        # Ensure site_id is a valid UUID
        if 'site_id' in payload_dict and isinstance(payload_dict['site_id'], str):
            try:
                payload_dict['site_id'] = UUID(payload_dict['site_id'])
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="site_id non è un UUID valido")
        
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
        
        usm = UnitaStratigraficaMuraria(**payload_dict)
        db.add(usm)
        await db.commit()
        await db.refresh(usm)
        return usm
        
    except ValidationError as e:
        logger.error(f"Validation error creating USM: {e}")
        raise HTTPException(status_code=422, detail=f"Errore di validazione: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating USM: {e}")
        raise HTTPException(status_code=500, detail=f"Errore interno del server: {str(e)}")

@us_router.get("/usm/{usm_id}", response_model=USMOut)
async def get_usm(
    usm_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
    )
    usm = result.scalar_one_or_none()
    if not usm:
        raise HTTPException(status_code=404, detail="USM non trovata")
    if not await verify_site_access(usm.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    return usm

@us_router.get("/usm", response_model=List[USMOut])
async def list_usm(
    site_id: UUID = Query(...),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    q = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.site_id == site_id)
    if search:
        like = f"%{search}%"
        q = q.where(UnitaStratigraficaMuraria.descrizione.ilike(like))
    q = q.order_by(desc(UnitaStratigraficaMuraria.created_at)).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows

@us_router.put("/usm/{usm_id}", response_model=USMOut)
async def update_usm(
    usm_id: UUID,
    payload: USMUpdate,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
    )
    usm = result.scalar_one_or_none()
    if not usm:
        raise HTTPException(status_code=404, detail="USM non trovata")
    if not await verify_site_access(usm.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(usm, k, v)
    await db.commit()
    await db.refresh(usm)
    return usm

@us_router.delete("/usm/{usm_id}", status_code=204)
async def delete_usm(
    usm_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    result = await db.execute(
        select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
    )
    usm = result.scalar_one_or_none()
    if not usm:
        raise HTTPException(status_code=404, detail="USM non trovata")
    if not await verify_site_access(usm.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    await db.delete(usm)
    await db.commit()
    return
