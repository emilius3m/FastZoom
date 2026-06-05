"""
API v1 - Team Management
Endpoints per gestione team siti archeologici.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from loguru import logger
from pydantic import BaseModel
from datetime import datetime, timezone

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)

# Models
from app.models import User, UserSitePermission, PermissionLevel, UserActivity, UserProfile
from app.models.sites import ArchaeologicalSite

router = APIRouter()

# Pydantic schemas
class TeamMemberUpdate(BaseModel):
    permission_level: str
    is_active: Optional[bool] = True
    notes: Optional[str] = None
    expires_at: Optional[str] = None
    access_duration: Optional[str] = "no_change"
    archaeological_role: Optional[str] = None
    specialization: Optional[str] = None
    institution: Optional[str] = None

class TeamInvite(BaseModel):
    email: Optional[str] = None
    permission_level: str
    user_id: Optional[str] = None
    invite_method: Optional[str] = "email"
    full_name: Optional[str] = None
    archaeological_role: Optional[str] = None
    specialization: Optional[str] = None
    institution: Optional[str] = None
    access_duration: Optional[str] = "permanent"
    welcome_message: Optional[str] = None
    notes: Optional[str] = None
    expires_at: Optional[str] = None

def normalize_permission_level(permission_level: str) -> str:
    """Validate and return the DB string value for a permission level."""
    try:
        return PermissionLevel(permission_level).value
    except ValueError:
        valid_levels = ", ".join(level.value for level in PermissionLevel)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"permission_level deve essere uno tra: {valid_levels}"
        )

def format_team_member(user: User, permission_obj: UserSitePermission) -> Dict[str, Any]:
    """Format a team member consistently for initial page data and API responses."""
    profile = getattr(user, "profile", None)
    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "permission_level": permission_obj.permission_level,
        "is_active": permission_obj.is_active,
        "is_pending": False,
        "created_at": permission_obj.created_at.isoformat() if permission_obj.created_at else None,
        "granted_at": permission_obj.created_at.isoformat() if permission_obj.created_at else None,
        "updated_at": permission_obj.updated_at.isoformat() if permission_obj.updated_at else None,
        "expires_at": permission_obj.expires_at.isoformat() if permission_obj.expires_at else None,
        "notes": permission_obj.notes,
        "archaeological_role": permission_obj.site_role or (profile.qualifica_professionale if profile else None),
        "specialization": profile.qualifica_professionale if profile else None,
        "institution": profile.ente_appartenenza if profile else None,
        "photos_uploaded": 0,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }

def update_user_profile_from_team_data(db: AsyncSession, user: User, data: Any) -> None:
    """Persist user profile fields that the team form can edit."""
    if not any([getattr(data, "specialization", None), getattr(data, "institution", None)]):
        return

    if not user.profile:
        user.profile = UserProfile(user_id=str(user.id))
        db.add(user.profile)

    if getattr(data, "specialization", None) is not None:
        user.profile.qualifica_professionale = data.specialization or None
    if getattr(data, "institution", None) is not None:
        user.profile.ente_appartenenza = data.institution or None

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    site_info = next(
        (site for site in user_sites if site["site_id"] == str(site_id)),
        None
    )
    
    if not site_info:
        raise SiteNotFoundError(str(site_id))
    
    return site_info

async def log_team_activity(
    db: AsyncSession,
    user_id: UUID,
    site_id: UUID,
    activity_type: str,
    activity_desc: str,
    extra_data: dict = None
):
    """Log attività team"""
    try:
        activity = UserActivity(
            user_id=str(user_id),
            site_id=str(site_id),
            activity_type=activity_type,
            activity_desc=activity_desc,
            extra_data=str(extra_data) if extra_data else None
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Team activity logged: {activity_type} by {user_id}")

    except Exception as e:
        logger.error(f"Error logging team activity: {e}")
        await db.rollback()

# NUOVI ENDPOINTS V1 - IMPLEMENTAZIONE COMPLETA

@router.get("/sites/{site_id}/members", summary="Lista team sito", tags=["Team Management"])
async def v1_get_site_team_members(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera tutti i membri del team di un sito.
    """
    site_info = verify_site_access(site_id, user_sites)
    
    try:
        # Query completa con JOIN per ottenere dati utente e profilo
        query = select(
            User,
            UserSitePermission
        ).join(
            UserSitePermission, UserSitePermission.user_id == User.id
        ).options(
            selectinload(User.profile)
        ).where(
            UserSitePermission.site_id == str(site_id)
        ).order_by(UserSitePermission.created_at.desc())

        result = await db.execute(query)
        team_data = result.fetchall()

        # Format response
        team_members = [
            format_team_member(user, permission_obj)
            for user, permission_obj in team_data
        ]

        return JSONResponse({
            "site_id": str(site_id),
            "members": team_members,
            "count": len(team_members),
            "site_info": site_info
        })

    except Exception as e:
        logger.error(f"Error fetching team members for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero team: {str(e)}")

