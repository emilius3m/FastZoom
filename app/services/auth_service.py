from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from loguru import logger

from app.models import User
from app.models.sites import ArchaeologicalSite, SiteStatusEnum
from app.models import UserSitePermission, PermissionLevel
from app.models import TokenBlacklist
from app.core.security import SecurityService
from app.services.site_service import SiteService
from app.core.config import get_settings
from app.core.domain_exceptions import (
    NoSiteAccessError,
    UserInactiveError,
    TokenInvalidError,
    TokenExpiredError,
)

settings = get_settings()

class AuthService:
    """Servizio per autenticazione archeologica multi-sito"""
    
    @logger.catch(
        reraise=True,
        message="User authentication failed for email {email}",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="authenticate_user",
            email=email,
            has_password=bool(password)
        ):
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
                    logger.warning(
                        "Authentication failed: user not found or inactive",
                        extra={
                            "email": email,
                            "reason": "user_not_found_or_inactive",
                            "user_active": False
                        }
                    )
                    return None
                
                # Verifica password
                if not SecurityService.verify_password(password, user.hashed_password):
                    logger.warning(
                        "Authentication failed: invalid password",
                        extra={
                            "email": email,
                            "reason": "invalid_password",
                            "user_id": str(user.id) if user else None,
                            "user_active": user.is_active if user else None
                        }
                    )
                    return None
                
                logger.success(
                    "User authenticated successfully",
                    extra={
                        "user_id": str(user.id),
                        "email": user.email,
                        "is_active": user.is_active,
                        "has_profile": bool(user.profile),
                        "site_permissions_count": len(user.site_permissions) if user.site_permissions else 0
                    }
                )
                return user
                
            except Exception as e:
                logger.error(
                    "Authentication error",
                    extra={
                        "email": email,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                return None

    @logger.catch(
        reraise=True,
        message="Failed to get user sites with permissions for user {user_id}",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="get_user_sites_with_permissions",
            user_id=str(user_id),
            user_id_type=type(user_id).__name__
        ):
            try:
                if not user_id:
                    logger.error(
                        "Invalid user_id provided",
                        extra={
                            "user_id": user_id,
                            "user_id_type": type(user_id).__name__ if user_id else None,
                            "reason": "empty_user_id"
                        }
                    )
                    return []
                
                # Convert user_id to string for database queries
                user_id_str = str(user_id)
                
                logger.debug(
                    "Loading user with permissions",
                    extra={
                        "user_id_str": user_id_str,
                        "loading_permissions": True
                    }
                )
                
                # Load user with eager loading to prevent greenlet errors
                user_query = select(User).options(
                    selectinload(User.site_permissions)
                ).where(User.id == user_id_str)
                user_result = await db.execute(user_query)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    logger.warning(
                        "User not found in database",
                        extra={
                            "user_id": str(user_id),
                            "user_id_str": user_id_str,
                            "reason": "user_not_found"
                        }
                    )
                    return []
                
                # Superuser gets access to all active sites
                if user.is_superuser:
                    logger.debug(
                        "Superuser accessing all active sites",
                        extra={
                            "user_email": user.email,
                            "user_id": str(user.id),
                            "is_superuser": True,
                            "access_level": "all_sites"
                        }
                    )
                    return await AuthService.get_all_sites_for_superuser(db)
                
                # Check if user is active
                if not user.is_active:
                    logger.warning(
                        "User is not active, denying site access",
                        extra={
                            "user_email": user.email,
                            "user_id": str(user.id),
                            "is_active": False,
                            "reason": "user_inactive"
                        }
                    )
                    return []
                
                logger.debug(
                    "Querying user site permissions",
                    extra={
                        "user_email": user.email,
                        "user_id": str(user.id),
                        "is_active": True,
                        "is_superuser": False
                    }
                )
                
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
                        UserSitePermission.user_id == user_id_str,
                        UserSitePermission.is_active == True,
                        ArchaeologicalSite.status == SiteStatusEnum.ACTIVE.value
                    )
                ).order_by(ArchaeologicalSite.name)
                
                result = await db.execute(query)
                sites_data = []
                
                for row in result:
                    if row.id and row.name:
                        site_data = {
                            "site_id": str(row.id),
                            "site_name": str(row.name),
                            "code": str(row.code) if row.code else "",
                            "location": str(row.municipality) if row.municipality else "",
                            "permission_level": str(row.permission_level) if row.permission_level else "read"
                        }
                        sites_data.append(site_data)
                        
                        logger.debug(
                            "Site permission found",
                            extra={
                                "site_id": site_data["site_id"],
                                "site_name": site_data["site_name"],
                                "permission_level": site_data["permission_level"],
                                "user_email": user.email
                            }
                        )
                
                if not sites_data:
                    logger.info(
                        "No accessible sites found for user",
                        extra={
                            "user_email": user.email,
                            "user_id": str(user.id),
                            "sites_count": 0,
                            "reason": "no_permissions"
                        }
                    )
                else:
                    logger.success(
                        "Found accessible sites for user",
                        extra={
                            "user_email": user.email,
                            "user_id": str(user.id),
                            "sites_count": len(sites_data),
                            "permission_levels": list(set(site["permission_level"] for site in sites_data))
                        }
                    )
                
                return sites_data
                
            except Exception as e:
                logger.error(
                    "Error getting user sites",
                    extra={
                        "user_id": str(user_id),
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                return []

    @logger.catch(
        reraise=True,
        message="Failed to get all sites for superuser",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="get_all_sites_for_superuser",
            access_level="regional_admin"
        ):
            try:
                logger.debug(
                    "Querying all active sites for superuser",
                    extra={
                        "status_filter": SiteStatusEnum.ACTIVE.value,
                        "permission_level": "regional_admin"
                    }
                )
                
                query = select(
                    ArchaeologicalSite.id,
                    ArchaeologicalSite.name,
                    ArchaeologicalSite.code,
                    ArchaeologicalSite.municipality,
                ).where(
                    ArchaeologicalSite.status == SiteStatusEnum.ACTIVE.value
                ).order_by(ArchaeologicalSite.name)
                
                result = await db.execute(query)
                sites_data = []
                
                for row in result:
                    site_data = {
                        "site_id": str(row.id),
                        "site_name": row.name,
                        "code": row.code,
                        "location": row.municipality or "",
                        "permission_level": "regional_admin"  # Massimo livello per superadmin
                    }
                    sites_data.append(site_data)
                    
                    logger.debug(
                        "Superuser site access granted",
                        extra={
                            "site_id": site_data["site_id"],
                            "site_name": site_data["site_name"],
                            "permission_level": site_data["permission_level"]
                        }
                    )
                
                logger.debug(
                    "Retrieved all active sites for superuser",
                    extra={
                        "sites_count": len(sites_data),
                        "permission_level": "regional_admin",
                        "status_filter": SiteStatusEnum.ACTIVE.value
                    }
                )
                
                return sites_data
                
            except Exception as e:
                logger.error(
                    "Error retrieving all sites for superuser",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "permission_level": "regional_admin"
                    },
                    exc_info=True
                )
                return []

    @logger.catch(
        reraise=True,
        message="Failed to create login response for user {user.email}",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="create_login_response",
            user_id=str(user.id),
            user_email=user.email,
            is_superuser=user.is_superuser
        ):
            try:
                logger.info(
                    "Creating login response",
                    extra={
                        "user_email": user.email,
                        "user_id": str(user.id),
                        "is_superuser": user.is_superuser,
                        "is_active": user.is_active
                    }
                )
                
                # Ottieni siti utente con permessi (gestisce automaticamente superuser)
                sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)
                
                logger.info(
                    "User sites retrieved for login response",
                    extra={
                        "user_email": user.email,
                        "sites_count": len(sites_data),
                        "has_sites": len(sites_data) > 0
                    }
                )
                
                if not sites_data:
                    # Verifica se è superuser - in questo caso consentiamo l'accesso anche senza siti
                    if user.is_superuser:
                        logger.info(
                            "Superuser accessing system without sites - allowing access for configuration",
                            extra={
                                "user_email": user.email,
                                "access_reason": "superuser_configuration_access",
                                "sites_count": 0
                            }
                        )
                        # Per superuser senza siti, consentiamo l'accesso con lista vuota
                    else:
                        logger.warning(
                            "User has no site access, denying login",
                            extra={
                                "user_email": user.email,
                                "user_id": str(user.id),
                                "is_superuser": False,
                                "sites_count": 0,
                                "reason": "no_site_permissions"
                            }
                        )
                        raise NoSiteAccessError(
                            "Utente non ha accesso a nessun sito archeologico",
                            details={
                                "user_id": str(user.id),
                                "user_email": user.email
                            }
                        )
                
                logger.debug(
                    "Creating site-aware JWT token",
                    extra={
                        "user_email": user.email,
                        "sites_count": len(sites_data),
                        "multi_site": len(sites_data) > 1
                    }
                )
                
                # Crea token JWT multi-sito
                access_token = SecurityService.create_site_aware_token(
                    user_id=user.id,
                    sites_data=sites_data
                )
                
                logger.debug(
                    "Determining smart redirect after login",
                    extra={
                        "user_email": user.email,
                        "sites_for_redirect": [{"id": site["site_id"], "name": site["site_name"]} for site in sites_data]
                    }
                )
                
                # Determina redirect intelligente
                redirect_url = await SiteService.smart_redirect_after_login(
                    [{"id": site["site_id"], "name": site["site_name"]} for site in sites_data]
                )
                
                login_response = {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "sites_count": len(sites_data),
                    "sites": sites_data,
                    "redirect_url": redirect_url,
                    "multi_site_enabled": len(sites_data) > 1
                }
                
                logger.success(
                    "Login response created successfully",
                    extra={
                        "user_email": user.email,
                        "user_id": str(user.id),
                        "sites_count": len(sites_data),
                        "multi_site_enabled": login_response["multi_site_enabled"],
                        "redirect_url": redirect_url,
                        "token_created": True
                    }
                )
                
                return login_response
                
            except (NoSiteAccessError, UserInactiveError):
                # Re-raise domain exceptions without modification
                raise
            except Exception as e:
                logger.error(
                    "Error creating login response",
                    extra={
                        "user_email": user.email,
                        "user_id": str(user.id),
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise

    @logger.catch(
        reraise=True,
        message="Failed to validate and refresh token",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="validate_and_refresh_token",
            has_token=bool(token),
            token_length=len(token) if token else 0
        ):
            try:
                logger.debug(
                    "Validating JWT token",
                    extra={
                        "token_length": len(token) if token else 0,
                        "has_token": bool(token)
                    }
                )
                
                payload = SecurityService.verify_token(token)
                
                user_id_str = payload.get("sub")
                
                logger.debug(
                    "Token verified, checking user status",
                    extra={
                        "user_id_str": user_id_str,
                        "token_subject": user_id_str,
                        "token_valid": True
                    }
                )
                
                # Verifica che l'utente sia ancora attivo
                user_query = select(User).options(
                    selectinload(User.site_permissions),
                    selectinload(User.profile)
                ).where(
                    and_(User.id == user_id_str, User.is_active == True)
                )
                
                result = await db.execute(user_query)
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.warning(
                        "Token validation failed - user not found or inactive",
                        extra={
                            "user_id_str": user_id_str,
                            "user_found": False,
                            "reason": "user_not_found_or_inactive"
                        }
                    )
                    raise UserInactiveError(
                        "Utente non più attivo",
                        details={"user_id": user_id_str}
                    )
                
                logger.success(
                    "Token validated successfully",
                    extra={
                        "user_id_str": user_id_str,
                        "user_email": user.email,
                        "user_active": user.is_active,
                        "has_profile": bool(user.profile),
                        "site_permissions_count": len(user.site_permissions) if user.site_permissions else 0
                    }
                )
                
                return payload
                
            except (UserInactiveError, TokenInvalidError):
                # Re-raise domain exceptions
                raise
            except Exception as e:
                logger.error(
                    "Unexpected error during token validation",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "token_length": len(token) if token else 0
                    },
                    exc_info=True
                )
                raise TokenInvalidError(
                    "Token validation failed",
                    details={"error": str(e)}
                )

    @logger.catch(
        reraise=True,
        message="Failed to prepare login redirect template data for {user_email}",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="get_login_redirect_template_data",
            user_email=user_email,
            sites_count=len(sites_data)
        ):
            try:
                logger.debug(
                    "Preparing login redirect template data",
                    extra={
                        "user_email": user_email,
                        "sites_count": len(sites_data),
                        "site_selection_enabled": settings.site_selection_enabled,
                        "museum_name": settings.museum_name
                    }
                )
                
                template_data = {
                    "user_email": user_email,
                    "sites_count": len(sites_data),
                    "sites": sites_data,
                    "single_site": len(sites_data) == 1,
                    "multiple_sites": len(sites_data) > 1,
                    "site_selection_enabled": settings.site_selection_enabled,
                    "museum_name": settings.museum_name
                }
                
                logger.info(
                    "Login redirect template data prepared",
                    extra={
                        "user_email": user_email,
                        "sites_count": len(sites_data),
                        "single_site": template_data["single_site"],
                        "multiple_sites": template_data["multiple_sites"],
                        "site_selection_enabled": template_data["site_selection_enabled"]
                    }
                )
                
                return template_data
                
            except Exception as e:
                logger.error(
                    "Error preparing login redirect template data",
                    extra={
                        "user_email": user_email,
                        "sites_count": len(sites_data),
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise

    @logger.catch(
        reraise=True,
        message="Failed to get user sites (legacy method) for user_id {user_id}",
        level="ERROR"
    )
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
        with logger.contextualize(
            operation="get_user_sites_legacy",
            user_id=user_id,
            method_type="legacy_compatibility"
        ):
            try:
                logger.debug(
                    "Legacy method called - delegating to get_user_sites_with_permissions",
                    extra={
                        "user_id": user_id,
                        "user_id_type": type(user_id).__name__,
                        "legacy_method": True
                    }
                )
                
                # Since user_id is already a string, we can use it directly
                sites_data = await AuthService.get_user_sites_with_permissions(db, UUID(user_id))
                
                logger.info(
                    "Legacy method completed successfully",
                    extra={
                        "user_id": user_id,
                        "sites_count": len(sites_data),
                        "delegated_to": "get_user_sites_with_permissions"
                    }
                )
                
                return sites_data
                
            except Exception as e:
                logger.error(
                    "Error in legacy get_user_sites method",
                    extra={
                        "user_id": user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "legacy_method": True
                    },
                    exc_info=True
                )
                raise
    
    @logger.catch(
        reraise=True,
        message="Failed to refresh access token",
        level="ERROR"
    )
    @staticmethod
    async def refresh_access_token(
        db: AsyncSession,
        refresh_token: str
    ) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Args:
            db: Database session
            refresh_token: Refresh token string
            
        Returns:
            Dictionary with new access token and metadata
            
        Raises:
            TokenInvalidError: If refresh token is invalid
            UserInactiveError: If user is inactive
        """
        with logger.contextualize(
            operation="refresh_access_token",
            has_refresh_token=bool(refresh_token)
        ):
            try:
                # Decode refresh token
                payload = SecurityService.decode_token(refresh_token)
                
                # Verify it's a refresh token
                if payload.get("type") != "refresh":
                    raise TokenInvalidError(
                        "Token non valido. Usa un refresh token.",
                        details={"token_type": payload.get("type")}
                    )
                
                # Check if token is blacklisted
                jti = payload.get("jti")
                if jti:
                    blacklisted = await db.execute(
                        select(TokenBlacklist).where(TokenBlacklist.token_jti == jti)
                    )
                    if blacklisted.scalar_one_or_none():
                        raise TokenInvalidError(
                            "Token revocato. Esegui nuovo login.",
                            details={"jti": jti}
                        )
                
                # Extract user_id
                user_id = payload.get("sub")
                if not user_id:
                    raise TokenInvalidError("Token non valido - missing user_id")
                
                # Verify user exists and is active
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                
                if not user:
                    raise TokenInvalidError(
                        "Utente non trovato",
                        details={"user_id": user_id}
                    )
                
                if not user.is_active:
                    raise UserInactiveError(
                        "Utente disabilitato",
                        details={"user_id": user_id}
                    )
                
                # Generate new access token with new JTI
                new_access_token = SecurityService.create_access_token({
                    "sub": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "su": user.is_superuser
                })
                
                logger.success(
                    "Access token refreshed successfully",
                    extra={
                        "user_id": str(user.id),
                        "user_email": user.email
                    }
                )
                
                return {
                    "access_token": new_access_token,
                    "token_type": "bearer",
                    "user_id": str(user.id),
                    "user_email": user.email
                }
                
            except (TokenInvalidError, UserInactiveError):
                # Re-raise domain exceptions
                raise
            except Exception as e:
                logger.error(
                    "Error refreshing access token",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise TokenInvalidError(
                    f"Refresh token non valido: {str(e)}",
                    details={"error": str(e)}
                )
    
    @logger.catch(
        reraise=True,
        message="Failed to logout user",
        level="ERROR"
    )
    @staticmethod
    async def logout(
        db: AsyncSession,
        token: str
    ) -> Dict[str, Any]:
        """
        Logout user by blacklisting token.
        
        Args:
            db: Database session
            token: Access token to invalidate
            
        Returns:
            Dictionary with logout status
        """
        with logger.contextualize(
            operation="logout",
            has_token=bool(token)
        ):
            try:
                # Extract user_id from token for blacklist
                try:
                    payload = SecurityService.verify_token(token)
                    user_id = UUID(payload.get("sub"))
                    
                    # Blacklist the token
                    await SecurityService.blacklist_token(token, db, user_id, "user_logout")
                    
                    logger.info(
                        "Token blacklisted successfully",
                        extra={
                            "user_id": str(user_id),
                            "reason": "user_logout"
                        }
                    )
                    
                    return {
                        "success": True,
                        "user_id": str(user_id),
                        "message": "Logout successful"
                    }
                    
                except Exception as e:
                    logger.warning(
                        "Could not blacklist token during logout",
                        extra={
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                    # Continue with logout even if blacklisting fails
                    return {
                        "success": True,
                        "message": "Logout successful (token blacklisting skipped)"
                    }
                    
            except Exception as e:
                logger.error(
                    "Error during logout",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                # Don't fail logout - return success anyway
                return {
                    "success": True,
                    "message": "Logout completed with warnings"
                }
