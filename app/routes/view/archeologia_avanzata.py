# app/routes/view/archeologia_avanzata.py
"""
View Routes per Archeologia Avanzata
Collegano i template HTML alle API REST
Gestiscono rendering delle pagine archeologiche
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_, desc
from sqlalchemy.orm import selectinload
from loguru import logger

# Import del sistema esistente FastZoom
from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import User

# Import modelli archeologia avanzata
from app.models.archeologia_avanzata import (
    UnitaStratigrafica, SchedaTomba, InventarioReperto, 
    MaterialeArcheologico, CampioneScientifico
)

# Template engine
templates = Jinja2Templates(directory="app/templates")

# Router per le view
router = APIRouter(prefix="/archeologia", tags=["archeologia-pages"])


# ===== HELPER FUNCTIONS =====

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica accesso utente al sito"""
    return any(site['id'] == str(site_id) for site in user_sites)


async def get_site_with_verification(
    site_id: UUID, 
    db: AsyncSession, 
    user_sites: List[Dict[str, Any]]
) -> ArchaeologicalSite:
    """Ottieni sito con verifica accesso"""
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accesso negato al sito {site_id}"
        )
    
    # Carica sito dal database
    result = await db.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    )
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato"
        )
    
    return site


# ===== DASHBOARD ARCHEOLOGIA =====

@router.get("/", response_class=HTMLResponse)
async def archeologia_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Dashboard principale archeologia avanzata"""
    try:
        # Carica siti accessibili
        accessible_sites = []
        for site_dict in user_sites:
            site_id = UUID(site_dict['id'])
            result = await db.execute(
                select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
            )
            site = result.scalar_one_or_none()
            if site:
                accessible_sites.append(site)
        
        # Prepara context
        context = {
            "request": request,
            "title": "Archeologia Avanzata - FastZoom",
            "sites": accessible_sites,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/dashboard.html", context)
        
    except Exception as e:
        logger.error(f"Errore dashboard archeologia: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della dashboard"
        )


# ===== UNITÀ STRATIGRAFICHE =====

@router.get("/us/site/{site_id}", response_class=HTMLResponse)
async def us_list(
    site_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista Unità Stratigrafiche per sito"""
    try:
        # Verifica accesso e ottieni sito
        site = await get_site_with_verification(site_id, db, user_sites)
        
        # Statistiche base (per header)
        us_count = await db.execute(
            select(func.count(UnitaStratigrafica.id))
            .where(UnitaStratigrafica.site_id == site_id)
        )
        total_us = us_count.scalar()
        
        # Context per template
        context = {
            "request": request,
            "title": f"Unità Stratigrafiche - {site.name}",
            "site": site,
            "total_us": total_us,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/us_list.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista US sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento delle US"
        )


