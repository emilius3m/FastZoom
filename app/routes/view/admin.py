"""
Admin View Routes - HTML Templates
Nuova implementazione che utilizza la API v1 per la gestione amministrativa.
Mantiene l'interfaccia web ma delega la logica alla API v1.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from uuid import UUID
from loguru import logger
from datetime import datetime
import httpx

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session
from app.templates import templates
from app.models import User
from app.models.user_profiles import UserProfile

# Base URL per la API v1
API_V1_BASE_URL = "http://127.0.0.1:8000/api/v1/admin"

admin_view_router = APIRouter(tags=["Admin - Views"])

# Helper function per creare il context base per tutti i template admin
async def get_admin_template_context(
    request: Request,
    current_user_id: UUID,
    user_sites: List[Dict[str, Any]],
    db: AsyncSession
) -> dict:
    """Crea il context base per tutti i template admin con tutte le variabili necessarie"""
    # Ottieni informazioni utente
    user = await db.execute(select(User).where(User.id == current_user_id))
    user = user.scalar_one_or_none()
    
    # 🔧 MENU LATERALE FIX: Crea un sito virtuale per le pagine admin per abilitare il menu laterale
    admin_site = {
        "id": "admin",
        "name": "Pannello Amministrazione",
        "location": "Sistema",
        "permission_level": "admin"
    }
    
    return {
        "request": request,
        # Variabili richieste da auth_navigation.html
        "sites": user_sites,
        "sites_count": len(user_sites) if user_sites else 0,
        "user_email": user.email if user else None,
        "user_type": "superuser" if user and user.is_superuser else "user",
        "current_site_name": user_sites[0]["name"] if user_sites else "Amministrazione",
        "current_page": request.url.path.split("/")[-1] or "admin",
        # 🔧 MENU LATERALE FIX: Aggiungi sito virtuale per attivare il menu laterale nelle pagine admin
        "site": admin_site,
        # Mantieni anche il primo sito reale se disponibile
        "first_site": user_sites[0] if user_sites else admin_site
    }

# Middleware per verificare che l'utente sia superuser
async def require_superuser(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    user = await db.execute(select(User).where(User.id == current_user_id))
    user = user.scalar_one_or_none()
    
    if not user or not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso negato: solo i superadmin possono accedere"
        )
    
    # Crea context completo
    context = await get_admin_template_context(request, current_user_id, user_sites, db)
    return user, context

# ===== GESTIONE SITI ARCHEOLOGICI =====

@admin_view_router.get("/admin/sites/", response_class=HTMLResponse)
async def admin_sites_list(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Lista siti archeologici per amministrazione"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per ottenere i dati
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.get(f"{API_V1_BASE_URL}/sites")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore nel caricamento dei dati"
                )
            
            api_data = response.json()
        
        context = {
            **base_context,
            "sites": api_data.get("sites", []),
            "count": api_data.get("count", 0)
        }
        
        return templates.TemplateResponse("admin/sites_list.html", context)
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.get("/admin/sites/new/", response_class=HTMLResponse)
async def admin_sites_new(
    request: Request,
    auth_data: tuple = Depends(require_superuser)
):
    """Form per nuovo sito archeologico"""
    superuser, base_context = auth_data
    
    context = {
        **base_context,
        "site": None,
        "action": "create",
    }
    
    return templates.TemplateResponse("admin/sites_form.html", context)

@admin_view_router.post("/admin/sites/new/")
async def admin_sites_create(
    request: Request,
    auth_data: tuple = Depends(require_superuser)
):
    """Crea nuovo sito archeologico"""
    superuser, base_context = auth_data
    
    try:
        # Get form data from request
        form_data = await request.form()
        
        # Prepara i dati per la API v1
        site_data = {
            "name": form_data.get("name", ""),
            "code": form_data.get("code", ""),
            "location": form_data.get("location"),
            "region": form_data.get("region"),
            "province": form_data.get("province"),
            "municipality": form_data.get("municipality"),
            "description": form_data.get("description"),
            "historical_period": form_data.get("historical_period"),
            "site_type": form_data.get("site_type"),
            "coordinates_lat": form_data.get("coordinates_lat"),
            "coordinates_lng": form_data.get("coordinates_lng"),
            "research_status": form_data.get("research_status"),
            "is_active": form_data.get("is_active") == "on",
            "is_public": form_data.get("is_public") == "on"
        }
        
        # Chiama la API v1 per creare il sito
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
         
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.post(f"{API_V1_BASE_URL}/sites", json=site_data)
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                # Torna al form con errore
                context = {
                    **base_context,
                    "site": site_data,
                    "action": "create",
                    "error": response.json().get("detail", "Errore nella creazione del sito")
                }
                return templates.TemplateResponse("admin/sites_form.html", context)
        
        return RedirectResponse(
            url="/admin/sites/?success=created",
            status_code=303
        )
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.get("/admin/site/{site_id}/edit/", response_class=HTMLResponse)
async def admin_sites_edit(
    request: Request,
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Form per modifica sito archeologico"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per ottenere i dati del sito
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.get(f"{API_V1_BASE_URL}/sites/{site_id}")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=404, detail="Sito non trovato")
            
            site_data = response.json().get("site", {})
        
        context = {
            **base_context,
            "site": site_data,
            "action": "edit",
        }
        
        return templates.TemplateResponse("admin/sites_form.html", context)
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.post("/admin/site/{site_id}/edit/")
async def admin_sites_update(
    site_id: UUID,
    name: str = Form(),
    code: str = Form(),
    location: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    province: Optional[str] = Form(None),
    municipality: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    historical_period: Optional[str] = Form(None),
    site_type: Optional[str] = Form(None),
    coordinates_lat: Optional[str] = Form(None),
    coordinates_lng: Optional[str] = Form(None),
    research_status: Optional[str] = Form(None),
    is_active: bool = Form(True),
    is_public: bool = Form(True),
    auth_data: tuple = Depends(require_superuser)
):
    """Aggiorna sito archeologico"""
    superuser, base_context = auth_data
    
    try:
        # Prepara i dati per la API v1
        site_data = {
            "name": name,
            "code": code,
            "location": location,
            "region": region,
            "province": province,
            "municipality": municipality,
            "description": description,
            "historical_period": historical_period,
            "site_type": site_type,
            "coordinates_lat": coordinates_lat,
            "coordinates_lng": coordinates_lng,
            "research_status": research_status,
            "is_active": is_active,
            "is_public": is_public
        }
        
        # Chiama la API v1 per aggiornare il sito
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.put(f"{API_V1_BASE_URL}/sites/{site_id}", json=site_data)
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                # Torna al form con errore
                context = {
                    **base_context,
                    "site": {**site_data, "id": str(site_id)},
                    "action": "edit",
                    "error": response.json().get("detail", "Errore nell'aggiornamento del sito")
                }
                return templates.TemplateResponse("admin/sites_form.html", context)
        
        return RedirectResponse(
            url="/admin/sites/?success=updated",
            status_code=303
        )
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

# ===== GESTIONE UTENTI =====

@admin_view_router.get("/admin/users/", response_class=HTMLResponse)
async def admin_users_list(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Lista utenti per amministrazione"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per ottenere i dati
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.get(f"{API_V1_BASE_URL}/users")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore nel caricamento dei dati"
                )
            
            api_data = response.json()
        
        context = {
            **base_context,
            "users": api_data.get("users", []),
            "count": api_data.get("count", 0)
        }
        
        return templates.TemplateResponse("admin/users_list.html", context)
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.get("/admin/users/new/", response_class=HTMLResponse)
async def admin_users_new(
    request: Request,
    auth_data: tuple = Depends(require_superuser)
):
    """Form per nuovo utente"""
    superuser, base_context = auth_data
    
    context = {
        **base_context,
        "user_data": None,
        "action": "create",
    }
    
    return templates.TemplateResponse("admin/users_form.html", context)

@admin_view_router.post("/admin/users/new/")
async def admin_users_create(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    is_superuser: bool = Form(False),
    is_active: bool = Form(True),
    auth_data: tuple = Depends(require_superuser)
):
    """Crea nuovo utente"""
    superuser, base_context = auth_data
    
    try:
        # Prepara i dati per la API v1
        user_data = {
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
            "is_superuser": is_superuser,
            "is_active": is_active
        }
        
        # Chiama la API v1 per creare l'utente
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.post(f"{API_V1_BASE_URL}/users", json=user_data)
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                # Torna al form con errore
                context = {
                    **base_context,
                    "user_data": user_data,
                    "action": "create",
                    "error": response.json().get("detail", "Errore nella creazione dell'utente")
                }
                return templates.TemplateResponse("admin/users_form.html", context)
        
        return RedirectResponse(
            url="/admin/users/?success=created",
            status_code=303
        )
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.get("/admin/users/{user_id}/edit/", response_class=HTMLResponse)
async def admin_users_edit(
    request: Request,
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Form per modifica utente"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per ottenere i dati dell'utente
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.get(f"{API_V1_BASE_URL}/users/{user_id}")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=404, detail="Utente non trovato")
            
            user_data = response.json().get("user", {})
        
        context = {
            **base_context,
            "user_data": user_data,
            "action": "edit"
        }
        
        return templates.TemplateResponse("admin/users_form.html", context)
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.post("/admin/users/{user_id}/edit/")
async def admin_users_update(
    user_id: UUID,
    email: str = Form(),
    password: Optional[str] = Form(None),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    is_superuser: bool = Form(False),
    is_active: bool = Form(True),
    is_verified: bool = Form(False),
    auth_data: tuple = Depends(require_superuser)
):
    """Aggiorna utente esistente"""
    superuser, base_context = auth_data
    
    try:
        # Prepara i dati per la API v1
        user_data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_superuser": is_superuser,
            "is_active": is_active,
            "is_verified": is_verified
        }
        
        # Aggiungi password solo se fornita
        if password and password.strip():
            user_data["password"] = password
        
        # Chiama la API v1 per aggiornare l'utente
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.put(f"{API_V1_BASE_URL}/users/{user_id}", json=user_data)
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                # Torna al form con errore
                context = {
                    **base_context,
                    "user_data": {**user_data, "id": str(user_id)},
                    "action": "edit",
                    "error": response.json().get("detail", "Errore nell'aggiornamento dell'utente")
                }
                return templates.TemplateResponse("admin/users_form.html", context)
        
        return RedirectResponse(
            url="/admin/users/?success=updated",
            status_code=303
        )
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.post("/admin/users/{user_id}/toggle-status/")
async def admin_users_toggle_status(
    user_id: UUID,
    auth_data: tuple = Depends(require_superuser)
):
    """Toggle stato attivo/inattivo utente"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per toggolare lo stato
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.post(f"{API_V1_BASE_URL}/users/{user_id}/toggle-status")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Errore nell'aggiornamento dello stato")
            
            result = response.json()
        
        return RedirectResponse(
            url="/admin/users/?success=toggled",
            status_code=303
        )
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

