"""
API v1 - Administrative Functions
Endpoints per funzioni amministrative del sistema.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.db import get_async_session

# Schemas
class UserCreate(BaseModel):
    email: str
    password: str
    is_superuser: bool = False
    is_active: bool = True

class SiteCreate(BaseModel):
    name: str
    code: str
    location: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    is_public: bool = True

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_admin_access(user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica che l'utente abbia privilegi di amministrazione"""
    if not user_sites:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso negato - nessun sito accessibile"
        )
    
    # Verifica se è superutente
    is_admin = any(site.get("is_superuser") for site in user_sites)
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso negato - privilegi insufficienti per funzioni admin"
        )
    
    return True

# NUOVI ENDPOINTS V1

@router.get("/sites", summary="Lista siti amministrazione", tags=["Administration"])
async def v1_admin_get_sites(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Lista tutti i siti archeologici per amministrazione.
    
    Solo superutenti possono accedere.
    """
    verify_admin_access(user_sites)
    
    # In una implementazione reale, questo queryerebbe tutti i siti dal database
    # Per ora, restituisce i siti accessibili all'utente (che è superutente)
    return {
        "sites": user_sites,
        "count": len(user_sites),
        "admin_user_id": str(current_user_id)
    }

@router.post("/sites", summary="Crea nuovo sito", tags=["Administration"])
async def v1_admin_create_site(
    site_data: SiteCreate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea nuovo sito archeologico.
    
    Solo superutenti possono creare siti.
    """
    verify_admin_access(user_sites)
    
    # TODO: Implementare logica completa creazione sito
    return {
        "message": "Site creation not implemented yet",
        "site_data": site_data.model_dump(),
        "created_by": str(current_user_id)
    }

@router.get("/users", summary="Lista utenti amministrazione", tags=["Administration"])
async def v1_admin_get_users(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Lista tutti gli utenti per amministrazione.
    
    Solo superutenti possono accedere.
    """
    verify_admin_access(user_sites)
    
    # TODO: Implementare logica completa lista utenti
    return {
        "users": [],
        "count": 0,
        "admin_user_id": str(current_user_id)
    }

@router.post("/users", summary="Crea nuovo utente", tags=["Administration"])
async def v1_admin_create_user(
    user_data: UserCreate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea nuovo utente nel sistema.
    
    Solo superutenti possono creare utenti.
    """
    verify_admin_access(user_sites)
    
    # TODO: Implementare logica completa creazione utente
    return {
        "message": "User creation not implemented yet",
        "user_data": user_data.model_dump(exclude={"password"}),
        "created_by": str(current_user_id)
    }

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/sites", summary="[DEPRECATED] Lista siti admin legacy", tags=["Administration - Legacy"])
async def legacy_admin_get_sites():
    """
    ⚠️ DEPRECATED: Lista siti admin endpoint legacy.
    
    Usa /api/v1/admin/sites invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning("Legacy admin sites endpoint used - deprecated")
    response = JSONResponse(content={"message": "Use new endpoint"})
    add_deprecation_headers(response, "/api/v1/admin/sites")
    return response

@router.get("/legacy/users", summary="[DEPRECATED] Lista utenti admin legacy", tags=["Administration - Legacy"])
async def legacy_admin_get_users():
    """
    ⚠️ DEPRECATED: Lista utenti admin endpoint legacy.
    
    Usa /api/v1/admin/users invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning("Legacy admin users endpoint used - deprecated")
    response = JSONResponse(content={"message": "Use new endpoint"})
    add_deprecation_headers(response, "/api/v1/admin/users")
    return response

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API admin", tags=["Administration - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per admin functions.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/admin/sites/": "/api/v1/admin/sites",
                "/admin/users/": "/api/v1/admin/users",
                "/admin/sites/new/": "/api/v1/admin/sites",
                "/admin/users/new/": "/api/v1/admin/users"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints admin in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata",
                "Separazione chiara endpoints admin da user"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints admin"
        }
    }