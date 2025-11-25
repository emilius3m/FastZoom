# app/routes/view/giornale_cantiere.py
"""
View Routes HTML per il Giornale di Cantiere Archeologico
Pagine web con template Jinja2 e Alpine.js per interfaccia utente
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from loguru import logger

# Import del sistema esistente
from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.models.sites import ArchaeologicalSite
from app.models import User
from app.models.user_profiles import UserProfile
from app.models.giornale_cantiere import GiornaleCantiere, OperatoreCantiere, CondizioniMeteoEnum
from app.templates import templates
from app.core.csrf_settings import _csrf_tokens_optional

# Import helper functions unificati
from app.services.view_helpers import (
    get_current_user_with_profile,
    verify_site_access,
    normalize_site_id,
    get_base_template_context
)

# Router per le view HTML
router = APIRouter(prefix="/giornale-cantiere", tags=["giornale-cantiere-pages"])





@router.get("/site/{site_id}/entry/{giornale_id}", response_class=HTMLResponse)
async def giornale_cantiere_detail(
    site_id: UUID,
    giornale_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina dettaglio di una voce specifica del giornale di cantiere
    """
    try:
        # Verifica accesso al sito - Handle both hyphenated and non-hyphenated UUID formats
        site_id_str = str(site_id)
        site_info = next(
            (site for site in user_sites if
             site["site_id"] == site_id_str or
             site["site_id"].replace("-", "") == site_id_str.replace("-", "")
            ),
            None
        )
        
        if not site_info:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Ottieni giornale con tutte le relazioni - Handle UUID format inconsistencies
        site_id_str = str(site_id)
        giornale_id_str = str(giornale_id)
        giornale_result = await db.execute(
            select(GiornaleCantiere)
            .where(
                and_(
                    (GiornaleCantiere.id == giornale_id_str) |
                    (GiornaleCantiere.id == giornale_id_str.replace('-', '')),
                    (GiornaleCantiere.site_id == site_id_str) |
                    (GiornaleCantiere.site_id == site_id_str.replace('-', ''))
                )
            )
            .options(
                selectinload(GiornaleCantiere.site),
                selectinload(GiornaleCantiere.responsabile),
                selectinload(GiornaleCantiere.operatori)
            )
        )
        giornale = giornale_result.scalar_one_or_none()
        
        if not giornale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Giornale {giornale_id} non trovato per il sito {site_id}"
            )
        
        # Ottieni informazioni utente corrente
        user = await get_current_user_with_profile(current_user_id, db)
        
        # Verifica permessi di modifica
        can_edit = (
            str(giornale.responsabile_id) == str(current_user_id) and not giornale.validato
        ) or (user and user.is_superuser)

        can_validate = (
            str(giornale.responsabile_id) == str(current_user_id) and not giornale.validato
        )
        
        can_delete = user and user.is_superuser and not giornale.validato
        
        # CSRF token
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, giornale.site, current_page="giornale_cantiere"
        )
        context.update({
            "title": f"Giornale {giornale.data.strftime('%d/%m/%Y')} - {giornale.site.name} | Sistema Archeologico",
            "site_info": site_info,
            "giornale": giornale,
            "permissions": {
                "can_edit": can_edit,
                "can_validate": can_validate,
                "can_delete": can_delete
            },
            "csrf_token": csrf_token
        })
        
        response = templates.TemplateResponse("pages/giornale_cantiere/detail.html", context)
        
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore dettaglio giornale {giornale_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento del dettaglio"
        )


