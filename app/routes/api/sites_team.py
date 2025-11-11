# app/routes/api/sites_team.py - Team management API endpoints

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, List
import json

from app.database.session import get_async_session
from app.models import UserSitePermission, PermissionLevel
from app.models import User
from app.routes.api.dependencies import get_site_access

team_router = APIRouter()


@team_router.get("/{site_id}/api/team")
async def get_team_members(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Get team members for a site"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    # Query corretta con JOIN per ottenere dati utente
    query = select(
        UserSitePermission,
        User.email,
        User.profile_data
    ).join(
        User, UserSitePermission.user_id == User.id
    ).where(
        UserSitePermission.site_id == site_id
    ).order_by(UserSitePermission.created_at.desc())

    result = await db.execute(query)
    team_data = result.fetchall()

    # Format response
    team_members = []
    for permission_obj, email, profile_data in team_data:
        # Parse profile_data if it's JSON
        profile = {}
        if profile_data:
            try:
                profile = json.loads(profile_data)
            except:
                pass

        member_data = {
            "user_id": str(permission_obj.user_id),
            "email": email,
            "permission_level": permission_obj.permission_level,
            "is_active": permission_obj.is_active,
            "is_pending": False,
            "created_at": permission_obj.created_at.isoformat(),
            "expires_at": permission_obj.expires_at.isoformat() if permission_obj.expires_at else None,
            "notes": permission_obj.notes,
            # Additional fields from profile
            "archaeological_role": profile.get("archaeological_role"),
            "specialization": profile.get("specialization"),
            "institution": profile.get("institution"),
            # Stats
            "photos_uploaded": 0,
            "last_login_at": None,
        }

        team_members.append(member_data)

    return {
        "team_members": team_members,
        "total": len(team_members)
    }


@team_router.put("/{site_id}/team/{user_id}/update-permissions")
async def update_team_member_permissions(
        site_id: UUID,
        user_id: UUID,
        permission_data: dict,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Update team member permissions"""
    site, permission = site_access

    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Solo gli amministratori possono modificare i permessi")

    # Usa UserSitePermission invece di UserSite
    member_query = select(UserSitePermission).where(
        and_(UserSitePermission.site_id == site_id, UserSitePermission.user_id == user_id)
    )
    member = await db.execute(member_query)
    member = member.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Membro del team non trovato")

    # Update permissions
    member.permission_level = PermissionLevel(permission_data.get('permission_level', member.permission_level))
    member.is_active = permission_data.get('is_active', member.is_active)

    # Update additional fields
    if 'notes' in permission_data:
        member.notes = permission_data['notes']

    # Update expiry if specified
    if permission_data.get('access_duration') != 'no_change':
        if permission_data.get('expires_at'):
            member.expires_at = datetime.fromisoformat(permission_data['expires_at'])
        elif permission_data.get('access_duration') == 'permanent':
            member.expires_at = None

    member.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {"message": "Permessi aggiornati con successo"}


async def get_site_team(db: AsyncSession, site_id: UUID) -> List[Dict]:
    """Recupera team del sito"""
    team_query = select(User, UserSitePermission).join(
        UserSitePermission, User.id == UserSitePermission.user_id
    ).options(selectinload(User.profile)).where(
        and_(
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        )
    ).order_by(UserSitePermission.permission_level.desc())

    team = await db.execute(team_query)
    team = team.all()

    return [
        {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "permission_level": permission.permission_level,
            "permission_display": permission.permission_level.replace('_', ' ').title(),
            "granted_at": permission.created_at.isoformat()
        }
        for user, permission in team
    ]