import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Cookie, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.db import get_async_session
from app.models import User
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission, PermissionLevel
from app.core.config import get_settings

# ===== CONFIGURAZIONE SICUREZZA =====

# Ottieni secret key da configurazione
def get_secret_key() -> str:
    settings = get_settings()
    return settings.secret_key

# Bearer token scheme per Authorization header
security = HTTPBearer(auto_error=False)

# ===== CLASSE PRINCIPALE SICUREZZA =====

class SecurityService:
    """
    Servizio sicurezza personalizzato per sistema archeologico
    Rimpiazza completamente fastapi-users
    """
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash password con bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica password"""
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Crea JWT token"""
        settings = get_settings()
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })
        
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """Verifica e decodifica JWT token"""
        try:
            settings = get_settings()
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            
            # Controlla scadenza
            exp = payload.get("exp")
            if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
                return None
                
            return payload
        except jwt.PyJWTError as e:
            logger.debug(f"Token verification failed: {e}")
            return None
    
    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
        """Autentica utente con email e password"""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            logger.debug(f"User not found or inactive: {email}")
            return None
        
        if not SecurityService.verify_password(password, user.hashed_password):
            logger.debug(f"Invalid password for user: {email}")
            return None
        
        logger.info(f"User authenticated successfully: {email}")
        return user

# ===== DEPENDENCY FUNCTIONS =====

async def get_current_user_from_token(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = Cookie(None, alias="access_token")
) -> Optional[User]:
    """
    Ottieni utente corrente da token JWT (Authorization header o cookie)
    """
    # Prova prima Authorization header
    jwt_token = None
    if credentials:
        jwt_token = credentials.credentials
    # Poi prova cookie
    elif token:
        jwt_token = token
    
    if not jwt_token:
        return None
    
    # Rimuovi "Bearer " prefix se presente (per cookie)
    if jwt_token.startswith("Bearer "):
        jwt_token = jwt_token[7:]
    
    # Verifica token
    payload = SecurityService.verify_token(jwt_token)
    if not payload:
        return None
    
    # Ottieni user_id dal payload
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return None
    
    # Carica utente dal database
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        return None
    
    return user

