import asyncio
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse ,Response
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from loguru import logger
from typing import List, Dict, Any
from uuid import UUID


# IMPORT MANCANTI - Aggiungi questi:
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Photo, UserSitePermission
from app.models import User, Role, UserActivity
from app.models.user_profiles import UserProfile
# Fix for SQLAlchemy relationship resolution - import Cantiere model
from app.models.cantiere import Cantiere
# Sicurezza multi-sito - DEPENDENCY CON BLACKLIST CHECK
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist, SecurityService
from app.core.config import get_settings

# Route imports
from app.database.db import create_db_and_tables, get_async_session
from app.exception import http_exception_handler

from fastapi_csrf_protect import CsrfProtect
from fastapi import APIRouter, Request, Form
from app.core.csrf_settings import CsrfSettings, _csrf_tokens_optional
from app.templates import templates
# VECCHIO ADMIN ROUTER - Migrato in API v1
# from app.routes.admin import admin_router
# 🔧 NUOVO IMPORT - Router Sites
from app.routes.sites_router import sites_router
# 🔧 NUOVO IMPORT - Router Photos (senza prefisso /sites) - MOVED TO API v1
# from app.routes.photos_router import photos_router  # REMOVED - moved to api/v1/photos.py
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
# 🌍 NUOVO IMPORT - Router Geographic Maps API (DEPRECATED)
# from app.routes.api.geographic_maps import geographic_maps_router
# 📡 NUOVO IMPORT - Router WebSocket Notifications
from app.routes.api.notifications_ws import notifications_router
# 🌐 NUOVO IMPORT - Router WebSocket Globale con token-based authentication
#from app.routes.api.notifications_global_ws import global_notifications_router
# 🆕 NUOVO IMPORT - Router Unified Dashboard API
from app.routes.api.unified_dashboard import router as unified_dashboard_router
# 🗄️ NUOVO IMPORT - Router Database Monitoring API
from app.routes.api.database_monitoring import router as database_monitoring_router
# 📋 NUOVO IMPORT - Router Queue Monitoring API
from app.routes.api.queue_monitoring import queue_monitoring_router
# 📊 NUOVO IMPORT - Router Performance Monitoring API
from app.routes.api.performance_monitoring import router as performance_monitoring_router
from app.routes import photo_metadata
from app.routes.api.us import us_router
from app.routes.view.us import us_view_router
from app.routes.api.us_word_export_api import router as us_word_export_router
from app.routes.api.us_files import router as us_files_router



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

try:
    from app.routes.view.cantieri import router as cantieri_view_router
    CANTIERI_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Cantieri view route not found")
    CANTIERI_ROUTE_EXISTS = False

# Configurazione
settings = get_settings()
# Configurazione FastAPI con Swagger UI personalizzato
app = FastAPI(
    title="Archaeological Catalog API",
    description="Catalogazione digitale per siti archeologici",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    exception_handlers={HTTPException: http_exception_handler},
    swagger_ui_parameters={
        "deepLinking": True,
        "displayOperationId": True,
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 1,
        "displayRequestDuration": True,
        "docExpansion": "list",
        "tryItOutEnabled": True,
        "persistAuthorization": True,
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True
    },
    openapi_url="/openapi.json"
)

# 🆕 NUOVO: CSRF Protection per forms HTMX
@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include route API - DEPRECATED: Removed old auth.py router, now using API v1

# 🆕 NUOVO: Includi router API v1 riorganizzato con backward compatibility
from app.routes.api.v1 import api_v1_router
app.include_router(
    api_v1_router,
    tags=["API v1 - Riorganizzata"],
    responses={404: {"description": "Not found"}}
)


from app.core.middleware import (
    UnifiedLoggingMiddleware,
    AuditMiddleware,setup_middleware, create_health_check_endpoint,
    SecurityHeadersMiddleware
)
# 📊 NUOVO IMPORT - Performance Tracking Middleware
from app.middleware.performance_tracking_middleware import (
    PerformanceTrackingMiddleware,
    RequestCountMiddleware
)

