# app/services/permissions_service.py

from typing import List, Dict, Optional
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from datetime import datetime, timezone

from app.models import User
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission, PermissionLevel

class PermissionsService:
    """Servizio per la gestione dei permessi utenti multi-sito"""
    
    @staticmethod
    async def get_user_permissions(
        db: AsyncSession,
        user_id: UUID,
        site_id: Optional[UUID] = None,
        active_only: bool = True
    ) -> List[UserSitePermission]:
        """Recupera i permessi di un utente, opzionalmente filtrati per sito"""
        
        query = select(UserSitePermission).where(UserSitePermission.user_id == str(user_id))
        
        if site_id:
            query = query.where(UserSitePermission.site_id == str(site_id))
        
        if active_only:
            query = query.where(
                and_(
                    UserSitePermission.is_active == True,
                    or_(
                        UserSitePermission.expires_at.is_(None),
                        UserSitePermission.expires_at > func.now()
                    )
                )
            )
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def assign_permission(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        permission_level: PermissionLevel,
        granted_by: UUID,
        expires_at: Optional[datetime] = None,
        notes: Optional[str] = None,
        replace_existing: bool = True
    ) -> UserSitePermission:
        """Assegna un permesso a un utente per un sito"""
        
        # DEBUG: Log incoming parameters
        from loguru import logger
        logger.info(f"[DEBUG] PermissionsService.assign_permission called")
        logger.info(f"[DEBUG] user_id: {user_id} (type: {type(user_id)})")
        logger.info(f"[DEBUG] site_id: {site_id} (type: {type(site_id)})")
        logger.info(f"[DEBUG] permission_level: {permission_level} (type: {type(permission_level)})")
        logger.info(f"[DEBUG] granted_by: {granted_by} (type: {type(granted_by)})")
        logger.info(f"[DEBUG] expires_at: {expires_at}")
        logger.info(f"[DEBUG] notes: {notes}")
        logger.info(f"[DEBUG] replace_existing: {replace_existing}")
        
        # Controlla se esiste già un permesso per questo user-site
        logger.info(f"[DEBUG] Checking for existing permission...")
        existing = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == str(user_id),
                    UserSitePermission.site_id == str(site_id)
                )
            )
        )
        existing_permission = existing.scalar_one_or_none()
        logger.info(f"[DEBUG] Existing permission found: {existing_permission}")
        
        if existing_permission:
            logger.info(f"[DEBUG] Existing permission found, updating...")
            if replace_existing:
                # Aggiorna il permesso esistente
                existing_permission.permission_level = permission_level
                existing_permission.granted_by = str(granted_by)
                existing_permission.expires_at = expires_at
                existing_permission.notes = notes
                existing_permission.is_active = True
                existing_permission.updated_at = datetime.now(timezone.utc)
                
                logger.info(f"[DEBUG] Updated existing permission: {existing_permission}")
                await db.commit()
                logger.info(f"[DEBUG] Database commit completed for updated permission")
                
                # Verify the update
                verify_query = await db.execute(
                    select(UserSitePermission).where(UserSitePermission.id == existing_permission.id)
                )
                verified_permission = verify_query.scalar_one_or_none()
                logger.info(f"[DEBUG] Verified updated permission: {verified_permission}")
                
                return existing_permission
            else:
                raise ValueError("Permesso già esistente per questo utente e sito")
        
        # Crea nuovo permesso
        logger.info(f"[DEBUG] Creating new permission...")
        new_permission_id = str(uuid4())
        logger.info(f"[DEBUG] New permission ID: {new_permission_id}")
        
        new_permission = UserSitePermission(
            id=new_permission_id,  # Convert UUID to string for SQLite compatibility
            user_id=str(user_id),  # Convert UUID to string for SQLite compatibility
            site_id=str(site_id),  # Convert UUID to string for SQLite compatibility
            permission_level=permission_level,
            permissions=[],  # Initialize with empty list to satisfy NOT NULL constraint
            granted_by=str(granted_by),  # Convert UUID to string for SQLite compatibility
            expires_at=expires_at,
            notes=notes,
            is_active=True
        )
        
        logger.info(f"[DEBUG] New permission object created: {new_permission}")
        
        db.add(new_permission)
        logger.info(f"[DEBUG] Permission added to session")
        
        await db.commit()
        logger.info(f"[DEBUG] Database commit completed for new permission")
        
        # Verify the permission was actually saved
        verify_query = await db.execute(
            select(UserSitePermission).where(UserSitePermission.id == new_permission_id)
        )
        verified_permission = verify_query.scalar_one_or_none()
        logger.info(f"[DEBUG] Verified new permission: {verified_permission}")
        
        return new_permission
    
    @staticmethod
    async def revoke_permission(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        soft_delete: bool = True
    ) -> bool:
        """Revoca un permesso utente per un sito"""
        
        permission = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == user_id,
                    UserSitePermission.site_id == site_id
                )
            )
        )
        permission = permission.scalar_one_or_none()
        
        if not permission:
            return False
        
        if soft_delete:
            # Disattiva il permesso
            permission.is_active = False
            permission.updated_at = datetime.now(timezone.utc)
        else:
            # Elimina fisicamente
            await db.delete(permission)
        
        await db.commit()
        return True
    
    @staticmethod
    async def user_can_access_site(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        required_level: PermissionLevel = PermissionLevel.READ
    ) -> bool:
        """Verifica se un utente può accedere a un sito con il livello richiesto. Include check superuser."""
        
        # 1. Check Superuser
        user_query = select(User).where(User.id == str(user_id))
        result = await db.execute(user_query)
        user = result.scalar_one_or_none()
        
        if user and user.is_superuser:
            return True
        
        # 2. Check Permissions
        permissions = await PermissionsService.get_user_permissions(
            db, user_id, site_id, active_only=True
        )
        
        for permission in permissions:
            if permission.has_permission_level(required_level):
                return True
        
        return False
    
    @staticmethod
    async def get_site_statistics(
        db: AsyncSession,
        site_id: UUID
    ) -> Dict:
        """Statistiche sui permessi per un sito"""
        
        stats_query = (
            select(
                UserSitePermission.permission_level,
                func.count(UserSitePermission.id).label('count')
            )
            .where(
                and_(
                    UserSitePermission.site_id == site_id,
                    UserSitePermission.is_active == True,
                    or_(
                        UserSitePermission.expires_at.is_(None),
                        UserSitePermission.expires_at > func.now()
                    )
                )
            )
            .group_by(UserSitePermission.permission_level)
        )
        
        result = await db.execute(stats_query)
        
        stats = {level.value: 0 for level in PermissionLevel}
        for row in result:
            stats[row.permission_level] = row.count
        
        return {
            'total_users': sum(stats.values()),
            'by_level': stats
        }
