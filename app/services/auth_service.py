from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status

from app.models.users import User
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission, PermissionLevel
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
        
        Args:
            db: Sessione database
            user_id: ID utente
            
        Returns:
            Lista dizionari con info siti e permessi
        """
        # Prima verifica se è superuser
        user_query = select(User).where(User.id == user_id)
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if user and user.is_superuser:
            # SUPERADMIN: accesso a tutti i siti attivi
            return await AuthService.get_all_sites_for_superuser(db)
        
        # UTENTE NORMALE: solo siti con permessi espliciti
        query = select(
            ArchaeologicalSite.id,
            ArchaeologicalSite.name,
            ArchaeologicalSite.code,
            ArchaeologicalSite.location,
            UserSitePermission.permission_level
        ).select_from(
            ArchaeologicalSite
        ).join(
            UserSitePermission,
            ArchaeologicalSite.id == UserSitePermission.site_id
        ).where(
            and_(
                UserSitePermission.user_id == user_id,
                UserSitePermission.is_active == True,
                ArchaeologicalSite.is_active == True
            )
        ).order_by(ArchaeologicalSite.name)
        
        result = await db.execute(query)
        sites_data = []
        
        for row in result:
            sites_data.append({
                "id": str(row.id),
                "name": row.name,
                "code": row.code,
                "location": row.location or "",
                "permission_level": row.permission_level.value
            })
        
        return sites_data

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
            ArchaeologicalSite.location,
        ).where(
            ArchaeologicalSite.is_active == True
        ).order_by(ArchaeologicalSite.name)
        
        result = await db.execute(query)
        sites_data = []
        
        for row in result:
            sites_data.append({
                "id": str(row.id),
                "name": row.name,
                "code": row.code,
                "location": row.location or "",
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
            user_id = UUID(payload.get("sub"))
            user_query = select(User).where(
                and_(User.id == user_id, User.is_active == True)
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
