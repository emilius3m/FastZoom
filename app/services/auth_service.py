from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
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
        # Trova utente per email
        query = select(User).where(
            and_(
                User.email == email,
                User.is_active == True
            )
        )
        
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        # Verifica password
        if not SecurityService.verify_password(password, user.hashed_password):
            return None

        print(user.id, user.email, user.is_active)
        return user

    @staticmethod
    async def get_user_sites_with_permissions(
        db: AsyncSession,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Ottiene siti accessibili dall'utente con dettagli permessi
        Se è superuser, ha accesso a TUTTI i siti attivi
        
        🔧 ENHANCED: Improved error handling and comprehensive debugging
        
        Args:
            db: Sessione database
            user_id: ID utente
            
        Returns:
            Lista dizionari con info siti e permessi
        """
        try:
            # 🔍 DEBUG: Enhanced logging for troubleshooting
            logger.info(f"🐛 [DEBUG] get_user_sites_with_permissions - START")
            logger.info(f"🐛 [DEBUG] Input user_id: {user_id} (type: {type(user_id)})")
            
            # 🔍 DEBUG: Validate input user_id
            if not user_id:
                logger.error(f"🐛 [DEBUG] Invalid user_id provided: {user_id}")
                return []
            
            # Prima verifica se è superuser
            logger.info(f"🐛 [DEBUG] Checking if user {user_id} is superuser...")
            
            # 🔧 UUID FORMAT FIX: Handle both dashed and non-dashed UUID formats
            user_id_str = str(user_id)
            user_id_no_dashes = user_id_str.replace('-', '')
            
            logger.info(f"🐛 [DEBUG] UUID formats to try:")
            logger.info(f"🐛 [DEBUG]  - With dashes: {user_id_str}")
            logger.info(f"🐛 [DEBUG]  - Without dashes: {user_id_no_dashes}")
            
            # Try with dashes first, then without dashes
            user_query = select(User).where(
                (User.id == user_id_str) | (User.id == user_id_no_dashes)
            )
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            logger.info(f"🐛 [DEBUG] User found: {user is not None}")
            if user:
                logger.info(f"🐛 [DEBUG] User details - email: {user.email}, is_active: {user.is_active}, is_superuser: {user.is_superuser}")
            else:
                logger.error(f"🐛 [DEBUG] User {user_id} not found in database!")
                return []
            
            if user and user.is_superuser:
                logger.info(f"🐛 [DEBUG] Superuser detected, getting all active sites")
                # SUPERADMIN: accesso a tutti i siti attivi
                return await AuthService.get_all_sites_for_superuser(db)
            
            # 🔍 DEBUG: Enhanced logging for normal user permissions
            logger.info(f"🐛 [DEBUG] Normal user detected, checking explicit permissions...")
            logger.info(f"🐛 [DEBUG] User is_active: {user.is_active}")
            
            if not user.is_active:
                logger.warning(f"🐛 [DEBUG] User {user_id} is not active, no site access")
                return []
            
            # 🔍 DEBUG: Enhanced query construction with validation
            logger.info(f"🐛 [DEBUG] Building site permissions query...")
            logger.info(f"🐛 [DEBUG] Query filters:")
            logger.info(f"🐛 [DEBUG]  - user_id: {user_id}")
            logger.info(f"🐛 [DEBUG]  - permission_active: True")
            logger.info(f"🐛 [DEBUG]  - site_status: {SiteStatusEnum.ACTIVE.value} (type: {type(SiteStatusEnum.ACTIVE.value)})")
            
            # UTENTE NORMALE: solo siti con permessi espliciti
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
                    (UserSitePermission.user_id == user_id_str) | (UserSitePermission.user_id == user_id_no_dashes),  # 🔧 FIX: Handle both UUID formats
                    UserSitePermission.is_active == True,
                    ArchaeologicalSite.status == SiteStatusEnum.ACTIVE.value
                )
            ).order_by(ArchaeologicalSite.name)
            
            logger.info(f"🐛 [DEBUG] Executing site permissions query...")
            result = await db.execute(query)
            sites_data = []
            
            logger.info(f"🐛 [DEBUG] Processing query results...")
            row_count = 0
            for row in result:
                row_count += 1
                logger.info(f"🐛 [DEBUG] Site {row_count}: {row.name} (ID: {row.id}, permission: {row.permission_level})")
                
                # 🔍 DEBUG: Validate site data before adding
                if row.id and row.name:
                    sites_data.append({
                        "id": str(row.id),  # 🔧 FIX: Ensure consistent UUID string format
                        "name": str(row.name),
                        "code": str(row.code) if row.code else "",
                        "location": str(row.municipality) if row.municipality else "",
                        "permission_level": str(row.permission_level) if row.permission_level else "read"
                    })
                else:
                    logger.warning(f"🐛 [DEBUG] Skipping invalid site row: {row}")
            
            logger.info(f"🐛 [DEBUG] Query processing complete. Processed {row_count} rows, returning {len(sites_data)} valid sites")
            
            if not sites_data:
                logger.warning(f"🐛 [DEBUG] No accessible sites found for user {user_id}")
                logger.warning(f"🐛 [DEBUG] This could mean:")
                logger.warning(f"🐛 [DEBUG]  - User has no explicit permissions")
                logger.warning(f"🐛 [DEBUG]  - All accessible sites are inactive")
                logger.warning(f"🐛 [DEBUG]  - Permission records are inactive")
            else:
                logger.info(f"🐛 [DEBUG] Successfully found {len(sites_data)} accessible sites for user {user_id}")
                for site in sites_data:
                    logger.info(f"🐛 [DEBUG]  - {site['name']} (ID: {site['id']}, permission: {site['permission_level']})")
            
            return sites_data
            
        except Exception as e:
            # 🔍 DEBUG: Enhanced error logging
            logger.error(f"🐛 [DEBUG] get_user_sites_with_permissions - ERROR: {str(e)}")
            logger.error(f"🐛 [DEBUG] Error type: {type(e).__name__}")
            logger.error(f"🐛 [DEBUG] User ID: {user_id} (type: {type(user_id)})")
            import traceback
            logger.error(f"🐛 [DEBUG] Full traceback: {traceback.format_exc()}")
            
            # Return empty list on error to prevent system crashes
            logger.error(f"🐛 [DEBUG] Returning empty sites list due to error")
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
        print(sites_data)
        
        if not sites_data:
            # Verifica se è superuser - in questo caso consentiamo l'accesso anche senza siti
            user_query = select(User).where(User.id == user.id)
            user_result = await db.execute(user_query)
            db_user = user_result.scalar_one_or_none()

            if db_user and db_user.is_superuser:
                print("Superuser accessing system without sites - allowing access for configuration")
                # Per superuser senza siti, consentiamo l'accesso con lista vuota
            else:
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
            user_query = select(User).where(
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
