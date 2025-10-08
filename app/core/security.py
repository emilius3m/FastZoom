from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import get_settings
from app.database.db import get_async_session
from app.services.site_service import SiteService
from app.models.user_sites import PermissionLevel
from app.models.users import User

settings = get_settings()

# Configurazione sicurezza
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Costanti JWT
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = settings.jwt_expires_hours

class SecurityService:
    """Servizio per autenticazione e sicurezza multi-sito"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica password con hash bcrypt"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Genera hash bcrypt per password"""
        return pwd_context.hash(password)
    
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
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

        # Genera JTI (JWT ID) univoco per questo token
        import uuid
        token_jti = str(uuid.uuid4())

        # Payload JWT multi-sito con JTI
        payload = {
            "sub": str(user_id),  # Subject = User ID
            "exp": expire,        # Expiration
            "iat": datetime.utcnow(),  # Issued at
            "jti": token_jti,     # JWT ID per blacklist
            "sites": sites_data,  # Lista siti accessibili
            "multi_site_enabled": True,
            "app_context": "archaeological_catalog"
        }

        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    @staticmethod
    async def verify_token(token: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """
        Verifica e decodifica token JWT con controllo blacklist

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

            # Controlla se il token è nella blacklist (se DB disponibile)
            if db and token_jti:
                from app.models.users import TokenBlacklist
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
        
        # Verifica permesso (gerarchia: REGIONAL_ADMIN > ADMIN > WRITE > READ)
        permission_hierarchy = {
            "read": 1,
            "write": 2,
            "admin": 3,
            "regional_admin": 4
        }
        
        user_level = permission_hierarchy.get(
            site_info.get("permission_level", "").lower(), 0
        )
        required_level = permission_hierarchy.get(required_permission.value.lower(), 0)
        
        return user_level >= required_level

    @staticmethod
    async def blacklist_token(token: str, db: AsyncSession, user_id: UUID, reason: Optional[str] = None) -> bool:
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
            # Decodifica il token per ottenere il JTI (senza verifica firma per velocità)
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_signature": False, "verify_exp": False})
            token_jti = payload.get("jti")

            if not token_jti:
                return False

            # Aggiungi alla blacklist
            from app.models.users import TokenBlacklist
            await TokenBlacklist.blacklist_token(db, token_jti, user_id, reason)

            return True

        except jwt.PyJWTError:
            return False
        except Exception:
            return False

# DEPENDENCY CORRETTE: Leggono dal cookie invece che dall'header
async def get_current_user_token(request: Request) -> Dict[str, Any]:
    """
    Dependency: ottiene e verifica token utente corrente DAL COOKIE
    """
    # Leggi token dal cookie
    access_token_cookie = request.cookies.get("access_token")

    if not access_token_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di accesso non trovato nei cookie",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rimuovi "Bearer " prefix se presente
    token = access_token_cookie.replace("Bearer ", "")

    # Verifica token usando SecurityService (senza DB per compatibilità)
    return await SecurityService.verify_token(token, None)

# NUOVE DEPENDENCY CON BLACKLIST CHECK - PER ENDPOINT PROTETTI
async def get_current_user_token_with_blacklist(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Dependency: ottiene e verifica token utente corrente DAL COOKIE con controllo blacklist
    """
    # Leggi token dal cookie
    access_token_cookie = request.cookies.get("access_token")

    if not access_token_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di accesso non trovato nei cookie",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rimuovi "Bearer " prefix se presente
    token = access_token_cookie.replace("Bearer ", "")

    # Verifica token usando SecurityService CON controllo blacklist
    return await SecurityService.verify_token(token, db)

async def get_current_user_id(request: Request) -> UUID:
    """
    Dependency: ottiene ID utente corrente dal token nel cookie
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
    Dependency: ottiene siti accessibili dal token nel cookie
    """
    token_payload = await get_current_user_token(request)
    return SecurityService.get_sites_from_token(token_payload)

# NUOVE DEPENDENCY CON BLACKLIST CHECK
async def get_current_user_id_with_blacklist(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
) -> UUID:
    """
    Dependency: ottiene ID utente corrente dal token nel cookie con controllo blacklist
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
    Dependency: ottiene siti accessibili dal token nel cookie con controllo blacklist
    """
    token_payload = await get_current_user_token_with_blacklist(request, db)
    return SecurityService.get_sites_from_token(token_payload)

async def current_active_user(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """
    Dependency: ottiene l'utente corrente attivo dal database
    """
    user = await db.get(User, user_id)
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

# Versioni alternative per compatibilità OAuth2 (header-based)
async def get_current_user_token_header(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Dependency: ottiene token dall'Authorization header (per API)"""
    return SecurityService.verify_token(token)

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

# CORREZIONE: Funzione async corretta
def require_site_access(
    site_id: UUID, 
    required_permission: PermissionLevel = PermissionLevel.READ
):
    """
    Dependency factory: verifica accesso a sito specifico
    Usa cookie-based authentication
    
    Usage:
        @app.get("/site/{site_id}/photos")
        async def get_photos(
            authorized: bool = Depends(require_site_access(site_id, PermissionLevel.READ))
        ):
    """
    async def _verify_access(request: Request) -> bool:  # AGGIUNTO async qui
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

# Utility per debug
def get_token_from_cookie_or_header(request: Request) -> Optional[str]:
    """Utility per ottenere token da cookie o header (fallback)"""
    # Prima prova dal cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token.replace("Bearer ", "")
    
    # Poi prova dall'header Authorization
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    
    return None

# Debug utilities
async def debug_current_token(request: Request) -> Dict[str, Any]:
    """Utility di debug per vedere il token corrente"""
    try:
        cookie_token = request.cookies.get("access_token")
        if not cookie_token:
            return {"error": "No access_token cookie found", "cookies": list(request.cookies.keys())}
        
        token = cookie_token.replace("Bearer ", "")
        payload = SecurityService.verify_token(token)
        
        return {
            "success": True,
            "user_id": payload.get("sub"),
            "sites_count": len(payload.get("sites", [])),
            "expires": payload.get("exp"),
            "issued_at": payload.get("iat")
        }
    except Exception as e:
        return {"error": str(e), "success": False}
