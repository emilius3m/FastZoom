"""/routes/api/v1/auth.py
API v1 - Authentication & Authorization
Endpoints per autenticazione, registrazione, gestione token e profilo utente.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID, uuid4
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel
from datetime import datetime

# Dependencies - Use blacklist versions for consistency with API routes
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.session import get_async_session
from app.core.config import get_settings
from app.core.security import current_active_user
from app.models import User, UserActivity, TokenBlacklist

# Get settings instance
settings = get_settings()

# Import existing auth dependencies and functions
from app.services.auth_service import AuthService
from app.core.security import SecurityService
from app.models.user_profiles import UserProfile as UserProfileModelDB
from app.routes.view.view_crud import SQLAlchemyCRUD
from fastapi import Depends, Form, Body
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
import nh3

# CRUD instances for user operations
user_crud = SQLAlchemyCRUD[User](User)
user_profile_crud = SQLAlchemyCRUD[UserProfileModelDB](UserProfileModelDB)

# ===== PYDANTIC SCHEMAS =====

class LoginRequest(BaseModel):
    """Schema per login JSON (API/script)"""
    username: str  # Email o username
    password: str


class LoginResponse(BaseModel):
    """Schema risposta login JSON"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    """Schema refresh token"""
    refresh_token: str


class RefreshResponse(BaseModel):
    """Schema risposta refresh"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfoResponse(BaseModel):
    """Schema info utente"""
    id: str
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    last_login_at: Optional[datetime]
    sites: List[Dict[str, Any]]

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

# NUOVI ENDPOINTS V1

