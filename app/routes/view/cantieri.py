"""
View Routes - Cantieri (Work Sites) Management
Routes HTML per gestione cantieri all'interno di siti archeologici.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from datetime import datetime, date

# Imports
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session
from app.models.cantiere import Cantiere
from app.models.sites import ArchaeologicalSite
from app.models.giornale_cantiere import GiornaleCantiere
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

# Import helper functions unificati
from app.services.view_helpers import (
    verify_site_access,
    normalize_site_id,
    get_base_template_context
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    # Handle both hyphenated and non-hyphenated UUID formats for compatibility
    site_id_str = str(site_id)
    site_info = next(
        (site for site in user_sites if
         site["site_id"] == site_id_str or
         site["site_id"].replace("-", "") == site_id_str.replace("-", "")
        ),
        None
    )
    
    if not site_info:
        # 🔍 DEBUG: Log the site_id and available sites for troubleshooting
        logger.error(f"🐛 [DEBUG] Site access failed - site_id: {site_id} (type: {type(site_id)})")
        logger.error(f"🐛 [DEBUG] Available site IDs: {[site['site_id'] for site in user_sites]}")
        logger.error(f"🐛 [DEBUG] Total user sites: {len(user_sites)}")
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato o access denied"
        )
    
    return site_info

@router.get("/sites/{site_id}/cantieri", response_class=HTMLResponse, summary="Pagina gestione cantieri sito", tags=["Cantieri - Views"])
async def v1_cantieri_sito_view(
    request: Request,
    site_id: UUID,
    search: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina principale per la gestione dei cantieri di un sito archeologico.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Query base per cantieri
        query = select(Cantiere).where(
            and_(Cantiere.site_id == str(site_id), Cantiere.is_active == True)
        )
        
        # Applica filtri
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Cantiere.nome.ilike(search_pattern),
                    Cantiere.codice.ilike(search_pattern),
                    Cantiere.descrizione.ilike(search_pattern),
                    # Campi aggiuntivi per ricerca
                    Cantiere.committente.ilike(search_pattern),
                    Cantiere.impresa_esecutrice.ilike(search_pattern),
                    Cantiere.direttore_lavori.ilike(search_pattern),
                    Cantiere.responsabile_procedimento.ilike(search_pattern),
                    Cantiere.oggetto_appalto.ilike(search_pattern),
                    Cantiere.codice_cup.ilike(search_pattern),
                    Cantiere.codice_cig.ilike(search_pattern)
                )
            )
        if stato:
            query = query.where(Cantiere.stato == stato)
        
        # Ordinamento
        query = query.order_by(
            Cantiere.priorita.asc(), Cantiere.created_at.desc()
        )
        
        result = await db.execute(query)
        cantieri = result.scalars().all()
        
        # Statistiche
        total_cantieri_result = await db.execute(
            select(func.count(Cantiere.id)).where(
                and_(
                    Cantiere.site_id == str(site_id),
                    Cantiere.is_active == True
                )
            )
        )
        total_cantieri = total_cantieri_result.scalar() or 0
        
        stati_result = await db.execute(
            select(
                Cantiere.stato,
                func.count(Cantiere.id).label("count")
            )
            .where(
                and_(
                    Cantiere.site_id == str(site_id),
                    Cantiere.is_active == True
                )
            )
            .group_by(Cantiere.stato)
        )
        stati = {stato: count for stato, count in stati_result.all()}
        
        # Opzioni per filtri
        stati_options = [
            {"value": "pianificato", "label": "Pianificato", "count": stati.get("pianificato", 0)},
            {"value": "in_corso", "label": "In Corso", "count": stati.get("in_corso", 0)},
            {"value": "completato", "label": "Completato", "count": stati.get("completato", 0)},
            {"value": "annullato", "label": "Annullato", "count": stati.get("annullato", 0)},
            {"value": "sospeso", "label": "Sospeso", "count": stati.get("sospeso", 0)}
        ]
        
        priorita_options = [
            {"value": 1, "label": "Alta", "color": "red"},
            {"value": 2, "label": "Media-Alta", "color": "orange"},
            {"value": 3, "label": "Media", "color": "yellow"},
            {"value": 4, "label": "Bassa", "color": "green"},
            {"value": 5, "label": "Molto Bassa", "color": "gray"}
        ]
        
        # Serialize cantieri data for Alpine.js
        cantieri_data = []
        for cantiere in cantieri:
            cantieri_data.append({
                "id": str(cantiere.id),
                "nome": cantiere.nome,
                "codice": cantiere.codice,
                "descrizione": cantiere.descrizione,
                # Campi per il giornale dei lavori
                "committente": cantiere.committente,
                "impresa_esecutrice": cantiere.impresa_esecutrice,
                "direttore_lavori": cantiere.direttore_lavori,
                "responsabile_procedimento": cantiere.responsabile_procedimento,
                "oggetto_appalto": cantiere.oggetto_appalto,
                # Campi opzionali
                "codice_cup": cantiere.codice_cup,
                "codice_cig": cantiere.codice_cig,
                "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None,
                # Campi temporali
                "stato": cantiere.stato,
                "stato_formattato": cantiere.stato_formattato,
                "data_inizio_prevista": cantiere.data_inizio_prevista.isoformat() if hasattr(cantiere.data_inizio_prevista, 'isoformat') else None,
                "data_fine_prevista": cantiere.data_fine_prevista.isoformat() if hasattr(cantiere.data_fine_prevista, 'isoformat') else None,
                "data_inizio_effettiva": cantiere.data_inizio_effettiva.isoformat() if hasattr(cantiere.data_inizio_effettiva, 'isoformat') else None,
                "data_fine_effettiva": cantiere.data_fine_effettiva.isoformat() if hasattr(cantiere.data_fine_effettiva, 'isoformat') else None,
                # Campi geografici
                "area_descrizione": cantiere.area_descrizione,
                "coordinate_lat": cantiere.coordinate_lat,
                "coordinate_lon": cantiere.coordinate_lon,
                "quota": cantiere.quota,
                # Metadati
                "responsabile_cantiere": cantiere.responsabile_cantiere,
                "tipologia_intervento": cantiere.tipologia_intervento,
                "priorita": cantiere.priorita,
                "e_in_corso": cantiere.e_in_corso,
                "durata_giorni": cantiere.durata_giorni,
                # Timestamp
                "created_at": cantiere.created_at.isoformat() if hasattr(cantiere.created_at, 'isoformat') else None,
                "updated_at": cantiere.updated_at.isoformat() if hasattr(cantiere.updated_at, 'isoformat') else None
            })

        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="cantieri"
        )
        context.update({
            "site_id": str(site_id),
            "site": site_info,  # Template expects 'site', not 'site_info'
            "site_info": site_info,
            "cantieri": cantieri_data,  # Pass serialized data
            "total_cantieri": total_cantieri,
            "stati": stati,
            "stati_options": stati_options,
            "priorita_options": priorita_options,
            "current_search": search,
            "current_stato": stato,
            # Add stats dict for template compatibility
            "stats": {
                "total": total_cantieri,
                "in_corso": stati.get("in_corso", 0),
                "pianificati": stati.get("pianificato", 0),
                "completati": stati.get("completato", 0)
            },
        })
        
        return templates.TemplateResponse(
            "pages/giornale_cantiere/cantieri.html", context
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina cantieri sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina cantieri"
        )

@router.get("/cantieri/{cantiere_id}", response_class=HTMLResponse, summary="Pagina dettaglio cantiere", tags=["Cantieri - Views"])
async def v1_cantiere_detail_view(
    request: Request,
    cantiere_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina di dettaglio per un cantiere specifico.
    """
    try:
        # Carica cantiere con relazioni
        result = await db.execute(
            select(Cantiere)
            .options(selectinload(Cantiere.site))
            .where(
                and_(Cantiere.id == str(cantiere_id), Cantiere.is_active == True)
            )
        )
        cantiere = result.scalar_one_or_none()

        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )

        # Verifica accesso al sito
        site_info = verify_site_access(cantiere.site_id, user_sites)

        # IMPORTANTE: Accedi alla relazione PRIMA di fare altre query async
        # Questo forza il caricamento mentre la sessione è ancora attiva
        site = cantiere.site
        
        # Se site è None, caricalo esplicitamente
        if not site:
            site_result = await db.execute(
                select(ArchaeologicalSite).where(ArchaeologicalSite.id == cantiere.site_id)
            )
            site = site_result.scalar_one_or_none()
        
        # Statistiche giornali di cantiere
        giornali_count_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                GiornaleCantiere.cantiere_id == str(cantiere_id)
            )
        )
        giornali_count = giornali_count_result.scalar() or 0
        
        # Ultimo giornale
        ultimo_giornale_result = await db.execute(
            select(GiornaleCantiere)
            .where(GiornaleCantiere.cantiere_id == str(cantiere_id))
            .order_by(GiornaleCantiere.data.desc())
            .limit(1)
        )
        ultimo_giornale = ultimo_giornale_result.scalar_one_or_none()
        
        operatori_count = 0
        
        # Serializza i dati del cantiere per evitare lazy loading nel template
        cantiere_data = {
            "id": str(cantiere.id),
            "nome": cantiere.nome,
            "codice": cantiere.codice,
            "descrizione": cantiere.descrizione,
            # Campi per il giornale dei lavori
            "committente": cantiere.committente,
            "impresa_esecutrice": cantiere.impresa_esecutrice,
            "direttore_lavori": cantiere.direttore_lavori,
            "responsabile_procedimento": cantiere.responsabile_procedimento,
            "oggetto_appalto": cantiere.oggetto_appalto,
            # Campi opzionali
            "codice_cup": cantiere.codice_cup,
            "codice_cig": cantiere.codice_cig,
            "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None,
            # Campi temporali
            "stato": cantiere.stato,
            "stato_formattato": cantiere.stato_formattato,
            "data_inizio_prevista": cantiere.data_inizio_prevista.isoformat() if hasattr(cantiere.data_inizio_prevista, 'isoformat') else None,
            "data_fine_prevista": cantiere.data_fine_prevista.isoformat() if hasattr(cantiere.data_fine_prevista, 'isoformat') else None,
            "data_inizio_effettiva": cantiere.data_inizio_effettiva.isoformat() if hasattr(cantiere.data_inizio_effettiva, 'isoformat') else None,
            "data_fine_effettiva": cantiere.data_fine_effettiva.isoformat() if hasattr(cantiere.data_fine_effettiva, 'isoformat') else None,
            # Campi geografici
            "area_descrizione": cantiere.area_descrizione,
            "coordinate_lat": cantiere.coordinate_lat,
            "coordinate_lon": cantiere.coordinate_lon,
            "quota": cantiere.quota,
            # Metadati
            "responsabile_cantiere": cantiere.responsabile_cantiere,
            "tipologia_intervento": cantiere.tipologia_intervento,
            "priorita": cantiere.priorita,
            "e_in_corso": cantiere.e_in_corso,
            "durata_giorni": cantiere.durata_giorni,
            # Timestamp
            "created_at": cantiere.created_at.isoformat() if hasattr(cantiere.created_at, 'isoformat') else None,
            "updated_at": cantiere.updated_at.isoformat() if hasattr(cantiere.updated_at, 'isoformat') else None,
        }
        
        # Serializza il sito
        site_data = {
            "id": str(site.id),
            "name": site.name,
            "codice": site.codice if hasattr(site, 'codice') else None,
        } if site else None
        
        # Serializza ultimo giornale se presente
        ultimo_giornale_data = None
        if ultimo_giornale:
            ultimo_giornale_data = {
                "id": str(ultimo_giornale.id),
                "data": ultimo_giornale.data.isoformat() if hasattr(ultimo_giornale.data, 'isoformat') else None,
                "condizioni_meteo": ultimo_giornale.condizioni_meteo if hasattr(ultimo_giornale, 'condizioni_meteo') else None,
            }
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="cantieri"
        )
        context.update({
            "cantiere": cantiere_data,  # Usa dati serializzati
            "site": site_data,           # Usa dati serializzati
            "site_info": site_info,
            "giornali_count": giornali_count,
            "ultimo_giornale": ultimo_giornale_data,  # Usa dati serializzati
            "operatori_count": operatori_count,
        })
        
        return templates.TemplateResponse(
            "pages/giornale_cantiere/cantiere_detail.html", context
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina dettaglio cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina dettaglio cantiere"
        )