async def get_current_user_id(
    current_user: Optional[User] = Depends(get_current_user_from_token)
) -> UUID:
    """
    Dependency che richiede utente autenticato e restituisce solo l'ID
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user.id

async def get_current_user(
    current_user: Optional[User] = Depends(get_current_user_from_token)
) -> User:
    """
    Dependency che richiede utente autenticato
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency per utente attivo (alias per compatibilità)
    """
    return current_user

async def get_current_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency che richiede superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required"
        )
    return current_user

# ===== FUNZIONI SISTEMA ARCHEOLOGICO =====

async def get_current_user_sites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> List[Dict[str, Any]]:
    """
    Ottieni siti accessibili dall'utente corrente con i relativi permessi
    """
    # Superuser ha accesso a tutti i siti
    if current_user.is_superuser:
        sites_result = await db.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.is_active == True)
        )
        sites = sites_result.scalars().all()
        
        return [
            {
                "id": str(site.id),
                "name": site.name,
                "code": site.code,
                "region": site.region,
                "permission_level": "regional_admin",
                "is_superuser_access": True
            }
            for site in sites
        ]
    
    # Utente normale - solo siti con permessi espliciti
    permissions_result = await db.execute(
        select(UserSitePermission, ArchaeologicalSite)
        .join(ArchaeologicalSite, UserSitePermission.site_id == ArchaeologicalSite.id)
        .where(
            UserSitePermission.user_id == current_user.id,
            UserSitePermission.is_active == True,
            ArchaeologicalSite.is_active == True
        )
    )
    permissions = permissions_result.all()
    
    return [
        {
            "id": str(site.id),
            "name": site.name,
            "code": site.code,
            "region": site.region,
            "permission_level": perm.permission_level,
            "is_superuser_access": False
        }
        for perm, site in permissions
    ]

async def require_site_access(
    site_id: UUID,
    required_level: PermissionLevel = PermissionLevel.READ,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """
    Dependency che richiede accesso ad un sito specifico con livello minimo
    """
    # Superuser ha sempre accesso
    if current_user.is_superuser:
        return current_user
    
    # Controlla permessi espliciti
    permission_result = await db.execute(
        select(UserSitePermission).where(
            UserSitePermission.user_id == current_user.id,
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        )
    )
    permission = permission_result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this archaeological site is not allowed"
        )
    
    # Controlla livello permesso
    permission_levels = [
        PermissionLevel.READ,
        PermissionLevel.WRITE,
        PermissionLevel.ADMIN,
        PermissionLevel.REGIONAL_ADMIN
    ]
    
    user_level_index = permission_levels.index(permission.permission_level)
    required_level_index = permission_levels.index(required_level)
    
    if user_level_index < required_level_index:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required permission level: {required_level.value}"
        )
    
    return current_user

async def require_regional_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """
    Dependency che richiede almeno un accesso regional_admin
    """
    if current_user.is_superuser:
        return current_user
    
    # Controlla se ha almeno un permesso regional_admin
    regional_permission = await db.execute(
        select(UserSitePermission).where(
            UserSitePermission.user_id == current_user.id,
            UserSitePermission.permission_level == PermissionLevel.REGIONAL_ADMIN,
            UserSitePermission.is_active == True
        )
    )
    
    if not regional_permission.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Regional administrator access required"
        )
    
    return current_user

# ===== UTILITY FUNCTIONS =====

async def check_user_site_access(
    user_id: UUID,
    site_id: UUID,
    db: AsyncSession,
    min_level: PermissionLevel = PermissionLevel.READ
) -> bool:
    """
    Controlla se un utente ha accesso ad un sito con livello minimo
    """
    # Carica utente
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    
    if not user or not user.is_active:
        return False
    
    # Superuser ha sempre accesso
    if user.is_superuser:
        return True
    
    # Controlla permessi
    permission_result = await db.execute(
        select(UserSitePermission).where(
            UserSitePermission.user_id == user_id,
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        )
    )
    permission = permission_result.scalar_one_or_none()
    
    if not permission:
        return False
    
    # Verifica livello
    levels = [PermissionLevel.READ, PermissionLevel.WRITE, PermissionLevel.ADMIN, PermissionLevel.REGIONAL_ADMIN]
    return levels.index(permission.permission_level) >= levels.index(min_level)

def create_login_response_data(user: User, sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Crea dati di risposta per login con informazioni archeologiche
    """
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "is_verified": user.is_verified
        },
        "sites": sites,
        "sites_count": len(sites),
        "has_multiple_sites": len(sites) > 1,
        "user_type": "superuser" if user.is_superuser else "user"
    }

# ===== LOGGING E AUDIT =====

async def log_user_activity(
    user_id: UUID,
    activity_type: str,
    description: str,
    site_id: Optional[UUID] = None,
    request: Optional[Request] = None,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Log attività utente per audit (se hai il modello UserActivity)
    """
    try:
        # Se hai UserActivity, decommentare:
        # from app.models.users import UserActivity
        # 
        # activity = UserActivity(
        #     user_id=user_id,
        #     activity_type=activity_type,
        #     activity_desc=description,
        #     site_id=site_id,
        #     ip_address=request.client.host if request else None,
        #     user_agent=request.headers.get("user-agent") if request else None
        # )
        # db.add(activity)
        # await db.commit()
        
        # Per ora solo log
        logger.info(f"User {user_id}: {activity_type} - {description}")
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

# ===== BACKWARD COMPATIBILITY =====

# Alias per compatibilità con codice esistente
current_active_user = get_current_active_user

# Per admin routes
async def require_superuser(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_id),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites),
    db: AsyncSession = Depends(get_async_session)
) -> tuple[User, dict]:
    """
    Dependency per admin routes che restituisce (user, context)
    """
    user_result = await db.execute(select(User).where(User.id == current_user_id))
    user = user_result.scalar_one_or_none()
    
    if not user or not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required"
        )
    
    # Crea context per template
    context = {
        "request": request,
        "sites": user_sites,
        "sites_count": len(user_sites),
        "user_email": user.email,
        "user_type": "superuser",
        "current_site_name": user_sites[0]["name"] if user_sites else None,
        "current_page": request.url.path.split("/")[-1] or "admin"
    }
    
    return user, context
