from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.routing import APIRouter
from fastapi_csrf_protect import CsrfProtect

from app.database.security import current_active_user, verify_jwt
from app.models.users import User as UserModelDB
from app.templates import templates

# Create an APIRouter
login_view_route = APIRouter()


def _csrf_tokens_optional():
    """Prova a generare token CSRF; se non configurato, fallback non bloccante."""
    try:
        csrf = CsrfProtect()
        token, signed = csrf.generate_csrf_tokens()
        return token, signed, csrf
    except Exception as e:
        logger.warning(f"CSRF disabled/fallback: {e}")
        return "csrf-disabled", None, None

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
):
    """
    Dashboard autenticata:
    - legge access_token dal cookie (nuovo flusso)
    - genera CSRF opzionale
    - rende pages/dashboard.html
    """
    # CSRF opzionale
    csrf_token, signed_token, csrf = _csrf_tokens_optional()

    # Trova email/ruolo se disponibile in payload via /auth/me (opzionale) o lascia placeholder
    user_email = ""  # Popola se hai un endpoint/me che ritorna email
    user_type = "superuser" if any(s.get("permission_level") == "regional_admin" for s in user_sites) else "user"

    context = {
        "request": request,
        "title": "FastAPI-HTMX",
        "message": f"Welcome to FastAPI-HTMX! {user_email}",
        "cookie_value": "[access_token cookie]",  # Non mostrare il vero token per sicurezza
        "csrf_token": csrf_token,
        "user_type": user_type,
        "sites_count": len(user_sites),
        "sites": user_sites,
    }

    response = templates.TemplateResponse("pages/dashboard.html", context)

    # Se CSRF disponibile, imposta cookie firmato
    if csrf and signed_token:
        csrf.set_csrf_cookie(signed_token, response)

    return response


@login_view_route.get("/")
async def get_index(request: Request, csrf_protect: CsrfProtect = Depends()):
    cookies = request.cookies
    cookie_value = cookies.get("fastapiusersauth")
    if cookie_value is not None:
        if await verify_jwt(cookie_value):
            return RedirectResponse("/dashboard", status_code=302)
        else:
            return RedirectResponse("/login", status_code=302)
    else:
        return RedirectResponse("/login", status_code=302)


@login_view_route.get(
    "/login",
    summary="Gets the login page",
    tags=["Pages", "Authentication"],
    response_class=HTMLResponse,
)
async def get_login(
    request: Request,
    csrf_protect: CsrfProtect = Depends(),
):
    current_page = request.url.path.split("/")[-1]
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()

    context = {
        "request": request,
        "current_page": current_page,
        "csrf_token": csrf_token,
    }

    response = templates.TemplateResponse("pages/login.html", context)

    csrf_protect.set_csrf_cookie(signed_token, response)
    return response


@login_view_route.get(
    "/register",
    summary="Gets the login page",
    tags=["Pages", "Register USer"],
    response_class=HTMLResponse,
)
async def get_register(
    request: Request,
):
    current_page = request.url.path.split("/")[-1]
    context = {
        "request": request,
        "current_page": current_page,
    }
    return templates.TemplateResponse("pages/register.html", context)