@router.get("/operatori", response_class=HTMLResponse)
async def operatori_management(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina gestione operatori - Reindirizza alla home per selezionare un sito
    """
    try:
        # Ottieni informazioni utente
        user = await get_current_user_with_profile(current_user_id, db)
        
        # Se l'utente ha accesso a un solo sito, reindirizza direttamente alla pagina operatori del sito
        if len(user_sites) == 1:
            site_id = user_sites[0]['site_id']
            return RedirectResponse(url=f"/giornale-cantiere/site/{site_id}/operatori", status_code=302)
        
        # Altrimenti, reindirizza alla home per selezionare un sito
        return RedirectResponse(url="/giornale-cantiere", status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore reindirizzamento operatori: {str(e)}")
        return RedirectResponse(url="/giornale-cantiere", status_code=302)
    

@router.get("/site/{site_id}/operatori", response_class=HTMLResponse)
async def site_operatori_view(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Visualizza gli operatori specifici per un sito archeologico
    URL RESTful: /giornale-cantiere/site/{site_id}/operatori
    """
    try:
        # Verifica accesso al sito - Handle both hyphenated and non-hyphenated UUID formats
        site_id_str = str(site_id)
        site_info = next(
            (site for site in user_sites if
             site["site_id"] == site_id_str or
             site["site_id"].replace("-", "") == site_id_str.replace("-", "")
            ),
            None
        )
        
        if not site_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sito {site_id} non trovato o access denied"
            )
        
        # Ottieni informazioni utente
        user = await get_current_user_with_profile(current_user_id, db)
        
        # Ottieni profilo utente
        user_profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == current_user_id)
        )
        user_profile = user_profile_result.scalar_one_or_none()
        
        # CSRF opzionale
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        # Prepare context for template
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="giornale-operatori"
        )
        context.update({
            "title": f"Gestione Operatori - {site_info['site_name']} | Sistema Archeologico",
            "message": f"Operatori del sito: {site_info['site_name']}",
            
            # Site-specific context
            "site_id": str(site_id),
            "site": site_info,
            "site_info": site_info,
            "site_name": site_info["site_name"],
            "site_code": site_info.get("code", ""),
            "site_location": site_info.get("location", ""),
            
            "user_profile": user_profile,
            "csrf_token": csrf_token,
            
            # Flag to indicate this is site-specific operator view
            "is_site_specific": True
        })
        
        logger.info(f"Site operatori view rendered: user_id={current_user_id}, site_id={site_id}, site_name={site_info['site_name']}")
        response = templates.TemplateResponse("pages/giornale_cantiere/operatori.html", context)
        
        # Se CSRF disponibile, imposta cookie firmato
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Site operatori view error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore interno visualizzazione operatori sito"
        )


@router.get("/reports", response_class=HTMLResponse)
async def giornale_reports(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina report e statistiche giornali di cantiere
    """
    try:
        # Ottieni informazioni utente
        user = await get_current_user_with_profile(current_user_id, db)
        
        # Statistiche generali per tutti i siti accessibili - Handle UUID format inconsistencies
        site_ids = []
        for site in user_sites:
            try:
                site_ids.append(UUID(site['site_id']))
            except:
                # Skip invalid UUIDs but continue processing other sites
                logger.warning(f"Invalid UUID format for site {site.get('site_id')}: {site['site_id']}")
                continue
        
        if site_ids:
            # Statistiche totali
            total_result = await db.execute(
                select(func.count(GiornaleCantiere.id))
                .where(GiornaleCantiere.site_id.in_(site_ids))
            )
            total_giornali = total_result.scalar() or 0
            
            validated_result = await db.execute(
                select(func.count(GiornaleCantiere.id))
                .where(
                    and_(
                        GiornaleCantiere.site_id.in_(site_ids),
                        GiornaleCantiere.validato == True
                    )
                )
            )
            validated_giornali = validated_result.scalar() or 0
            
            # Statistiche per condizioni meteo
            meteo_stats = []
            for condition in CondizioniMeteoEnum:
                count_result = await db.execute(
                    select(func.count(GiornaleCantiere.id))
                    .where(
                        and_(
                            GiornaleCantiere.site_id.in_(site_ids),
                            GiornaleCantiere.condizioni_meteo == condition.value
                        )
                    )
                )
                count = count_result.scalar() or 0
                meteo_stats.append({
                    "condition": condition.value.replace("_", " ").title(),
                    "count": count,
                    "percentage": round((count / total_giornali * 100) if total_giornali > 0 else 0, 1)
                })
            
        else:
            total_giornali = 0
            validated_giornali = 0
            meteo_stats = []
        
        # CSRF token
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="giornale_cantiere"
        )
        context.update({
            "title": "Report Giornali di Cantiere | Sistema Archeologico",
            "stats": {
                "total_giornali": total_giornali,
                "validated_giornali": validated_giornali,
                "pending_giornali": total_giornali - validated_giornali,
                "validation_percentage": round((validated_giornali / total_giornali * 100) if total_giornali > 0 else 0, 1)
            },
            "meteo_stats": meteo_stats,
            "csrf_token": csrf_token
        })
        
        response = templates.TemplateResponse("pages/giornale_cantiere/reports.html", context)
        
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento dei report"
        )