@router.get("/sites/{site_id}/cantieri/nuovo", response_class=HTMLResponse, summary="Pagina nuovo cantiere", tags=["Cantieri - Views"])
async def v1_nuovo_cantiere_view(
    request: Request,
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina per la creazione di un nuovo cantiere.
    """
    try:
        # Verifica accesso al sito
        site_info = verify_site_access(site_id, user_sites)
        
        # Opzioni per il form
        stati_options = [
            {"value": "pianificato", "label": "Pianificato"},
            {"value": "in_corso", "label": "In Corso"},
            {"value": "completato", "label": "Completato"},
            {"value": "annullato", "label": "Annullato"},
            {"value": "sospeso", "label": "Sospeso"}
        ]
        
        priorita_options = [
            {"value": 1, "label": "Alta"},
            {"value": 2, "label": "Media-Alta"},
            {"value": 3, "label": "Media"},
            {"value": 4, "label": "Bassa"},
            {"value": 5, "label": "Molto Bassa"}
        ]
        
        tipologie_intervento = [
            {"value": "scavo", "label": "Scavo Archeologico"},
            {"value": "prospezione", "label": "Prospezione Geofisica"},
            {"value": "ricerca", "label": "Ricerca di Superficie"},
            {"value": "documentazione", "label": "Documentazione"},
            {"value": "conservazione", "label": "Conservazione e Restauro"},
            {"value": "monitoraggio", "label": "Monitoraggio"},
            {"value": "altro", "label": "Altro"}
        ]
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="cantieri"
        )
        context.update({
            "site_id": str(site_id),
            "site_info": site_info,
            "stati_options": stati_options,
            "priorita_options": priorita_options,
            "tipologie_intervento": tipologie_intervento,
        })
        
        return templates.TemplateResponse(
            "pages/giornale_cantiere/nuovo_cantiere.html", context
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina nuovo cantiere sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina nuovo cantiere"
        )

@router.get("/cantieri/{cantiere_id}/modifica", response_class=HTMLResponse, summary="Pagina modifica cantiere", tags=["Cantieri - Views"])
async def v1_modifica_cantiere_view(
    request: Request,
    cantiere_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina per la modifica di un cantiere esistente.
    """
    try:
        # Carica cantiere esistente
        result = await db.execute(
            select(Cantiere)
            .options(
                selectinload(Cantiere.site)
            )
            .where(
                and_(Cantiere.id == str(cantiere_id), Cantiere.is_active == True)
            )
        )
        cantiere = result.scalar_one_or_none()
        
        if not cantiere:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cantiere non trovato"
            )
        
        # Verifica accesso al sito
        site_info = verify_site_access(cantiere.site_id, user_sites)
        
        # Opzioni per il form
        stati_options = [
            {"value": "pianificato", "label": "Pianificato"},
            {"value": "in_corso", "label": "In Corso"},
            {"value": "completato", "label": "Completato"},
            {"value": "annullato", "label": "Annullato"},
            {"value": "sospeso", "label": "Sospeso"}
        ]
        
        priorita_options = [
            {"value": 1, "label": "Alta"},
            {"value": 2, "label": "Media-Alta"},
            {"value": 3, "label": "Media"},
            {"value": 4, "label": "Bassa"},
            {"value": 5, "label": "Molto Bassa"}
        ]
        
        tipologie_intervento = [
            {"value": "scavo", "label": "Scavo Archeologico"},
            {"value": "prospezione", "label": "Prospezione Geofisica"},
            {"value": "ricerca", "label": "Ricerca di Superficie"},
            {"value": "documentazione", "label": "Documentazione"},
            {"value": "conservazione", "label": "Conservazione e Restauro"},
            {"value": "monitoraggio", "label": "Monitoraggio"},
            {"value": "altro", "label": "Altro"}
        ]
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="cantieri"
        )
        context.update({
            "cantiere": cantiere,
            "site_info": site_info,
            "stati_options": stati_options,
            "priorita_options": priorita_options,
            "tipologie_intervento": tipologie_intervento,
        })
        
        return templates.TemplateResponse(
            "pages/giornale_cantiere/modifica_cantiere.html", context
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina modifica cantiere {cantiere_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina modifica cantiere"
        )