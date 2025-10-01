from fastapi import APIRouter, Depends, Request, HTTPException, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id, get_current_user_sites
from app.models.users import User
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission, PermissionLevel
from app.models.photos import Photo
from app.services.auth_service import AuthService
from app.templates import templates



from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import text, func, update
from fastapi.responses import JSONResponse






admin_router = APIRouter(prefix="/admin", tags=["admin"])

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
    
    return {
        "request": request,
        # Variabili richieste da auth_navigation.html
        "sites": user_sites,
        "sites_count": len(user_sites) if user_sites else 0,
        "user_email": user.email if user else None,
        "user_type": "superuser" if user and user.is_superuser else "user",
        "current_site_name": user_sites[0]["name"] if user_sites else None,
        "current_page": request.url.path.split("/")[-1] or "admin"
    }

# Middleware per verificare che l'utente sia superuser
async def require_superuser(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
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

@admin_router.get("/sites/", response_class=HTMLResponse)
async def admin_sites_list(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Lista siti archeologici per amministrazione"""
    # Scomponi la tupla
    superuser, base_context = auth_data

    # Query con conteggi utenti e foto per ogni sito
    sites_query = (
        select(
            ArchaeologicalSite,
            func.count(UserSitePermission.id).label('users_count'),
            func.count(Photo.id).label('photos_count')
        )
        .outerjoin(UserSitePermission, and_(
            UserSitePermission.site_id == ArchaeologicalSite.id,
            UserSitePermission.is_active == True
        ))
        .outerjoin(Photo, Photo.site_id == ArchaeologicalSite.id)
        .group_by(ArchaeologicalSite.id)
        .order_by(ArchaeologicalSite.name)
    )

    sites_result = await db.execute(sites_query)
    sites = sites_result.all()

    # Converti in formato compatibile con il template
    sites_data = []
    for site, users_count, photos_count in sites:
        site_dict = {
            "id": str(site.id),
            "name": site.name,
            "code": site.code,
            "location": site.location,
            "region": site.region,
            "province": site.province,
            "description": site.description,
            "historical_period": site.historical_period,
            "coordinates_lat": site.coordinates_lat,
            "coordinates_lng": site.coordinates_lng,
            "is_active": site.is_active,
            "is_public": site.is_public,
            "created_at": site.created_at.isoformat() if site.created_at else None,
            "updated_at": site.updated_at.isoformat() if site.updated_at else None,
            "users_count": users_count,
            "photos_count": photos_count
        }
        sites_data.append(site_dict)

    context = {
        **base_context,
        "sites": sites_data,  # Pass sites for template compatibility
    }

    return templates.TemplateResponse("admin/sites_list.html", context)

@admin_router.get("/sites/new/", response_class=HTMLResponse)
async def admin_sites_new(
    request: Request,
    auth_data: tuple = Depends(require_superuser)
):
    """Form per nuovo sito archeologico"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    context = {
        **base_context,
        "site": None,
        "action": "create",
    }
    
    return templates.TemplateResponse("admin/sites_form.html", context)

@admin_router.post("/sites/new/")
async def admin_sites_create(
    request: Request,
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
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Crea nuovo sito archeologico"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    try:
        # Verifica che il codice sia unico
        existing = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.code == code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Codice sito '{code}' già esistente"
            )
        
        site = ArchaeologicalSite(
            id=uuid4(),
            name=name,
            code=code,
            location=location,
            region=region,
            province=province,
            municipality=municipality,
            description=description,
            historical_period=historical_period,
            site_type=site_type,
            coordinates_lat=coordinates_lat,
            coordinates_lng=coordinates_lng,
            research_status=research_status,
            is_active=is_active,
            is_public=is_public
        )
        
        db.add(site)
        await db.commit()
        
        return RedirectResponse(
            url="/admin/sites/?success=created",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_router.get("/sites/{site_id}/edit/", response_class=HTMLResponse)
async def admin_sites_edit(
    request: Request,
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Form per modifica sito archeologico"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    site = await db.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    )
    site = site.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Sito non trovato")
    
    context = {
        **base_context,
        "site": site,
        "action": "edit",
    }
    
    return templates.TemplateResponse("admin/sites_form.html", context)

@admin_router.post("/sites/{site_id}/edit/")
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
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Aggiorna sito archeologico"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    try:
        site = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        # Verifica unicità codice (escludendo il sito corrente)
        existing = await db.execute(
            select(ArchaeologicalSite).where(
                and_(
                    ArchaeologicalSite.code == code,
                    ArchaeologicalSite.id != site_id
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Codice sito '{code}' già esistente"
            )
        
        # Aggiorna campi
        site.name = name
        site.code = code
        site.location = location
        site.region = region
        site.province = province
        site.municipality = municipality
        site.description = description
        site.historical_period = historical_period
        site.site_type = site_type
        site.coordinates_lat = coordinates_lat
        site.coordinates_lng = coordinates_lng
        site.research_status = research_status
        site.is_active = is_active
        site.is_public = is_public
        
        await db.commit()
        
        return RedirectResponse(
            url="/admin/sites/?success=updated",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== GESTIONE UTENTI =====

# @admin_router.get("/users/", response_class=HTMLResponse)
# async def admin_users_list(
    # request: Request,
    # db: AsyncSession = Depends(get_async_session),
    # auth_data: tuple = Depends(require_superuser)
# ):
    # """Lista utenti per amministrazione"""
    
    # superuser, base_context = auth_data
    
    # users = await db.execute(
        # select(User).order_by(User.email)
    # )
    # users = users.scalars().all()
    
    # context = {
        # **base_context,
        # "users": users,
    # }
    
    # return templates.TemplateResponse("admin/users_list.html", context)
    
# Aggiungi questi import all'inizio di admin.py


# Modello Pydantic per serializzazione utenti
class UserListItem(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_superuser: bool
    sites_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login: Optional[str] = None
    
    class Config:
        from_attributes = True

# Versione alternativa più semplice dell'endpoint
@admin_router.get("/users/", response_class=HTMLResponse)
async def admin_users_list(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Lista utenti per amministrazione - VERSIONE PYDANTIC"""
    
    superuser, base_context = auth_data
    
    # Query base utenti
    users = await db.execute(select(User).order_by(User.email))
    users = users.scalars().all()
    
    # Converti in lista serializzabile
    users_list = []
    for user in users:
        # Conta i siti per ogni utente
        sites_count_query = await db.execute(
            select(func.count(UserSitePermission.id))
            .where(
                and_(
                    UserSitePermission.user_id == user.id,
                    UserSitePermission.is_active == True
                )
            )
        )
        sites_count = sites_count_query.scalar() or 0
        
        user_dict = {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.profile.first_name if user.profile else None,
            "last_name": user.profile.last_name if user.profile else None,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_superuser": user.is_superuser,
            "sites_count": sites_count,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None
        }
        users_list.append(user_dict)
    
    context = {
        **base_context,
        "users": users_list,
    }
    
    return templates.TemplateResponse("admin/users_list.html", context)


@admin_router.get("/users/new/", response_class=HTMLResponse)
async def admin_users_new(
    request: Request,
    auth_data: tuple = Depends(require_superuser)
):
    """Form per nuovo utente"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    context = {
        **base_context,
        "user_data": None,
        "action": "create",
    }
    
    return templates.TemplateResponse("admin/users_form.html", context)

@admin_router.post("/users/new/")
async def admin_users_create(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    is_superuser: bool = Form(False),
    is_active: bool = Form(True),
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Crea nuovo utente"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    try:
        # Verifica che l'email sia unica
        existing = await db.execute(
            select(User).where(User.email == email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Email '{email}' già esistente"
            )
        
        from app.core.security import SecurityService
        hashed_password = SecurityService.get_password_hash(password)
        
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=hashed_password,
            is_active=is_active,
            is_superuser=is_superuser,
            is_verified=True
        )
        
        db.add(user)
        await db.commit()
        
        return RedirectResponse(
            url="/admin/users/?success=created",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# Aggiungi questi endpoint in admin.py per le azioni della tabella utenti

@admin_router.post("/users/{user_id}/toggle-status/")
async def admin_users_toggle_status(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Toggle stato attivo/inattivo utente"""
    
    superuser, base_context = auth_data
    
    try:
        user = await db.execute(select(User).where(User.id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Impedisce auto-disattivazione
        if user.id == superuser.id:
            raise HTTPException(
                status_code=400,
                detail="Non puoi disattivare il tuo stesso account"
            )
        
        # Toggle stato
        user.is_active = not user.is_active
        await db.commit()
        
        return JSONResponse({
            "success": True,
            "message": f"Utente {'attivato' if user.is_active else 'disattivato'} con successo",
            "is_active": user.is_active
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_router.post("/users/{user_id}/delete/")
async def admin_users_delete(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Elimina utente (soft delete)"""
    
    superuser, base_context = auth_data
    
    try:
        user = await db.execute(select(User).where(User.id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Impedisce auto-eliminazione
        if user.id == superuser.id:
            raise HTTPException(
                status_code=400,
                detail="Non puoi eliminare il tuo stesso account"
            )
        
        # Soft delete - disattiva utente e rimuovi permessi
        user.is_active = False
        
        # Disattiva tutti i permessi
        await db.execute(
            update(UserSitePermission)
            .where(UserSitePermission.user_id == user_id)
            .values(is_active=False)
        )
        
        await db.commit()
        
        return JSONResponse({
            "success": True,
            "message": "Utente eliminato con successo"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Aggiunta a admin.py per gestione modifica utenti

@admin_router.get("/users/{user_id}/edit/", response_class=HTMLResponse)
async def admin_users_edit(
    request: Request,
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Form per modifica utente"""
    superuser, base_context = auth_data
    
    # Carica utente con relazioni
    user_query = select(User).where(User.id == user_id)
    user = await db.execute(user_query)
    user = user.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    # Carica permessi utente
    permissions_query = (
        select(UserSitePermission, ArchaeologicalSite)
        .join(ArchaeologicalSite, UserSitePermission.site_id == ArchaeologicalSite.id)
        .where(UserSitePermission.user_id == user_id)
        .order_by(ArchaeologicalSite.name)
    )
    permissions = await db.execute(permissions_query)
    user_permissions = permissions.all()
    
    # Carica tutti i siti disponibili
    sites_query = select(ArchaeologicalSite).order_by(ArchaeologicalSite.name)
    sites = await db.execute(sites_query)
    available_sites = sites.scalars().all()
    
    context = {
        **base_context,
        "user_data": user,
        "user_permissions": user_permissions,
        "available_sites": available_sites,
        "permission_levels": [level.value for level in PermissionLevel],
        "action": "edit"
    }
    
    return templates.TemplateResponse("admin/users_form.html", context)

@admin_router.post("/users/{user_id}/edit/")
async def admin_users_update(
    user_id: UUID,
    email: str = Form(),
    password: Optional[str] = Form(None),
    is_superuser: bool = Form(False),
    is_active: bool = Form(True),
    is_verified: bool = Form(False),
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Aggiorna utente esistente"""
    superuser, base_context = auth_data
    
    try:
        user = await db.execute(select(User).where(User.id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Verifica unicità email (escludendo utente corrente)
        existing = await db.execute(
            select(User).where(
                and_(User.email == email, User.id != user_id)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Email '{email}' già esistente"
            )
        
        # Aggiorna campi
        user.email = email
        user.is_active = is_active
        user.is_superuser = is_superuser
        user.is_verified = is_verified
        
        # Aggiorna password solo se fornita
        if password and password.strip():
            from app.core.security import SecurityService
            user.hashed_password = SecurityService.get_password_hash(password)
        
        await db.commit()
        
        return RedirectResponse(
            url="/admin/users/?success=updated",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_router.post("/users/{user_id}/delete/")
async def admin_users_delete(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Elimina utente (soft delete)"""
    superuser, base_context = auth_data
    
    try:
        user = await db.execute(select(User).where(User.id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        # Impedisce auto-eliminazione
        if user.id == superuser.id:
            raise HTTPException(
                status_code=400,
                detail="Non puoi eliminare il tuo stesso account"
            )
        
        # Soft delete - disattiva utente
        user.is_active = False
        await db.commit()
        
        return RedirectResponse(
            url="/admin/users/?success=deleted",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Gestione permessi utente-sito
@admin_router.post("/users/{user_id}/permissions/")
async def admin_user_add_permission(
    user_id: UUID,
    site_id: UUID = Form(),
    permission_level: str = Form(),
    expires_at: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Aggiungi permesso sito per utente"""
    superuser, base_context = auth_data
    
    try:
        # Verifica esistenza utente e sito
        user = await db.execute(select(User).where(User.id == user_id))
        if not user.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        site = await db.execute(select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id))
        if not site.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Sito non trovato")
        
        # Controlla se permesso già esistente
        existing = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == user_id,
                    UserSitePermission.site_id == site_id
                )
            )
        )
        
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Permesso già esistente per questo utente e sito"
            )
        
        # Parsing data scadenza opzionale
        expires_datetime = None
        if expires_at and expires_at.strip():
            try:
                expires_datetime = datetime.fromisoformat(expires_at)
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato data non valido")
        
        # Crea permesso
        permission = UserSitePermission(
            id=uuid4(),
            user_id=user_id,
            site_id=site_id,
            permission_level=PermissionLevel(permission_level),
            expires_at=expires_datetime,
            assigned_by=superuser.id,
            notes=notes,
            is_active=True
        )
        
        db.add(permission)
        await db.commit()
        
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit/?success=permission_added",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_router.post("/users/{user_id}/permissions/{permission_id}/delete/")
async def admin_user_remove_permission(
    user_id: UUID,
    permission_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Rimuovi permesso sito da utente"""
    superuser, base_context = auth_data
    
    try:
        permission = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.id == permission_id,
                    UserSitePermission.user_id == user_id
                )
            )
        )
        permission = permission.scalar_one_or_none()
        
        if not permission:
            raise HTTPException(status_code=404, detail="Permesso non trovato")
        
        await db.delete(permission)
        await db.commit()
        
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit/?success=permission_removed",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))







# ===== GESTIONE PERMESSI SITI =====

@admin_router.get("/permissions/", response_class=HTMLResponse)
async def admin_permissions_list(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Lista permessi utenti-siti"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    permissions = await db.execute(
        select(UserSitePermission, User, ArchaeologicalSite)
        .join(User, UserSitePermission.user_id == User.id)
        .join(ArchaeologicalSite, UserSitePermission.site_id == ArchaeologicalSite.id)
        .order_by(User.email, ArchaeologicalSite.name)
    )
    permissions = permissions.all()
    
    context = {
        **base_context,
        "permissions": permissions,
    }
    
    return templates.TemplateResponse("admin/permissions_list.html", context)

@admin_router.get("/permissions/new/", response_class=HTMLResponse)
async def admin_permissions_new(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Form per nuovo permesso utente-sito"""
    # Scomponi la tupla
    superuser, base_context = auth_data
    
    users = await db.execute(select(User).order_by(User.email))
    users = users.scalars().all()
    
    sites_list = await db.execute(select(ArchaeologicalSite).order_by(ArchaeologicalSite.name))
    sites_list = sites_list.scalars().all()
    
    context = {
        **base_context,
        "users": users,
        "sites_list": sites_list,  # Rinominato per evitare conflitto
        "permission_levels": [level.value for level in PermissionLevel],
        "permission": None,
        "action": "create",
    }
    
    return templates.TemplateResponse("admin/permissions_form.html", context)

# Nel file admin.py, aggiorna questo endpoint:
@admin_router.post("/permissions/new/")
async def admin_permissions_create(
    user_id: UUID = Form(),
    site_id: UUID = Form(),
    permission_level: str = Form(),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """Crea nuovo permesso utente-sito"""
    superuser, base_context = auth_data

    try:
        # Verifica che non esista già
        existing = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == user_id,
                    UserSitePermission.site_id == site_id
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Permesso già esistente per questo utente e sito"
            )

        # Crea permesso - CORRETTO con assigned_by
        permission = UserSitePermission(
            id=uuid4(),
            user_id=user_id,
            site_id=site_id,
            permission_level=PermissionLevel(permission_level),
            is_active=True,
            assigned_by=superuser.id,  # CORRETTO: usa assigned_by
            notes=notes
        )

        db.add(permission)
        await db.commit()

        return RedirectResponse(
            url="/admin/permissions/?success=created",
            status_code=303
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== ELIMINAZIONE PERICOLOSA SITI ARCHEOLOGICI =====

@admin_router.post("/sites/{site_id}/dangerous-delete/")
async def admin_sites_dangerous_delete(
    site_id: UUID,
    request: Request,
    delete_data: Dict[str, Any],
    db: AsyncSession = Depends(get_async_session),
    auth_data: tuple = Depends(require_superuser)
):
    """
    Elimina definitivamente un sito archeologico e tutti i dati correlati.
    Operazione PERICOLOSA che richiede conferma password amministratore.
    """
    from app.core.security import SecurityService

    superuser, base_context = auth_data

    try:
        # Verifica password amministratore
        admin_password = delete_data.get("admin_password")
        if not admin_password:
            raise HTTPException(
                status_code=400,
                detail="Password amministratore richiesta"
            )

        if not SecurityService.verify_password(admin_password, superuser.hashed_password):
            raise HTTPException(
                status_code=401,
                detail="Password amministratore non corretta"
            )

        # Verifica conferma eliminazione
        confirm_delete = delete_data.get("confirm_delete", False)
        if not confirm_delete:
            raise HTTPException(
                status_code=400,
                detail="Conferma eliminazione richiesta"
            )

        # Verifica esistenza sito
        site = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        )
        site = site.scalar_one_or_none()

        if not site:
            raise HTTPException(status_code=404, detail="Sito non trovato")

        # Conta dati correlati per log
        users_count = await db.execute(
            select(func.count(UserSitePermission.id)).where(
                and_(
                    UserSitePermission.site_id == site_id,
                    UserSitePermission.is_active == True
                )
            )
        )
        users_count = users_count.scalar() or 0

        photos_count = await db.execute(
            select(func.count(Photo.id)).where(Photo.site_id == site_id)
        )
        photos_count = photos_count.scalar() or 0

        # Log operazione pericolosa
        logger.warning(
            f"ELIMINAZIONE PERICOLOSA: Sito '{site.name}' ({site.code}) "
            f"da parte di {superuser.email}. "
            f"Dati correlati: {users_count} utenti, {photos_count} foto"
        )

        # Elimina sito - CASCADE gestirà eliminazione automatica di:
        # - UserSitePermission (permessi utenti)
        # - Photo (foto del sito)
        await db.delete(site)
        await db.commit()

        logger.info(
            f"Sito '{site.name}' eliminato definitivamente da {superuser.email}"
        )

        return JSONResponse({
            "success": True,
            "message": f"Sito '{site.name}' eliminato definitivamente",
            "deleted_data": {
                "site": {
                    "id": str(site.id),
                    "name": site.name,
                    "code": site.code
                },
                "related_data": {
                    "users_permissions": users_count,
                    "photos": photos_count
                }
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore eliminazione sito {site_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore durante eliminazione: {str(e)}")