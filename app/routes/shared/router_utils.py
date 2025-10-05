# app/routes/shared/router_utils.py - Shared utilities for router consolidation
"""
Shared utilities for router consolidation.
Extracts common patterns used across multiple routers.
"""

from fastapi import HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List, Tuple
from uuid import UUID
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.users import User
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission


def handle_permission_denied(action: str = "eseguire questa operazione") -> HTTPException:
    """Create standardized permission denied error response.

    Args:
        action: Description of the action that was denied

    Returns:
        HTTPException with 403 status code and localized message
    """
    return HTTPException(
        status_code=403,
        detail=f"Permessi insufficienti per {action}"
    )


def handle_resource_not_found(resource: str = "Risorsa") -> HTTPException:
    """Create standardized resource not found error response.

    Args:
        resource: Name of the resource that was not found

    Returns:
        HTTPException with 404 status code and localized message
    """
    return HTTPException(
        status_code=404,
        detail=f"{resource} non trovato"
    )


def create_user_context(
    current_user: User,
    user_sites: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create standardized user context for templates.

    Args:
        current_user: The authenticated user object
        user_sites: List of accessible sites for the user

    Returns:
        Dictionary containing user context information for templates
    """
    return {
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": None,  # Will be set by caller if needed
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user"
    }


async def get_current_user_with_context(
    current_user_id: UUID,
    db: AsyncSession
) -> User:
    """Retrieve current user with centralized error handling.

    Args:
        current_user_id: UUID of the current user
        db: Database session

    Returns:
        User object with error handling for not found cases

    Raises:
        HTTPException: If user is not found
    """
    try:
        user_query = select(User).where(User.id == current_user_id)
        user = await db.execute(user_query)
        current_user = user.scalar_one_or_none()

        if not current_user:
            raise HTTPException(status_code=404, detail="Utente non trovato")

        return current_user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving current user {current_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Errore nel recupero utente")


def get_base_context(
    request: Request,
    site: ArchaeologicalSite,
    permission: UserSitePermission,
    current_user: User,
    user_sites: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create comprehensive base context for site endpoints.

    This function centralizes all common context data needed across
    all site-related endpoints, reducing code duplication and ensuring
    consistency.

    Args:
        request: FastAPI request object
        site: Archaeological site object
        permission: User's site permissions
        current_user: Authenticated user object
        user_sites: List of user's accessible sites

    Returns:
        Dictionary containing all base context data for templates
    """
    return {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "sites": user_sites,
        "sites_count": len(user_sites),
        "current_site_name": site.name if site else None,
        "user_email": current_user.email if current_user else None,
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }


async def get_site_access(
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
) -> Tuple[ArchaeologicalSite, UserSitePermission]:
    """Validate user access to site and return site with permissions.

    This dependency function performs comprehensive access validation:
    1. Verifies site exists
    2. Checks user permissions for the site
    3. Validates permission is active and not expired

    Args:
        site_id: UUID of the site to access
        current_user_id: UUID of the current user
        db: Database session

    Returns:
        Tuple of (ArchaeologicalSite, UserSitePermission)

    Raises:
        HTTPException: If site not found (404) or access denied (403)
    """
    from sqlalchemy import select, and_, or_, func

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == current_user_id,
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True,
            or_(
                UserSitePermission.expires_at.is_(None),
                UserSitePermission.expires_at > func.now()
            )
        )
    )

    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )

    return site, permission


class RouterUtils:
    """Utility class for common router operations."""

    @staticmethod
    def create_json_response(data: Any, message: str = None) -> dict:
        """Create standardized JSON response."""
        response = {"data": data}
        if message:
            response["message"] = message
        return response

    @staticmethod
    def create_error_response(error: str, status_code: int = 500) -> dict:
        """Create standardized error response."""
        return {
            "error": error,
            "status_code": status_code
        }

    @staticmethod
    def validate_uuid(uuid_string: str, field_name: str = "ID") -> UUID:
        """Validate and convert string to UUID."""
        try:
            return UUID(uuid_string)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} non valido: {uuid_string}"
            )