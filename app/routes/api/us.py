# app/routes/api/us.py
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

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
    payload: USCreate,
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    if not await verify_site_access(payload.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    us = UnitaStratigrafica(**payload.model_dump(exclude_unset=True))
    db.add(us)
    await db.commit()
    await db.refresh(us)
    return us

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
    payload: USMCreate,
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    if not await verify_site_access(payload.site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")
    usm = UnitaStratigraficaMuraria(**payload.model_dump(exclude_unset=True))
    db.add(usm)
    await db.commit()
    await db.refresh(usm)
    return usm

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
