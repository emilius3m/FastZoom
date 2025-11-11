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
from sqlalchemy import select, func
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

def normalize_site_id(site_id: str) -> Optional[str]:
    """
    Normalizza l'ID del sito per supportare diversi formati.
    
    Supporta:
    - UUID standard con trattini: eb8d88e1-74e3-46d3-8e86-81f926c01cab
    - Hash esadecimali senza trattini: eeedd3ceda34bf3b47d749a971b22ba
    
    Returns:
        str: L'ID normalizzato o None se non valido
    """
    if not site_id:
        return None
    
    # Rimuovi spazi bianchi
    site_id = site_id.strip()
    
    # Se è un UUID standard con trattini, valida e restituiscilo
    if '-' in site_id:
        try:
            # Crea un oggetto UUID per validare il formato
            uuid_obj = UUID(site_id)
            # Restituisci la stringa originale (già nel formato corretto)
            return site_id
        except (ValueError, AttributeError):
            return None
    
    # Se è un hash esadecimale senza trattini
    if len(site_id) == 32:
        try:
            # Verifica che sia esadecimale
            int(site_id, 16)
            # Converti in formato UUID standard (inserisci trattini)
            uuid_formatted = f"{site_id[0:8]}-{site_id[8:12]}-{site_id[12:16]}-{site_id[16:20]}-{site_id[20:32]}"
            # Valida il formato UUID risultante
            UUID(uuid_formatted)
            return uuid_formatted
        except (ValueError, AttributeError):
            return None
    
    # Altri formati non supportati
    return None

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

    # 🔧 FIX: Handle both UUID formats for consistency
    user_id_str = str(current_user_id)
    user_id_no_dashes = user_id_str.replace('-', '')
    
    # Ottieni informazioni utente completa con entrambi i formati UUID
    # Carica anche il profilo per evitare AttributeError
    from sqlalchemy.orm import selectinload
    user_query = select(User).options(selectinload(User.profile)).where(
        (User.id == user_id_str) | (User.id == user_id_no_dashes)
    )
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        logger.warning(f"User {current_user_id} not found in database (tried both UUID formats)")

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

    # 🔧 FIX: Handle both UUID formats and ensure fresh data
    user_id_str = str(current_user_id)
    user_id_no_dashes = user_id_str.replace('-', '')
    
    logger.info(f"🐛 [DEBUG] require_superuser - Checking user {current_user_id}")
    logger.info(f"🐛 [DEBUG] UUID formats to try: {user_id_str} (with dashes), {user_id_no_dashes} (without dashes)")
    
    # Try with both UUID formats to ensure we find the user
    # Carica anche il profilo per evitare AttributeError
    from sqlalchemy.orm import selectinload
    user_query = select(User).options(selectinload(User.profile)).where(
        (User.id == user_id_str) | (User.id == user_id_no_dashes)
    )
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    
    logger.info(f"🐛 [DEBUG] User found in require_superuser: {user is not None}")
    if user:
        logger.info(f"🐛 [DEBUG] User details in require_superuser - email: {user.email}, is_active: {user.is_active}, is_superuser: {user.is_superuser}")
    else:
        logger.error(f"🐛 [DEBUG] User {current_user_id} not found in require_superuser!")

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
        "site": base_context.get("site", {"id": "admin"}),  # Ensure site object exists for sidebar
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

    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(site_id)
    if not normalized_site_id:
        logger.warning(f"Invalid site_id format: {site_id}")
        raise HTTPException(status_code=404, detail="ID sito non valido")

    context = {
        **base_context,
        "page_title": "Modifica Sito Archeologico",
        "site_id": normalized_site_id,
        "action": "edit",
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Siti", "url": "/admin/sites"},
            {"label": "Modifica", "url": f"/admin/sites/{normalized_site_id}/edit", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} editing site {normalized_site_id}")

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

    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(site_id)
    if not normalized_site_id:
        logger.warning(f"Invalid site_id format: {site_id}")
        raise HTTPException(status_code=404, detail="ID sito non valido")

    context = {
        **base_context,
        "page_title": "Gestione Utenti del Sito",
        "site_id": normalized_site_id,
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin"},
            {"label": "Siti", "url": "/admin/sites"},
            {"label": "Utenti", "url": f"/admin/sites/{normalized_site_id}/users", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} managing users for site {normalized_site_id}")

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
    authdata: tuple = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Form per modificare un utente.
    Fetch i dati utente tramite API GET /api/v1/admin/users/{user_id}
    Template: admin_users_form.html con action='edit'
    """
    superuser, base_context = authdata

    # Validazione UUID - support both hyphenated and non-hyphenated formats
    normalized_user_id = user_id
    try:
        # Try to validate as UUID
        UUID(user_id)
    except ValueError:
        # If it's a 32-char hex string, try to format as UUID
        if len(user_id) == 32:
            try:
                # Convert hex to UUID format
                uuid_formatted = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
                UUID(uuid_formatted)  # Validate the formatted UUID
                normalized_user_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid user_id format: {user_id}")
                raise HTTPException(status_code=404, detail="ID utente non valido")
        else:
            logger.warning(f"Invalid user_id format: {user_id}")
            raise HTTPException(status_code=404, detail="ID utente non valido")

    # Fetch user data from database - try both formats
    from app.models.user_profiles import UserProfile
    from sqlalchemy.orm import selectinload
    
    # First try with normalized ID
    user_result = await db.execute(
        select(User).options(selectinload(User.profile))
        .where(User.id == normalized_user_id)
    )
    user = user_result.scalar_one_or_none()

    # If not found, try with original ID
    if not user and user_id != normalized_user_id:
        user_result = await db.execute(
            select(User).options(selectinload(User.profile))
            .where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
    
    # If still not found, try with hyphenated format of original ID
    if not user and '-' not in user_id and len(user_id) == 32:
        hyphenated_id = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
        user_result = await db.execute(
            select(User).options(selectinload(User.profile))
            .where(User.id == hyphenated_id)
        )
        user = user_result.scalar_one_or_none()
        
    if not user:
        logger.warning(f"User {user_id} not found (tried: {normalized_user_id}, {user_id}, {hyphenated_id if '-' not in user_id and len(user_id) == 32 else 'N/A'})")
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    # Fetch user permissions and sites for the permissions panel
    from app.models import UserSitePermission, ArchaeologicalSite
    from sqlalchemy import or_
    
    # Get user permissions with site details - try both user ID formats
    conditions = [
        UserSitePermission.user_id == user_id,
        UserSitePermission.user_id == normalized_user_id
    ]
    
    # Add hyphenated ID condition if applicable
    if '-' not in user_id and len(user_id) == 32:
        hyphenated_id = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
        conditions.append(UserSitePermission.user_id == hyphenated_id)
    
    permissions_result = await db.execute(
        select(UserSitePermission, ArchaeologicalSite)
        .join(ArchaeologicalSite, UserSitePermission.site_id == ArchaeologicalSite.id)
        .where(or_(*conditions))
        .where(UserSitePermission.is_active == True)
    )
    permissions_rows = permissions_result.all()
    
    user_permissions = []
    for perm, site in permissions_rows:
        user_permissions.append({
            "id": str(perm.id),
            "permission_level": str(perm.permission_level),
            "permission_display_name": {
                "read": "Visualizzatore",
                "write": "Curatore",
                "admin": "Amministratore Sito",
                "regional_admin": "Amministratore Regionale"
            }.get(str(perm.permission_level), str(perm.permission_level)),
            "status_badge_class": {
                "read": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
                "write": "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
                "admin": "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300",
                "regional_admin": "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
            }.get(str(perm.permission_level), "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300"),
            "site": {
                "id": str(site.id),
                "name": site.name,
                "code": site.code
            }
        })
    
    # Get available sites for adding permissions
    sites_result = await db.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.status == "active")
    )
    available_sites = sites_result.scalars().all()
    
    # Prepare user data for template
    # First try to get from User model directly (for backward compatibility)
    # Then fallback to UserProfile if available
    first_name = getattr(user, 'first_name', None)
    last_name = getattr(user, 'last_name', None)
    
    # If not found in User model, try to get from profile
    try:
        if not first_name and user.profile:
            first_name = user.profile.first_name
        if not last_name and user.profile:
            last_name = user.profile.last_name
    except AttributeError:
        # Profile relationship not loaded
        pass
    
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "first_name": first_name,
        "last_name": last_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at
    }

    context = {
        **base_context,
        "page_title": "Modifica Utente",
        "user_id": user_id,
        "action": "edit",
        "user_data": user_data,
        "user_permissions": user_permissions,
        "available_sites": available_sites,
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
# DASHBOARD ADMIN (OPZIONALE)
# ============================================================================

@admin_view_router.get("", response_class=HTMLResponse, name="admin_dashboard")
@admin_view_router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    authdata: tuple = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Dashboard principale amministrazione (opzionale).
    Mostra statistiche e scorciatoie rapide.
    """
    superuser, base_context = authdata

    # Fetch statistics for dashboard
    try:
        # Count total users
        users_total_result = await db.execute(select(func.count(User.id)))
        users_total = users_total_result.scalar() or 0
        
        # Count active users
        users_active_result = await db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        users_active = users_active_result.scalar() or 0
        
        # Count photos if Photo model exists
        photos_total = 0
        try:
            from app.models import Photo
            photos_result = await db.execute(select(func.count(Photo.id)))
            photos_total = photos_result.scalar() or 0
        except ImportError:
            # Photo model not available, set to 0
            photos_total = 0
        
    except Exception as e:
        logger.error(f"Error fetching dashboard statistics: {e}")
        users_total = 0
        users_active = 0
        photos_total = 0

    context = {
        **base_context,
        "page_title": "Pannello Amministrazione",
        "users_count": users_total,
        "users_active": users_active,
        "photos_count": photos_total,
        "breadcrumb": [
            {"label": "Home", "url": "/"},
            {"label": "Admin", "url": "/admin", "active": True}
        ]
    }

    logger.debug(f"User {superuser.email} accessing admin dashboard")

    # Puoi creare un template admin/dashboard.html per la dashboard
    # Se non esiste, questo renderizzerà un template generico
    return templates.TemplateResponse("admin/dashboard.html", context)
