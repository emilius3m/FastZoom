# app/routes/view/redirect.py - Route per gestire URL con prefisso /view/

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse
from uuid import UUID
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from loguru import logger

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.templates import templates
from app.models.cantiere import Cantiere
from app.models.giornale_cantiere import GiornaleCantiere
from app.services.view_helpers import get_base_template_context

router = APIRouter(prefix="/view", tags=["View Routes"])


@router.get("/{site_id}/giornale", response_class=HTMLResponse)
async def view_site_giornale(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Pagina giornale di cantiere per un sito specifico
    URL: /view/{site_id}/giornale
    """
    try:
        # Verifica accesso al sito
        site_id_str = str(site_id)
        site_info = next(
            (site for site in user_sites if
             site["site_id"] == site_id_str or
             site["site_id"].replace("-", "") == site_id_str.replace("-", "")),
            None
        )
        
        if not site_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sito {site_id} non trovato o accesso negato"
            )
        
        # Ottieni statistiche cantieri
        cantieri_result = await db.execute(
            select(Cantiere).where(Cantiere.site_id == site_id_str)
        )
        cantieri = cantieri_result.scalars().all()
        
        # Serializza cantieri
        cantieri_data = []
        for c in cantieri:
            # Conta giornali per ogni cantiere
            giornali_count_result = await db.execute(
                select(func.count(GiornaleCantiere.id)).where(
                    GiornaleCantiere.cantiere_id == c.id
                )
            )
            giornali_count = giornali_count_result.scalar() or 0
            
            cantieri_data.append({
                "id": str(c.id),
                "nome": c.nome,
                "codice": c.codice,
                "stato": c.stato if isinstance(c.stato, str) else str(c.stato) if c.stato else "attivo",
                "data_inizio": c.data_inizio_effettiva.isoformat() if c.data_inizio_effettiva else None,
                "data_fine": c.data_fine_effettiva.isoformat() if c.data_fine_effettiva else None,
                "giornali_count": giornali_count
            })
        
        # Statistiche generali
        stats = {
            "total_cantieri": len(cantieri_data),
            "attivi": sum(1 for c in cantieri_data if c["stato"] == "attivo"),
            "completati": sum(1 for c in cantieri_data if c["stato"] == "completato"),
            "sospesi": sum(1 for c in cantieri_data if c["stato"] == "sospeso")
        }
        
        # Context
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, current_page="giornale"
        )
        context.update({
            "title": f"Giornale di Cantiere - {site_info['site_name']}",
            "site_id": site_id_str,
            "site": site_info,
            "site_info": site_info,
            "cantieri": cantieri_data,
            "stats": stats
        })
        
        return templates.TemplateResponse(
            "pages/giornale_cantiere/cantieri.html", context
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore pagina giornale sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della pagina"
        )
