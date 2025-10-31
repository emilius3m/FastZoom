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

# Router per le view HTML
router = APIRouter(prefix="/giornale-cantiere", tags=["giornale-cantiere-pages"])


@router.get("/", response_class=HTMLResponse)
async def giornale_cantiere_home(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina principale giornale di cantiere con selezione sito
    """
    try:
        if not user_sites:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nessun sito archeologico accessibile"
            )
        
        # Ottieni informazioni utente
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        
        # Statistiche generali per tutti i siti
        total_giornali = 0
        total_validated = 0
        
        for site in user_sites:
            site_id = UUID(site['id'])
            
            # Conteggio giornali per sito
            count_result = await db.execute(
                select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == site_id)
            )
            site_giornali = count_result.scalar() or 0
            
            validated_result = await db.execute(
                select(func.count(GiornaleCantiere.id)).where(
                    and_(
                        GiornaleCantiere.site_id == site_id,
                        GiornaleCantiere.validato == True
                    )
                )
            )
            site_validated = validated_result.scalar() or 0
            
            # Aggiungi ai totali
            total_giornali += site_giornali
            total_validated += site_validated
            
            # Aggiungi statistiche al sito
            site['giornali_count'] = site_giornali
            site['validated_count'] = site_validated
            site['pending_count'] = site_giornali - site_validated
        
        # CSRF token
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        context = {
            "request": request,
            "title": "Giornale di Cantiere | Sistema Archeologico",
            "current_page": "giornale_cantiere",
            "user": user,
            "current_user": user,  # Add current_user for profile modal
            "sites": user_sites,
            "sites_count": len(user_sites),
            "total_giornali": total_giornali,
            "total_validated": total_validated,
            "csrf_token": csrf_token
        }
        
        response = templates.TemplateResponse("pages/giornale_cantiere/home.html", context)
        
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina home giornale cantiere: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina"
        )


@router.get("/site/{site_id}", response_class=HTMLResponse)
async def giornale_cantiere_site(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina giornale di cantiere per un sito specifico
    """
    try:
        # Verifica accesso al sito
        site_info = next(
            (site for site in user_sites if site["id"] == str(site_id)),
            None
        )
        
        if not site_info:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Ottieni dettagli sito dal database
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sito {site_id} non trovato"
            )
        
        # Ottieni informazioni utente
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        
        # Carica operatori attivi per il form
        operatori_result = await db.execute(
            select(OperatoreCantiere)
            .where(OperatoreCantiere.is_active == True)
            .order_by(OperatoreCantiere.cognome, OperatoreCantiere.nome)
        )
        operatori = operatori_result.scalars().all()
        
        # Statistiche del sito
        stats_total = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == site_id)
        )
        total_giornali = stats_total.scalar() or 0
        
        stats_validated = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                and_(GiornaleCantiere.site_id == site_id, GiornaleCantiere.validato == True)
            )
        )
        validated_giornali = stats_validated.scalar() or 0
        
        # Ultimo giornale
        last_result = await db.execute(
            select(GiornaleCantiere.data)
            .where(GiornaleCantiere.site_id == site_id)
            .order_by(GiornaleCantiere.data.desc())
            .limit(1)
        )
        last_date = last_result.scalar_one_or_none()
        
        # Condizioni meteo disponibili
        condizioni_meteo = [
            {"value": condition.value, "label": condition.value.replace("_", " ").title()}
            for condition in CondizioniMeteoEnum
        ]
        
        # CSRF token
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        context = {
            "request": request,
            "title": f"Giornale di Cantiere - {site.name} | Sistema Archeologico",
            "current_page": "giornale_cantiere",
            "user": user,
            "current_user": user,  # Add current_user for profile modal
            "site": site,
            "site_info": site_info,
            "sites": user_sites,
            "operatori": [
                {
                    "id": str(op.id),
                    "nome_completo": op.nome_completo,
                    "qualifica": op.qualifica
                }
                for op in operatori
            ],
            "condizioni_meteo": condizioni_meteo,
            "stats": {
                "total_giornali": total_giornali,
                "validated_giornali": validated_giornali,
                "pending_giornali": total_giornali - validated_giornali,
                "last_date": last_date.isoformat() if last_date else None,
                "validation_percentage": round((validated_giornali / total_giornali * 100) if total_giornali > 0 else 0, 1)
            },
            "csrf_token": csrf_token
        }
        
        response = templates.TemplateResponse("pages/giornale_cantiere/site.html", context)
        
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina giornale cantiere sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina del sito"
        )


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
        # Verifica accesso al sito
        site_info = next(
            (site for site in user_sites if site["id"] == str(site_id)),
            None
        )
        
        if not site_info:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}"
            )
        
        # Ottieni giornale con tutte le relazioni
        giornale_result = await db.execute(
            select(GiornaleCantiere)
            .where(
                and_(
                    GiornaleCantiere.id == giornale_id,
                    GiornaleCantiere.site_id == site_id
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
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        
        # Verifica permessi di modifica
        can_edit = (
            giornale.responsabile_id == current_user_id and not giornale.validato
        ) or (user and user.is_superuser)
        
        can_validate = (
            giornale.responsabile_id == current_user_id and not giornale.validato
        )
        
        can_delete = user and user.is_superuser and not giornale.validato
        
        # CSRF token
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        context = {
            "request": request,
            "title": f"Giornale {giornale.data.strftime('%d/%m/%Y')} - {giornale.site.name} | Sistema Archeologico",
            "current_page": "giornale_cantiere",
            "user": user,
            "current_user": user,  # Add current_user for profile modal
            "site": giornale.site,
            "site_info": site_info,
            "sites": user_sites,
            "giornale": giornale,
            "permissions": {
                "can_edit": can_edit,
                "can_validate": can_validate,
                "can_delete": can_delete
            },
            "csrf_token": csrf_token
        }
        
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
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        
        # Se l'utente ha accesso a un solo sito, reindirizza direttamente alla pagina operatori del sito
        if len(user_sites) == 1:
            site_id = user_sites[0]['id']
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
        # Verifica accesso al sito
        site_info = next(
            (site for site in user_sites if site["id"] == str(site_id)),
            None
        )
        
        if not site_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sito {site_id} non trovato o access denied"
            )
        
        # Ottieni informazioni utente
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        
        # Ottieni profilo utente
        user_profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == current_user_id)
        )
        user_profile = user_profile_result.scalar_one_or_none()
        
        # CSRF opzionale
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()
        
        # Prepare context for template
        context = {
            "request": request,
            "title": f"Gestione Operatori - {site_info['name']} | Sistema Archeologico",
            "message": f"Operatori del sito: {site_info['name']}",
            
            # Site-specific context
            "site_id": str(site_id),
            "site": site_info,
            "site_info": site_info,
            "site_name": site_info["name"],
            "site_code": site_info.get("code", ""),
            "site_location": site_info.get("location", ""),
            
            # User context
            "user_email": user.email if user else None,
            "user_type": "superuser" if user and user.is_superuser else "user",
            "current_user": user,  # Already included but ensuring consistency
            "user_profile": user_profile,
            "csrf_token": csrf_token,
            
            # Navigation context
            "current_page": "giornale-operatori",
            "current_site_name": site_info["name"],
            "sites": user_sites,
            "sites_count": len(user_sites),
            
            # Flag to indicate this is site-specific operator view
            "is_site_specific": True
        }
        
        logger.info(f"Site operatori view rendered: user_id={current_user_id}, site_id={site_id}, site_name={site_info['name']}")
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
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        user = user_result.scalar_one_or_none()
        
        # Statistiche generali per tutti i siti accessibili
        site_ids = [UUID(site['id']) for site in user_sites]
        
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
        
        context = {
            "request": request,
            "title": "Report Giornali di Cantiere | Sistema Archeologico",
            "current_page": "giornale_cantiere",
            "user": user,
            "current_user": user,  # Add current_user for profile modal
            "sites": user_sites,
            "stats": {
                "total_giornali": total_giornali,
                "validated_giornali": validated_giornali,
                "pending_giornali": total_giornali - validated_giornali,
                "validation_percentage": round((validated_giornali / total_giornali * 100) if total_giornali > 0 else 0, 1)
            },
            "meteo_stats": meteo_stats,
            "csrf_token": csrf_token
        }
        
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