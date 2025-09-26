from typing import List
from uuid import UUID
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from loguru import logger


# 🆕 NUOVI IMPORT: Sistema archeologico multi-sito
#from app.database.session import get_async_session

from app.models.users import User, UserProfile, Role, UserActivity
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission, PermissionLevel


# 🆕 NUOVI IMPORT: Sicurezza multi-sito
from app.core.security import get_current_user_id, get_current_user_sites
from app.core.config import get_settings
from app.routes.api.auth import router as auth_api_router

from app.database.db import User, create_db_and_tables
#from app.database.security import auth_backend, current_active_user, fastapi_users
from app.exception import http_exception_handler
###from app.routes.view.group import group_view_route

# importing the route

###from app.routes.view.role import role_view_route
from app.routes.view.upload import upload_view_route
from app.routes.view.user import user_view_route
from app.schema.users import UserCreate, UserRead, UserUpdate

from fastapi_csrf_protect import CsrfProtect

from app.core.csrf_settings import CsrfSettings



# 🆕 NUOVO: Import template per route view
try:
    from app.routes.view.login import login_view_route
    LOGIN_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Login view route not found")
    LOGIN_ROUTE_EXISTS = False

try:
    from app.routes.view.upload import upload_view_route
    UPLOAD_ROUTE_EXISTS = True
except ImportError:
    logger.warning("Upload view route not found")
    UPLOAD_ROUTE_EXISTS = False

try:
    from app.routes.view.user import user_view_route
    USER_ROUTE_EXISTS = True
except ImportError:
    logger.warning("User view route not found")
    USER_ROUTE_EXISTS = False

# Configurazione app
settings = get_settings()



app = FastAPI(exception_handlers={HTTPException: http_exception_handler})
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# 🆕 NUOVO: Include route API archeologiche
app.include_router(auth_api_router, tags=["Authentication Multi-Sito"])

# ✅ CONDIZIONALI: Include route view solo se esistono
if LOGIN_ROUTE_EXISTS:
    app.include_router(login_view_route, tags=["Pages", "Authentication"])

if UPLOAD_ROUTE_EXISTS:
    app.include_router(upload_view_route, tags=["Pages", "Upload"])

if USER_ROUTE_EXISTS:
    app.include_router(user_view_route, tags=["Pages", "User Management"])


# In app.py - temporaneo per debug
@app.get("/dashboard-debug")
async def dashboard_debug():
    """Dashboard senza autenticazione per test"""
    return {"message": "Dashboard accessibile senza auth", "status": "debug"}

@app.get("/cookie-test")
async def cookie_test(request: Request):
    """Test per vedere i cookie ricevuti"""
    cookies = dict(request.cookies)
    return {"cookies": cookies, "headers": dict(request.headers)}

# 🆕 NUOVO: Route principale dashboard archeologica
@app.get("/")
async def home_redirect():
    """Redirect alla pagina di login"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")

@app.get("/dashboard")
async def archaeological_dashboard(
    request: Request,  # Aggiungi questo
    current_user_id: UUID = None,
    user_sites: List = None
):
    """Dashboard principale sistema archeologico"""
    
    # Try to get auth info, fallback if not authenticated
    try:
        from app.core.security import get_current_user_id, get_current_user_sites
        current_user_id = await get_current_user_id(request)
        user_sites = await get_current_user_sites(request)
    except HTTPException:
        # Not authenticated - redirect to login
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    
    print("ciao - user authenticated")
    return {
        "message": f"Benvenuto nel sistema archeologico!",
        "user_id": str(current_user_id),
        "sites_accessible": len(user_sites) if user_sites else 0,
        "sites": user_sites or [],
        "museum_name": settings.museum_name
    }


@app.get("/site-selection")
async def site_selection_page(
    current_user_id = Depends(get_current_user_id),
    user_sites = Depends(get_current_user_sites)
):
    """Pagina selezione sito per utenti multi-sito"""
    if not user_sites:
        raise HTTPException(status_code=403, detail="Nessun sito accessibile")
    
    return templates.TemplateResponse(
        "auth/site_selection.html",
        {
            "request": {},  # Sarà riempito dal template
            "sites": user_sites,
            "sites_count": len(user_sites),
            "museum_name": settings.museum_name
        }
    )

@app.get("/health")
async def health_check():
    """Health check per monitoraggio sistema"""
    return {
        "status": "ok",
        "system": "archaeological_catalog",
        "version": "1.0.0",
        "multi_site_enabled": settings.site_selection_enabled
    }

# 🆕 NUOVO: Route info sistema
@app.get("/info")
async def system_info():
    """Informazioni sistema archeologico"""
    return {
        "museum_name": settings.museum_name,
        "catalog_version": settings.catalog_version,
        "max_photo_size_mb": settings.max_photo_size_mb,
        "supported_formats": settings.supported_formats_list,
        "thumbnail_sizes": settings.thumbnail_sizes_list,
        "multi_site_enabled": settings.site_selection_enabled
    }

# 🆕 NUOVO: Startup event per sistema archeologico
@app.on_event("startup")
async def on_startup():
    """Inizializzazione sistema archeologico"""
    try:
        # Crea tabelle database
        await create_db_and_tables()
        
        logger.info(f"🏺 {settings.museum_name} - Sistema Archeologico avviato")
        logger.info(f"📁 Max foto size: {settings.max_photo_size_mb}MB")
        logger.info(f"🖼️ Formati supportati: {settings.supported_formats}")
        logger.info(f"🏛️ Multi-sito abilitato: {settings.site_selection_enabled}")
        
        # Verifica connessione MinIO (opzionale)
        if settings.minio_url:
            logger.info(f"💾 MinIO configurato: {settings.minio_url}")
            
    except Exception as e:
        logger.error(f"❌ Errore avvio sistema archeologico: {e}")
        raise

@app.on_event("shutdown")
async def on_shutdown():
    """Chiusura sistema archeologico"""
    logger.info(f"🏺 {settings.museum_name} - Sistema Archeologico arrestato")

# 🆕 NUOVO: CSRF Protection per forms HTMX
@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()

# 🆕 NUOVO: Dependency per template context
async def get_template_context():
    """Context globale per template"""
    return {
        "museum_name": settings.museum_name,
        "catalog_version": settings.catalog_version,
        "multi_site_enabled": settings.site_selection_enabled
    }

# app.include_router(
#     fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
# )

# app.include_router(
#     fastapi_users.get_register_router(UserRead, UserCreate),
#     prefix="/auth",
#     tags=["auth"],
# )
# app.include_router(
#     fastapi_users.get_reset_password_router(),
#     prefix="/auth",
#     tags=["auth"],
# )
# app.include_router(
#     fastapi_users.get_verify_router(UserRead),
#     prefix="/auth",
#     tags=["auth"],
# )
# app.include_router(
#     fastapi_users.get_users_router(UserRead, UserUpdate),
#     prefix="/users",
#     tags=["users"],
# )


app.include_router(login_view_route, tags=["Pages", "Authentication/Create"])
#app.include_router(role_view_route, tags=["Pages", "Role"])
#app.include_router(group_view_route, tags=["Pages", "Group"])
app.include_router(user_view_route, tags=["Pages", "User"])
app.include_router(upload_view_route, tags=["Pages", "Upload"])


@app.get("/authenticated-route")
#async def authenticated_route(user: User = Depends(current_active_user)):
#    logger.info(user.id)
#    return {"message": f"Hello {user.email}!"}


@app.on_event("startup")
async def on_startup():
    # Not needed if you setup a migration system like Alembic
    await create_db_and_tables()
    # await create_superuser()
    logger.info("Application started")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Application shutdown")


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()
