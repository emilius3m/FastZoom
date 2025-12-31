from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.models import ArchaeologicalSite
from app.models import UserSitePermission, PermissionLevel
from app.core.config import get_settings
from app.core.domain_exceptions import ResourceAlreadyExistsError

settings = get_settings()

class SiteService:
    """Servizio per gestione logica multi-sito archeologica"""
    
    @staticmethod
    async def get_user_sites(
        db: AsyncSession, 
        user_id: UUID,
        active_only: bool = True
    ) -> List[ArchaeologicalSite]:
        """
        Recupera tutti i siti accessibili da un utente
        
        Args:
            db: Sessione database
            user_id: ID utente
            active_only: Solo siti attivi
            
        Returns:
            Lista siti archeologici accessibili
        """
        query = select(ArchaeologicalSite).join(
            UserSitePermission, 
            ArchaeologicalSite.id == UserSitePermission.site_id
        ).where(
            and_(
                UserSitePermission.user_id == user_id,
                UserSitePermission.is_active == True
            )
        )
        
        if active_only:
            # Fix: Use status field instead of is_active to match ArchaeologicalSite model
            from app.models.sites import SiteStatusEnum
            query = query.where(ArchaeologicalSite.status == SiteStatusEnum.ACTIVE.value)
            
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_user_site_permission(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID
    ) -> Optional[UserSitePermission]:
        """
        Verifica permessi utente su sito specifico
        
        Args:
            db: Sessione database
            user_id: ID utente
            site_id: ID sito
            
        Returns:
            Permesso utente o None se non autorizzato
        """
        query = select(UserSitePermission).where(
            and_(
                UserSitePermission.user_id == user_id,
                UserSitePermission.site_id == site_id,
                UserSitePermission.is_active == True
            )
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def smart_redirect_after_login(user_sites: List[ArchaeologicalSite]) -> str:
        """
        Decide dove reindirizzare dopo login basato sui siti accessibili
        
        Args:
            user_sites: Lista siti utente
            
        Returns:
            URL di redirect appropriato
        """
        if not user_sites:
            return "/no-sites-available"
        elif len(user_sites) == 1:
            # Accesso diretto se utente ha un solo sito
            return f"/dashboard?site={user_sites[0].id}"
        else:
            # Selezione sito se utente ha accesso multiplo
            return "/site-selection"
    
    @staticmethod
    async def validate_site_access(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        required_permission: PermissionLevel = PermissionLevel.READ
    ) -> bool:
        """
        Valida se utente può accedere al sito con permesso richiesto
        
        Args:
            db: Sessione database
            user_id: ID utente
            site_id: ID sito
            required_permission: Livello permesso minimo richiesto
            
        Returns:
            True se autorizzato, False altrimenti
        """
        permission = await SiteService.get_user_site_permission(db, user_id, site_id)
        
        if not permission:
            return False
            
        # Gerarchia permessi: REGIONAL_ADMIN > ADMIN > WRITE > READ
        permission_hierarchy = {
            PermissionLevel.READ: 1,
            PermissionLevel.WRITE: 2,
            PermissionLevel.ADMIN: 3,
            PermissionLevel.REGIONAL_ADMIN: 4
        }
        
        user_level = permission_hierarchy.get(permission.permission_level, 0)
        required_level = permission_hierarchy.get(required_permission, 0)
        
        return user_level >= required_level
    
    @staticmethod
    async def create_site(
        db: AsyncSession,
        name: str,
        code: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs
    ) -> ArchaeologicalSite:
        """
        Crea nuovo sito archeologico
        
        Args:
            db: Sessione database
            name: Nome sito
            code: Codice identificativo sito
            location: Localizzazione
            description: Descrizione
            **kwargs: Altri parametri opzionali
            
        Returns:
            Sito archeologico creato
            
        Raises:
            HTTPException: Se sito già esistente
        """
        # Verifica unicità
        existing = await db.execute(
            select(ArchaeologicalSite).where(
                or_(
                    ArchaeologicalSite.name == name,
                    ArchaeologicalSite.code == code
                )
            )
        )
        
        if existing.scalar_one_or_none():
            raise ResourceAlreadyExistsError(
                "ArchaeologicalSite",
                f"{name} or {code}",
                details={"name": name, "code": code}
            )
        
        site = ArchaeologicalSite(
            name=name,
            code=code,
            location=location,
            description=description,
            **kwargs
        )
        
        db.add(site)
        await db.commit()
        await db.refresh(site)
        
        return site