@router.get("/us/{us_id}", response_class=HTMLResponse)
async def us_detail(
    us_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Dettaglio Unità Stratigrafica"""
    try:
        # Carica US con relazioni
        us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id).options(
            selectinload(UnitaStratigrafica.site),
            selectinload(UnitaStratigrafica.us_superiori),
            selectinload(UnitaStratigrafica.us_inferiori),
            selectinload(UnitaStratigrafica.reperti),
            selectinload(UnitaStratigrafica.campioni)
        )
        
        result = await db.execute(us_query)
        us = result.scalar_one_or_none()
        
        if not us:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"US {us_id} non trovata"
            )
        
        # Verifica accesso al sito
        if not await verify_site_access(us.site_id, user_sites):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito della US"
            )
        
        # Context per template
        context = {
            "request": request,
            "title": f"{us.numero_us} - {us.site.name}",
            "us": us,
            "site": us.site,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/us_detail.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore dettaglio US {us_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della US"
        )


# ===== TOMBE =====

@router.get("/tombe/site/{site_id}", response_class=HTMLResponse)
async def tombe_list(
    site_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista Tombe per sito"""
    try:
        # Verifica accesso e ottieni sito
        site = await get_site_with_verification(site_id, db, user_sites)
        
        # Statistiche base
        tombe_count = await db.execute(
            select(func.count(SchedaTomba.id))
            .where(SchedaTomba.site_id == site_id)
        )
        total_tombe = tombe_count.scalar()
        
        # Statistiche per rito sepolcrale
        inumazioni_count = await db.execute(
            select(func.count(SchedaTomba.id))
            .where(and_(
                SchedaTomba.site_id == site_id,
                SchedaTomba.rito_sepolcrale == 'inumazione'
            ))
        )
        inumazioni = inumazioni_count.scalar()
        
        incinerazioni_count = await db.execute(
            select(func.count(SchedaTomba.id))
            .where(and_(
                SchedaTomba.site_id == site_id,
                SchedaTomba.rito_sepolcrale == 'incinerazione'
            ))
        )
        incinerazioni = incinerazioni_count.scalar()
        
        # Tombe con corredo
        con_corredo_count = await db.execute(
            select(func.count(SchedaTomba.id))
            .where(and_(
                SchedaTomba.site_id == site_id,
                SchedaTomba.presenza_corredo == True
            ))
        )
        con_corredo = con_corredo_count.scalar()
        
        # Context per template
        context = {
            "request": request,
            "title": f"Tombe - {site.name}",
            "site": site,
            "stats": {
                "total": total_tombe,
                "inumazioni": inumazioni,
                "incinerazioni": incinerazioni,
                "con_corredo": con_corredo
            },
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/tombe_list.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista tombe sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento delle tombe"
        )


@router.get("/tombe/{tomba_id}", response_class=HTMLResponse)
async def tomba_detail(
    tomba_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Dettaglio Tomba"""
    try:
        # Carica tomba con relazioni
        tomba_query = select(SchedaTomba).where(SchedaTomba.id == tomba_id).options(
            selectinload(SchedaTomba.site),
            selectinload(SchedaTomba.us_taglio),
            selectinload(SchedaTomba.us_riempimento)
        )
        
        result = await db.execute(tomba_query)
        tomba = result.scalar_one_or_none()
        
        if not tomba:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tomba {tomba_id} non trovata"
            )
        
        # Verifica accesso al sito
        if not await verify_site_access(tomba.site_id, user_sites):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito della tomba"
            )
        
        # Carica reperti associati (corredo)
        reperti_query = select(InventarioReperto).where(
            InventarioReperto.tomba_id == tomba_id
        ).options(selectinload(InventarioReperto.unita_stratigrafica))
        
        reperti_result = await db.execute(reperti_query)
        reperti_corredo = reperti_result.scalars().all()
        
        # Context per template
        context = {
            "request": request,
            "title": f"{tomba.numero_tomba} - {tomba.site.name}",
            "tomba": tomba,
            "site": tomba.site,
            "reperti_corredo": reperti_corredo,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/tomba_detail.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore dettaglio tomba {tomba_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della tomba"
        )


# ===== REPERTI =====

@router.get("/reperti/site/{site_id}", response_class=HTMLResponse)
async def reperti_list(
    site_id: UUID,
    request: Request,
    tomba_id: Optional[UUID] = Query(None, alias="tomba"),
    us_id: Optional[UUID] = Query(None, alias="us"),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista Reperti per sito (con filtri opzionali)"""
    try:
        # Verifica accesso e ottieni sito
        site = await get_site_with_verification(site_id, db, user_sites)
        
        # Statistiche base
        reperti_count = await db.execute(
            select(func.count(InventarioReperto.id))
            .where(InventarioReperto.site_id == site_id)
        )
        total_reperti = reperti_count.scalar()
        
        # Statistiche per categoria materiale
        ceramica_count = await db.execute(
            select(func.count(InventarioReperto.id))
            .where(and_(
                InventarioReperto.site_id == site_id,
                InventarioReperto.categoria_materiale == 'ceramica'
            ))
        )
        ceramica = ceramica_count.scalar()
        
        metallo_count = await db.execute(
            select(func.count(InventarioReperto.id))
            .where(and_(
                InventarioReperto.site_id == site_id,
                InventarioReperto.categoria_materiale == 'metallo'
            ))
        )
        metallo = metallo_count.scalar()
        
        vetro_count = await db.execute(
            select(func.count(InventarioReperto.id))
            .where(and_(
                InventarioReperto.site_id == site_id,
                InventarioReperto.categoria_materiale == 'vetro'
            ))
        )
        vetro = vetro_count.scalar()
        
        # Alta rilevanza
        alta_rilevanza_count = await db.execute(
            select(func.count(InventarioReperto.id))
            .where(and_(
                InventarioReperto.site_id == site_id,
                InventarioReperto.rilevanza_scientifica == 'alta'
            ))
        )
        alta_rilevanza = alta_rilevanza_count.scalar()
        
        # Carica liste casse per filtri
        casse_result = await db.execute(
            select(InventarioReperto.numero_cassa)
            .where(and_(
                InventarioReperto.site_id == site_id,
                InventarioReperto.numero_cassa.isnot(None)
            ))
            .distinct()
        )
        casse_disponibili = [row[0] for row in casse_result.fetchall() if row[0]]
        
        # Context specifico se filtrato per tomba o US
        filter_info = {}
        if tomba_id:
            tomba_result = await db.execute(
                select(SchedaTomba).where(SchedaTomba.id == tomba_id)
            )
            tomba = tomba_result.scalar_one_or_none()
            if tomba:
                filter_info = {"type": "tomba", "object": tomba}
                
        if us_id:
            us_result = await db.execute(
                select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id)
            )
            us = us_result.scalar_one_or_none()
            if us:
                filter_info = {"type": "us", "object": us}
        
        # Context per template
        context = {
            "request": request,
            "title": f"Reperti - {site.name}",
            "site": site,
            "stats": {
                "total": total_reperti,
                "ceramica": ceramica,
                "metallo": metallo,
                "vetro": vetro,
                "alta_rilevanza": alta_rilevanza,
                "pubblicati": 0  # TODO: implementare campo
            },
            "casse_disponibili": casse_disponibili,
            "filter_info": filter_info,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/reperti_list.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista reperti sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento dei reperti"
        )


@router.get("/reperti/{reperto_id}", response_class=HTMLResponse)
async def reperto_detail(
    reperto_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Dettaglio Reperto"""
    try:
        # Carica reperto con relazioni
        reperto_query = select(InventarioReperto).where(
            InventarioReperto.id == reperto_id
        ).options(
            selectinload(InventarioReperto.site),
            selectinload(InventarioReperto.unita_stratigrafica),
            selectinload(InventarioReperto.tomba)
        )
        
        result = await db.execute(reperto_query)
        reperto = result.scalar_one_or_none()
        
        if not reperto:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reperto {reperto_id} non trovato"
            )
        
        # Verifica accesso al sito
        if not await verify_site_access(reperto.site_id, user_sites):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito del reperto"
            )
        
        # Context per template
        context = {
            "request": request,
            "title": f"{reperto.numero_inventario} - {reperto.site.name}",
            "reperto": reperto,
            "site": reperto.site,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/reperto_detail.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore dettaglio reperto {reperto_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento del reperto"
        )


# ===== CAMPIONI SCIENTIFICI =====

@router.get("/campioni/site/{site_id}", response_class=HTMLResponse)
async def campioni_list(
    site_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Lista Campioni scientifici per sito"""
    try:
        # Verifica accesso e ottieni sito
        site = await get_site_with_verification(site_id, db, user_sites)
        
        # Statistiche base
        campioni_count = await db.execute(
            select(func.count(CampioneScientifico.id))
            .where(CampioneScientifico.site_id == site_id)
        )
        total_campioni = campioni_count.scalar()
        
        # Statistiche per tipo campione
        c14_count = await db.execute(
            select(func.count(CampioneScientifico.id))
            .where(and_(
                CampioneScientifico.site_id == site_id,
                CampioneScientifico.tipo_campione == 'carbonio_14'
            ))
        )
        carbonio_14 = c14_count.scalar()
        
        paleobotanici_count = await db.execute(
            select(func.count(CampioneScientifico.id))
            .where(and_(
                CampioneScientifico.site_id == site_id,
                CampioneScientifico.tipo_campione == 'paleobotanico'
            ))
        )
        paleobotanici = paleobotanici_count.scalar()
        
        # Campioni analizzati (con risultati)
        analizzati_count = await db.execute(
            select(func.count(CampioneScientifico.id))
            .where(and_(
                CampioneScientifico.site_id == site_id,
                CampioneScientifico.data_risultati.isnot(None)
            ))
        )
        analizzati = analizzati_count.scalar()
        
        # Laboratori coinvolti
        laboratori_result = await db.execute(
            select(CampioneScientifico.laboratorio_analisi)
            .where(and_(
                CampioneScientifico.site_id == site_id,
                CampioneScientifico.laboratorio_analisi.isnot(None)
            ))
            .distinct()
        )
        laboratori = [row[0] for row in laboratori_result.fetchall() if row[0]]
        
        # Context per template
        context = {
            "request": request,
            "title": f"Campioni Scientifici - {site.name}",
            "site": site,
            "stats": {
                "total": total_campioni,
                "carbonio_14": carbonio_14,
                "paleobotanici": paleobotanici,
                "analizzati": analizzati,
                "in_attesa": total_campioni - analizzati
            },
            "laboratori": laboratori,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/campioni_list.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore lista campioni sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento dei campioni"
        )


@router.get("/campioni/{campione_id}", response_class=HTMLResponse)
async def campione_detail(
    campione_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Dettaglio Campione scientifico"""
    try:
        # Carica campione con relazioni
        campione_query = select(CampioneScientifico).where(
            CampioneScientifico.id == campione_id
        ).options(
            selectinload(CampioneScientifico.site),
            selectinload(CampioneScientifico.unita_stratigrafica),
            selectinload(CampioneScientifico.tomba)
        )
        
        result = await db.execute(campione_query)
        campione = result.scalar_one_or_none()
        
        if not campione:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campione {campione_id} non trovato"
            )
        
        # Verifica accesso al sito
        if not await verify_site_access(campione.site_id, user_sites):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso negato al sito del campione"
            )
        
        # Context per template
        context = {
            "request": request,
            "title": f"{campione.numero_campione} - {campione.site.name}",
            "campione": campione,
            "site": campione.site,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/campione_detail.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore dettaglio campione {campione_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento del campione"
        )


# ===== MATRIX HARRIS =====

@router.get("/matrix-harris/site/{site_id}", response_class=HTMLResponse)
async def matrix_harris(
    site_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Visualizzazione Matrix Harris per sito"""
    try:
        # Verifica accesso e ottieni sito
        site = await get_site_with_verification(site_id, db, user_sites)
        
        # Context per template
        context = {
            "request": request,
            "title": f"Matrix Harris - {site.name}",
            "site": site,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/matrix_harris.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore Matrix Harris sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della Matrix Harris"
        )


# ===== REPORTS E UTILITY =====

@router.get("/reports/site/{site_id}", response_class=HTMLResponse)
async def reports_archeologia(
    site_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Report e statistiche archeologiche per sito"""
    try:
        # Verifica accesso e ottieni sito
        site = await get_site_with_verification(site_id, db, user_sites)
        
        # Raccogli statistiche complete
        us_count = await db.execute(
            select(func.count(UnitaStratigrafica.id))
            .where(UnitaStratigrafica.site_id == site_id)
        )
        
        tombe_count = await db.execute(
            select(func.count(SchedaTomba.id))
            .where(SchedaTomba.site_id == site_id)
        )
        
        reperti_count = await db.execute(
            select(func.count(InventarioReperto.id))
            .where(InventarioReperto.site_id == site_id)
        )
        
        campioni_count = await db.execute(
            select(func.count(CampioneScientifico.id))
            .where(CampioneScientifico.site_id == site_id)
        )
        
        # Statistiche per periodo (se disponibili)
        periodi_result = await db.execute(
            select(UnitaStratigrafica.periodo, func.count(UnitaStratigrafica.id))
            .where(and_(
                UnitaStratigrafica.site_id == site_id,
                UnitaStratigrafica.periodo.isnot(None)
            ))
            .group_by(UnitaStratigrafica.periodo)
        )
        periodi_stats = dict(periodi_result.fetchall())
        
        # Context per template
        context = {
            "request": request,
            "title": f"Report Archeologici - {site.name}",
            "site": site,
            "stats": {
                "us_total": us_count.scalar(),
                "tombe_total": tombe_count.scalar(),
                "reperti_total": reperti_count.scalar(),
                "campioni_total": campioni_count.scalar()
            },
            "periodi_stats": periodi_stats,
            "current_user_id": current_user_id
        }
        
        return templates.TemplateResponse("pages/archeologia/reports.html.old", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore reports sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento dei report"
        )


# ===== MODAL E UTILITY ROUTES =====

@router.get("/reference-data", response_class=HTMLResponse)
async def get_reference_data(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist)
):
    """Endpoint per ottenere dati di riferimento (enum, lookup tables)"""
    try:
        from app.models.archeologia_avanzata import (
            TipoUS, TipoTomba, TipoMateriale, TipoCampione, 
            StatoConservazione, RitoSepolcrale
        )
        
        reference_data = {
            "tipi_us": [{"value": t.value, "label": t.value.replace("_", " ").title()} for t in TipoUS],
            "tipi_tomba": [{"value": t.value, "label": t.value.replace("_", " ").title()} for t in TipoTomba],
            "riti_sepolcrali": [{"value": r.value, "label": r.value.replace("_", " ").title()} for r in RitoSepolcrale],
            "tipi_materiale": [{"value": m.value, "label": m.value.replace("_", " ").title()} for m in TipoMateriale],
            "tipi_campione": [{"value": c.value, "label": c.value.replace("_", " ").title()} for c in TipoCampione],
            "stati_conservazione": [{"value": s.value, "label": s.value.replace("_", " ").title()} for s in StatoConservazione]
        }
        
        return reference_data
        
    except Exception as e:
        logger.error(f"Errore reference data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel recupero dei dati di riferimento"
        )