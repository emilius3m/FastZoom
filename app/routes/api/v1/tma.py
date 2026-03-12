from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.core.dependencies import get_database_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.tma import (
    SchedaTMA,
    TMAMateriale,
    TMAFotografia,
    TMACompilatore,
    TMAFunzionario,
    TMAMotivazioneCronologia,
)
from app.schemas.tma import SchedaTMACreate, SchedaTMAUpdate, SchedaTMARead


router = APIRouter()


async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    return any(s["site_id"] == str(site_id) for s in user_sites)


def serialize_scheda_tma(row: SchedaTMA) -> SchedaTMARead:
    payload = {
        "id": row.id,
        "site_id": row.site_id,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "tsk": row.tsk,
        "lir": row.lir,
        "nctr": row.nctr,
        "nctn": row.nctn,
        "esc": row.esc,
        "ecp": row.ecp,
        "ogtd": row.ogtd,
        "ogtm": row.ogtm,
        "pvcs": row.pvcs,
        "pvcr": row.pvcr,
        "pvcp": row.pvcp,
        "pvcc": row.pvcc,
        "ldct": row.ldct,
        "ldcn": row.ldcn,
        "ldcu": row.ldcu,
        "ldcs": row.ldcs,
        "altre_localizzazioni": row.altre_localizzazioni or [],
        "scan": row.scan,
        "dscf": row.dscf,
        "dsca": row.dsca,
        "dsct": row.dsct,
        "dscm": row.dscm,
        "dscd": row.dscd,
        "dscu": row.dscu,
        "dscn": row.dscn,
        "dtzg": row.dtzg,
        "dtm": [m.motivazione for m in (row.motivazioni_cronologia or [])],
        "nsc": row.nsc,
        "materiali": [
            {
                "id": item.id,
                "ordine": item.ordine,
                "macc": item.macc,
                "macl": item.macl,
                "macd": item.macd,
                "macp": item.macp,
                "macq": item.macq,
                "mas": item.mas,
            }
            for item in (row.materiali or [])
        ],
        "cdgg": row.cdgg,
        "fotografie": [
            {
                "id": foto.id,
                "ordine": foto.ordine,
                "ftax": foto.ftax,
                "ftap": foto.ftap,
                "ftan": foto.ftan,
                "file_path": foto.file_path,
            }
            for foto in (row.fotografie or [])
        ],
        "adsp": row.adsp,
        "adsm": row.adsm,
        "cmpd": row.cmpd,
        "cmpn": [c.nome for c in (row.compilatori or [])],
        "fur": [f.nome for f in (row.funzionari or [])],
    }
    return SchedaTMARead.model_validate(payload)


async def load_scheda_with_children(db: AsyncSession, record_id: str) -> Optional[SchedaTMA]:
    result = await db.execute(
        select(SchedaTMA)
        .options(
            selectinload(SchedaTMA.materiali),
            selectinload(SchedaTMA.fotografie),
            selectinload(SchedaTMA.compilatori),
            selectinload(SchedaTMA.funzionari),
            selectinload(SchedaTMA.motivazioni_cronologia),
        )
        .where(SchedaTMA.id == record_id)
    )
    return result.scalar_one_or_none()