@router.post("/login", response_class=HTMLResponse, summary="Login con redirect intelligente", tags=["Authentication"])
async def v1_login(
    request: Request,
    response: Response,
    email: str = Form(),
    password: str = Form(),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Login endpoint con redirect intelligente multi-sito.
    
    Comportamento:
    - 1 sito: redirect diretto a dashboard
    - Più siti: redirect a selezione sito
    - 0 siti: errore accesso negato
    """
    try:
        # Autentica utente
        user = await AuthService.authenticate_user(db, email, password)
        
        if not user:
            # Risposta HTML per errore autenticazione
            return HTMLResponse(
                content='''
                <div class="alert alert-danger" role="alert">
                    <strong>Errore:</strong> Credenziali non valide. Verifica email e password.
                </div>
                ''',
                status_code=401
            )
        
        logger.info(f"User authenticated: {user.id}")

        # Aggiorna ultimo accesso
        await user.update_last_login(db)

        # Ottieni siti accessibili per l'utente
        sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)
        logger.info(f"User sites: {len(sites_data) if sites_data else 0}")

        # 🔧 FIX: Allow authentication without blocking on site permissions
        # All authenticated users can get cookies, site access handled later
        if not sites_data:
            if user.is_superuser:
                logger.info("Superuser accessing system without sites - allowing access for configuration")
                # Per superuser senza siti, consentiamo l'accesso
            else:
                logger.info("User has no site permissions, but will receive authentication cookies")
                logger.info("User will need to be assigned site permissions by admin")
                # 🔧 CRITICAL FIX: Don't block authentication - allow users to get cookies
                # They can access admin or need site assignment from admin
                sites_data = []
        
        # Crea token JWT multi-sito
        token = SecurityService.create_site_aware_token(
            user_id=user.id,
            sites_data=sites_data
        )
        
        # Imposta cookie di autenticazione con logging dettagliato
        logger.info(f"🍪 [COOKIE_SET] Setting access_token cookie in v1_login")
        logger.info(f"🍪 [COOKIE_SET] Token preview: {token[:50]}...")
        logger.info(f"🍪 [COOKIE_SET] Cookie attributes: httponly=True, secure=False, samesite=lax, max_age={settings.jwt_expires_hours * 3600}, path=/")
        
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            secure=False,  # False per sviluppo locale
            samesite="lax",
            max_age=settings.jwt_expires_hours * 3600,
            path="/",
            domain=None  # Esplicito per consistenza
        )
        
        logger.info(f"🍪 [COOKIE_SET] Cookie set successfully")
        
        # Logica di redirect intelligente
        if len(sites_data) == 1:
            # Un solo sito: redirect diretto alla dashboard
            site_id = sites_data[0]["id"]
            return RedirectResponse(url=f"/site/{site_id}/dashboard", status_code=303)
        elif len(sites_data) > 1:
            # Più siti: redirect a selezione sito
            return RedirectResponse(url="/api/v1/auth/select-site", status_code=303)
        elif user.is_superuser and len(sites_data) == 0:
            # Superuser senza siti: redirect all'admin per creare siti e configurare
            return RedirectResponse(url="/admin/sites", status_code=303)

        return HTMLResponse(content="", status_code=200)
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return HTMLResponse(
            content='''
            <div class="alert alert-danger" role="alert">
                <strong>Errore del server:</strong> Si è verificato un errore durante l'autenticazione.
            </div>
            ''',
            status_code=500
        )

@router.post(
    "/login/json",
    response_model=LoginResponse,
    summary="Login API (JSON)",
    tags=["Authentication - API"]
)
async def v1_login_json(
    credentials: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Login endpoint per API/script Python con risposta JSON.
    
    Restituisce:
    - access_token: Token JWT per autenticazione API (15 min)
    - refresh_token: Token per rinnovare access_token (7 giorni)
    - user: Informazioni utente complete con siti
    
    Esempio uso:
    ```
    response = requests.post(
        "http://localhost:8000/api/v1/auth/login/json",
        json={"username": "user@user.com", "password": "user@user.com"}
    )
    tokens = response.json()
    access_token = tokens["access_token"]
    ```
    """
    try:
        # Autentica utente
        user = await AuthService.authenticate_user(db, credentials.username, credentials.password)
        
        if not user:
            # Skip logging failed login attempts without user_id to avoid NOT NULL constraint
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username o password non corretti",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verifica utente attivo
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Utente disabilitato. Contatta l'amministratore."
            )
        
        # Genera JWT tokens
        jti = str(uuid4())  # Unique token ID per revoca
        
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "jti": jti
        }
        
        access_token = SecurityService.create_access_token(token_data)
        refresh_token = SecurityService.create_refresh_token(token_data)
        
        # Aggiorna ultimo login
        user.last_login_at = datetime.utcnow()
        await db.commit()
        
        # Log login riuscito
        await UserActivity.log_login(db, user.id, success=True, ip_address=request.client.host)
        
        # Ottieni siti utente
        user_sites = await AuthService.get_user_sites_with_permissions(db, user.id)
        
        logger.info(f"Login API riuscito per {user.email} da {request.client.host}")
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "sites": user_sites,
                "sites_count": len(user_sites)
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore login JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante il login: {str(e)}"
        )

# ===== REFRESH TOKEN =====

