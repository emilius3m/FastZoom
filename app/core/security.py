from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import uuid
import traceback

import jwt
import bcrypt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.core.config import get_settings
from app.database.db import get_async_session
from app.services.site_service import SiteService
from app.models import PermissionLevel, User

settings = get_settings()

# Configurazione sicurezza
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Costanti JWT
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_HOURS = settings.jwt_expires_hours
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
BCRYPT_MAX_PASSWORD_LENGTH = 72

# Gerarchia permessi (costante globale)
PERMISSION_HIERARCHY = {
    "read": 1,
    "write": 2,
    "admin": 3,
    "regional_admin": 4
}


class SecurityService:
    """Servizio per autenticazione e sicurezza multi-sito"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica password con hash bcrypt"""
        try:
            # Tronca la password a 72 byte come richiesto da bcrypt
            if len(plain_password.encode('utf-8')) > BCRYPT_MAX_PASSWORD_LENGTH:
                plain_password = plain_password[:BCRYPT_MAX_PASSWORD_LENGTH]
                logger.debug("Password truncated to 72 bytes for bcrypt compatibility")

            return pwd_context.verify(plain_password, hashed_password)

        except Exception as e:
            logger.error(f"Password verification failed: {type(e).__name__} - {str(e)}")
            raise

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Genera hash bcrypt per password"""
        return pwd_context.hash(password)

    @staticmethod
    def _generate_jti() -> str:
        """Genera JWT ID univoco"""
        return str(uuid.uuid4())

    @staticmethod
    def _get_current_utc() -> datetime:
        """Ottiene timestamp UTC corrente"""
        return datetime.utcnow()

    @staticmethod
    def create_site_aware_token(
        user_id: UUID,
        sites_data: List[Dict[str, Any]],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Crea JWT con informazioni sui siti accessibili e JTI per blacklist

        Args:
            user_id: ID utente
            sites_data: Lista siti con permessi [{id, name, permission_level}]
            expires_delta: Durata custom del token

        Returns:
            Token JWT multi-sito
        """
        now = SecurityService._get_current_utc()
        
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

        payload = {
            "sub": str(user_id),
            "exp": expire,
            "iat": now,
            "jti": SecurityService._generate_jti(),
            "sites": sites_data,
            "multi_site_enabled": True,
            "app_context": "archaeological_catalog"
        }

        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    async def verify_token(token: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """
        Verifica e decodifica token JWT con controllo blacklist opzionale

        Args:
            token: Token JWT da verificare
            db: Sessione database per controllo blacklist (opzionale)

        Returns:
            Payload decodificato

        Raises:
            HTTPException: Se token non valido o nella blacklist
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub")
            token_jti: str = payload.get("jti")

            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token non valido: missing subject",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Controlla blacklist solo se DB disponibile e JTI presente
            if db and token_jti:
                from app.models import TokenBlacklist
                if await TokenBlacklist.is_token_blacklisted(db, token_jti):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token invalidato",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            return payload

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token scaduto",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token non valido",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    def get_sites_from_token(token_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Estrae informazioni siti dal payload JWT"""
        return token_payload.get("sites", [])

    @staticmethod
    def verify_site_access_in_token(
        token_payload: Dict[str, Any],
        site_id: UUID,
        required_permission: PermissionLevel = PermissionLevel.READ
    ) -> bool:
        """
        Verifica accesso a sito specifico dal token

        Args:
            token_payload: Payload JWT decodificato
            site_id: ID sito da verificare
            required_permission: Permesso minimo richiesto

        Returns:
            True se autorizzato
        """
        sites = SecurityService.get_sites_from_token(token_payload)
        
        # Cerca sito nel token
        site_info = next(
            (site for site in sites if site.get("id") == str(site_id)),
            None
        )

        if not site_info:
            return False

        # Verifica permesso usando gerarchia globale
        user_level = PERMISSION_HIERARCHY.get(
            site_info.get("permission_level", "").lower(), 0
        )
        required_level = PERMISSION_HIERARCHY.get(required_permission.value.lower(), 0)
        
        return user_level >= required_level

    @staticmethod
    async def blacklist_token(
        token: str, 
        db: AsyncSession, 
        user_id: UUID, 
        reason: Optional[str] = None
    ) -> bool:
        """
        Invalida un token aggiungendolo alla blacklist

        Args:
            token: Token JWT da invalidare
            db: Sessione database
            user_id: ID utente che invalida il token
            reason: Motivo dell'invalidazione (opzionale)

        Returns:
            True se il token è stato invalidato con successo
        """
        try:
            # Decodifica senza verifica per velocità
            payload = jwt.decode(
                token, 
                SECRET_KEY, 
                algorithms=[ALGORITHM], 
                options={"verify_signature": False, "verify_exp": False}
            )
            token_jti = payload.get("jti")
            
            if not token_jti:
                return False

            from app.models import TokenBlacklist
            await TokenBlacklist.blacklist_token(db, token_jti, user_id, reason)
            return True

        except (jwt.PyJWTError, Exception):
            return False

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Crea un access token JWT

        Args:
            data: Dati da includere nel payload
            expires_delta: Durata custom del token

        Returns:
            Token JWT access
        """
        now = SecurityService._get_current_utc()
        
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = data.copy()
        to_encode.update({
            "exp": expire,
            "iat": now,
            "jti": SecurityService._generate_jti(),
            "type": "access"
        })
        
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Crea un refresh token JWT

        Args:
            data: Dati da includere nel payload
            expires_delta: Durata custom del token

        Returns:
            Token JWT refresh
        """
        now = SecurityService._get_current_utc()
        
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode = data.copy()
        to_encode.update({
            "exp": expire,
            "iat": now,
            "jti": SecurityService._generate_jti(),
            "type": "refresh"
        })
        
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        """
        Decodifica un token JWT senza controllo blacklist

        Args:
            token: Token JWT da decodificare

        Returns:
            Payload decodificato

        Raises:
            jwt.PyJWTError: Se token non valido
        """
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# Utility per estrarre token da richiesta
def _extract_token_from_request(request: Request) -> str:
    """
    Estrae token da cookie o header Authorization con fallback

    Args:
        request: FastAPI Request object

    Returns:
        Token pulito (senza 'Bearer ')

    Raises:
        HTTPException: Se token non trovato
    """
    # 1. Prova dal cookie access_token
    token = request.cookies.get("access_token")
    
    # 2. Fallback: prova dall'header Authorization
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header
    
    if not token:
        logger.warning(
            f"No access token found - Path: {request.url.path}, "
            f"Cookies: {list(request.cookies.keys())}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di accesso non trovato",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Rimuovi prefisso "Bearer " se presente
    return token.replace("Bearer ", "")


# DEPENDENCY: Token e User Info (senza blacklist check)
async def get_current_user_token(request: Request) -> Dict[str, Any]:
    """
    Dependency: ottiene e verifica token utente corrente dal cookie/header
    """
    token = _extract_token_from_request(request)
    return await SecurityService.verify_token(token, db=None)


async def get_current_user_id(request: Request) -> UUID:
    """
    Dependency: ottiene ID utente corrente dal token
    """
    token_payload = await get_current_user_token(request)
    user_id = token_payload.get("sub")
    
    try:
        return UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ID utente non valido nel token"
        )


async def get_current_user_sites(request: Request) -> List[Dict[str, Any]]:
    """
    Dependency: ottiene siti accessibili dal token
    """
    token_payload = await get_current_user_token(request)
    return SecurityService.get_sites_from_token(token_payload)


# DEPENDENCY: Con blacklist check (per endpoint protetti)
async def get_current_user_token_with_blacklist(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Dependency: ottiene e verifica token con controllo blacklist
    """
    token = _extract_token_from_request(request)
    
    try:
        payload = await SecurityService.verify_token(token, db)
        logger.debug(f"Token verified successfully for user: {payload.get('sub')}")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {type(e).__name__} - {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        raise


async def get_current_user_id_with_blacklist(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
) -> UUID:
    """
    Dependency: ottiene ID utente corrente con controllo blacklist
    """
    token_payload = await get_current_user_token_with_blacklist(request, db)
    user_id = token_payload.get("sub")
    
    try:
        return UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ID utente non valido nel token"
        )


async def get_current_user_sites_with_blacklist(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
) -> List[Dict[str, Any]]:
    """
    Dependency: ottiene siti accessibili dal DATABASE in tempo reale
    NON usa il token JWT per evitare dati cached
    """
    token_payload = await get_current_user_token_with_blacklist(request, db)
    user_id_str = token_payload.get("sub")
    
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ID utente non valido nel token"
        )

    # Interroga il database per siti in tempo reale
    from app.services.auth_service import AuthService
    
    try:
        sites_data = await AuthService.get_user_sites_with_permissions(db, user_id)
    except Exception as e:
        logger.error(f"Error in get_user_sites_with_permissions: {str(e)}")
        sites_data = []  # Fallback sicuro
    
    return sites_data


async def current_active_user(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """
    Dependency: ottiene l'utente corrente attivo dal database
    """
    result = await db.execute(select(User).where(User.id == str(user_id)))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user


# DEPENDENCY: Header-based (per compatibilità OAuth2 API)
async def get_current_user_token_header(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Dependency: ottiene token dall'Authorization header (per API)"""
    return await SecurityService.verify_token(token, db=None)


async def get_current_user_id_header(
    token_payload: Dict[str, Any] = Depends(get_current_user_token_header)
) -> UUID:
    """Dependency: ottiene ID utente dal token nell'header"""
    user_id = token_payload.get("sub")
    
    try:
        return UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ID utente non valido nel token"
        )


async def get_current_user_sites_header(
    token_payload: Dict[str, Any] = Depends(get_current_user_token_header)
) -> List[Dict[str, Any]]:
    """Dependency: ottiene siti dal token nell'header"""
    return SecurityService.get_sites_from_token(token_payload)


# Dependency factory per accesso a sito specifico
def require_site_access(
    site_id: UUID,
    required_permission: PermissionLevel = PermissionLevel.READ
):
    """
    Dependency factory: verifica accesso a sito specifico
    
    Usage:
        @app.get("/site/{site_id}/photos")
        async def get_photos(
            authorized: bool = Depends(require_site_access(site_id, PermissionLevel.READ))
        ):
            ...
    """
    async def _verify_access(request: Request) -> bool:
        token_payload = await get_current_user_token(request)
        
        if not SecurityService.verify_site_access_in_token(
            token_payload, site_id, required_permission
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accesso negato al sito {site_id}: permesso {required_permission.value} richiesto"
            )
        
        return True
    
    return _verify_access


# Debug utility
async def debug_current_token(request: Request) -> Dict[str, Any]:
    """Utility di debug per vedere il token corrente"""
    try:
        token = _extract_token_from_request(request)
        payload = await SecurityService.verify_token(token, db=None)
        
        return {
            "success": True,
            "user_id": payload.get("sub"),
            "sites_count": len(payload.get("sites", [])),
            "expires": payload.get("exp"),
            "issued_at": payload.get("iat")
        }
    except Exception as e:
        return {"error": str(e), "success": False}