@router.post("/sites/{site_id}/members", summary="Invita utente al team", tags=["Team Management"])
async def v1_invite_team_member(
    site_id: UUID,
    invite_data: TeamInvite,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Invita un nuovo utente al team del sito.
    """
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di admin/regional_admin
    if site_info.get("permission_level") not in ["admin", "regional_admin"]:
        raise InsufficientPermissionsError("Solo gli amministratori possono invitare membri al team")
    
    try:
        permission_level = normalize_permission_level(invite_data.permission_level)

        # Verifica che l'utente esista
        if invite_data.invite_method == "existing":
            if not invite_data.user_id:
                raise HTTPException(status_code=422, detail="Seleziona un utente esistente")
            user_query = select(User).options(selectinload(User.profile)).where(User.id == str(invite_data.user_id))
        else:
            if not invite_data.email:
                raise HTTPException(status_code=422, detail="Email obbligatoria per invito via email")
            user_query = select(User).options(selectinload(User.profile)).where(User.email == invite_data.email)

        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise ResourceNotFoundError("Utente", invite_data.user_id or invite_data.email)
        
        # Verifica che l'utente non sia già nel team
        existing_permission_query = select(UserSitePermission).where(
            and_(
                UserSitePermission.user_id == str(user.id),
                UserSitePermission.site_id == str(site_id)
            )
        )
        existing_permission = await db.execute(existing_permission_query)
        existing_permission = existing_permission.scalar_one_or_none()
        
        if existing_permission:
            raise DomainValidationError("L'utente è già membro del team")
        
        # Crea nuova permission
        new_permission = UserSitePermission(
            user_id=str(user.id),
            site_id=str(site_id),
            permission_level=permission_level,
            site_role=invite_data.archaeological_role,
            is_active=True,
            notes=invite_data.notes or invite_data.welcome_message,
            expires_at=datetime.fromisoformat(invite_data.expires_at) if invite_data.expires_at else None
        )
        
        db.add(new_permission)
        update_user_profile_from_team_data(db, user, invite_data)
        await db.commit()
        await db.refresh(new_permission)
        formatted_member = format_team_member(user, new_permission)
        
        # Log attività
        await log_team_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TEAM_INVITE",
            activity_desc=f"Invitato {user.email} al team con permesso {permission_level}",
            extra_data={"invited_user_id": str(user.id), "permission_level": permission_level}
        )
        
        return JSONResponse({
            "message": "Utente invitato con successo",
            "member": formatted_member,
            "user_id": str(user.id),
            "email": user.email,
            "permission_level": new_permission.permission_level
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inviting team member: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'invito: {str(e)}")

@router.put("/sites/{site_id}/members/{user_id}", summary="Aggiorna membro team", tags=["Team Management"])
async def v1_update_team_member(
    site_id: UUID,
    user_id: UUID,
    member_data: TeamMemberUpdate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Aggiorna i permessi di un membro del team.
    """
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di admin/regional_admin
    if site_info.get("permission_level") not in ["admin", "regional_admin"]:
        raise InsufficientPermissionsError("Solo gli amministratori possono modificare i permessi")
    
    try:
        permission_level = normalize_permission_level(member_data.permission_level)

        # Recupera il membro del team
        member_query = select(
            User,
            UserSitePermission
        ).join(
            UserSitePermission, UserSitePermission.user_id == User.id
        ).options(
            selectinload(User.profile)
        ).where(
            and_(
                UserSitePermission.site_id == str(site_id),
                UserSitePermission.user_id == str(user_id)
            )
        )
        member_result = await db.execute(member_query)
        member_row = member_result.first()
        
        if not member_row:
            raise HTTPException(status_code=404, detail="Membro del team non trovato")

        user, member = member_row
        
        # Aggiorna i permessi
        member.permission_level = permission_level
        member.is_active = member_data.is_active
        member.notes = member_data.notes
        member.site_role = member_data.archaeological_role or None
        update_user_profile_from_team_data(db, user, member_data)
        
        # Gestione scadenza
        if member_data.access_duration != "no_change":
            if member_data.expires_at:
                member.expires_at = datetime.fromisoformat(member_data.expires_at)
            elif member_data.access_duration == "permanent":
                member.expires_at = None
        
        member.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        formatted_member = format_team_member(user, member)
        
        # Log attività
        await log_team_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TEAM_UPDATE",
            activity_desc=f"Aggiornati permessi per utente {user_id}",
            extra_data={"updated_user_id": str(user_id), "new_permission_level": permission_level}
        )
        
        return JSONResponse({
            "message": "Permessi aggiornati con successo",
            "member": formatted_member,
            "user_id": str(user_id),
            "permission_level": formatted_member["permission_level"],
            "is_active": formatted_member["is_active"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating team member: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nell'aggiornamento: {str(e)}")

@router.delete("/sites/{site_id}/members/{user_id}", summary="Rimuovi membro team", tags=["Team Management"])
async def v1_remove_team_member(
    site_id: UUID,
    user_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Rimuove un membro dal team del sito.
    """
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di admin/regional_admin
    if site_info.get("permission_level") not in ["admin", "regional_admin"]:
        raise InsufficientPermissionsError("Solo gli amministratori possono rimuovere membri dal team")
    
    try:
        # Recupera il membro del team
        member_query = select(UserSitePermission).where(
            and_(
                UserSitePermission.site_id == str(site_id),
                UserSitePermission.user_id == str(user_id)
            )
        )
        member = await db.execute(member_query)
        member = member.scalar_one_or_none()
        
        if not member:
            raise HTTPException(status_code=404, detail="Membro del team non trovato")
        
        # Impedisce la rimozione dell'ultimo admin
        if member.permission_level == PermissionLevel.ADMIN.value:
            # Conta altri admin
            admin_count_query = select(UserSitePermission).where(
                and_(
                    UserSitePermission.site_id == str(site_id),
                    UserSitePermission.permission_level == PermissionLevel.ADMIN.value,
                    UserSitePermission.is_active == True,
                    UserSitePermission.user_id != str(user_id)
                )
            )
            admin_count = await db.execute(admin_count_query)
            admin_count = len(admin_count.scalars().all())
            
            if admin_count == 0:
                raise DomainValidationError("Non è possibile rimuovere l'ultimo amministratore del sito")
        
        # Rimuovi il membro
        await db.delete(member)
        await db.commit()
        
        # Log attività
        await log_team_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TEAM_REMOVE",
            activity_desc=f"Rimosso utente {user_id} dal team",
            extra_data={"removed_user_id": str(user_id)}
        )
        
        return JSONResponse({
            "message": "Membro rimosso con successo",
            "user_id": str(user_id)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing team member: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nella rimozione: {str(e)}")

@router.get("/sites/{site_id}/members/{user_id}", summary="Dettagli membro team", tags=["Team Management"])
async def v1_get_team_member(
    site_id: UUID,
    user_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera i dettagli di un singolo membro del team.
    """
    site_info = verify_site_access(site_id, user_sites)
    
    try:
        # Query completa con JOIN per ottenere dati utente e profilo
        query = select(
            User,
            UserSitePermission
        ).join(
            UserSitePermission, UserSitePermission.user_id == User.id
        ).options(
            selectinload(User.profile)
        ).where(
            and_(
                UserSitePermission.site_id == str(site_id),
                UserSitePermission.user_id == str(user_id)
            )
        )

        result = await db.execute(query)
        member_data = result.first()
        
        if not member_data:
            raise HTTPException(status_code=404, detail="Membro del team non trovato")
        
        user, permission_obj = member_data
        member_details = format_team_member(user, permission_obj)

        return JSONResponse({
            "member": member_details,
            "site_info": site_info
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching team member {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero dettagli: {str(e)}")

@router.get("/sites/{site_id}/available-users", summary="Utenti disponibili per invito", tags=["Team Management"])
async def v1_get_available_users_for_invite(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_database_session)
):
    """
    Recupera utenti disponibili per l'invito al team.
    """
    site_info = verify_site_access(site_id, user_sites)
    
    # Verifica permessi di admin/regional_admin
    if site_info.get("permission_level") not in ["admin", "regional_admin"]:
        raise InsufficientPermissionsError("Solo gli amministratori possono invitare membri")
    
    try:
        # Recupera utenti non ancora membri del team
        existing_members_query = select(UserSitePermission.user_id).where(
            UserSitePermission.site_id == str(site_id)
        )
        existing_members_result = await db.execute(existing_members_query)
        existing_member_ids = [row[0] for row in existing_members_result.fetchall()]
        
        all_users_query = select(User).options(
            selectinload(User.profile)
        ).where(
            and_(
                User.id != current_user_id,  # Escludi se stesso
                ~User.id.in_(existing_member_ids)  # Escludi già membri
            )
        ).order_by(User.email)
        
        all_users_result = await db.execute(all_users_query)
        all_users = all_users_result.scalars().all()
        
        # Formatta risultati
        available_users = []
        for user in all_users:
            available_users.append({
                "id": str(user.id),
                "name": user.full_name or user.email,
                "email": user.email
            })
        
        return JSONResponse({
            "available_users": available_users,
            "total": len(available_users)
        })
        
    except Exception as e:
        logger.error(f"Error fetching available users for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore nel recupero utenti: {str(e)}")

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API teams", tags=["Team Management - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per teams.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/{site_id}/team": "/api/v1/teams/sites/{site_id}/members",
                "/api/{site_id}/team/{user_id}/update-permissions": "/api/v1/teams/sites/{site_id}/members/{user_id}"
            },
            "new_endpoints": {
                "/api/v1/teams/sites/{site_id}/members": "Lista completa team",
                "/api/v1/teams/sites/{site_id}/members": "Invita nuovo membro (POST)",
                "/api/v1/teams/sites/{site_id}/members/{user_id}": "Dettagli membro (GET)",
                "/api/v1/teams/sites/{site_id}/members/{user_id}": "Aggiorna membro (PUT)",
                "/api/v1/teams/sites/{site_id}/members/{user_id}": "Rimuovi membro (DELETE)"
            },
            "changes": [
                "Standardizzazione URL patterns RESTful",
                "Agregazione endpoints teams in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata",
                "CRUD completo per gestione team",
                "Validazione permessi granulare",
                "Logging attività completo"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints teams"
        }
    }