@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh Access Token",
    tags=["Authentication - API"]
)
async def v1_refresh_token(
    refresh_request: RefreshRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Rinnova access token usando refresh token.
    
    Quando l'access token scade (dopo 15 minuti), usa questo endpoint
    per ottenere un nuovo access token senza dover rifare login.
    
    Il refresh token dura 7 giorni.
    
    Esempio uso:
    ```
    response = requests.post(
        "http://localhost:8000/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    new_access_token = response.json()["access_token"]
    ```
    """
    try:
        # Decodifica refresh token
        payload = SecurityService.decode_token(refresh_request.refresh_token)
        
        # Verifica che sia refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token non valido. Usa un refresh token."
            )
        
        # Verifica blacklist
        jti = payload.get("jti")
        if jti:
            blacklisted = await db.execute(
                select(TokenBlacklist).where(TokenBlacklist.token_jti == jti)
            )
            if blacklisted.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token revocato. Esegui nuovo login."
                )
        
        # Estrai user_id
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token non valido"
            )
        
        # Verifica che utente esista e sia attivo
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utente non trovato"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Utente disabilitato"
            )
        
        # Genera nuovo access token (mantieni stesso jti per revoca)
        new_access_token = SecurityService.create_access_token({
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "jti": jti
        })
        
        logger.info(f"Access token rinnovato per {user.email}")
        
        return RefreshResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore refresh token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Refresh token non valido: {str(e)}"
        )

@router.post("/register", summary="Registra nuovo utente", tags=["Authentication"])
async def v1_register(
    request: Request,
    response: Response,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_session)
):
    """Register endpoint per nuovi utenti (JSON API)"""
    try:
        # Debug: log incoming data
        logger.info(f"Registration request data: {data}")
        
        email = data.get("email")
        password = data.get("password")
        first_name = data.get("first_name")
        last_name = data.get("last_name")

        if not email or not password:
            return JSONResponse(
                status_code=422,
                content={"detail": "Email and password are required"}
            )

        # Check if user already exists
        existing_user = await db.execute(
            select(User).where(User.email == email)
        )
        if existing_user.scalar_one_or_none():
            return JSONResponse(
                status_code=400,
                content={"detail": "Un account con questa email è già registrato."}
            )

        # Hash password
        hashed_password = SecurityService.get_password_hash(password)

        # Generate default values for required fields if not provided
        if not first_name:
            first_name = email.split("@")[0].capitalize()
        if not last_name:
            last_name = "User"
        
        full_name = f"{first_name} {last_name}"

        # Create new user
        user = User(
            id=str(uuid4()),  # Convert UUID to string for SQLite compatibility
            email=email,
            username=email.split("@")[0],  # Generate username from email
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
            is_verified=False  # Require admin verification or email confirmation
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create user profile with first_name and last_name
        profile = UserProfileModelDB(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name
        )
        db.add(profile)
        await db.commit()

        logger.info(f"User registered successfully: {user.id}")

        return JSONResponse(
            status_code=201,
            content={"message": "User created successfully"}
        )

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Si è verificato un errore durante la registrazione."}
        )

@router.post("/token", response_class=JSONResponse, summary="OAuth2 Token", tags=["Authentication"])
async def v1_oauth2_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_session)
):
    """Endpoint OAuth2 standard per login JavaScript/API"""
    try:
        logger.info(f"OAuth2 login attempt: {form_data.username}")
        
        # Autentica utente (OAuth2 usa 'username' ma accetta email)
        user = await AuthService.authenticate_user(db, form_data.username, form_data.password)
        
        if not user:
            logger.info("Authentication failed: user not found or invalid password")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect username or password"
            )
        
        logger.info(f"User authenticated: {user.id}, superuser: {user.is_superuser}")

        # Aggiorna ultimo accesso
        await user.update_last_login(db)

        # Ottieni siti per l'utente usando il metodo unificato
        sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)

        logger.info(f"Sites found: {len(sites_data) if sites_data else 0}")

        # 🔧 FIX: Authentication should not be blocked by site permissions
        # Allow all authenticated users to receive cookies, then handle site access later
        if not sites_data:
            if user.is_superuser:
                logger.info("Superuser accessing system without sites - allowing access for configuration")
                # Per superuser senza siti, creiamo una lista vuota ma consentiamo l'accesso
                sites_data = []
            else:
                logger.info("User has no site permissions, but will receive authentication cookies")
                logger.info("Site access will be verified per-request later")
                # 🔧 CRITICAL FIX: Don't block authentication - allow users to get cookies
                # Site-specific access control happens at the resource level, not at authentication level
                sites_data = []
        
        # Crea token JWT multi-sito
        token = SecurityService.create_site_aware_token(
            user_id=user.id,
            sites_data=sites_data
        )
        
        logger.info("Token created successfully")
        
        # Imposta cookie HttpOnly con logging dettagliato
        logger.info(f"🍪 [COOKIE_SET] Setting access_token cookie in v1_oauth2_token")
        logger.info(f"🍪 [COOKIE_SET] Token preview: {token[:50]}...")
        logger.info(f"🍪 [COOKIE_SET] Cookie attributes: httponly=True, secure=False, samesite=lax, max_age={settings.jwt_expires_hours * 3600}, path=/, domain=None")
        
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            secure=False,  # False per sviluppo locale, True per produzione
            samesite="lax",
            max_age=settings.jwt_expires_hours * 3600,
            path="/",
            domain=None  # Esplicito per consistenza
        )
        
        logger.info(f"🍪 [COOKIE_SET] OAuth2 cookie set successfully")
        
        # Ritorna 204 No Content come si aspetta il JavaScript
        response.status_code = 204
        return None
        
    except HTTPException as e:
        logger.error(f"HTTP Exception in OAuth2 login: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"OAuth2 login error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/select-site", summary="Selezione sito", tags=["Authentication"])
async def v1_select_site(
    request: Request,
    response: Response,
    site_id: UUID = Form(),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Selezione sito specifico dopo login multi-sito"""
    try:
        # Verifica che il sito selezionato sia tra quelli accessibili
        site_ids = [UUID(site["id"]) for site in user_sites]
        
        if site_id not in site_ids:
            return HTMLResponse(
                content='''
                <div class="alert alert-danger" role="alert">
                    <strong>Errore:</strong> Non hai i permessi per accedere a questo sito.
                </div>
                ''',
                status_code=403
            )
        
        # Trova i dati del sito selezionato
        selected_site = next(
            (site for site in user_sites if UUID(site["id"]) == site_id),
            None
        )
        
        if not selected_site:
            return HTMLResponse(
                content='''
                <div class="alert alert-danger" role="alert">
                    <strong>Errore:</strong> Sito non trovato.
                </div>
                ''',
                status_code=404
            )
        
        # Aggiorna cookie con sito selezionato (opzionale) con logging
        logger.info(f"🍪 [COOKIE_SET] Setting selected_site_id cookie in v1_select_site")
        logger.info(f"🍪 [COOKIE_SET] Site ID: {site_id}")
        logger.info(f"🍪 [COOKIE_SET] Cookie attributes: httponly=True, secure=False, samesite=lax, max_age={settings.jwt_expires_hours * 3600}, path=/")
        
        response.set_cookie(
            key="selected_site_id",
            value=str(site_id),
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=settings.jwt_expires_hours * 3600,
            path="/",
            domain=None  # Esplicito per consistenza
        )
        
        logger.info(f"🍪 [COOKIE_SET] Selected site cookie set successfully")
        
        # Redirect alla dashboard del sito selezionato
        return RedirectResponse(url=f"/site/{site_id}/dashboard", status_code=303)
        
    except Exception as e:
        logger.error(f"Site selection error: {e}")
        return HTMLResponse(
            content='''
            <div class="alert alert-danger" role="alert">
                <strong>Errore del server:</strong> Si è verificato un errore durante la selezione del sito.
            </div>
            ''',
            status_code=500
        )

@router.post("/logout", summary="Logout", tags=["Authentication"])
async def v1_logout(request: Request, response: Response, db: AsyncSession = Depends(get_async_session)):
    """Logout dell'utente corrente"""
    logger.info("Logout endpoint called")
    # DEBUG: stampa l'origine della richiesta
    referer = request.headers.get("referer", "unknown")
    user_agent = request.headers.get("user-agent", "unknown")
    logger.info(f"LOGOUT CALLED FROM: {referer}")
    logger.info(f"USER AGENT: {user_agent}")

    """
    Logout utente - invalida token server-side, rimuove cookie e redirect a login
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

        # IMPORTANTE: Usa gli STESSI attributi usati per impostare il cookie
        logger.info(f"🍪 [COOKIE_DELETE] Deleting cookies in v1_logout")
        logger.info(f"🍪 [COOKIE_DELETE] Cookie attributes for deletion: path=/, secure=False, samesite=lax, httponly=True, domain=None")
        
        response.delete_cookie(
            key="access_token",
            path="/",
            secure=False,  # Stesso valore usato nel login
            samesite="lax",  # Stesso valore usato nel login
            httponly=True,   # Stesso valore usato nel login
            domain=None      # Stesso valore usato nel login
        )
        response.delete_cookie(
            key="selected_site_id",
            path="/",
            secure=False,
            samesite="lax",
            httponly=True,
            domain=None
        )

        logger.info(f"🍪 [COOKIE_DELETE] Cookies deleted successfully with matching attributes")

        return JSONResponse(content={"success": True, "redirect": "/login"}, status_code=200)

    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.get("/me", summary="Info utente corrente", tags=["Authentication"])
async def v1_me(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Ottieni informazioni utente corrente e siti accessibili"""
    return JSONResponse(content={
        "user_id": str(current_user_id),
        "sites": user_sites,
        "total_sites": len(user_sites)
    })

@router.post("/users/{user_id}/update", summary="Aggiorna profilo utente", tags=["Authentication"])
async def v1_update_user(
    user_id: str,
    first_name: str = Form(None),
    last_name: str = Form(None),
    gender: str = Form(None),
    dob: str = Form(None),
    city: str = Form(None),
    country: str = Form(None),
    address: str = Form(None),
    phone: str = Form(None),
    company: str = Form(None),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
):
    """API endpoint to update user profile information"""
    try:
        # Convert string user_id to UUID
        try:
            target_user_id = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )

        # Check permissions: allow self-update or superuser
        if target_user_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this user profile"
            )

        # Sanitize input data using nh3
        sanitized_data = {}
        form_data = {
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "date_of_birth": dob,
            "city": city,
            "country": country,
            "address": address,
            "phone": phone,
            "company": company
        }

        for field, value in form_data.items():
            if value is not None and value != "":
                if field == "date_of_birth" and value:
                    # Handle date parsing
                    try:
                        sanitized_data[field] = datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid date format. Use YYYY-MM-DD"
                        )
                else:
                    # Sanitize string fields
                    sanitized_data[field] = nh3.clean(str(value))

        # Check if user already has a profile
        existing_profile = await user_profile_crud.read_by_column(db, "user_id", target_user_id)

        if existing_profile is None:
            # Create new UserProfile
            new_profile = await user_profile_crud.create({
                "user_id": str(target_user_id),  # Convert UUID to string for SQLite compatibility
                **sanitized_data
            }, db)

            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "message": "User profile created successfully",
                    "profile_id": str(new_profile.id),
                    "user_id": str(target_user_id)
                }
            )

        else:
            # Update existing user profile
            updated_profile = await user_profile_crud.update(
                db, existing_profile.id, sanitized_data
            )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "message": "User profile updated successfully",
                    "profile_id": str(updated_profile.id),
                    "user_id": str(target_user_id)
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user profile: {str(e)}"
        )

