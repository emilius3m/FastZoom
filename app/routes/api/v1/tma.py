from typing import List, Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_database_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.stratigraphy import TabellaMaterialiArcheologici
from app.schemas.tma import TMACreate, TMAUpdate, TMAOut


router = APIRouter()


async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    return any(s["site_id"] == str(site_id) for s in user_sites)


def normalize_tma_payload(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize extended TMA payload while keeping backward compatibility columns."""
    normalized = dict(payload_dict)

    # MA repeatable block (required operationally)
    ma_items = normalized.get("ma_items") or []
    if not ma_items:
        # backward compatibility: derive from legacy mandatory single MA fields
        if normalized.get("macc") and normalized.get("macq"):
            ma_items = [{
                "macc": normalized.get("macc"),
                "macq": normalized.get("macq"),
                "macl": None,
                "macd": None,
                "macp": None,
                "mas": None,
            }]
    if not ma_items:
        raise HTTPException(status_code=422, detail="È necessario inserire almeno un blocco MA (categoria + quantità)")

    normalized["ma_items"] = ma_items
    normalized["macc"] = ma_items[0].get("macc", "")
    normalized["macq"] = ma_items[0].get("macq", "")

    # Optional extended structures defaults
    normalized["ldc"] = normalized.get("ldc") or {}
    normalized["provenienze"] = normalized.get("provenienze") or []
    normalized["scavo"] = normalized.get("scavo") or {}
    normalized["fta"] = normalized.get("fta") or []
    normalized["entita_multimediali"] = normalized.get("entita_multimediali") or []

    return normalized


@router.post(
    "/sites/{site_id}/records",
    response_model=TMAOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create TMA record",
    tags=["TMA"]
)
async def create_tma_record(
    site_id: UUID,
    payload: TMACreate,
    db: AsyncSession = Depends(get_database_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    payload_dict = payload.model_dump(exclude_unset=True)
    payload_dict = normalize_tma_payload(payload_dict)
    payload_dict["site_id"] = str(site_id)
    payload_dict["created_by"] = str(user_id)
    payload_dict["updated_by"] = str(user_id)

    row = TabellaMaterialiArcheologici(**payload_dict)
    db.add(row)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Errore validazione/salvataggio TMA: {str(e)}")

    await db.refresh(row)
    return row


@router.get(
    "/sites/{site_id}/records",
    response_model=List[TMAOut],
    summary="List TMA records",
    tags=["TMA"]
)
async def list_tma_records(
    site_id: UUID,
    search: Optional[str] = Query(None, description="Ricerca testuale su NCT, OGTD, OGTM, PVCC"),
    nct: Optional[str] = Query(None, description="Filtro per codice NCT concatenato"),
    ogtd: Optional[str] = Query(None, description="Tipo oggetto"),
    pvcc: Optional[str] = Query(None, description="Comune"),
    dtzg: Optional[str] = Query(None, description="Ambito cronologico"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    q = select(TabellaMaterialiArcheologici).where(
        TabellaMaterialiArcheologici.site_id == str(site_id)
    )

    if search:
        like = f"%{search}%"
        q = q.where(or_(
            TabellaMaterialiArcheologici.nctr.ilike(like),
            TabellaMaterialiArcheologici.nctn.ilike(like),
            TabellaMaterialiArcheologici.ogtd.ilike(like),
            TabellaMaterialiArcheologici.ogtm.ilike(like),
            TabellaMaterialiArcheologici.pvcc.ilike(like),
        ))

    if nct:
        # split fallback: search on both pieces
        q = q.where(or_(
            TabellaMaterialiArcheologici.nctr.ilike(f"%{nct}%"),
            TabellaMaterialiArcheologici.nctn.ilike(f"%{nct}%")
        ))

    if ogtd:
        q = q.where(TabellaMaterialiArcheologici.ogtd.ilike(f"%{ogtd}%"))

    if pvcc:
        q = q.where(TabellaMaterialiArcheologici.pvcc.ilike(f"%{pvcc}%"))

    if dtzg:
        q = q.where(TabellaMaterialiArcheologici.dtzg.ilike(f"%{dtzg}%"))

    q = q.order_by(desc(TabellaMaterialiArcheologici.created_at)).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return list(rows)


@router.get(
    "/sites/{site_id}/records/{record_id}",
    response_model=TMAOut,
    summary="Get TMA record",
    tags=["TMA"]
)
async def get_tma_record(
    site_id: UUID,
    record_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = (await db.execute(
        select(TabellaMaterialiArcheologici).where(TabellaMaterialiArcheologici.id == record_id)
    )).scalar_one_or_none()

    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    return row


@router.put(
    "/sites/{site_id}/records/{record_id}",
    response_model=TMAOut,
    summary="Update TMA record",
    tags=["TMA"]
)
async def update_tma_record(
    site_id: UUID,
    record_id: str,
    payload: TMAUpdate,
    db: AsyncSession = Depends(get_database_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = (await db.execute(
        select(TabellaMaterialiArcheologici).where(TabellaMaterialiArcheologici.id == record_id)
    )).scalar_one_or_none()

    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    payload_dict = payload.model_dump(exclude_unset=True)

    merged_payload = {
        "macc": row.macc,
        "macq": row.macq,
        "ma_items": row.ma_items or [],
        "ldc": row.ldc or {},
        "provenienze": row.provenienze or [],
        "scavo": row.scavo or {},
        "fta": row.fta or [],
        "entita_multimediali": row.entita_multimediali or [],
        **payload_dict,
    }
    merged_payload = normalize_tma_payload(merged_payload)
    merged_payload["updated_by"] = str(user_id)

    for k, v in merged_payload.items():
        setattr(row, k, v)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Errore aggiornamento TMA: {str(e)}")

    await db.refresh(row)
    return row


@router.delete(
    "/sites/{site_id}/records/{record_id}",
    status_code=204,
    summary="Delete TMA record",
    tags=["TMA"]
)
async def delete_tma_record(
    site_id: UUID,
    record_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = (await db.execute(
        select(TabellaMaterialiArcheologici).where(TabellaMaterialiArcheologici.id == record_id)
    )).scalar_one_or_none()

    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    await db.delete(row)
    await db.commit()
    return

