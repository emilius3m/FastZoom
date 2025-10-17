# app/services/permissions_service.py

from typing import List, Dict, Optional
from uuid import UUID
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
        
        query = select(UserSitePermission).where(UserSitePermission.user_id == user_id)
        
        if site_id:
            query = query.where(UserSitePermission.site_id == site_id)
        
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
        
        # Controlla se esiste già un permesso per questo user-site
        existing = await db.execute(
            select(UserSitePermission).where(
                and_(
                    UserSitePermission.user_id == user_id,
                    UserSitePermission.site_id == site_id
                )
            )
        )
        existing_permission = existing.scalar_one_or_none()
        
        if existing_permission:
            if replace_existing:
                # Aggiorna il permesso esistente
                existing_permission.permission_level = permission_level
                existing_permission.granted_by = granted_by
                existing_permission.expires_at = expires_at
                existing_permission.notes = notes
                existing_permission.is_active = True
                existing_permission.updated_at = datetime.now(timezone.utc)
                
                await db.commit()
                return existing_permission
            else:
                raise ValueError("Permesso già esistente per questo utente e sito")
        
        # Crea nuovo permesso
        new_permission = UserSitePermission(
            user_id=user_id,
            site_id=site_id,
            permission_level=permission_level,
            granted_by=granted_by,
            expires_at=expires_at,
            notes=notes,
            is_active=True
        )
        
        db.add(new_permission)
        await db.commit()
        
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
        """Verifica se un utente può accedere a un sito con il livello richiesto"""
        
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
            stats[row.permission_level.value] = row.count
        
        return {
            'total_users': sum(stats.values()),
            'by_level': stats
        }
