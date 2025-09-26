# app/routes/view/login.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_csrf_protect import CsrfProtect
from loguru import logger

from app.templates import templates

login_view_route = APIRouter()

def _get_csrf_tokens_or_fallback():
    """
    Genera token CSRF se la configurazione è disponibile,
    altrimenti fornisce un fallback non bloccante.
    """
    try:
        # Usa CsrfProtect se correttamente configurato dall'app
        csrf_protect = CsrfProtect()
        csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
        return csrf_token, signed_token, csrf_protect
    except Exception as e:
        logger.warning(f"CSRF not available, falling back: {e}")
        return "csrf-disabled", None, None

@login_view_route.get(
    "/",
    summary="Home → redirect a /login",
)
async def index_redirect():
    return RedirectResponse("/login", status_code=302)

@login_view_route.get(
    "/login",
    summary="Pagina di login",
    response_class=HTMLResponse,
)
async def get_login(request: Request):
    """
    Rende la pagina di login.
    Non usa fastapi-users né cookie legacy.
    CSRF è opzionale: se non configurato, non blocca la pagina.
    """
    current_page = request.url.path.split("/")[-1]
    csrf_token, signed_token, csrf_protect = _get_csrf_tokens_or_fallback()

    context = {
        "request": request,
        "current_page": current_page,
        "csrf_token": csrf_token,
    }

    response = templates.TemplateResponse("pages/login.html", context)

    # Se CSRF è disponibile, imposta il cookie firmato
    if csrf_protect and signed_token:
        csrf_protect.set_csrf_cookie(signed_token, response)

    return response

@login_view_route.get(
    "/register",
    summary="Pagina di registrazione",
    response_class=HTMLResponse,
)
async def get_register(request: Request):
    """
    Rende la pagina di registrazione (solo view).
    Nessuna dipendenza da fastapi-users.
    """
    current_page = request.url.path.split("/")[-1]
    context = {
        "request": request,
        "current_page": current_page,
    }
    return templates.TemplateResponse("pages/register.html", context)

# IMPORTANTE: questa view NON deve definire /dashboard
# La dashboard autenticata è gestita dall'app API principale (app.py)
# che legge l'access_token dal cookie tramite le dependency in app.core.security.
