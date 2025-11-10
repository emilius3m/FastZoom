"""
Admin View Routes - HTML Templates with Alpine.js
FastZoom Archaeological Site Management System

Nuova implementazione che serve solo template HTML statici.
Alpine.js gestisce tutte le chiamate alle API v1 lato client.

NO httpx - Pure FastAPI view routes returning HTML.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
from app.models import User

# Router initialization
admin_view_router = APIRouter(tags=["Admin - Views"], prefix="/admin")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_admin_template_context(
    request: Request,
    current_user_id: UUID,
    user_sites: List[Dict[str, Any]],
    db: AsyncSession
) -> dict:
    """
    Crea il context base per tutti i template admin.
    Contiene informazioni utente e configurazione menu.
    """

    # Ottieni informazioni utente completa
    user = await db.execute(select(User).where(User.id == current_user_id))
    user = user.scalar_one_or_none()

    if not user:
        logger.warning(f"User {current_user_id} not found in database")

    # Sito virtuale per il pannello amministrazione (per il menu laterale)
    admin_site = {
        "id": "admin",
        "name": "Pannello Amministrazione",
        "location": "Sistema",
        "permission_level": "admin",
        "is_active": True
    }

    # Context da passare ai template
    context = {
        "request": request,
        "sites": user_sites or [],
        "sites_count": len(user_sites) if user_sites else 0,
        "user_email": user.email if user else "Unknown",
        "user_name": user.full_name if user and hasattr(user, 'full_name') else user.email if user else "Admin",
        "user_type": "superuser" if user and user.is_superuser else "user",
        "is_superuser": user.is_superuser if user else False,
        "current_site_name": user_sites[0]["name"] if user_sites else "Amministrazione",
        "current_page": request.url.path.split("/")[-1] or "admin",
        "site": admin_site,  # Per attivare il menu laterale
        "first_site": user_sites[0] if user_sites else admin_site,
    }

    return context


async def require_superuser(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
) -> tuple:
    """
    Middleware per verificare che l'utente sia superuser.
    Ritorna una tupla (user, context) per le route.
    """

    user = await db.execute(select(User).where(User.id == current_user_id))
    user = user.scalar_one_or_none()

    if not user or not user.is_superuser:
        logger.warning(
            f"Access denied for user {current_user_id}: "
            f"is_superuser={user.is_superuser if user else False}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso negato: solo i superadmin possono accedere a questa sezione"
        )

    context = await get_admin_template_context(request, current_user_id, user_sites, db)

    logger.debug(f"Superuser {user.email} accessing admin area")

    return user, context


# ============================================================================
# GESTIONE SITI ARCHEOLOGICI
# ============================================================================

@admin_view_router.get("/sites", response_class=HTMLResponse, name="admin_sites_list")
async def admin_sites_list(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Pagina lista siti archeologici.
    Alpine.js carica i dati tramite API GET /api/v1/admin/sites
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Gestione Siti Archeologici",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Siti", "url": "/admin/sites", "active": True}
        ]
    }

    logger.debug(f"Loading admin sites list for {superuser.email}")

    return templates.TemplateResponse("admin/sites_list.html", context)


@admin_view_router.get("/sites/new", response_class=HTMLResponse, name="admin_sites_new")
async def admin_sites_new(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Form per creare un nuovo sito archeologico.
    Template: admin_sites_form.html con action='create'
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Nuovo Sito Archeologico",
        "action": "create",
        "site": None,
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Siti", "url": "/admin/sites"},
            {"label": "Nuovo", "url": "/admin/sites/new", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} accessing new site form")

    return templates.TemplateResponse("admin/sites_form.html", context)


@admin_view_router.get("/sites/{site_id}/edit", response_class=HTMLResponse, name="admin_sites_edit")
async def admin_sites_edit(
    request: Request,
    site_id: str,
    authdata: tuple = Depends(require_superuser)
):
    """
    Form per modificare un sito archeologico.
    Alpine.js carica i dati tramite API GET /api/v1/admin/sites/{site_id}
    Template: admin_sites_form.html con action='edit'
    """
    superuser, base_context = authdata

    # Validazione UUID
    try:
        UUID(site_id)
    except ValueError:
        logger.warning(f"Invalid site_id format: {site_id}")
        raise HTTPException(status_code=404, detail="ID sito non valido")

    context = {
        **base_context,
        "page_title": "Modifica Sito Archeologico",
        "site_id": site_id,
        "action": "edit",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Siti", "url": "/admin/sites"},
            {"label": "Modifica", "url": f"/admin/sites/{site_id}/edit", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} editing site {site_id}")

    return templates.TemplateResponse("admin/sites_form.html", context)


@admin_view_router.get("/sites/{site_id}/users", response_class=HTMLResponse, name="admin_site_users")
async def admin_site_users(
    request: Request,
    site_id: str,
    authdata: tuple = Depends(require_superuser)
):
    """
    Gestione utenti associati a un sito specifico.
    Alpine.js carica i dati tramite API GET /api/v1/admin/sites/{site_id}/users
    """
    superuser, base_context = authdata

    # Validazione UUID
    try:
        UUID(site_id)
    except ValueError:
        logger.warning(f"Invalid site_id format: {site_id}")
        raise HTTPException(status_code=404, detail="ID sito non valido")

    context = {
        **base_context,
        "page_title": "Gestione Utenti del Sito",
        "site_id": site_id,
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Siti", "url": "/admin/sites"},
            {"label": "Utenti", "url": f"/admin/sites/{site_id}/users", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} managing users for site {site_id}")

    return templates.TemplateResponse("admin/site_users.html", context)


# ============================================================================
# GESTIONE UTENTI
# ============================================================================

@admin_view_router.get("/users", response_class=HTMLResponse, name="admin_users_list")
async def admin_users_list(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Pagina lista utenti sistema.
    Alpine.js carica i dati tramite API GET /api/v1/admin/users
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Gestione Utenti",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Utenti", "url": "/admin/users", "active": True}
        ]
    }

    logger.debug(f"Loading admin users list for {superuser.email}")

    return templates.TemplateResponse("admin/users_list.html", context)


@admin_view_router.get("/users/new", response_class=HTMLResponse, name="admin_users_new")
async def admin_users_new(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Form per creare un nuovo utente.
    Template: admin_users_form.html con action='create'
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Nuovo Utente",
        "action": "create",
        "user": None,
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Utenti", "url": "/admin/users"},
            {"label": "Nuovo", "url": "/admin/users/new", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} accessing new user form")

    return templates.TemplateResponse("admin/users_form.html", context)


@admin_view_router.get("/users/{user_id}/edit", response_class=HTMLResponse, name="admin_users_edit")
async def admin_users_edit(
    request: Request,
    user_id: str,
    authdata: tuple = Depends(require_superuser)
):
    """
    Form per modificare un utente.
    Alpine.js carica i dati tramite API GET /api/v1/admin/users/{user_id}
    Template: admin_users_form.html con action='edit'
    """
    superuser, base_context = authdata

    # Validazione UUID
    try:
        UUID(user_id)
    except ValueError:
        logger.warning(f"Invalid user_id format: {user_id}")
        raise HTTPException(status_code=404, detail="ID utente non valido")

    context = {
        **base_context,
        "page_title": "Modifica Utente",
        "user_id": user_id,
        "action": "edit",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Utenti", "url": "/admin/users"},
            {"label": "Modifica", "url": f"/admin/users/{user_id}/edit", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} editing user {user_id}")

    return templates.TemplateResponse("admin/users_form.html", context)


# ============================================================================
# GESTIONE PERMESSI
# ============================================================================

@admin_view_router.get("/permissions", response_class=HTMLResponse, name="admin_permissions_list")
async def admin_permissions_list(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Pagina lista permessi utenti-siti.
    Alpine.js carica i dati tramite API GET /api/v1/admin/permissions
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Gestione Permessi",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Permessi", "url": "/admin/permissions", "active": True}
        ]
    }

    logger.debug(f"Loading admin permissions list for {superuser.email}")

    return templates.TemplateResponse("admin/permissions_list.html", context)


@admin_view_router.get("/permissions/new", response_class=HTMLResponse, name="admin_permissions_new")
async def admin_permissions_new(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Form per assegnare un nuovo permesso a un utente per un sito.
    Template: admin_permissions_form.html con action='create'
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Assegna Permesso",
        "action": "create",
        "permission": None,
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Permessi", "url": "/admin/permissions"},
            {"label": "Nuovo", "url": "/admin/permissions/new", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} accessing new permission form")

    return templates.TemplateResponse("admin/permissions_form.html", context)


@admin_view_router.get("/permissions/{permission_id}/edit", response_class=HTMLResponse, name="admin_permissions_edit")
async def admin_permissions_edit(
    request: Request,
    permission_id: str,
    authdata: tuple = Depends(require_superuser)
):
    """
    Form per modificare un permesso.
    Alpine.js carica i dati tramite API GET /api/v1/admin/permissions/{permission_id}
    Template: admin_permissions_form.html con action='edit'
    """
    superuser, base_context = authdata

    # Validazione UUID
    try:
        UUID(permission_id)
    except ValueError:
        logger.warning(f"Invalid permission_id format: {permission_id}")
        raise HTTPException(status_code=404, detail="ID permesso non valido")

    context = {
        **base_context,
        "page_title": "Modifica Permesso",
        "permission_id": permission_id,
        "action": "edit",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Permessi", "url": "/admin/permissions"},
            {"label": "Modifica", "url": f"/admin/permissions/{permission_id}/edit", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} editing permission {permission_id}")

    return templates.TemplateResponse("admin/permissions_form.html", context)


# ============================================================================
# DASHBOARD ADMIN (OPZIONALE)
# ============================================================================

@admin_view_router.get("", response_class=HTMLResponse, name="admin_dashboard")
@admin_view_router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    authdata: tuple = Depends(require_superuser)
):
    """
    Dashboard principale amministrazione (opzionale).
    Mostra statistiche e scorciatoie rapide.
    """
    superuser, base_context = authdata

    context = {
        **base_context,
        "page_title": "Pannello Amministrazione",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} accessing admin dashboard")

    # Puoi creare un template admin/dashboard.html per la dashboard
    # Se non esiste, questo renderizzerà un template generico
    return templates.TemplateResponse("admin/dashboard.html", context)
