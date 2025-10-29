from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime
import nh3
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Response, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.database.session import get_async_session
from app.services.auth_service import AuthService
from app.core.security import get_current_user_id, get_current_user_sites, SecurityService, current_active_user
from app.core.config import get_settings
from app.models import User
from app.models.user_profiles import UserProfile as UserProfileModelDB
from app.routes.view.view_crud import SQLAlchemyCRUD

settings = get_settings()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

router = APIRouter(prefix="/auth", tags=["Authentication"])

# CRUD instances for user operations
user_crud = SQLAlchemyCRUD[User](User)
user_profile_crud = SQLAlchemyCRUD[UserProfileModelDB](UserProfileModelDB)

@router.post("/login", response_class=HTMLResponse, summary="[DEPRECATED] Login", tags=["Authentication - Deprecated"])
async def login(
    request: Request,
    response: Response,
    email: str = Form(),
    password: str = Form(),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Login endpoint con redirect intelligente multi-sito Comportamento:
    - 1 sito: redirect diretto a dashboard
    - Più siti: redirect a selezione sito
    - 0 siti: errore accesso negato
    """
    try:
        # Autentica utente
        user = await AuthService.authenticate_user(db, email, password)
        
        if not user:
            # Risposta HTMX per errore autenticazione
            return HTMLResponse(
                content='''
                <div class="alert alert-danger" role="alert">
                    <strong>Errore:</strong> Credenziali non valide. Verifica email e password.
                </div>
                ''',
                status_code=401
            )
        
        print(f"User authenticated: {user.id}")

        # Aggiorna ultimo accesso
        await user.update_last_login(db)

        # Ottieni siti accessibili per l'utente
        sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)
        print(f"User sites: {len(sites_data) if sites_data else 0}")

        # Verifica accesso ai siti (eccetto per superuser che può accedere per configurare)
        if not sites_data:
            if user.is_superuser:
                print("Superuser accessing system without sites - allowing access for configuration")
                # Per superuser senza siti, consentiamo l'accesso
            else:
                # Nessun sito accessibile
                return HTMLResponse(
                    content='''
                    <div class="alert alert-warning" role="alert">
                        <strong>Accesso negato:</strong> Il tuo account non ha permessi per accedere ad alcun sito.
                    </div>
                    ''',
                    status_code=403
                )
        
        # Crea token JWT multi-sito
        token = SecurityService.create_site_aware_token(
            user_id=user.id,
            sites_data=sites_data
        )
        
        # Imposta cookie di autenticazione
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            secure=False,  # False per sviluppo locale
            samesite="lax",
            max_age=settings.jwt_expires_hours * 3600,
            path="/"
        )
        
        # Logica di redirect intelligente
        if len(sites_data) == 1:
            # Un solo sito: redirect diretto alla dashboard
            site_id = sites_data[0]["id"]
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=f"/site/{site_id}/dashboard", status_code=303)
        elif len(sites_data) > 1:
            # Più siti: redirect a selezione sito
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/auth/select-site", status_code=303)
        elif user.is_superuser and len(sites_data) == 0:
            # Superuser senza siti: redirect all'admin per creare siti e configurare
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/admin/sites", status_code=303)

        response = HTMLResponse(content="", status_code=200)
        add_deprecation_headers(response, "/api/v1/auth/login")
        return response
        
    except Exception as e:
        logger.warning(f"Legacy login endpoint used - deprecated")
        response = HTMLResponse(
            content='''
            <div class="alert alert-danger" role="alert">
                <strong>Errore del server:</strong> Si è verificato un errore durante l'autenticazione.
            </div>
            ''',
            status_code=500
        )
        add_deprecation_headers(response, "/api/v1/auth/login")
        return response


@router.post("/register", summary="[DEPRECATED] Register", tags=["Authentication - Deprecated"])
async def register(
    request: Request,
    response: Response,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Register endpoint per nuovi utenti (JSON API)
    Accetta {email, password} dal frontend JS, crea utente e ritorna JSON
    """
    try:
        # Debug: log incoming data
        print(f"Registration request data: {data}")
        
        email = data.get("email")
        password = data.get("password")
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")

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

        # Create new user
        user = User(
            email=email,
            username=email.split("@")[0],  # Generate username from email
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_superuser=False,
            is_verified=False  # Require admin verification or email confirmation
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        print(f"User registered successfully: {user.id}")

        response = JSONResponse(
            status_code=201,
            content={"message": "User created successfully"}
        )
        add_deprecation_headers(response, "/api/v1/auth/register")
        return response

    except Exception as e:
        logger.warning(f"Legacy register endpoint used - deprecated")
        response = JSONResponse(
            status_code=500,
            content={"detail": "Si è verificato un errore durante la registrazione."}
        )
        add_deprecation_headers(response, "/api/v1/auth/register")
        return response

@router.post("/token", response_class=JSONResponse, summary="[DEPRECATED] OAuth2 Token", tags=["Authentication - Deprecated"])
async def login_oauth2(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Endpoint OAuth2 standard per login JavaScript/API
    Ritorna 204 No Content + cookie su successo
    Compatibile con il frontend JavaScript esistente che si aspetta 204
    """
    try:
        print(f"OAuth2 login attempt: {form_data.username}")
        
        # Autentica utente (OAuth2 usa 'username' ma accetta email)
        user = await AuthService.authenticate_user(db, form_data.username, form_data.password)
        
        if not user:
            print("Authentication failed: user not found or invalid password")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect username or password"
            )
        
        print(f"User authenticated: {user.id}, superuser: {user.is_superuser}")

        # Aggiorna ultimo accesso
        await user.update_last_login(db)

        # Ottieni siti per l'utente usando il metodo unificato
        sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)

        print(f"Sites found: {len(sites_data) if sites_data else 0}")

        # Verifica che abbia almeno un sito (eccetto per superuser che può accedere per configurare)
        if not sites_data:
            if user.is_superuser:
                print("Superuser accessing system without sites - allowing access for configuration")
                # Per superuser senza siti, creiamo una lista vuota ma consentiamo l'accesso
                sites_data = []
            else:
                print("No sites accessible for user")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: no site permissions"
                )
        
        # Crea token JWT multi-sito
        token = SecurityService.create_site_aware_token(
            user_id=user.id,
            sites_data=sites_data
        )
        
        print("Token created successfully")
        
        # Imposta cookie HttpOnly
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            secure=False,  # False per sviluppo locale, True per produzione
            samesite="lax",
            max_age=settings.jwt_expires_hours * 3600,
            path="/",
            domain=None  # Lascia che FastAPI gestisca automaticamente
        )
        
        print("Cookie set successfully")
        
        # Ritorna 204 No Content come si aspetta il JavaScript
        response.status_code = 204
        add_deprecation_headers(response, "/api/v1/auth/token")
        return None
        
    except HTTPException as e:
        logger.warning(f"Legacy OAuth2 token endpoint used - deprecated")
        raise
    except Exception as e:
        logger.warning(f"Legacy OAuth2 token endpoint used - deprecated")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/select-site", summary="[DEPRECATED] Select Site", tags=["Authentication - Deprecated"])
async def select_site(
    request: Request,
    response: Response,
    site_id: UUID = Form(),
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Selezione sito specifico dopo login multi-sito
    Verifica che l'utente abbia accesso al sito selezionato
    """
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
        
        # Aggiorna cookie con sito selezionato (opzionale)
        response.set_cookie(
            key="selected_site_id",
            value=str(site_id),
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=settings.jwt_expires_hours * 3600,
            path="/"
        )
        
        # Redirect alla dashboard del sito selezionato
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url=f"/site/{site_id}/dashboard", status_code=303)
        add_deprecation_headers(response, "/api/v1/auth/select-site")
        return response
        
    except Exception as e:
        logger.warning(f"Legacy select-site endpoint used - deprecated")
        response = HTMLResponse(
            content='''
            <div class="alert alert-danger" role="alert">
                <strong>Errore del server:</strong> Si è verificato un errore durante la selezione del sito.
            </div>
            ''',
            status_code=500
        )
        add_deprecation_headers(response, "/api/v1/auth/select-site")
        return response



@router.post("/logout", summary="[DEPRECATED] Logout", tags=["Authentication - Deprecated"])
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_async_session)):
    logger.warning("Legacy logout endpoint used - deprecated")
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

                print(f"Token invalidated for user: {user_id}")

            except Exception as e:
                print(f"Could not invalidate token: {e}")
                # Continua comunque con il logout

        # IMPORTANTE: Usa gli STESSI attributi usati per impostare il cookie
        response.delete_cookie(
            key="access_token",
            path="/",
            secure=False,  # Stesso valore usato nel login
            samesite="lax",  # Stesso valore usato nel login
            httponly=True   # Stesso valore usato nel login
        )
        response.delete_cookie(
            key="selected_site_id",
            path="/",
            secure=False,
            samesite="lax",
            httponly=True
        )

        print("Cookies deleted with matching attributes")

        response = JSONResponse(content={"success": True, "redirect": "/login"}, status_code=200)
        add_deprecation_headers(response, "/api/v1/auth/logout")
        return response

    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )






