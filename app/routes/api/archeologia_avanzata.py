# app/routes/api/archeologia_avanzata.py
"""
API Routes per Archeologia Avanzata
Gestisce US, Tombe, Reperti, Campioni scientifici
CRUD completo con controllo accessi multi-sito
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_, desc
from sqlalchemy.orm import selectinload
from loguru import logger

# Import del sistema esistente
from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import User

# Import modelli archeologia avanzata
from app.models.archeologia_avanzata import (
    UnitaStratigrafica, SchedaTomba, InventarioReperto, 
    MaterialeArcheologico, CampioneScientifico,
    TipoUS, TipoTomba, TipoMateriale, TipoCampione, StatoConservazione
)

# Import schemi Pydantic (da creare dopo)
from app.schemas.archeologia_avanzata import (
    UnitaStratigrafica_Create, UnitaStratigrafica_Update, UnitaStratigrafica_Out,
    SchedaTomba_Create, SchedaTomba_Update, SchedaTomba_Out,
    InventarioReperto_Create, InventarioReperto_Update, InventarioReperto_Out,
    CampioneScientifico_Create, CampioneScientifico_Update, CampioneScientifico_Out,
    MaterialeArcheologico_Create, MaterialeArcheologico_Out,
    USFilter, TombaFilter, RepertoFilter, CampioneFilter
)

router = APIRouter(prefix="/api/archeologia", tags=["archeologia-avanzata"])


# ===== GESTIONE UNITÀ STRATIGRAFICHE =====

@router.post("/us", response_model=UnitaStratigrafica_Out, status_code=status.HTTP_201_CREATED)
async def create_unita_stratigrafica(
    us: UnitaStratigrafica_Create,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Crea una nuova Unità Stratigrafica"""
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(us.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {us.site_id}"
            )
        
        # Verifica che il numero US non sia già utilizzato nel sito
        existing_us = await db.execute(
            select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == us.site_id,
                    UnitaStratigrafica.numero_us == us.numero_us
                )
            )
        )
        if existing_us.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"US {us.numero_us} già esistente per questo sito"
            )
        
        # Crea US
        db_us = UnitaStratigrafica(**us.model_dump())
        
        db.add(db_us)
        await db.commit()
        await db.refresh(db_us, ['site'])
        
        logger.info(f"US {us.numero_us} creata per sito {us.site_id} da user {current_user_id}")
        return db_us
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore creazione US: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione della US: {str(e)}"
        )


