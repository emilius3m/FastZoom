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
from app.models import User, UserSitePermission, PermissionLevel, UserActivity
from app.models.sites import ArchaeologicalSite

router = APIRouter()

# Pydantic schemas
class TeamMemberUpdate(BaseModel):
    permission_level: str
    is_active: Optional[bool] = True
    notes: Optional[str] = None
    expires_at: Optional[str] = None
    access_duration: Optional[str] = "no_change"

class TeamInvite(BaseModel):
    email: str
    permission_level: str
    notes: Optional[str] = None
    expires_at: Optional[str] = None

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
        # Query completa con JOIN per ottenere dati utente
        query = select(
            UserSitePermission,
            User.email,
            User.full_name,
            User.profile_data
        ).join(
            User, UserSitePermission.user_id == User.id
        ).where(
            UserSitePermission.site_id == str(site_id)
        ).order_by(UserSitePermission.created_at.desc())

        result = await db.execute(query)
        team_data = result.fetchall()

        # Format response
        team_members = []
        for permission_obj, email, full_name, profile_data in team_data:
            # Parse profile_data if it's JSON
            profile = {}
            if profile_data:
                try:
                    import json
                    profile = json.loads(profile_data)
                except:
                    pass

            member_data = {
                "user_id": str(permission_obj.user_id),
                "email": email,
                "full_name": full_name,
                "permission_level": permission_obj.permission_level,
                "is_active": permission_obj.is_active,
                "created_at": permission_obj.created_at.isoformat(),
                "updated_at": permission_obj.updated_at.isoformat() if permission_obj.updated_at else None,
                "expires_at": permission_obj.expires_at.isoformat() if permission_obj.expires_at else None,
                "notes": permission_obj.notes,
                # Additional fields from profile
                "archaeological_role": profile.get("archaeological_role"),
                "specialization": profile.get("specialization"),
                "institution": profile.get("institution"),
            }

            team_members.append(member_data)

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
    
    # Verifica permessi di admin
    if site_info.get("permission_level") not in ["admin"]:
        raise InsufficientPermissionsError("Solo gli amministratori possono invitare membri al team")
    
    try:
        # Verifica che l'utente esista
        user_query = select(User).where(User.email == invite_data.email)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise ResourceNotFoundError("Utente", invite_data.email)
        
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
            permission_level=PermissionLevel(invite_data.permission_level),
            is_active=True,
            notes=invite_data.notes,
            expires_at=datetime.fromisoformat(invite_data.expires_at) if invite_data.expires_at else None
        )
        
        db.add(new_permission)
        await db.commit()
        await db.refresh(new_permission)
        
        # Log attività
        await log_team_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TEAM_INVITE",
            activity_desc=f"Invitato {invite_data.email} al team con permesso {invite_data.permission_level}",
            extra_data={"invited_user_id": str(user.id), "permission_level": invite_data.permission_level}
        )
        
        return JSONResponse({
            "message": "Utente invitato con successo",
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
    
    # Verifica permessi di admin
    if site_info.get("permission_level") not in ["admin"]:
        raise InsufficientPermissionsError("Solo gli amministratori possono modificare i permessi")
    
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
        
        # Aggiorna i permessi
        member.permission_level = PermissionLevel(member_data.permission_level)
        member.is_active = member_data.is_active
        member.notes = member_data.notes
        
        # Gestione scadenza
        if member_data.access_duration != "no_change":
            if member_data.expires_at:
                member.expires_at = datetime.fromisoformat(member_data.expires_at)
            elif member_data.access_duration == "permanent":
                member.expires_at = None
        
        member.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        # Log attività
        await log_team_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="TEAM_UPDATE",
            activity_desc=f"Aggiornati permessi per utente {user_id}",
            extra_data={"updated_user_id": str(user_id), "new_permission_level": member_data.permission_level}
        )
        
        return JSONResponse({
            "message": "Permessi aggiornati con successo",
            "user_id": str(user_id),
            "permission_level": member.permission_level,
            "is_active": member.is_active
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
    
    # Verifica permessi di admin
    if site_info.get("permission_level") not in ["admin"]:
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
        if member.permission_level == PermissionLevel.ADMIN:
            # Conta altri admin
            admin_count_query = select(UserSitePermission).where(
                and_(
                    UserSitePermission.site_id == str(site_id),
                    UserSitePermission.permission_level == PermissionLevel.ADMIN,
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
        # Query completa con JOIN per ottenere dati utente
        query = select(
            UserSitePermission,
            User.email,
            User.full_name,
            User.profile_data
        ).join(
            User, UserSitePermission.user_id == User.id
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
        
        permission_obj, email, full_name, profile_data = member_data
        
        # Parse profile_data if it's JSON
        profile = {}
        if profile_data:
            try:
                import json
                profile = json.loads(profile_data)
            except:
                pass

        member_details = {
            "user_id": str(permission_obj.user_id),
            "email": email,
            "full_name": full_name,
            "permission_level": permission_obj.permission_level,
            "is_active": permission_obj.is_active,
            "created_at": permission_obj.created_at.isoformat(),
            "updated_at": permission_obj.updated_at.isoformat() if permission_obj.updated_at else None,
            "expires_at": permission_obj.expires_at.isoformat() if permission_obj.expires_at else None,
            "notes": permission_obj.notes,
            # Additional fields from profile
            "archaeological_role": profile.get("archaeological_role"),
            "specialization": profile.get("specialization"),
            "institution": profile.get("institution"),
        }

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
    
    # Verifica permessi di admin
    if site_info.get("permission_level") not in ["admin"]:
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