# ENDPOINTS DEBUG

@router.get("/debug/cookie-test", summary="Debug Cookie Test", tags=["Authentication - Debug"])
async def v1_debug_cookie_test(request: Request):
    """Endpoint di debug per vedere i cookie ricevuti"""
    return {
        "cookies": dict(request.cookies),
        "headers": dict(request.headers),
        "method": request.method,
        "url": str(request.url)
    }

@router.get("/debug/token-test", summary="Debug Token Test", tags=["Authentication - Debug"])
async def v1_debug_token_test(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """Test parsing token dal cookie"""
    try:
        access_token_cookie = request.cookies.get("access_token")
        if not access_token_cookie:
            return {"error": "No access_token cookie found"}
        
        # Rimuovi "Bearer " prefix se presente
        token = access_token_cookie.replace("Bearer ", "")
        
        # Verifica token
        payload = await SecurityService.verify_token(token, db)
        
        return {
            "token_found": True,
            "payload": payload,
            "user_id": payload.get("sub"),
            "sites_count": len(payload.get("sites", []))
        }
    except Exception as e:
        return {
            "error": str(e),
            "token_found": access_token_cookie is not None,
            "raw_cookie": access_token_cookie
        }

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API", tags=["Authentication - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/auth/login": "/api/v1/auth/login",
                "/auth/register": "/api/v1/auth/register",
                "/auth/token": "/api/v1/auth/token",
                "/auth/select-site": "/api/v1/auth/select-site",
                "/auth/logout": "/api/v1/auth/logout",
                "/auth/me": "/api/v1/auth/me"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints per dominio",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints"
        }
    }