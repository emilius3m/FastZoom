from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from loguru import logger

from app.models import User
from app.models.sites import ArchaeologicalSite, SiteStatusEnum
from app.models import UserSitePermission, PermissionLevel
from app.core.security import SecurityService
from app.services.site_service import SiteService
from app.core.config import get_settings

settings = get_settings()

class AuthService:
    """Servizio per autenticazione archeologica multi-sito"""
    
    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str
    ) -> Optional[User]:
        """
        Autentica utente con email e password
        
        Args:
            db: Sessione database
            email: Email utente
            password: Password in chiaro
            
        Returns:
            Utente se autenticazione riuscita, None altrimenti
        """
        try:
            # Trova utente per email con eager loading delle relazioni
            query = select(User).options(
                selectinload(User.site_permissions),
                selectinload(User.profile)
            ).where(
                and_(
                    User.email == email,
                    User.is_active == True
                )
            )
            
            result = await db.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"Authentication failed: user not found or inactive - {email}")
                return None
            
            # Verifica password
            if not SecurityService.verify_password(password, user.hashed_password):
                logger.warning(f"Authentication failed: invalid password - {email}")
                return None
            
            logger.info(f"User authenticated successfully: {user.id} - {user.email}")
            return user
            
        except Exception as e:
            logger.error(f"Authentication error for {email}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def get_user_sites_with_permissions(
        db: AsyncSession,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Ottiene siti accessibili dall'utente con dettagli permessi
        Se è superuser, ha accesso a TUTTI i siti attivi
        
        Args:
            db: Sessione database
            user_id: ID utente
            
        Returns:
            Lista dizionari con info siti e permessi
        """
        try:
            if not user_id:
                logger.error(f"Invalid user_id provided: {user_id}")
                return []
            
            # Convert user_id to string for database queries
            user_id_str = str(user_id)
            
            # Load user with eager loading to prevent greenlet errors
            user_query = select(User).options(
                selectinload(User.site_permissions)
            ).where(
                (User.id == user_id_str) | (User.id == user_id_str.replace('-', ''))
            )
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"User {user_id} not found in database")
                return []
            
            # Superuser gets access to all active sites
            if user.is_superuser:
                logger.info(f"Superuser {user.email} accessing all active sites")
                return await AuthService.get_all_sites_for_superuser(db)
            
            # Check if user is active
            if not user.is_active:
                logger.warning(f"User {user.email} is not active, no site access")
                return []
            
            # Normal user: only sites with explicit permissions
            query = select(
                ArchaeologicalSite.id,
                ArchaeologicalSite.name,
                ArchaeologicalSite.code,
                ArchaeologicalSite.municipality,
                UserSitePermission.permission_level
            ).select_from(
                ArchaeologicalSite
            ).join(
                UserSitePermission,
                ArchaeologicalSite.id == UserSitePermission.site_id
            ).where(
                and_(
                    (UserSitePermission.user_id == user_id_str) | (UserSitePermission.user_id == user_id_str.replace('-', '')),
                    UserSitePermission.is_active == True,
                    ArchaeologicalSite.status == SiteStatusEnum.ACTIVE.value
                )
            ).order_by(ArchaeologicalSite.name)
            
            result = await db.execute(query)
            sites_data = []
            
            for row in result:
                if row.id and row.name:
                    sites_data.append({
                        "id": str(row.id),
                        "name": str(row.name),
                        "code": str(row.code) if row.code else "",
                        "location": str(row.municipality) if row.municipality else "",
                        "permission_level": str(row.permission_level) if row.permission_level else "read"
                    })
            
            if not sites_data:
                logger.info(f"No accessible sites found for user {user.email}")
            else:
                logger.info(f"Found {len(sites_data)} accessible sites for user {user.email}")
            
            return sites_data
            
        except Exception as e:
            logger.error(f"Error getting user sites for {user_id}: {str(e)}", exc_info=True)
            return []

    # NUOVO METODO - MANCAVA QUESTO
    @staticmethod
    async def get_all_sites_for_superuser(db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Ottiene TUTTI i siti attivi per il superadmin
        Il superadmin ha automaticamente accesso REGIONAL_ADMIN a tutti i siti
        
        Args:
            db: Sessione database
            
        Returns:
            Lista di tutti i siti attivi con permesso REGIONAL_ADMIN
        """
        try:
            query = select(
                ArchaeologicalSite.id,
                ArchaeologicalSite.name,
                ArchaeologicalSite.code,
                ArchaeologicalSite.municipality,
            ).where(
                ArchaeologicalSite.status == SiteStatusEnum.ACTIVE.value  # 🔥 FIX: Use .value to get string value
            ).order_by(ArchaeologicalSite.name)
            
            result = await db.execute(query)
            sites_data = []
            
            for row in result:
                sites_data.append({
                    "id": str(row.id),
                    "name": row.name,
                    "code": row.code,
                    "location": row.municipality or "",
                    "permission_level": "regional_admin"  # Massimo livello per superadmin
                })
            
            return sites_data
        except Exception as e:
            logger.error(f"Error in get_all_sites_for_superuser: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    @staticmethod
    async def create_login_response(
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """
        Crea risposta completa per login multi-sito
        
        Args:
            db: Sessione database
            user: Utente autenticato
            
        Returns:
            Dizionario con token e informazioni redirect
        """
        # Ottieni siti utente con permessi (gestisce automaticamente superuser)
        sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)
        
        logger.info(f"Login response for user {user.email}: {len(sites_data)} sites found")
        
        if not sites_data:
            # Verifica se è superuser - in questo caso consentiamo l'accesso anche senza siti
            if user.is_superuser:
                logger.info("Superuser accessing system without sites - allowing access for configuration")
                # Per superuser senza siti, consentiamo l'accesso con lista vuota
            else:
                logger.warning(f"User {user.email} has no site access, denying login")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Utente non ha accesso a nessun sito archeologico"
                )
        
        # Crea token JWT multi-sito
        access_token = SecurityService.create_site_aware_token(
            user_id=user.id,
            sites_data=sites_data
        )
        
        # Determina redirect intelligente
        redirect_url = await SiteService.smart_redirect_after_login(
            [{"id": site["id"], "name": site["name"]} for site in sites_data]
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(user.id),
            "user_email": user.email,
            "sites_count": len(sites_data),
            "sites": sites_data,
            "redirect_url": redirect_url,
            "multi_site_enabled": len(sites_data) > 1
        }

    @staticmethod
    async def validate_and_refresh_token(
        db: AsyncSession,
        token: str
    ) -> Dict[str, Any]:
        """
        Valida token esistente e refresh se necessario
        
        Args:
            db: Sessione database
            token: Token JWT da validare
            
        Returns:
            Payload token validato o nuovo token se refresh
        """
        try:
            payload = SecurityService.verify_token(token)
            
            # Verifica che l'utente sia ancora attivo
            user_id_str = payload.get("sub")
            user_query = select(User).options(
                selectinload(User.site_permissions),
                selectinload(User.profile)
            ).where(
                and_(User.id == user_id_str, User.is_active == True)
            )
            
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Utente non più attivo"
                )
            
            return payload
            
        except HTTPException as e:
            # Token scaduto o non valido
            raise e

    @staticmethod
    def get_login_redirect_template_data(
        sites_data: List[Dict[str, Any]],
        user_email: str
    ) -> Dict[str, Any]:
        """
        Prepara dati per template di redirect post-login
        
        Args:
            sites_data: Lista siti utente
            user_email: Email utente
            
        Returns:
            Dizionario dati per template
        """
        return {
            "user_email": user_email,
            "sites_count": len(sites_data),
            "sites": sites_data,
            "single_site": len(sites_data) == 1,
            "multiple_sites": len(sites_data) > 1,
            "site_selection_enabled": settings.site_selection_enabled,
            "museum_name": settings.museum_name
        }

    @staticmethod
    async def get_user_sites(db: AsyncSession, user_id: str) -> List[Dict[str, Any]]:
        """
        Ottieni siti accessibili dall'utente (versione legacy per compatibilità)
        
        Args:
            db: Sessione database
            user_id: ID utente come stringa
            
        Returns:
            Lista dizionari con info siti
        """
        # Since user_id is already a string, we can use it directly
        return await AuthService.get_user_sites_with_permissions(db, UUID(user_id))