# Remove duplicate/typo endpoint - use the main /auth/logout

@router.get("/me", summary="[DEPRECATED] Get Current User Info", tags=["Authentication - Deprecated"])
async def get_current_user_info(
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites)
):
    """
    Ottieni informazioni utente corrente e siti accessibili
    Utile per frontend che deve mostrare info utente/siti
    """
    response = JSONResponse(content={
        "user_id": str(current_user_id),
        "sites": user_sites,
        "total_sites": len(user_sites)
    })
    add_deprecation_headers(response, "/api/v1/auth/me")
    return response

# Endpoint di debug per test
@router.get("/debug/cookie-test")
async def debug_cookie_test(request: Request):
    """Endpoint di debug per vedere i cookie ricevuti"""
    return {
        "cookies": dict(request.cookies),
        "headers": dict(request.headers),
        "method": request.method,
        "url": str(request.url)
    }

@router.get("/debug/token-test")
async def debug_token_test(
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

@router.post("/post_update_user/{user_id}", summary="[DEPRECATED] Update User Profile", tags=["Authentication - Deprecated"])
async def post_update_user(
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
    """
    API endpoint to update user profile information.
    Allows users to update their own profile or superusers to update any profile.
    Accepts form data from HTMX.
    """
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
                "user_id": target_user_id,
                **sanitized_data
            }, db)

            response = JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "message": "User profile created successfully",
                    "profile_id": str(new_profile.id),
                    "user_id": str(target_user_id)
                }
            )
            add_deprecation_headers(response, f"/api/v1/auth/users/{user_id}/update")
            return response

        else:
            # Update existing user profile
            updated_profile = await user_profile_crud.update(
                db, existing_profile.id, sanitized_data
            )

            response = JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "message": "User profile updated successfully",
                    "profile_id": str(updated_profile.id),
                    "user_id": str(target_user_id)
                }
            )
            add_deprecation_headers(response, f"/api/v1/auth/users/{user_id}/update")
            return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user profile: {str(e)}"
        )
