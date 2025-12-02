"""
View Routes per Harris Matrix Editor
FastZoom Archaeological Site Management System

Implementa i template HTML per l'editor grafico delle Matrici di Harris.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from uuid import UUID
from loguru import logger

# Dependencies
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist
)
from app.database.db import get_async_session
from app.templates import templates

# Import helper functions unificati
from app.services.view_helpers import (
    get_current_user_with_profile,
    verify_site_access,
    get_site_with_verification,
    get_base_template_context,
    normalize_site_id
)

# Router initialization
harris_matrix_view_router = APIRouter(tags=["Harris Matrix - Views"], prefix="/sites")


# ============================================================================
# HARRIS MATRIX EDITOR
# ============================================================================

@harris_matrix_view_router.get("/{site_id}/harris-matrix/editor", 
                              response_class=HTMLResponse, 
                              name="harris_matrix_editor")
async def harris_matrix_editor(
    request: Request,
    site_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Editor grafico per la Matrix Harris.
    Alpine.js gestisce tutte le chiamate alle API v1 lato client.
    """
    try:
        # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.warning(f"Invalid site_id format: {site_id}")
            raise HTTPException(status_code=404, detail="ID sito non valido")

        # Converti a UUID per le funzioni helper
        try:
            site_uuid = UUID(normalized_site_id)
        except ValueError:
            logger.error(f"Site ID normalization failed: {site_id} -> {normalized_site_id}")
            raise HTTPException(status_code=404, detail="ID sito non valido")

        # Verifica accesso al sito e ottieni sito
        site = await get_site_with_verification(site_uuid, db, user_sites)

        # Get current user information
        current_user = await get_current_user_with_profile(current_user_id, db)
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, site, current_page="harris_matrix"
        )
        
        context.update({
            "page_title": f"Editor Matrix Harris - {site.name}",
            "site_id": normalized_site_id,
            "breadcrumb": [
                {"label": "Home", "url": "/"},
                {"label": "Siti", "url": "/sites"},
                {"label": site.name, "url": f"/sites/{normalized_site_id}"},
                {"label": "Matrix Harris", "url": f"/sites/{normalized_site_id}/harris-matrix", "active": True},
                {"label": "Editor", "url": f"/sites/{normalized_site_id}/harris-matrix/editor", "active": True}
            ],
            # API endpoints disponibili per l'editor
            "api_endpoints": {
                "matrix_data": f"/api/v1/harris-matrix/{normalized_site_id}",
                "save_matrix": f"/api/v1/harris-matrix/{normalized_site_id}",
                "elements": f"/api/v1/harris-matrix/{normalized_site_id}/elements",
                "periodization": f"/api/v1/harris-matrix/{normalized_site_id}/periodization",
                "validation": f"/api/v1/harris-matrix/{normalized_site_id}/validate",
                "export": f"/api/v1/harris-matrix/{normalized_site_id}/export",
                "import": f"/api/v1/harris-matrix/{normalized_site_id}/import"
            },
            # Configurazione specifica dell'editor
            "editor_config": {
                "enable_elk_layout": True,
                "enable_grid_snap": True,
                "default_layout": "tree",
                "auto_save_interval": 30000,  # 30 secondi
                "max_undo_steps": 50
            }
        })

        logger.debug(f"User {current_user.email if current_user else current_user_id} accessing Harris Matrix editor for site {normalized_site_id}")

        return templates.TemplateResponse("pages/us/harris_matrix_editor.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore accesso editor Matrix Harris sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento dell'editor Matrix Harris"
        )


# ============================================================================
# HARRIS MATRIX VIEWER (opzionale - per visualizzazione sola lettura)
# ============================================================================

@harris_matrix_view_router.get("/{site_id}/harris-matrix", 
                              response_class=HTMLResponse, 
                              name="harris_matrix_viewer")
async def harris_matrix_viewer(
    request: Request,
    site_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Visualizzazione Matrix Harris (sola lettura).
    """
    try:
        # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.warning(f"Invalid site_id format: {site_id}")
            raise HTTPException(status_code=404, detail="ID sito non valido")

        # Converti a UUID per le funzioni helper
        try:
            site_uuid = UUID(normalized_site_id)
        except ValueError:
            logger.error(f"Site ID normalization failed: {site_id} -> {normalized_site_id}")
            raise HTTPException(status_code=404, detail="ID sito non valido")

        # Verifica accesso al sito e ottieni sito
        site = await get_site_with_verification(site_uuid, db, user_sites)

        # Get current user information
        current_user = await get_current_user_with_profile(current_user_id, db)
        
        # Prepara context base
        context = await get_base_template_context(
            request, current_user_id, user_sites, db, site, current_page="harris_matrix"
        )
        
        context.update({
            "page_title": f"Matrix Harris - {site.name}",
            "site_id": normalized_site_id,
            "breadcrumb": [
                {"label": "Home", "url": "/"},
                {"label": "Siti", "url": "/sites"},
                {"label": site.name, "url": f"/sites/{normalized_site_id}"},
                {"label": "Matrix Harris", "url": f"/sites/{normalized_site_id}/harris-matrix", "active": True}
            ],
            # API endpoints disponibili per il viewer
            "api_endpoints": {
                "matrix_data": f"/api/v1/harris-matrix/{normalized_site_id}",
                "export": f"/api/v1/harris-matrix/{normalized_site_id}/export"
            },
            # Configurazione specifica del viewer (sola lettura)
            "viewer_config": {
                "read_only": True,
                "enable_zoom": True,
                "enable_pan": True,
                "default_layout": "hierarchical"
            }
        })

        logger.debug(f"User {current_user.email if current_user else current_user_id} accessing Harris Matrix viewer for site {normalized_site_id}")

        return templates.TemplateResponse("pages/us/harris_matrix_viewer.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore accesso viewer Matrix Harris sito {site_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore nel caricamento della Matrix Harris"
        )