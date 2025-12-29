# app/routes/view/view_dependencies.py
# Centralized dependencies for view routes with superuser bypass

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from uuid import UUID
from typing import Optional, Tuple, Any
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import ArchaeologicalSite, User, UserSitePermission


class SuperuserPermission:
    """
    Virtual permission class for superusers.
    Provides full access without explicit UserSitePermission records.
    """
    permission_level = 'admin'
    site_role = 'superuser'
    is_active = True
    expires_at = None
    
    def can_read(self) -> bool:
        return True
    
    def can_write(self) -> bool:
        return True
    
    def can_admin(self) -> bool:
        return True
    
    def is_valid(self) -> bool:
        return True
    
    def is_expired(self) -> bool:
        return False
    
    def has_permission(self, perm: str) -> bool:
        return True


async def get_site_with_permission(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session),
    required_level: str = "read"  # "read", "write", "admin"
) -> Tuple[ArchaeologicalSite, Any, User, bool]:
    """
    Centralized dependency for view routes with SUPERUSER BYPASS.
    
    Returns:
        Tuple of (site, permission, user, is_superuser)
        
    For superusers, permission will be a SuperuserPermission instance.
    For regular users, permission will be the actual UserSitePermission or 403 is raised.
    """
    # Get site
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site_result = await db.execute(site_query)
    site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")
    
    # Get user to check superuser status
    user_query = select(User).where(User.id == str(current_user_id))
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    
    is_superuser = user.is_superuser
    
    # Superuser bypass - return virtual permission
    if is_superuser:
        logger.debug(f"Superuser {user.email} accessing site {site_id} - BYPASS")
        return site, SuperuserPermission(), user, True
    
    # Regular user - check actual permissions
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == str(current_user_id),
            UserSitePermission.site_id == str(site_id),
            UserSitePermission.is_active == True,
            or_(
                UserSitePermission.expires_at.is_(None),
                UserSitePermission.expires_at > func.now()
            )
        )
    )
    permission_result = await db.execute(permission_query)
    permission = permission_result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )
    
    # Check required level
    if required_level == "read" and not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    elif required_level == "write" and not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    elif required_level == "admin" and not permission.can_admin():
        raise HTTPException(status_code=403, detail="Permessi di amministrazione richiesti")
    
    return site, permission, user, False


# Convenience dependencies for specific permission levels
async def get_site_read_access(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> Tuple[ArchaeologicalSite, Any, User, bool]:
    """Requires read access to site"""
    return await get_site_with_permission(site_id, current_user_id, db, "read")


async def get_site_write_access(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> Tuple[ArchaeologicalSite, Any, User, bool]:
    """Requires write access to site"""
    return await get_site_with_permission(site_id, current_user_id, db, "write")


async def get_site_admin_access(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> Tuple[ArchaeologicalSite, Any, User, bool]:
    """Requires admin access to site"""
    return await get_site_with_permission(site_id, current_user_id, db, "admin")