@router.get("/us/site/{site_id}", response_model=List[UnitaStratigrafica_Out])
async def list_us_by_site(
    site_id: UUID,
    filters: USFilter = Depends(),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista US per sito con filtri avanzati"""
    try:
        # Verifica accesso
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Query base
        query = select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == site_id)
        
        # Applica filtri
        if filters.tipo_us:
            query = query.where(UnitaStratigrafica.tipo_us == filters.tipo_us)
        
        if filters.fase:
            query = query.where(UnitaStratigrafica.fase == filters.fase)
        
        if filters.periodo:
            query = query.where(UnitaStratigrafica.periodo.ilike(f"%{filters.periodo}%"))
        
        if filters.data_scavo_da:
            query = query.where(UnitaStratigrafica.data_scavo >= filters.data_scavo_da)
        
        if filters.data_scavo_a:
            query = query.where(UnitaStratigrafica.data_scavo <= filters.data_scavo_a)
        
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    UnitaStratigrafica.numero_us.ilike(search_pattern),
                    UnitaStratigrafica.descrizione.ilike(search_pattern),
                    UnitaStratigrafica.interpretazione.ilike(search_pattern)
                )
            )
        
        # Include relazioni
        query = query.options(selectinload(UnitaStratigrafica.site))
        
        # Ordinamento e paginazione
        query = query.order_by(UnitaStratigrafica.numero_us).offset(skip).limit(limit)
        
        result = await db.execute(query)
        us_list = result.scalars().all()
        
        logger.info(f"Lista US sito {site_id}: {len(us_list)} trovate")
        return us_list
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista US sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero delle US"
        )


@router.get("/us/{us_id}", response_model=UnitaStratigrafica_Out)
async def get_unita_stratigrafica(
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni dettagli US con relazioni stratigrafiche"""
    try:
        # Query con relazioni
        query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id).options(
            selectinload(UnitaStratigrafica.site),
            selectinload(UnitaStratigrafica.us_superiori),
            selectinload(UnitaStratigrafica.us_inferiori),
            selectinload(UnitaStratigrafica.reperti),
            selectinload(UnitaStratigrafica.campioni)
        )
        
        result = await db.execute(query)
        us = result.scalar_one_or_none()
        
        if not us:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"US {us_id} non trovata"
            )
        
        # Verifica accesso al sito
        site_access = any(site['id'] == str(us.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito della US"
            )
        
        return us
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore get US {us_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero della US"
        )


# ===== GESTIONE MATRIX HARRIS =====

@router.post("/us/{us_id}/relations/{target_us_id}")
async def create_harris_relation(
    us_id: UUID,
    target_us_id: UUID,
    relation_type: str = Query(..., pattern="^(copre|taglia|riempie|è_contemporaneo_a)$"),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Crea relazione stratigrafica tra due US (Matrix Harris)"""
    try:
        # Verifica che entrambe le US esistano e siano nello stesso sito
        us1 = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id))
        us1 = us1.scalar_one_or_none()
        
        us2 = await db.execute(select(UnitaStratigrafica).where(UnitaStratigrafica.id == target_us_id))
        us2 = us2.scalar_one_or_none()
        
        if not us1 or not us2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Una o entrambe le US non trovate"
            )
        
        if us1.site_id != us2.site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le US devono essere dello stesso sito"
            )
        
        # Verifica accesso al sito
        site_access = any(site['id'] == str(us1.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito delle US"
            )
        
        # Crea la relazione stratigrafica
        from app.models.archeologia_avanzata import matrix_harris_relations
        
        # Verifica che la relazione non esista già
        existing = await db.execute(
            select(matrix_harris_relations).where(
                and_(
                    matrix_harris_relations.c.us_superiore_id == us_id,
                    matrix_harris_relations.c.us_inferiore_id == target_us_id,
                    matrix_harris_relations.c.tipo_relazione == relation_type
                )
            )
        )
        
        if existing.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Relazione {relation_type} già esistente tra {us1.numero_us} e {us2.numero_us}"
            )
        
        # Inserisci relazione
        await db.execute(
            matrix_harris_relations.insert().values(
                us_superiore_id=us_id,
                us_inferiore_id=target_us_id,
                tipo_relazione=relation_type
            )
        )
        
        await db.commit()
        
        logger.info(f"Relazione Matrix Harris creata: {us1.numero_us} {relation_type} {us2.numero_us}")
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": f"Relazione creata: {us1.numero_us} {relation_type} {us2.numero_us}",
                "us_superiore": us1.numero_us,
                "us_inferiore": us2.numero_us,
                "tipo_relazione": relation_type
            }
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore creazione relazione Harris: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione della relazione: {str(e)}"
        )


@router.get("/matrix-harris/site/{site_id}")
async def get_matrix_harris(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni Matrix Harris completa per un sito"""
    try:
        # Verifica accesso
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Ottieni tutte le US del sito
        us_result = await db.execute(
            select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == site_id).order_by(UnitaStratigrafica.numero_us)
        )
        us_list = us_result.scalars().all()
        
        # Ottieni tutte le relazioni stratigrafiche
        from app.models.archeologia_avanzata import matrix_harris_relations
        
        relations_result = await db.execute(
            select(matrix_harris_relations).join(
                UnitaStratigrafica, 
                matrix_harris_relations.c.us_superiore_id == UnitaStratigrafica.id
            ).where(UnitaStratigrafica.site_id == site_id)
        )
        relations = relations_result.fetchall()
        
        # Formatta per visualizzazione
        nodes = [
            {
                "id": str(us.id),
                "numero_us": us.numero_us,
                "tipo_us": us.tipo_us,
                "descrizione": us.descrizione[:100] + "..." if us.descrizione and len(us.descrizione) > 100 else us.descrizione,
                "interpretazione": us.interpretazione,
                "fase": us.fase,
                "periodo": us.periodo
            }
            for us in us_list
        ]
        
        edges = [
            {
                "source": str(rel.us_superiore_id),
                "target": str(rel.us_inferiore_id),
                "relation_type": rel.tipo_relazione,
                "created_at": rel.created_at.isoformat() if rel.created_at else None
            }
            for rel in relations
        ]
        
        return {
            "site_id": str(site_id),
            "nodes": nodes,
            "edges": edges,
            "total_us": len(nodes),
            "total_relations": len(edges)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore Matrix Harris sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero della Matrix Harris"
        )


# ===== GESTIONE TOMBE =====

@router.post("/tombe", response_model=SchedaTomba_Out, status_code=status.HTTP_201_CREATED)
async def create_scheda_tomba(
    tomba: SchedaTomba_Create,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Crea una nuova scheda tomba"""
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(tomba.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {tomba.site_id}"
            )
        
        # Verifica che il numero tomba non sia già utilizzato
        existing = await db.execute(
            select(SchedaTomba).where(
                and_(
                    SchedaTomba.site_id == tomba.site_id,
                    SchedaTomba.numero_tomba == tomba.numero_tomba
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tomba {tomba.numero_tomba} già esistente per questo sito"
            )
        
        # Crea tomba
        db_tomba = SchedaTomba(**tomba.model_dump())
        
        db.add(db_tomba)
        await db.commit()
        await db.refresh(db_tomba, ['site', 'us_taglio', 'us_riempimento'])
        
        logger.info(f"Tomba {tomba.numero_tomba} creata per sito {tomba.site_id}")
        return db_tomba
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore creazione tomba: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione della tomba: {str(e)}"
        )


@router.get("/tombe/site/{site_id}", response_model=List[SchedaTomba_Out])
async def list_tombe_by_site(
    site_id: UUID,
    filters: TombaFilter = Depends(),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista tombe per sito con filtri"""
    try:
        # Verifica accesso
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Query con filtri
        query = select(SchedaTomba).where(SchedaTomba.site_id == site_id)
        
        if filters.tipo_tomba:
            query = query.where(SchedaTomba.tipo_tomba == filters.tipo_tomba)
        
        if filters.rito_sepolcrale:
            query = query.where(SchedaTomba.rito_sepolcrale == filters.rito_sepolcrale)
        
        if filters.presenza_corredo is not None:
            query = query.where(SchedaTomba.presenza_corredo == filters.presenza_corredo)
        
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    SchedaTomba.numero_tomba.ilike(search_pattern),
                    SchedaTomba.interpretazione.ilike(search_pattern)
                )
            )
        
        # Include relazioni
        query = query.options(
            selectinload(SchedaTomba.site),
            selectinload(SchedaTomba.us_taglio),
            selectinload(SchedaTomba.us_riempimento)
        )
        
        # Ordinamento e paginazione
        query = query.order_by(SchedaTomba.numero_tomba).offset(skip).limit(limit)
        
        result = await db.execute(query)
        tombe = result.scalars().all()
        
        logger.info(f"Lista tombe sito {site_id}: {len(tombe)} trovate")
        return tombe
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista tombe sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero delle tombe"
        )


