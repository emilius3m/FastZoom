from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse ,Response
from loguru import logger
from typing import List, Dict, Any
from uuid import UUID

# IMPORT MANCANTI - Aggiungi questi:
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

# Sistema archeologico multi-sito
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.photos import Photo
from app.models.users import User, Role, UserActivity
from app.models.user_profiles import UserProfile
# Sicurezza multi-sito - DEPENDENCY CON BLACKLIST CHECK
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist, SecurityService
from app.core.config import get_settings

# Route imports
from app.routes.api.auth import router as auth_api_router
from app.database.db import create_db_and_tables, get_async_session
from app.exception import http_exception_handler

from fastapi_csrf_protect import CsrfProtect
from fastapi import APIRouter, Request
from app.core.csrf_settings import CsrfSettings, _csrf_tokens_optional
from app.templates import templates
from app.routes.admin import admin_router
# 🔧 NUOVO IMPORT - Router Sites
from app.routes.sites_router import sites_router
# 🔧 NUOVO IMPORT - Router Photos (senza prefisso /sites)
from app.routes.photos_router import photos_router
# 🔧 NUOVO IMPORT - Router Form Schemas
from app.routes.api.form_schemas import form_schemas_router
from app.routes.api.documents import documents_router  # NUOVO
from app.routes.view.documentation import documentation_router
# 🗺️ NUOVO IMPORT - Router Archaeological Plans API
from app.routes.api.archaeological_plans import plans_router as archaeological_plans_router
# 🏺 NUOVO IMPORT - Router ICCD Records API
from app.routes.api.iccd_records import iccd_router
# 🏺 NUOVO IMPORT - Router ICCD API (draft)
#from app.routes.iccd_api import router as iccd_api_router
# 🌍 NUOVO IMPORT - Router Geographic Maps API
from app.routes.api.geographic_maps import geographic_maps_router
# 📡 NUOVO IMPORT - Router WebSocket Notifications
from app.routes.api.notifications_ws import notifications_router

from app.routes import photo_metadata




# Import condizionali delle route view
try:
    from app.routes.view.login import login_view_route
    LOGIN_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Login view route not found")
    LOGIN_ROUTE_EXISTS = False

try:
    from app.routes.view.user import user_view_route
    USER_ROUTE_EXISTS = True
except ImportError:
    logger.warning("User view route not found")
    USER_ROUTE_EXISTS = False

try:
    from app.routes.view.geographic_map import geographic_map_router
    GEOGRAPHIC_MAP_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Geographic map view route not found")
    GEOGRAPHIC_MAP_ROUTE_EXISTS = False

try:
    from app.routes.view.dashboard import dashboard_router
    DASHBOARD_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Dashboard view route not found")
    DASHBOARD_ROUTE_EXISTS = False

try:
    from app.routes.view.photos import photos_view_router
    PHOTOS_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Photos view route not found")
    PHOTOS_ROUTE_EXISTS = False

try:
    from app.routes.view.team import team_router
    TEAM_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Team view route not found")
    TEAM_ROUTE_EXISTS = False

try:
    from app.routes.view.documentation import documentation_router
    DOCUMENTATION_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Documentation view route not found")
    DOCUMENTATION_ROUTE_EXISTS = False

try:
    from app.routes.view.archaeological_plans import archaeological_plans_view_router
    ARCHAEOLOGICAL_PLANS_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Archaeological plans view route not found")
    ARCHAEOLOGICAL_PLANS_ROUTE_EXISTS = False

try:
    from app.routes.view.iccd import iccd_router
    ICCD_ROUTE_EXISTS = True
except ImportError:
    logger.warning("ICCD view route not found")
    ICCD_ROUTE_EXISTS = False

# Configurazione
settings = get_settings()
app = FastAPI(
    title="Sistema Archeologico Multi-Sito",
    description="Catalogazione digitale per siti archeologici",
    version="1.0.1",
    exception_handlers={HTTPException: http_exception_handler}
)

