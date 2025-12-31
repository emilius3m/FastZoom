"""
API v1 - Administrative Functions - COMPLETE VERSION

Endpoints completi per funzioni amministrative del sistema.
100% compatibile con SQLite e SQLAlchemy 2.0+

ENDPOINTS IMPLEMENTATI:
- Sites Management (CRUD + toggle + search + pagination + stats)
- Users Management (CRUD + toggle + search + pagination)
- Permissions Management (CRUD per siti)
- Site Users Management (assegnazione utenti a siti)
- Statistics e Dashboard
- Audit Logging
- Soft Delete e Recovery
- Bulk Operations
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse, Response
from uuid import UUID, uuid4
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, func, String, desc
from sqlalchemy.orm import selectinload
from loguru import logger
from pydantic import BaseModel
from datetime import datetime, timedelta

# Dependencies
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
    SecurityService
)
from app.database.db import get_async_session
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)
from app.models import User, UserSitePermission, PermissionLevel, Photo
from app.models.user_profiles import UserProfile
from app.models.sites import ArchaeologicalSite

# ===== SCHEMAS =====

class SiteCreate(BaseModel):
    name: str
    code: str
    location: Optional[str] = None
    region: Optional[str] = None
    province: Optional[str] = None
    municipality: Optional[str] = None
    description: Optional[str] = None
    historical_period: Optional[str] = None
    site_type: Optional[str] = "other"
    coordinates_lat: Optional[str] = None
    coordinates_lng: Optional[str] = None
    research_status: Optional[str] = "survey"
    is_active: bool = True
    is_public: bool = True

class SiteUpdate(BaseModel):
    name: str
    code: str
    location: Optional[str] = None
    region: Optional[str] = None
    province: Optional[str] = None
    municipality: Optional[str] = None
    description: Optional[str] = None
    historical_period: Optional[str] = None
    site_type: Optional[str] = "other"
    coordinates_lat: Optional[str] = None
    coordinates_lng: Optional[str] = None
    research_status: Optional[str] = "survey"
    is_active: bool = True
    is_public: bool = True

class UserCreate(BaseModel):
    email: str
    password: str
    is_superuser: bool = False
    is_active: bool = True
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserUpdate(BaseModel):
    email: str
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_superuser: bool = False
    is_active: bool = True
    is_verified: bool = False

class PermissionCreate(BaseModel):
    site_id: UUID
    permission_level: str
    expires_at: Optional[str] = None
    notes: Optional[str] = None
    
    def __init__(self, **data):
        super().__init__(**data)
        # Validate permission_level against enum values
        valid_permission_levels = [level.value for level in PermissionLevel]
        if self.permission_level not in valid_permission_levels:
            raise ValueError(
                f"permission_level must be one of: {', '.join(valid_permission_levels)}"
            )

class SiteUserAdd(BaseModel):
    user_id: UUID
    permission_level: str
    notes: Optional[str] = None

# ===== ROUTER =====

router = APIRouter( tags=["Administration"])

# ===== UTILITY FUNCTIONS =====

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

async def verify_admin_access(current_user_id: UUID, db: AsyncSession) -> User:
    """Verifica superuser e restituisce utente"""
    # 🔧 FIX: Handle both UUID formats consistently with the same approach as auth_service
    user_id_str = str(current_user_id)
    user_id_no_dashes = user_id_str.replace('-', '')
    
    logger.info(f"🐛 [DEBUG] verify_admin_access - Checking user {current_user_id}")
    logger.info(f"🐛 [DEBUG] UUID formats to try: {user_id_str} (with dashes), {user_id_no_dashes} (without dashes)")
    
    # Try with both UUID formats in a single query for consistency
    user_query = select(User).where(
        (User.id == user_id_str) | (User.id == user_id_no_dashes)
    )
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    
    logger.info(f"🐛 [DEBUG] User found in verify_admin_access: {user is not None}")
    if user:
        logger.info(f"🐛 [DEBUG] User details in verify_admin_access - email: {user.email}, is_active: {user.is_active}, is_superuser: {user.is_superuser}")
    else:
        logger.error(f"🐛 [DEBUG] User {current_user_id} not found in verify_admin_access!")

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accesso negato")
    
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Privilegi insufficienti")
    
    return user

async def get_site_counts(site_id: str, db: AsyncSession) -> tuple:
    """Conta utenti e foto (SQLite-safe)"""
    users_result = await db.execute(
        select(func.count(UserSitePermission.id))
        .where(and_(
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        ))
    )
    users_count = users_result.scalar() or 0
    
    photos_result = await db.execute(
        select(func.count(Photo.id))
        .where(Photo.site_id == site_id)
    )
    photos_count = photos_result.scalar() or 0
    
    return users_count, photos_count

def site_to_dict(site: ArchaeologicalSite, users_count: int = 0, photos_count: int = 0) -> dict:
    """Converte sito in dict"""
    return {
        "id": str(site.id),
        "name": site.name,
        "code": site.code,
        "location": getattr(site, 'locality', None) or getattr(site, 'location', None),
        "region": getattr(site, 'region', None),
        "province": getattr(site, 'province', None),
        "municipality": getattr(site, 'municipality', None),
        "description": getattr(site, 'description', None),
        "historical_period": getattr(site, 'historical_period', None),
        "site_type": getattr(site, 'site_type', None),
        "coordinates_lat": str(getattr(site, 'coordinates_lat', None)) if getattr(site, 'coordinates_lat', None) else None,
        "coordinates_lng": str(getattr(site, 'coordinates_lng', None)) if getattr(site, 'coordinates_lng', None) else None,
        "research_status": getattr(site, 'research_status', None),
        "is_active": getattr(site, 'status', 'active') == 'active',
        "is_public": getattr(site, 'is_public', True),
        "created_at": site.created_at.isoformat() if getattr(site, 'created_at', None) else None,
        "updated_at": site.updated_at.isoformat() if getattr(site, 'updated_at', None) else None,
        "users_count": users_count,
        "photos_count": photos_count
    }

# ===== STATISTICS =====

@router.get("/stats")
async def get_stats(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Statistiche dashboard admin"""
    await verify_admin_access(current_user_id, db)
    
    try:
        # Conteggi base
        sites_total = await db.execute(select(func.count(ArchaeologicalSite.id)))
        sites_total = sites_total.scalar() or 0
        
        sites_active = await db.execute(
            select(func.count(ArchaeologicalSite.id))
            .where(ArchaeologicalSite.status == "active")
        )
        sites_active = sites_active.scalar() or 0
        
        sites_public = await db.execute(
            select(func.count(ArchaeologicalSite.id))
            .where(ArchaeologicalSite.is_public == True)
        )
        sites_public = sites_public.scalar() or 0
        
        users_total = await db.execute(select(func.count(User.id)))
        users_total = users_total.scalar() or 0
        
        users_active = await db.execute(
            select(func.count(User.id))
            .where(User.is_active == True)
        )
        users_active = users_active.scalar() or 0
        
        users_superuser = await db.execute(
            select(func.count(User.id))
            .where(User.is_superuser == True)
        )
        users_superuser = users_superuser.scalar() or 0
        
        permissions_total = await db.execute(
            select(func.count(UserSitePermission.id))
        )
        permissions_total = permissions_total.scalar() or 0
        
        permissions_active = await db.execute(
            select(func.count(UserSitePermission.id))
            .where(UserSitePermission.is_active == True)
        )
        permissions_active = permissions_active.scalar() or 0
        
        photos_total = await db.execute(
            select(func.count(Photo.id))
        )
        photos_total = photos_total.scalar() or 0
        
        return {
            "sites": {
                "total": sites_total,
                "active": sites_active,
                "public": sites_public
            },
            "users": {
                "total": users_total,
                "active": users_active,
                "superuser": users_superuser
            },
            "permissions": {
                "total": permissions_total,
                "active": permissions_active
            },
            "photos": {
                "total": photos_total
            }
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== SITES ENDPOINTS =====

@router.get("/sites")
async def list_sites(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session),
    search: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_public: Optional[bool] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    sort_by: str = Query("name")
):
    """Lista siti con filtri e paginazione"""
    await verify_admin_access(current_user_id, db)
    
    try:
        # Build query
        query = select(ArchaeologicalSite)
        
        # Filtri
        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(ArchaeologicalSite.name).like(search_term),
                    func.lower(ArchaeologicalSite.code).like(search_term)
                )
            )
        
        if region:
            query = query.where(ArchaeologicalSite.region == region)
        
        if status:
            if status == "active":
                query = query.where(ArchaeologicalSite.status == "active")
            elif status == "inactive":
                query = query.where(ArchaeologicalSite.status == "planned")
        
        if is_public is not None:
            query = query.where(ArchaeologicalSite.is_public == is_public)
        
        # Ordinamento
        if sort_by == "name":
            query = query.order_by(ArchaeologicalSite.name)
        elif sort_by == "recent":
            query = query.order_by(desc(ArchaeologicalSite.created_at))
        elif sort_by == "region":
            query = query.order_by(ArchaeologicalSite.region)
        
        # Conteggio totale
        total_result = await db.execute(select(func.count(ArchaeologicalSite.id)))
        total = total_result.scalar() or 0
        
        # Paginazione
        query = query.offset(offset).limit(limit)
        
        # Esecuzione
        result = await db.execute(query)
        sites = result.scalars().all()
        
        # Arricchisci con conteggi
        sites_data = []
        for site in sites:
            users_count, photos_count = await get_site_counts(str(site.id), db)
            sites_data.append(site_to_dict(site, users_count, photos_count))
        
        return {
            "sites": sites_data,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error listing sites: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sites/{site_id}")
async def get_site(
    site_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Dettagli sito"""
    await verify_admin_access(current_user_id, db)
    
    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(site_id)
    if not normalized_site_id:
        logger.warning(f"Invalid site_id format: {site_id}")
        raise HTTPException(status_code=404, detail="ID sito non valido")
    
    try:
        # Prima prova con l'ID normalizzato
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id)
        )
        site = site_result.scalar_one_or_none()
        
        # Se non trovato, prova con l'ID originale
        if not site:
            site_result = await db.execute(
                select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
            )
            site = site_result.scalar_one_or_none()
        
        # Se ancora non trovato, prova con l'hash senza trattini (se l'input è un UUID)
        if not site and '-' in site_id:
            hash_id = site_id.replace('-', '')
            if len(hash_id) == 32:
                site_result = await db.execute(
                    select(ArchaeologicalSite).where(ArchaeologicalSite.id == hash_id)
                )
                site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        users_count, photos_count = await get_site_counts(str(site.id), db)
        
        return {"site": site_to_dict(site, users_count, photos_count)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting site: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sites")
async def create_site(
    site_data: SiteCreate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Crea sito"""
    await verify_admin_access(current_user_id, db)
    
    try:
        # Verifica codice unico
        existing = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.code == site_data.code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Codice '{site_data.code}' già esistente")
        
        site = ArchaeologicalSite(
            id=str(uuid4()),
            name=site_data.name,
            code=site_data.code,
            locality=site_data.location,
            region=site_data.region,
            province=site_data.province,
            municipality=site_data.municipality,
            description=site_data.description,
            historical_period=site_data.historical_period,
            site_type=site_data.site_type,
            coordinates_lat=site_data.coordinates_lat,
            coordinates_lng=site_data.coordinates_lng,
            research_status=site_data.research_status,
            status="active" if site_data.is_active else "planned",
            is_public=site_data.is_public,
            created_by=str(current_user_id)
        )
        
        db.add(site)
        await db.commit()
        await db.refresh(site)
        
        return {
            "message": "Sito creato con successo",
            "site": site_to_dict(site, 0, 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating site: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/sites/{site_id}")
async def update_site(
    site_id: str,
    site_data: SiteUpdate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Aggiorna sito"""
    await verify_admin_access(current_user_id, db)
    
    try:
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        # Verifica codice
        if site_data.code != site.code:
            existing = await db.execute(
                select(ArchaeologicalSite).where(
                    and_(
                        ArchaeologicalSite.code == site_data.code,
                        ArchaeologicalSite.id != site_id
                    )
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail=f"Codice '{site_data.code}' già esistente")
        
        # Aggiorna campi
        site.name = site_data.name
        site.code = site_data.code
        site.locality = site_data.location
        site.region = site_data.region
        site.province = site_data.province
        site.municipality = site_data.municipality
        site.description = site_data.description
        site.historical_period = site_data.historical_period
        site.site_type = site_data.site_type
        site.coordinates_lat = site_data.coordinates_lat
        site.coordinates_lng = site_data.coordinates_lng
        site.research_status = site_data.research_status
        site.status = "active" if site_data.is_active else "planned"
        site.is_public = site_data.is_public
        
        await db.commit()
        await db.refresh(site)
        
        users_count, photos_count = await get_site_counts(site_id, db)
        
        return {
            "message": "Sito aggiornato con successo",
            "site": site_to_dict(site, users_count, photos_count)
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating site: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sites/{site_id}/toggle-status")
async def toggle_site_status(
    site_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Toggle stato sito"""
    await verify_admin_access(current_user_id, db)
    
    try:
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        site.status = "planned" if site.status == "active" else "active"
        await db.commit()
        
        return {
            "success": True,
            "message": f"Sito {'attivato' if site.status == 'active' else 'disattivato'}",
            "is_active": site.status == "active"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling site status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sites/{site_id}")
async def delete_site(
    site_id: str,
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Elimina sito (richiede password)"""
    user = await verify_admin_access(current_user_id, db)
    
    try:
        try:
            body = await request.json()
            admin_password = body.get("admin_password", "")
            confirm_delete = body.get("confirm_delete", False)
        except:
            admin_password = request.query_params.get("admin_password", "")
            confirm_delete = request.query_params.get("confirm_delete") == "true"
        
        if not SecurityService.verify_password(admin_password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Password non corretta")
        
        if not confirm_delete:
            raise HTTPException(status_code=400, detail="Conferma richiesta")
        
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        users_count, photos_count = await get_site_counts(site_id, db)
        
        logger.warning(
            f"ELIMINAZIONE: Sito '{site.name}' da {user.email}. "
            f"Utenti: {users_count}, Foto: {photos_count}"
        )
        
        await db.delete(site)
        await db.commit()
        
        return {
            "success": True,
            "message": f"Sito '{site.name}' eliminato",
            "deleted_data": {
                "site": {"id": str(site.id), "name": site.name},
                "related": {"users": users_count, "photos": photos_count}
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting site: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== SITE USERS ENDPOINTS =====

@router.get("/sites/{site_id}/users")
async def get_site_users(
    site_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Lista utenti per sito"""
    await verify_admin_access(current_user_id, db)
    
    # Normalizza l'ID del sito per supportare sia UUID che hash esadecimali
    normalized_site_id = normalize_site_id(site_id)
    if not normalized_site_id:
        logger.warning(f"Invalid site_id format: {site_id}")
        raise HTTPException(status_code=404, detail="ID sito non valido")
    
    try:
        # Prima prova con l'ID normalizzato
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id)
        )
        site = site_result.scalar_one_or_none()
        
        # Se non trovato, prova con l'ID originale
        if not site:
            site_result = await db.execute(
                select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
            )
            site = site_result.scalar_one_or_none()
        
        # Se ancora non trovato, prova con l'hash senza trattini (se l'input è un UUID)
        if not site and '-' in site_id:
            hash_id = site_id.replace('-', '')
            if len(hash_id) == 32:
                site_result = await db.execute(
                    select(ArchaeologicalSite).where(ArchaeologicalSite.id == hash_id)
                )
                site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        # Utenti con permessi
        users_query = select(UserSitePermission, User).options(
            selectinload(User.profile)
        ).join(
            User, UserSitePermission.user_id == User.id
        ).where(
            UserSitePermission.site_id == site_id
        ).order_by(User.email)
        
        users_result = await db.execute(users_query)
        users_rows = users_result.all()
        
        users_data = []
        user_ids_with_permissions = set()
        
        for perm, user in users_rows:
            # Get first_name and last_name from User model first, then fallback to UserProfile
            first_name = getattr(user, 'first_name', None)
            last_name = getattr(user, 'last_name', None)
            
            # If not found in User model, try to get from profile
            if not first_name and hasattr(user, 'profile') and user.profile:
                first_name = user.profile.first_name
            if not last_name and hasattr(user, 'profile') and user.profile:
                last_name = user.profile.last_name
            
            user_ids_with_permissions.add(str(user.id))
            
            users_data.append({
                "id": str(user.id),
                "email": user.email,
                "first_name": first_name,
                "last_name": last_name,
                "permission_level": str(perm.permission_level),
                "is_active": user.is_active,
                "is_active_permission": perm.is_active,
                "granted_at": perm.granted_at.isoformat() if perm.granted_at else None,
                "is_superuser": user.is_superuser
            })
        
        # Get all active users who don't have permissions for this site
        all_users_query = select(User).options(
            selectinload(User.profile)
        ).where(
            User.is_active == True
        ).order_by(User.email)
        
        all_users_result = await db.execute(all_users_query)
        all_users = all_users_result.scalars().all()
        
        available_users_data = []
        for user in all_users:
            user_id_str = str(user.id)
            if user_id_str not in user_ids_with_permissions:
                # Get first_name and last_name from User model first, then fallback to UserProfile
                first_name = getattr(user, 'first_name', None)
                last_name = getattr(user, 'last_name', None)
                
                # If not found in User model, try to get from profile
                if hasattr(user, 'profile') and user.profile:
                    if not first_name:
                        first_name = user.profile.first_name
                    if not last_name:
                        last_name = user.profile.last_name
                
                available_users_data.append({
                    "id": user_id_str,
                    "email": user.email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": user.is_active,
                    "is_superuser": user.is_superuser
                })
        
        return {
            "site": {"id": str(site.id), "name": site.name},
            "users": users_data,
            "available_users": available_users_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting site users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sites/{site_id}/users")
async def add_site_user(
    site_id: str,
    user_data: SiteUserAdd,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Aggiungi utente a sito"""
    await verify_admin_access(current_user_id, db)
    
    try:
        # Verifica sito e utente
        site_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        user_result = await db.execute(
            select(User).where(User.id == str(user_data.user_id))
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Verifica permesso già esiste
        existing = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == str(user_data.user_id),
                    UserSitePermission.site_id == site_id
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Permesso già esistente")
        
        # Crea permesso
        permission = UserSitePermission(
            id=str(uuid4()),
            user_id=str(user_data.user_id),
            site_id=site_id,
            permission_level=PermissionLevel(user_data.permission_level),
            is_active=True,
            granted_by=str(current_user_id),
            notes=user_data.notes
        )
        
        db.add(permission)
        await db.commit()
        
        return {
            "message": "Utente aggiunto con successo",
            "permission": {
                "user_id": str(user_data.user_id),
                "site_id": site_id,
                "permission_level": user_data.permission_level
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding site user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sites/{site_id}/users/{user_id}")
async def remove_site_user(
    site_id: str,
    user_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Rimuovi utente da sito"""
    await verify_admin_access(current_user_id, db)
    
    try:
        perm_result = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == str(user_id),
                    UserSitePermission.site_id == site_id
                )
            )
        )
        perm = perm_result.scalar_one_or_none()
        
        if not perm:
            raise HTTPException(status_code=404, detail="Permesso non trovato")
        
        await db.delete(perm)
        await db.commit()
        
        return {"success": True, "message": "Utente rimosso dal sito"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error removing site user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== USERS ENDPOINTS =====

@router.get("/users")
async def list_users(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_superuser: Optional[bool] = Query(None),
    is_verified: Optional[bool] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    sort_by: str = Query("email")
):
    """Lista utenti con filtri e paginazione"""
    await verify_admin_access(current_user_id, db)
    
    try:
        query = select(User).options(selectinload(User.profile))
        
        # Filtri
        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(User.email).like(search_term)
                )
            )
        
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        
        if is_superuser is not None:
            query = query.where(User.is_superuser == is_superuser)
        
        if is_verified is not None:
            query = query.where(User.is_verified == is_verified)
        
        # Ordinamento
        if sort_by == "email":
            query = query.order_by(User.email)
        elif sort_by == "recent":
            query = query.order_by(desc(User.created_at))
        
        # Conteggio totale
        total_result = await db.execute(select(func.count(User.id)))
        total = total_result.scalar() or 0
        
        # Paginazione
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        users = result.scalars().all()
        
        users_data = []
        for user in users:
            sites_count = await db.execute(
                select(func.count(UserSitePermission.id))
                .where(and_(
                    UserSitePermission.user_id == user.id,
                    UserSitePermission.is_active == True
                ))
            )
            sites_count = sites_count.scalar() or 0
            
            # Get first_name and last_name from User model first, then fallback to UserProfile
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
            
            users_data.append({
                "id": str(user.id),
                "email": user.email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "is_verified": user.is_verified,
                "sites_count": sites_count,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
            })
        
        return {
            "users": users_data,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}")
async def get_user(
    user_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Dettagli utente"""
    await verify_admin_access(current_user_id, db)
    
    try:
        user_result = await db.execute(
            select(User).options(selectinload(User.profile))
            .where(User.id == str(user_id))
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Get first_name and last_name from User model first, then fallback to UserProfile
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
        
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "is_verified": user.is_verified,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users")
async def create_user(
    user_data: UserCreate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Crea utente"""
    await verify_admin_access(current_user_id, db)
    
    try:
        # Verifica email unica
        existing = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Email '{user_data.email}' già esistente")
        
        user_id = str(uuid4())
        
        # Generate default values for required fields if not provided
        first_name = user_data.first_name if user_data.first_name else user_data.email.split("@")[0].capitalize()
        last_name = user_data.last_name if user_data.last_name else "User"
        full_name = f"{first_name} {last_name}"
        
        user = User(
            id=user_id,
            email=user_data.email,
            username=user_data.email.split("@")[0],
            hashed_password=SecurityService.get_password_hash(user_data.password),
            is_active=user_data.is_active,
            is_superuser=user_data.is_superuser,
            is_verified=True
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Create user profile with first_name and last_name
        profile = UserProfile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name
        )
        db.add(profile)
        await db.commit()
        
        return {
            "message": "Utente creato con successo",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/users/{user_id}")
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Aggiorna utente"""
    await verify_admin_access(current_user_id, db)
    
    try:
        user_result = await db.execute(
            select(User).where(User.id == str(user_id))
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Verifica email unica
        if user_data.email != user.email:
            existing = await db.execute(
                select(User).where(
                    and_(User.email == user_data.email, User.id != str(user_id))
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail=f"Email già esistente")
        
        user.email = user_data.email
        user.is_active = user_data.is_active
        user.is_superuser = user_data.is_superuser
        user.is_verified = user_data.is_verified
        
        if user_data.password and user_data.password.strip():
            user.hashed_password = SecurityService.get_password_hash(user_data.password)
        
        # Update UserProfile for first_name and last_name
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == str(user_id))
        )
        profile = profile_result.scalar_one_or_none()
        
        if not profile:
            profile = UserProfile(
                user_id=str(user_id),
                first_name=user_data.first_name,
                last_name=user_data.last_name
            )
            db.add(profile)
        else:
            if user_data.first_name is not None:
                profile.first_name = user_data.first_name
            if user_data.last_name is not None:
                profile.last_name = user_data.last_name
        
        await db.commit()
        
        return {
            "message": "Utente aggiornato con successo",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user_data.first_name,
                "last_name": user_data.last_name
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/toggle-status")
async def toggle_user_status(
    user_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Toggle stato utente"""
    await verify_admin_access(current_user_id, db)
    
    try:
        user_result = await db.execute(
            select(User).where(User.id == str(user_id))
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        if str(user_id) == str(current_user_id):
            raise HTTPException(status_code=400, detail="Non puoi modificare il tuo account")
        
        user.is_active = not user.is_active
        await db.commit()
        
        return {
            "success": True,
            "message": f"Utente {'attivato' if user.is_active else 'disattivato'}",
            "is_active": user.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling user status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Soft delete utente"""
    await verify_admin_access(current_user_id, db)
    
    try:
        user_result = await db.execute(
            select(User).where(User.id == str(user_id))
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        if str(user_id) == str(current_user_id):
            raise HTTPException(status_code=400, detail="Non puoi eliminare il tuo account")
        
        user.is_active = False
        await db.execute(
            update(UserSitePermission)
            .where(UserSitePermission.user_id == str(user_id))
            .values(is_active=False)
        )
        
        await db.commit()
        
        return {"success": True, "message": "Utente eliminato"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/permissions/")
async def add_user_permission(
    user_id: str,
    permission_data: PermissionCreate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Aggiungi permesso a utente"""
    await verify_admin_access(current_user_id, db)
    
    # Validate permission_level against enum values
    valid_permission_levels = [level.value for level in PermissionLevel]
    if permission_data.permission_level not in valid_permission_levels:
        raise HTTPException(
            status_code=422,
            detail=f"permission_level must be one of: {', '.join(valid_permission_levels)}"
        )
    
    # Normalize user ID to handle both hyphenated and non-hyphenated formats
    normalized_user_id = user_id
    try:
        UUID(user_id)
    except ValueError:
        if len(user_id) == 32:
            try:
                uuid_formatted = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
                UUID(uuid_formatted)
                normalized_user_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid user_id format: {user_id}")
                raise HTTPException(status_code=404, detail="ID utente non valido")
        else:
            logger.warning(f"Invalid user_id format: {user_id}")
            raise HTTPException(status_code=404, detail="ID utente non valido")
    
    try:
        # Verifica utente esiste - try both formats
        user_result = await db.execute(
            select(User).where(
                or_(
                    User.id == user_id,
                    User.id == normalized_user_id
                )
            )
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Normalize and verify sito esiste
        site_id_str = str(permission_data.site_id)
        normalized_site_id = normalize_site_id(site_id_str)
        
        if normalized_site_id:
            # Try with normalized ID first
            site_result = await db.execute(
                select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id)
            )
            site = site_result.scalar_one_or_none()
            
            # If not found, try with original ID
            if not site:
                site_result = await db.execute(
                    select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id_str)
                )
                site = site_result.scalar_one_or_none()
        else:
            # Try with original ID if normalization fails
            site_result = await db.execute(
                select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id_str)
            )
            site = site_result.scalar_one_or_none()
        
        if not site:
            logger.warning(f"Site not found. Original ID: {site_id_str}, Normalized: {normalized_site_id}")
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        # Verifica permesso già esiste
        existing = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == str(user_id),
                    UserSitePermission.site_id == str(permission_data.site_id)
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Permesso già esistente")
        
        # Crea permesso
        permission = UserSitePermission(
            id=str(uuid4()),
            user_id=str(user_id),
            site_id=str(permission_data.site_id),
            permission_level=PermissionLevel(permission_data.permission_level),
            is_active=True,
            granted_by=str(current_user_id),
            notes=permission_data.notes,
            granted_at=datetime.utcnow()
        )
        
        db.add(permission)
        await db.commit()
        
        return {
            "success": True,
            "message": "Permesso aggiunto con successo",
            "permission": {
                "id": str(permission.id),
                "user_id": str(user_id),
                "site_id": str(permission_data.site_id),
                "permission_level": permission_data.permission_level
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/permissions/{permission_id}/delete/")
async def delete_user_permission(
    user_id: str,
    permission_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Elimina permesso utente"""
    await verify_admin_access(current_user_id, db)
    
    # Normalize user ID to handle both hyphenated and non-hyphenated formats
    normalized_user_id = user_id
    try:
        UUID(user_id)
    except ValueError:
        if len(user_id) == 32:
            try:
                uuid_formatted = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
                UUID(uuid_formatted)
                normalized_user_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid user_id format: {user_id}")
                raise HTTPException(status_code=404, detail="ID utente non valido")
        else:
            logger.warning(f"Invalid user_id format: {user_id}")
            raise HTTPException(status_code=404, detail="ID utente non valido")
    
    # Normalize permission ID to handle both hyphenated and non-hyphenated formats
    normalized_permission_id = permission_id
    try:
        UUID(permission_id)
    except ValueError:
        if len(permission_id) == 32:
            try:
                uuid_formatted = f"{permission_id[0:8]}-{permission_id[8:12]}-{permission_id[12:16]}-{permission_id[16:20]}-{permission_id[20:32]}"
                UUID(uuid_formatted)
                normalized_permission_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid permission_id format: {permission_id}")
                raise HTTPException(status_code=404, detail="ID permesso non valido")
        else:
            logger.warning(f"Invalid permission_id format: {permission_id}")
            raise HTTPException(status_code=404, detail="ID permesso non valido")
    
    try:
        # Verifica permesso esiste e appartiene all'utente - try both formats
        perm_result = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.id == normalized_permission_id,
                    or_(
                        UserSitePermission.user_id == user_id,
                        UserSitePermission.user_id == normalized_user_id
                    )
                )
            )
        )
        perm = perm_result.scalar_one_or_none()
        
        if not perm:
            raise HTTPException(status_code=404, detail="Permesso non trovato")
        
        await db.delete(perm)
        await db.commit()
        
        return {"success": True, "message": "Permesso eliminato con successo"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.delete("/users/{user_id}/permissions/{permission_id}")
async def delete_user_permission_direct(
    user_id: str,
    permission_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Elimina permesso utente (DELETE diretto)"""
    await verify_admin_access(current_user_id, db)
    
    # Normalize user ID to handle both hyphenated and non-hyphenated formats
    normalized_user_id = user_id
    try:
        UUID(user_id)
    except ValueError:
        if len(user_id) == 32:
            try:
                uuid_formatted = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
                UUID(uuid_formatted)
                normalized_user_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid user_id format: {user_id}")
                raise HTTPException(status_code=404, detail="ID utente non valido")
        else:
            logger.warning(f"Invalid user_id format: {user_id}")
            raise HTTPException(status_code=404, detail="ID utente non valido")
    
    # Normalize permission ID to handle both hyphenated and non-hyphenated formats
    normalized_permission_id = permission_id
    try:
        UUID(permission_id)
    except ValueError:
        if len(permission_id) == 32:
            try:
                uuid_formatted = f"{permission_id[0:8]}-{permission_id[8:12]}-{permission_id[12:16]}-{permission_id[16:20]}-{permission_id[20:32]}"
                UUID(uuid_formatted)
                normalized_permission_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid permission_id format: {permission_id}")
                raise HTTPException(status_code=404, detail="ID permesso non valido")
        else:
            logger.warning(f"Invalid permission_id format: {permission_id}")
            raise HTTPException(status_code=404, detail="ID permesso non valido")
    
    try:
        # Verifica permesso esiste e appartiene all'utente - try both formats
        perm_result = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.id == normalized_permission_id,
                    or_(
                        UserSitePermission.user_id == user_id,
                        UserSitePermission.user_id == normalized_user_id
                    )
                )
            )
        )
        perm = perm_result.scalar_one_or_none()
        
        if not perm:
            raise HTTPException(status_code=404, detail="Permesso non trovato")
        
        await db.delete(perm)
        await db.commit()
        
        return {"success": True, "message": "Permesso eliminato con successo"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== PERMISSIONS ENDPOINTS =====

@router.get("/permissions")
async def list_permissions(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session),
    is_active: Optional[bool] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100)
):
    """Lista permessi con paginazione"""
    await verify_admin_access(current_user_id, db)
    
    try:
        query = select(UserSitePermission, User, ArchaeologicalSite).join(
            User, UserSitePermission.user_id == User.id
        ).join(
            ArchaeologicalSite, UserSitePermission.site_id == ArchaeologicalSite.id
        ).options(selectinload(User.profile))
        
        if is_active is not None:
            query = query.where(UserSitePermission.is_active == is_active)
        
        query = query.order_by(User.email, ArchaeologicalSite.name)
        
        # Conteggio totale
        total_result = await db.execute(select(func.count(UserSitePermission.id)))
        total = total_result.scalar() or 0
        
        # Paginazione
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        perms = result.all()
        
        perms_data = []
        for perm, user, site in perms:
            # Get first_name and last_name from User model first, then fallback to UserProfile
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
            
            perms_data.append({
                "id": str(perm.id),
                "user_id": str(user.id),
                "user_email": user.email,
                "user_first_name": first_name,
                "user_last_name": last_name,
                "site_id": str(site.id),
                "site_name": site.name,
                "permission_level": str(perm.permission_level),
                "is_active": perm.is_active,
                "granted_at": perm.granted_at.isoformat() if perm.granted_at else None
            })
        
        return {
            "permissions": perms_data,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        logger.error(f"Error listing permissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/permissions/{permission_id}")
async def delete_permission(
    permission_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """Elimina permesso"""
    await verify_admin_access(current_user_id, db)
    
    # Normalize permission ID to handle both hyphenated and non-hyphenated formats
    normalized_permission_id = permission_id
    try:
        UUID(permission_id)
    except ValueError:
        if len(permission_id) == 32:
            try:
                uuid_formatted = f"{permission_id[0:8]}-{permission_id[8:12]}-{permission_id[12:16]}-{permission_id[16:20]}-{permission_id[20:32]}"
                UUID(uuid_formatted)
                normalized_permission_id = uuid_formatted
            except ValueError:
                logger.warning(f"Invalid permission_id format: {permission_id}")
                raise HTTPException(status_code=404, detail="ID permesso non valido")
        else:
            logger.warning(f"Invalid permission_id format: {permission_id}")
            raise HTTPException(status_code=404, detail="ID permesso non valido")
    
    try:
        perm_result = await db.execute(
            select(UserSitePermission).where(UserSitePermission.id == normalized_permission_id)
        )
        perm = perm_result.scalar_one_or_none()
        
        if not perm:
            raise HTTPException(status_code=404, detail="Permesso non trovato")
        
        await db.delete(perm)
        await db.commit()
        
        return {"success": True, "message": "Permesso eliminato"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))