# ===== GESTIONE INVENTARIO REPERTI =====

@router.post("/reperti", response_model=InventarioReperto_Out, status_code=status.HTTP_201_CREATED)
async def create_reperto(
    reperto: InventarioReperto_Create,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Crea nuovo reperto in inventario"""
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(reperto.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {reperto.site_id}"
            )
        
        # Verifica unicità numero inventario
        existing = await db.execute(
            select(InventarioReperto).where(
                InventarioReperto.numero_inventario == reperto.numero_inventario
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Numero inventario {reperto.numero_inventario} già esistente"
            )
        
        # Ottieni informazioni utente per catalogatore
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        catalogatore = user.email if user else "Utente sconosciuto"
        
        # Crea reperto
        reperto_data = reperto.model_dump()
        db_reperto = InventarioReperto(
            **reperto_data,
            catalogatore=catalogatore
        )
        
        db.add(db_reperto)
        await db.commit()
        await db.refresh(db_reperto, ['site', 'unita_stratigrafica', 'tomba'])
        
        logger.info(f"Reperto {reperto.numero_inventario} creato per sito {reperto.site_id}")
        return db_reperto
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore creazione reperto: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione del reperto: {str(e)}"
        )


@router.get("/reperti/site/{site_id}", response_model=List[InventarioReperto_Out])
async def list_reperti_by_site(
    site_id: UUID,
    filters: RepertoFilter = Depends(),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista reperti per sito con filtri avanzati"""
    try:
        # Verifica accesso
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Query con filtri
        query = select(InventarioReperto).where(InventarioReperto.site_id == site_id)
        
        if filters.categoria_materiale:
            query = query.where(InventarioReperto.categoria_materiale == filters.categoria_materiale)
        
        if filters.stato_conservazione:
            query = query.where(InventarioReperto.stato_conservazione == filters.stato_conservazione)
        
        if filters.numero_cassa:
            query = query.where(InventarioReperto.numero_cassa == filters.numero_cassa)
        
        if filters.rilevanza_scientifica:
            query = query.where(InventarioReperto.rilevanza_scientifica == filters.rilevanza_scientifica)
        
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    InventarioReperto.numero_inventario.ilike(search_pattern),
                    InventarioReperto.descrizione_breve.ilike(search_pattern),
                    InventarioReperto.tipo.ilike(search_pattern)
                )
            )
        
        # Include relazioni
        query = query.options(
            selectinload(InventarioReperto.site),
            selectinload(InventarioReperto.unita_stratigrafica),
            selectinload(InventarioReperto.tomba)
        )
        
        # Ordinamento e paginazione
        query = query.order_by(InventarioReperto.numero_inventario).offset(skip).limit(limit)
        
        result = await db.execute(query)
        reperti = result.scalars().all()
        
        logger.info(f"Lista reperti sito {site_id}: {len(reperti)} trovati")
        return reperti
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista reperti sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei reperti"
        )