# Queue middleware
from app.middleware.queue_middleware import QueueMiddleware, QueueStatusMiddleware, register_queue_handlers

# Add SessionMiddleware first (must be added before other middleware that might use request.session)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key if hasattr(settings, 'secret_key') else "your-secret-key-here-change-in-production",
    session_cookie="session_id",
    max_age=3600 * 24 * 7,  # 7 days
    same_site="lax",
    https_only=False
)

# Aggiungi middleware all'app
app.add_middleware(UnifiedLoggingMiddleware)
app.add_middleware(AuditMiddleware)
# 📊 NUOVO: Aggiungi Performance Tracking Middleware
app.add_middleware(RequestCountMiddleware)
app.add_middleware(PerformanceTrackingMiddleware)
#app.add_middleware(SecurityHeadersMiddleware)

# Add queue middleware (order matters - queue middleware should be before status middleware)
from app.core.config import get_settings
settings = get_settings()

if settings.queue_enabled:
    # Import RequestPriority enum for queue configuration
    from app.services.request_queue_service import RequestPriority
    
    queue_config = {
        'rate_limits': {
            'upload': {
                'requests': settings.rate_limit_upload_requests,
                'window': settings.rate_limit_upload_window
            },
            'default': {
                'requests': settings.rate_limit_default_requests,
                'window': settings.rate_limit_default_window
            }
        },
        'queue_settings': {
            '/api/site/{site_id}/photos/upload': {
                'enable_queue': True,
                'priority': RequestPriority.NORMAL,
                'timeout': settings.queue_timeout_seconds,
                'max_retries': settings.queue_max_retries
            }
        }
    }
    
    app.add_middleware(QueueMiddleware, queue_config=queue_config)
    app.add_middleware(QueueStatusMiddleware)
    
    logger.info("Queue middleware enabled")


# Setup tutti i middleware in una riga
setup_middleware(app, {
    'enable_rate_limit': True,
    'requests_per_minute': 100,
    'enable_audit': True,
    'enable_cors': True,
    'cors_origins': ["http://localhost:3000", "http://localhost:8000"],
    'slow_threshold': 2.0,
    'strict_csp': False
})

# Aggiungi health check endpoint
@app.get("/health")
async def health_check():
    return create_health_check_endpoint(
        logging_middleware=app.state.logging_middleware
    )()

@app.get("/test-session")
async def test_session(request: Request):
    """Test endpoint to verify SessionMiddleware is working"""
    session = request.session
    session["test_key"] = "test_value"
    
    return {
        "session_id": session.get("session_id"),
        "test_key": session.get("test_key"),
        "has_session": True,
        "session_data": dict(session)
    }

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

# 🖼️ INCLUSIONE ROUTER PHOTOS - Endpoints foto senza prefisso /sites - MOVED TO API v1
# app.include_router(
#     photos_router,
#     tags=["photos"],
#     dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
# )  # REMOVED - moved to api/v1/photos.py

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

try:
    from app.routes.view.giornale_cantiere import router as giornale_cantiere_view_router
    GIORNALE_VIEW_EXISTS = True
except ImportError:
    logger.warning("Giornale cantiere view route not found")
    GIORNALE_VIEW_EXISTS = False

# Import view redirect router for backward compatibility
try:
    from app.routes.view_redirect import router as view_redirect_router
    VIEW_REDIRECT_EXISTS = True
except ImportError:
    logger.warning("View redirect route not found")
    VIEW_REDIRECT_EXISTS = False