@admin_view_router.post("/admin/users/{user_id}/delete/")
async def admin_users_delete(
    user_id: UUID,
    auth_data: tuple = Depends(require_superuser)
):
    """Elimina utente (soft delete)"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per eliminare l'utente
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.delete(f"{API_V1_BASE_URL}/users/{user_id}")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Errore nell'eliminazione dell'utente")
        
        return RedirectResponse(
            url="/admin/users/?success=deleted",
            status_code=303
        )
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")

# ===== GESTIONE PERMESSI =====

@admin_view_router.get("/admin/permissions/", response_class=HTMLResponse)
async def admin_permissions_list(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Lista permessi utenti-siti"""
    superuser, base_context = auth_data
    
    try:
        # Chiama la API v1 per ottenere i dati
        # Estrai i cookie dalla richiesta originale e passali alla richiesta API
        cookies = {}
        for cookie_name, cookie_value in request.cookies.items():
            cookies[cookie_name] = cookie_value
            
        async with httpx.AsyncClient(cookies=cookies) as client:
            response = await client.get(f"{API_V1_BASE_URL}/permissions")
            
            if response.status_code != 200:
                logger.error(f"API v1 error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Errore nel caricamento dei dati"
                )
            
            api_data = response.json()
        
        context = {
            **base_context,
            "permissions": api_data.get("permissions", []),
            "count": api_data.get("count", 0)
        }
        
        return templates.TemplateResponse("admin/permissions_list.html", context)
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(status_code=500, detail="Errore di connessione al servizio API")