@router.post(
    "/sites/{site_id}/records",
    response_model=SchedaTMARead,
    status_code=status.HTTP_201_CREATED,
    summary="Create TMA record",
    tags=["TMA"],
)
async def create_tma_record(
    site_id: UUID,
    payload: SchedaTMACreate,
    db: AsyncSession = Depends(get_database_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    payload_dict = payload.model_dump()
    materiali = payload_dict.pop("materiali", [])
    fotografie = payload_dict.pop("fotografie", [])
    motivazioni = payload_dict.pop("dtm", [])
    compilatori = payload_dict.pop("cmpn", [])
    funzionari = payload_dict.pop("fur", [])

    scheda = SchedaTMA(
        **payload_dict,
        site_id=str(site_id),
        created_by=str(user_id),
        updated_by=str(user_id),
    )
    db.add(scheda)

    try:
        await db.flush()

        for idx, item in enumerate(materiali):
            db.add(TMAMateriale(scheda_id=scheda.id, ordine=idx, **item))

        for idx, item in enumerate(fotografie):
            db.add(TMAFotografia(scheda_id=scheda.id, ordine=idx, **item))

        for idx, item in enumerate(motivazioni):
            db.add(TMAMotivazioneCronologia(scheda_id=scheda.id, ordine=idx, motivazione=item))

        for idx, item in enumerate(compilatori):
            db.add(TMACompilatore(scheda_id=scheda.id, ordine=idx, nome=item))

        for idx, item in enumerate(funzionari):
            db.add(TMAFunzionario(scheda_id=scheda.id, ordine=idx, nome=item))

        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Errore validazione/salvataggio TMA: {str(exc)}")

    stored = await load_scheda_with_children(db, scheda.id)
    if not stored:
        raise HTTPException(status_code=500, detail="Errore interno durante il caricamento della scheda")
    return serialize_scheda_tma(stored)


@router.get(
    "/sites/{site_id}/records",
    response_model=List[SchedaTMARead],
    summary="List TMA records",
    tags=["TMA"],
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

    query = (
        select(SchedaTMA)
        .options(
            selectinload(SchedaTMA.materiali),
            selectinload(SchedaTMA.fotografie),
            selectinload(SchedaTMA.compilatori),
            selectinload(SchedaTMA.funzionari),
            selectinload(SchedaTMA.motivazioni_cronologia),
        )
        .where(SchedaTMA.site_id == str(site_id))
    )

    if search:
        like = f"%{search}%"
        query = query.where(
            or_(
                SchedaTMA.nctr.ilike(like),
                SchedaTMA.nctn.ilike(like),
                SchedaTMA.ogtd.ilike(like),
                SchedaTMA.ogtm.ilike(like),
                SchedaTMA.pvcc.ilike(like),
            )
        )

    if nct:
        query = query.where(or_(SchedaTMA.nctr.ilike(f"%{nct}%"), SchedaTMA.nctn.ilike(f"%{nct}%")))

    if ogtd:
        query = query.where(SchedaTMA.ogtd.ilike(f"%{ogtd}%"))

    if pvcc:
        query = query.where(SchedaTMA.pvcc.ilike(f"%{pvcc}%"))

    if dtzg:
        query = query.where(SchedaTMA.dtzg.ilike(f"%{dtzg}%"))

    query = query.order_by(desc(SchedaTMA.created_at)).offset(skip).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    return [serialize_scheda_tma(row) for row in rows]


@router.get(
    "/sites/{site_id}/records/{record_id}",
    response_model=SchedaTMARead,
    summary="Get TMA record",
    tags=["TMA"],
)
async def get_tma_record(
    site_id: UUID,
    record_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = await load_scheda_with_children(db, record_id)
    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    return serialize_scheda_tma(row)


@router.put(
    "/sites/{site_id}/records/{record_id}",
    response_model=SchedaTMARead,
    summary="Update TMA record",
    tags=["TMA"],
)
async def update_tma_record(
    site_id: UUID,
    record_id: str,
    payload: SchedaTMAUpdate,
    db: AsyncSession = Depends(get_database_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = await load_scheda_with_children(db, record_id)
    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    payload_dict = payload.model_dump(exclude_unset=True)

    materiali = payload_dict.pop("materiali", None)
    fotografie = payload_dict.pop("fotografie", None)
    motivazioni = payload_dict.pop("dtm", None)
    compilatori = payload_dict.pop("cmpn", None)
    funzionari = payload_dict.pop("fur", None)

    for key, value in payload_dict.items():
        setattr(row, key, value)
    row.updated_by = str(user_id)

    if materiali is not None:
        row.materiali = [
            TMAMateriale(
                ordine=idx,
                macc=item["macc"],
                macl=item.get("macl"),
                macd=item.get("macd"),
                macp=item.get("macp"),
                macq=item["macq"],
                mas=item.get("mas"),
            )
            for idx, item in enumerate(materiali)
        ]

    if fotografie is not None:
        row.fotografie = [
            TMAFotografia(
                ordine=idx,
                ftax=item.get("ftax"),
                ftap=item.get("ftap"),
                ftan=item.get("ftan"),
                file_path=item.get("file_path"),
            )
            for idx, item in enumerate(fotografie)
        ]

    if motivazioni is not None:
        row.motivazioni_cronologia = [
            TMAMotivazioneCronologia(ordine=idx, motivazione=item)
            for idx, item in enumerate(motivazioni)
        ]

    if compilatori is not None:
        row.compilatori = [TMACompilatore(ordine=idx, nome=item) for idx, item in enumerate(compilatori)]

    if funzionari is not None:
        row.funzionari = [TMAFunzionario(ordine=idx, nome=item) for idx, item in enumerate(funzionari)]

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Errore aggiornamento TMA: {str(exc)}")

    stored = await load_scheda_with_children(db, record_id)
    if not stored:
        raise HTTPException(status_code=500, detail="Errore interno durante il caricamento della scheda")
    return serialize_scheda_tma(stored)


@router.delete(
    "/sites/{site_id}/records/{record_id}",
    status_code=204,
    summary="Delete TMA record",
    tags=["TMA"],
)
async def delete_tma_record(
    site_id: UUID,
    record_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = await load_scheda_with_children(db, record_id)
    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    await db.delete(row)
    await db.commit()
    return


# ===== EXPORT ENDPOINTS =====

@router.get(
    "/sites/{site_id}/records/{record_id}/export-pdf",
    summary="Export TMA record as PDF",
    tags=["TMA"],
)
async def export_tma_pdf(
    site_id: UUID,
    record_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    """Esporta una singola scheda TMA in formato PDF (ICCD 3.00)."""
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = await load_scheda_with_children(db, record_id)
    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    try:
        scheda_dict = serialize_scheda_tma(row).model_dump()
        from app.services.tma_export_service import generate_tma_pdf
        pdf_bytes = generate_tma_pdf(scheda_dict)

        nct = f"{row.nctr or ''}{row.nctn or ''}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"TMA_{nct}_{timestamp}.pdf"

        logger.info(f"✓ Export PDF TMA {record_id}: {filename} ({len(pdf_bytes)} bytes)")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        logger.error(f"Errore export PDF TMA {record_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore generazione PDF: {str(e)}")


@router.get(
    "/sites/{site_id}/records/{record_id}/export-word",
    summary="Export TMA record as Word",
    tags=["TMA"],
)
async def export_tma_word(
    site_id: UUID,
    record_id: str,
    db: AsyncSession = Depends(get_database_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
):
    """Esporta una singola scheda TMA in formato Word (.docx) conforme ICCD 3.00."""
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Accesso negato al sito")

    row = await load_scheda_with_children(db, record_id)
    if not row or row.site_id != str(site_id):
        raise HTTPException(status_code=404, detail="Record TMA non trovato")

    try:
        scheda_dict = serialize_scheda_tma(row).model_dump()
        from app.services.tma_export_service import generate_tma_word
        word_bytes = generate_tma_word(scheda_dict)

        nct = f"{row.nctr or ''}{row.nctn or ''}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"TMA_{nct}_{timestamp}.docx"

        logger.info(f"✓ Export Word TMA {record_id}: {filename} ({len(word_bytes)} bytes)")

        return Response(
            content=word_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(word_bytes)),
            },
        )
    except Exception as e:
        logger.error(f"Errore export Word TMA {record_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore generazione Word: {str(e)}")