# ===== GESTIONE CAMPIONI SCIENTIFICI =====

@router.post("/campioni", response_model=CampioneScientifico_Out, status_code=status.HTTP_201_CREATED)
async def create_campione(
    campione: CampioneScientifico_Create,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Crea nuovo campione scientifico"""
    try:
        # Verifica accesso al sito
        site_access = any(site['id'] == str(campione.site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {campione.site_id}"
            )
        
        # Verifica unicità numero campione
        existing = await db.execute(
            select(CampioneScientifico).where(
                CampioneScientifico.numero_campione == campione.numero_campione
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Numero campione {campione.numero_campione} già esistente"
            )
        
        # Ottieni informazioni utente per responsabile prelievo
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        responsabile_prelievo = user.email if user else "Utente sconosciuto"
        
        # Crea campione
        campione_data = campione.model_dump()
        db_campione = CampioneScientifico(
            **campione_data,
            responsabile_prelievo=responsabile_prelievo
        )
        
        db.add(db_campione)
        await db.commit()
        await db.refresh(db_campione, ['site', 'unita_stratigrafica', 'tomba'])
        
        logger.info(f"Campione {campione.numero_campione} creato per sito {campione.site_id}")
        return db_campione
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Errore creazione campione: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella creazione del campione: {str(e)}"
        )


# ===== STATISTICHE E UTILITY =====

@router.get("/stats/site/{site_id}")
async def get_archeologia_stats(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Statistiche archeologia per un sito"""
    try:
        # Verifica accesso
        site_access = any(site['id'] == str(site_id) for site in user_sites)
        if not site_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Conteggi
        us_count = await db.execute(
            select(func.count(UnitaStratigrafica.id)).where(UnitaStratigrafica.site_id == site_id)
        )
        us_total = us_count.scalar()
        
        tombe_count = await db.execute(
            select(func.count(SchedaTomba.id)).where(SchedaTomba.site_id == site_id)
        )
        tombe_total = tombe_count.scalar()
        
        reperti_count = await db.execute(
            select(func.count(InventarioReperto.id)).where(InventarioReperto.site_id == site_id)
        )
        reperti_total = reperti_count.scalar()
        
        campioni_count = await db.execute(
            select(func.count(CampioneScientifico.id)).where(CampioneScientifico.site_id == site_id)
        )
        campioni_total = campioni_count.scalar()
        
        return {
            "site_id": str(site_id),
            "us_total": us_total,
            "tombe_total": tombe_total,
            "reperti_total": reperti_total,
            "campioni_total": campioni_total,
            "documenti_totali": us_total + tombe_total + reperti_total + campioni_total
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore stats archeologia sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero delle statistiche"
        )


# ===== ENUM E REFERENCE DATA =====

@router.get("/reference/tipo-us")
async def get_tipi_us():
    """Elenco tipologie US disponibili"""
    return {
        "tipi_us": [
            {"value": tipo.value, "label": tipo.value.replace("_", " ").title()}
            for tipo in TipoUS
        ]
    }


@router.get("/reference/tipo-tombe")
async def get_tipi_tombe():
    """Elenco tipologie tombe disponibili"""
    return {
        "tipi_tombe": [
            {"value": tipo.value, "label": tipo.value.replace("_", " ").title()}
            for tipo in TipoTomba
        ]
    }


@router.get("/reference/materiali")
async def get_tipi_materiali():
    """Elenco categorie materiali disponibili"""
    return {
        "tipi_materiali": [
            {"value": tipo.value, "label": tipo.value.replace("_", " ").title()}
            for tipo in TipoMateriale
        ]
    }


@router.get("/reference/campioni")
async def get_tipi_campioni():
    """Elenco tipologie campioni disponibili"""
    return {
        "tipi_campioni": [
            {"value": tipo.value, "label": tipo.value.replace("_", " ").title()}
            for tipo in TipoCampione
        ]
    }


@router.get("/reference/stati-conservazione")
async def get_stati_conservazione():
    """Elenco stati di conservazione disponibili"""
    return {
        "stati_conservazione": [
            {"value": stato.value, "label": stato.value.replace("_", " ").title()}
            for stato in StatoConservazione
        ]
    }