# 🆕 NUOVO: CSRF Protection per forms HTMX
@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include route API
app.include_router(auth_api_router, tags=["Authentication"])


from app.core.middleware import (
    RequestLoggingMiddleware,
    AuditMiddleware,
    PerformanceMonitoringMiddleware,
    SecurityHeadersMiddleware
)

# Aggiungi middleware all'app
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
#app.add_middleware(SecurityHeadersMiddleware)



from app.routes.photo_metadata import router as photo_metadata_router

# Registra router
app.include_router(
    photo_metadata_router,
    tags=["Photo Metadata"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)


# Include admin routes
#####app.include_router(admin_router, tags=["Administration"])
# 🏛️ INCLUSIONE ROUTER SITES - CONFIGURAZIONE PRINCIPALE
app.include_router(
    sites_router,
    # prefix="/sites" # Già definito nel router stesso
    tags=["sites"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)

# 🖼️ INCLUSIONE ROUTER PHOTOS - Endpoints foto senza prefisso /sites
app.include_router(
    photos_router,
    tags=["photos"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)

# 📋 INCLUSIONE ROUTER FORM SCHEMAS - Endpoints per form builder
app.include_router(
    form_schemas_router,
    tags=["form-schemas"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)
app.include_router(
    documents_router,
    tags=["documents"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)


# 🗺️ INCLUSIONE ROUTER ARCHAEOLOGICAL PLANS - API per piante archeologiche
app.include_router(
    archaeological_plans_router,
    tags=["archaeological_plans"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)

# 🏺 INCLUSIONE ROUTER ICCD - API per schede ICCD standard
app.include_router(
    iccd_router,
    tags=["iccd-catalogation"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)

# 🏺 INCLUSIONE ROUTER ICCD API (draft) - API ICCD draft
#app.include_router(
#    iccd_api_router,
#    tags=["iccd-api-draft"],
#    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
#)

# 🌍 INCLUSIONE ROUTER GEOGRAPHIC MAPS - API per mappe geografiche
app.include_router(
    geographic_maps_router,
    tags=["geographic-map"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)



# Import del router giornale cantiere
try:
    from app.routes.api.giornale_cantiere import router as giornale_cantiere_api_router
    GIORNALE_API_EXISTS = True
except ImportError:
    logger.warning("Giornale cantiere API route not found")
    GIORNALE_API_EXISTS = False

try:
    from app.routes.view.giornale_cantiere import router as giornale_cantiere_view_router
    GIORNALE_VIEW_EXISTS = True
except ImportError:
    logger.warning("Giornale cantiere view route not found")
    GIORNALE_VIEW_EXISTS = False

# Registrazione router API
if GIORNALE_API_EXISTS:
    app.include_router(
        giornale_cantiere_api_router,
        tags=["giornale-cantiere"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

# Registrazione router view
if GIORNALE_VIEW_EXISTS:
    app.include_router(
        giornale_cantiere_view_router,
        tags=["Pages", "Giornale Cantiere"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )


# 📡 INCLUSIONE ROUTER WEBSOCKET NOTIFICATIONS - WebSocket per notifiche real-time
app.include_router(
    notifications_router,
    tags=["websocket-notifications"]
)

# Router esistenti
app.include_router(
    admin_router,
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Admin richiede autenticazione con blacklist
)

# Include route view condizionali
if LOGIN_ROUTE_EXISTS:
    app.include_router(login_view_route, tags=["Pages", "Authentication"])

if USER_ROUTE_EXISTS:
    app.include_router(user_view_route, tags=["Pages", "User Management"])
if GEOGRAPHIC_MAP_ROUTE_EXISTS:
    app.include_router(
        geographic_map_router,
        tags=["Pages", "geographic-map"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if DASHBOARD_ROUTE_EXISTS:
    app.include_router(
        dashboard_router,
        tags=["Pages", "Dashboard"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if TEAM_ROUTE_EXISTS:
    app.include_router(
        team_router,
        tags=["Pages", "Team"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if DOCUMENTATION_ROUTE_EXISTS:
    app.include_router(
        documentation_router,
        tags=["Pages", "Documentation"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if ARCHAEOLOGICAL_PLANS_ROUTE_EXISTS:
    app.include_router(
        archaeological_plans_router,
        tags=["Archaeological Plans"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )
    app.include_router(
        archaeological_plans_view_router,
        tags=["Pages", "Archaeological Plans View"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if PHOTOS_ROUTE_EXISTS:
    app.include_router(
        photos_view_router,
        tags=["Pages", "Photos"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if ICCD_ROUTE_EXISTS:
    app.include_router(
        iccd_router,
        tags=["Pages", "ICCD Cataloging"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

# Route principali
@app.get("/")
async def home_redirect():
    """Redirect alla pagina di login"""
    return RedirectResponse(url="/login")

@app.post("/logout")
async def logout_endpoint(request: Request, response: Response, db: AsyncSession = Depends(get_async_session)):
    """
    Logout endpoint accessibile direttamente su /logout (POST)
    Invalida token, rimuove cookie e redirect a login
    """
    try:
        # Ottieni il token dal cookie prima di eliminarlo
        access_token_cookie = request.cookies.get("access_token")

        # Se c'è un token, invalidalo server-side
        if access_token_cookie:
            token = access_token_cookie.replace("Bearer ", "")

            # Ottieni l'ID utente dal token per la blacklist
            try:
                payload = await SecurityService.verify_token(token, db)
                user_id = UUID(payload.get("sub"))

                # Invalida il token server-side
                await SecurityService.blacklist_token(token, db, user_id, "user_logout")

                logger.info(f"Token invalidated for user: {user_id}")

            except Exception as e:
                logger.warning(f"Could not invalidate token: {e}")
                # Continua comunque con il logout

        # Rimuovi tutti i cookie di autenticazione
        response.delete_cookie(
            key="access_token",
            path="/",
            secure=False,  # Stesso valore usato nel login
            samesite="lax",
            httponly=True
        )
        response.delete_cookie(
            key="selected_site_id",
            path="/",
            secure=False,
            samesite="lax",
            httponly=True
        )

        logger.info("Logout successful - cookies deleted")

        # Redirect to login
        return RedirectResponse(url="/login", status_code=303)

    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

# DASHBOARD CORRETTO CON TEMPLATE CONTEXT COMPLETO
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Dashboard principale con template HTML completo
    Include tutte le variabili necessarie per auth_navigation.html
    """
    try:
        # Ottieni informazioni utente dal database
        user = await db.execute(select(User).where(User.id == current_user_id))
        user = user.scalar_one_or_none()

        # Ottieni profilo utente
        user_profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == current_user_id)
        )
        user_profile = user_profile_result.scalar_one_or_none()

        # Calcola conteggio foto reali per tutti i siti accessibili
        photos_count = 0
        users_count = 0
        if user_sites:
            site_ids = [UUID(site['id']) for site in user_sites]
            
            # Conteggio foto
            photos_result = await db.execute(
                select(func.count(Photo.id)).where(Photo.site_id.in_(site_ids))
            )
            photos_count = photos_result.scalar() or 0
            
            # Conteggio utenti unici
            users_result = await db.execute(
                select(func.count(User.id.distinct())).join(
                    UserSitePermission, UserSitePermission.user_id == User.id
                ).where(
                    UserSitePermission.site_id.in_(site_ids)
                )
            )
            users_count = users_result.scalar() or 0
        
        # CSRF opzionale
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()

        # Context completo per il template
        context = {
            "request": request,
            "title": "Dashboard | Sistema Archeologico",
            "message": "Benvenuto nel Sistema Archeologico",
            
            # VARIABILI RICHIESTE DA auth_navigation.html
            "sites": user_sites,
            "sites_count": len(user_sites),
            "photos_count": photos_count,
            "users_count": users_count,
            "user_email": user.email if user else None,
            "user_type": "superuser" if user and user.is_superuser else "user",
            "current_site_name": user_sites[0]["name"] if user_sites else None,
            "current_page": "dashboard",
            "current_user": user,
            "user_profile": user_profile,
            "csrf_token": csrf_token
        }

        logger.info(f"Dashboard rendered: user_id={current_user_id}, sites={len(user_sites)}")
        response = templates.TemplateResponse("pages/dashboard.html", context)
        
        # Se CSRF disponibile, imposta cookie firmato
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore interno dashboard"
        )


# Test cookie e autenticazione
@app.get("/auth-test")
async def auth_test(request: Request, db: AsyncSession = Depends(get_async_session)):
    """Test completo di autenticazione"""
    try:
        # Test manuale delle dependency con blacklist
        from app.core.security import get_current_user_token_with_blacklist

        # Controlla se cookie esiste
        access_token_cookie = request.cookies.get("access_token")
        if not access_token_cookie:
            return {
                "error": "No access_token cookie found",
                "cookies_found": list(request.cookies.keys()),
                "auth_status": "no_cookie"
            }

        # Test token parsing con blacklist
        token_payload = await get_current_user_token_with_blacklist(request, db)
        user_id = await get_current_user_id_with_blacklist(request, db)
        user_sites = await get_current_user_sites_with_blacklist(request, db)
        
        return {
            "success": True,
            "auth_status": "authenticated",
            "user_id": str(user_id),
            "sites_count": len(user_sites),
            "sites": user_sites[:2],  # Prime 2 per brevità
            "token_exp": token_payload.get("exp"),
            "cookie_found": True
        }
        
    except Exception as e:
        logger.error(f"Auth test error: {str(e)}")
        return {
            "error": str(e),
            "auth_status": "failed",
            "success": False,
            "cookie_found": access_token_cookie is not None
        }

@app.get("/site-selection")
async def site_selection_page(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Pagina selezione sito per utenti multi-sito"""
    if not user_sites:
        raise HTTPException(status_code=403, detail="Nessun sito accessibile")
    
    logger.info(f"Site selection: user_id={current_user_id}, sites={len(user_sites)}")
    
    return {
        "request_info": {"method": request.method, "url": str(request.url)},
        "sites": user_sites,
        "sites_count": len(user_sites),
        "user_id": str(current_user_id),
        "museum_name": getattr(settings, 'museum_name', 'Museo Archeologico')
    }

# Route per singoli siti
@app.get("/site/{site_id}/dashboard")
async def site_dashboard(
    site_id: UUID,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Dashboard specifica per un sito archeologico"""
    
    # Verifica accesso al sito
    site_info = next(
        (site for site in user_sites if site["id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise HTTPException(
            status_code=403,
            detail=f"Accesso negato al sito {site_id}"
        )
    
    logger.info(f"Site dashboard: user_id={current_user_id}, site_id={site_id}")
    
    return {
        "message": f"Dashboard {site_info['name']}",
        "site": site_info,
        "user_id": str(current_user_id),
        "permission": site_info.get("permission_level", "read"),
        "system": "archaeological_catalog"
    }

@app.get("/health")
async def health_check():
    """Health check per monitoraggio sistema"""
    return {
        "status": "ok",
        "system": "archaeological_catalog",
        "version": "1.0.0",
        "timestamp": "2025-09-19 20:43",
        "multi_site_enabled": getattr(settings, 'site_selection_enabled', True)
    }



@app.on_event("shutdown")
async def on_shutdown():
    """Chiusura sistema"""
    museum_name = getattr(settings, 'museum_name', 'Museo Archeologico')
    logger.info(f"🏺 {museum_name} - Sistema arrestato")

@app.on_event("startup")
async def on_startup():
    """Inizializzazione sistema archeologico"""
    try:
        await create_db_and_tables()
        museum_name = getattr(settings, 'museum_name', 'Museo Archeologico')
        logger.info(f"🏺 {museum_name} - Sistema Archeologico avviato")
        logger.info(f"🔐 Cookie-based authentication enabled")
        logger.info(f"📊 Admin routes enabled")
    except Exception as e:
        logger.error(f"❌ Errore avvio: {e}")
        raise