# Registrazione router view
if GIORNALE_VIEW_EXISTS:
    app.include_router(
        giornale_cantiere_view_router,
        tags=["Pages", "Giornale Cantiere"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

# Include view redirect router for backward compatibility
if VIEW_REDIRECT_EXISTS:
    app.include_router(
        view_redirect_router,
        tags=["Pages", "View Redirects"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

# Import delle nuove routes archeologia
try:
    from app.routes.api.archeologia_avanzata import router as archeologia_api_router
    ARCHEOLOGIA_API_EXISTS = True
except ImportError:
    logger.warning("Archeologia avanzata API route not found")
    ARCHEOLOGIA_API_EXISTS = False

try:
    import importlib
    archeologia_view_module = importlib.import_module('app.routes.view.archeologia-view-routes')
    archeologia_view_router = archeologia_view_module.router

    ARCHEOLOGIA_VIEW_EXISTS = True
except ImportError:
    logger.warning("Archeologia avanzata view route not found")
    ARCHEOLOGIA_VIEW_EXISTS = False


# Registra archeologia routes
if ARCHEOLOGIA_API_EXISTS:
    app.include_router(
        archeologia_api_router,
        tags=["archeologia-api"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

if ARCHEOLOGIA_VIEW_EXISTS:
    app.include_router(
        archeologia_view_router,
        tags=["Pages", "Archeologia"],
        dependencies=[Depends(get_current_user_id_with_blacklist)]
    )

# 📡 INCLUSIONE ROUTER WEBSOCKET NOTIFICATIONS - WebSocket per notifiche real-time
app.include_router(
    notifications_router,
    tags=["websocket-notifications"]
)

# 🌐 INCLUSIONE ROUTER WEBSOCKET GLOBALE - Endpoint globale con token-based authentication
#app.include_router(
#    global_notifications_router,
#    tags=["websocket-global-notifications"]
#)

# 🆕 INCLUSIONE ROUTER UNIFIED DASHBOARD API - API per dashboard unificata
app.include_router(
    unified_dashboard_router,
    tags=["unified-dashboard"],
    prefix="/api/unified",
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 🗄️ INCLUSIONE ROUTER DATABASE MONITORING - API per monitoring connection pool
app.include_router(
    database_monitoring_router,
    tags=["database-monitoring"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 📋 INCLUSIONE ROUTER QUEUE MONITORING - API per monitoring request queue
app.include_router(
    queue_monitoring_router,
    tags=["queue-monitoring"],
    prefix="/api/queue",
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 📊 INCLUSIONE ROUTER PERFORMANCE MONITORING - API per monitoring performance
app.include_router(
    performance_monitoring_router,
    tags=["performance-monitoring"],
    prefix="/api/performance-monitoring",
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 🏺 INCLUSIONE ROUTER US/USM - API per Unità Stratigrafiche
app.include_router(
    us_router,
    tags=["us-usm-api"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)

# 📄 INCLUSIONE ROUTER US/USM WORD EXPORT - Export Word per US/USM
app.include_router(
    us_word_export_router,
    tags=["us-word-export"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 📎 INCLUSIONE ROUTER US/USM FILES - Gestione file US/USM
app.include_router(
    us_files_router,
    tags=["us-files"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]  # Autenticazione con blacklist
)

# Router esistenti - VECCHIO ADMIN ROUTER DISABILITATO (migrato in API v1)
##### app.include_router(
#####     admin_router,
#####     dependencies=[Depends(get_current_user_id_with_blacklist)]  # Admin richiede autenticazione con blacklist
##### )

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

# 🏺 INCLUSIONE ROUTER US/USM VIEW - Visualizzazione pagina gestione US/USM
app.include_router(
    us_view_router,
    tags=["Pages", "US/USM"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 🛠️ NUOVO INCLUSIONE ROUTER ADMIN VIEW - Interfaccia web che usa API v1
from app.routes.view.admin import admin_view_router
app.include_router(
    admin_view_router,
    tags=["Pages", "Administration"],
    dependencies=[Depends(get_current_user_id_with_blacklist)]
)

# 🏗️ INCLUSIONE ROUTER CANTIERI VIEW - Gestione cantieri lavoro
if CANTIERI_ROUTE_EXISTS:
    app.include_router(
        cantieri_view_router,
        tags=["Pages", "Cantieri"],
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
                user_id = payload.get("sub")  # Keep as string

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

# DASHBOARD UNIFICATO - Supporto per vecchia e nuova interfaccia
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session),
    view: str = None  # Parameter to switch between 'unified' and 'classic' view
):
    """
    Dashboard unificata con supporto per template classico e nuovo
    Include tutte le variabili necessarie per auth_navigation.html
    """
    try:
        # Determine which template to use
        use_unified = view == 'unified' or view is None  # Default to unified
        
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
        documents_count = 0
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

        # Prepare base context
        base_context = {
            "request": request,
            "title": "Dashboard Unificata | Sistema Archeologico" if use_unified else "Dashboard | Sistema Archeologico",
            "message": "Benvenuto nel Sistema Archeologico Unificato" if use_unified else "Benvenuto nel Sistema Archeologico",
            
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
            "csrf_token": csrf_token,
            "use_unified": use_unified
        }

        # Add unified-specific context
        if use_unified:
            unified_context = {
                **base_context,
                # Additional data for unified dashboard
                "unified_stats": {
                    "sites_count": len(user_sites),
                    "photos_count": photos_count,
                    "documents_count": documents_count,
                    "users_count": users_count
                }
            }
            
            template_name = "pages/unified/dashboard.html"
            context = unified_context
        else:
            # Classic dashboard context
            template_name = "pages/dashboard.html"
            context = base_context

        logger.info(f"Dashboard rendered: user_id={current_user_id}, sites={len(user_sites)}, unified={use_unified}")
        response = templates.TemplateResponse(template_name, context)
        
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

# DASHBOARD CLASSICA (per retrocompatibilità)
@app.get("/dashboard/classic", response_class=HTMLResponse)
async def dashboard_classic_view(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Dashboard classica per retrocompatibilità
    """
    return await dashboard_view(request, current_user_id, user_sites, db, view='classic')

# DASHBOARD UNIFICATA (esplicita)
@app.get("/dashboard/unified", response_class=HTMLResponse)
async def dashboard_unified_view(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Dashboard unificata esplicita
    """
    return await dashboard_view(request, current_user_id, user_sites, db, view='unified')

# 📊 PERFORMANCE DASHBOARD - Dashboard per monitoring performance
@app.get("/performance-dashboard", response_class=HTMLResponse)
async def performance_dashboard_view(
    request: Request,
    current_user_id: str = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Dashboard per monitoring delle performance del sistema"""
    try:
        # Ottieni informazioni utente dal database
        user = await db.execute(select(User).where(User.id == current_user_id))
        user = user.scalar_one_or_none()

        # Ottieni profilo utente
        user_profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == current_user_id)
        )
        user_profile = user_profile_result.scalar_one_or_none()

        # CSRF opzionale
        csrf_token, signed_token, csrf_instance = _csrf_tokens_optional()

        # Prepare context
        context = {
            "request": request,
            "title": "Performance Dashboard | FastZoom",
            "message": "Sistema di Monitoring Performance",
            
            # VARIABILI RICHIESTE DA auth_navigation.html
            "sites": user_sites,
            "sites_count": len(user_sites),
            "user_email": user.email if user else None,
            "user_type": "superuser" if user and user.is_superuser else "user",
            "current_page": "performance_dashboard",
            "current_user": user,
            "user_profile": user_profile,
            "csrf_token": csrf_token,
        }

        logger.info(f"Performance dashboard rendered: user_id={current_user_id}")
        response = templates.TemplateResponse("pages/performance_dashboard.html", context)
        
        # Se CSRF disponibile, imposta cookie firmato
        if csrf_instance and signed_token:
            csrf_instance.set_csrf_cookie(signed_token, response)
        
        return response
        
    except Exception as e:
        logger.error(f"Performance dashboard error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Errore interno dashboard performance"
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



# BACKWARD COMPATIBILITY ROUTE FOR LEGACY AUTH ENDPOINT
@app.post("/auth/post_update_user/{user_id}", include_in_schema=False)
async def legacy_update_user(
    user_id: str,
    request: Request,
    first_name: str = Form(None),
    last_name: str = Form(None),
    gender: str = Form(None),
    dob: str = Form(None),
    city: str = Form(None),
    country: str = Form(None),
    address: str = Form(None),
    phone: str = Form(None),
    company: str = Form(None),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Legacy endpoint for backward compatibility.
    Redirects to the new API v1 endpoint.
    """
    logger.warning(f"Legacy auth endpoint used: /auth/post_update_user/{user_id} - redirecting to API v1")
    
    # Get current user from token
    try:
        access_token_cookie = request.cookies.get("access_token")
        if not access_token_cookie:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        token = access_token_cookie.replace("Bearer ", "")
        payload = await SecurityService.verify_token(token, db)
        current_user_id = UUID(payload.get("sub"))
        
        # Get current user object
        result = await db.execute(select(User).where(User.id == current_user_id))
        current_user = result.scalar_one_or_none()
        
        if not current_user:
            raise HTTPException(status_code=401, detail="User not found")
            
    except Exception as e:
        logger.error(f"Error authenticating user for legacy endpoint: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    # Import the v1 update function and call it
    from app.routes.api.v1.auth import v1_update_user
    return await v1_update_user(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        dob=dob,
        city=city,
        country=country,
        address=address,
        phone=phone,
        company=company,
        db=db,
        current_user=current_user
    )


@app.on_event("shutdown")
async def on_shutdown():
    """Chiusura sistema"""
    try:
        logger.info("🛑 Starting FastZoom application shutdown...")
        
        # Ferma il servizio di background processing per deep zoom tiles
        logger.info("🔄 Stopping DeepZoom background processor...")
        try:
            from app.services.deep_zoom_background_service import deep_zoom_background_service
            await deep_zoom_background_service.stop_background_processor()
            logger.info("✅ Deep zoom background processor stopped")
        except Exception as deepzoom_error:
            logger.error(f"❌ Error stopping DeepZoom background processor: {deepzoom_error}")
        
        # Ferma il servizio di verifica periodica tiles
        logger.info("🔄 Stopping tiles verification service...")
        try:
            from app.services.tiles_verification_service import tiles_verification_service
            await tiles_verification_service.stop_periodic_verification()
            logger.info("✅ Tiles verification service stopped")
        except Exception as tiles_error:
            logger.error(f"❌ Error stopping tiles verification service: {tiles_error}")
        
        # Ferma il servizio di monitoring delle performance
        logger.info("🔄 Stopping performance monitoring service...")
        try:
            from app.services.performance_monitoring_service import performance_monitoring_service
            await performance_monitoring_service.stop_monitoring()
            logger.info("✅ Performance monitoring service stopped")
        except Exception as perf_error:
            logger.error(f"❌ Error stopping performance monitoring service: {perf_error}")
        
        # Stop queue service
        if settings.queue_enabled:
            logger.info("🔄 Stopping request queue service...")
            try:
                from app.services.request_queue_service import request_queue_service
                await request_queue_service.stop()
                logger.info("✅ Request queue service stopped")
            except Exception as queue_error:
                logger.error(f"❌ Error stopping request queue service: {queue_error}")
        
        museum_name = getattr(settings, 'museum_name', 'Museo Archeologico')
        logger.info(f"🏺 {museum_name} - Sistema arrestato")
        logger.info("✅ FastZoom application shutdown completed")
        
    except Exception as e:
        logger.error(f"❌ Critical error during shutdown: {e}")

@app.on_event("startup")
async def on_startup():
    """Inizializzazione sistema archeologico"""
    try:
        logger.info("🚀 Starting FastZoom application initialization...")
        
        # Initialize models first to ensure proper relationship mapping
        from app.database.base import init_models
        init_models()
        logger.info("✅ Database models initialized")
        
        await create_db_and_tables()
        logger.info("✅ Database tables created/verified")
        
        # Avvia il servizio di background processing per deep zoom tiles con error handling migliorato
        logger.info("🔄 Starting DeepZoom background processor...")
        try:
            from app.services.deep_zoom_background_service import deep_zoom_background_service
            
            if not deep_zoom_background_service._running:
                await deep_zoom_background_service.start_background_processor()
                
                # Verify service status
                queue_status = await deep_zoom_background_service.get_queue_status()
                logger.info(f"📊 DeepZoom service status: {queue_status}")
                logger.info("✅ DeepZoom background processor started successfully")
            else:
                logger.info("ℹ️ DeepZoom background processor already running")
                
        except Exception as deepzoom_error:
            logger.error(f"❌ Failed to start DeepZoom background processor: {deepzoom_error}")
            logger.warning("⚠️ Application will continue but DeepZoom tiles processing may not work")
            # Continue with application startup despite DeepZoom failure
        
        # Avvia il servizio di verifica periodica tiles
        logger.info("🔄 Starting tiles verification service...")
        try:
            from app.services.tiles_verification_service import tiles_verification_service
            await tiles_verification_service.start_periodic_verification()
            logger.info("✅ Tiles verification service started")
        except Exception as tiles_error:
            logger.error(f"❌ Failed to start tiles verification service: {tiles_error}")
            logger.warning("⚠️ Application will continue but tiles verification may not work")
        
        # Avvia il servizio di monitoring delle performance
        logger.info("🔄 Starting performance monitoring service...")
        try:
            from app.services.performance_monitoring_service import performance_monitoring_service
            await performance_monitoring_service.start_monitoring()
            logger.info("✅ Performance monitoring service started")
        except Exception as perf_error:
            logger.error(f"❌ Failed to start performance monitoring service: {perf_error}")
            logger.warning("⚠️ Application will continue but performance monitoring may not work")
        
        # Initialize queue service and register handlers
        if settings.queue_enabled:
            logger.info("🔄 Starting request queue service...")
            try:
                from app.services.request_queue_service import request_queue_service
                await request_queue_service.start()

                # CRITICAL: Wait a moment for service to fully start
                await asyncio.sleep(0.1)

                # Register queue handlers AFTER service is started
                from app.middleware.queue_middleware import register_queue_handlers
                register_queue_handlers()

                # Register photo upload handler
                from app.routes.api.sites_photos import process_queued_upload
                request_queue_service.register_handler('POST_/api/site/{site_id}/photos/upload', process_queued_upload)

                # Register bulk upload handler
                from app.middleware.queue_middleware import bulk_upload_request_handler
                request_queue_service.register_handler('POST_/api/site/{site_id}/photos/bulk-upload', bulk_upload_request_handler)

                # Register deep zoom processing handler
                from app.services.deep_zoom_background_service import deep_zoom_background_service
                if hasattr(deep_zoom_background_service, 'process_queued_deep_zoom'):
                    request_queue_service.register_handler('POST_/api/site/{site_id}/photos/deep-zoom/start-background', deep_zoom_background_service.process_queued_deep_zoom)

                logger.info(f"✅ Request queue service started with {len(request_queue_service.request_handlers)} handlers")
            except Exception as queue_error:
                logger.error(f"❌ Failed to start request queue service: {queue_error}")
                logger.warning("⚠️ Application will continue but request queue may not work")
        
        museum_name = getattr(settings, 'museum_name', 'Museo Archeologico')
        logger.info(f"🏺 {museum_name} - Sistema Archeologico avviato")
        logger.info(f"🔐 Cookie-based authentication enabled")
        logger.info(f"📊 Admin routes enabled")
        logger.info(f"🚀 Deep zoom background processor started")
        logger.info(f"🔍 Tiles verification service started")
        if settings.queue_enabled:
            logger.info(f"📋 Request queue system enabled")
        logger.info("✅ FastZoom application initialization completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Critical error during application startup: {e}")
        logger.error("❌ Application startup failed - cannot continue")
        raise



