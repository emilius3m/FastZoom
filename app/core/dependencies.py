"""
Dependency Injection Providers for FastZoom Application

This module provides dependency injection functions for services,
following FastAPI's dependency injection pattern.

Usage in routes:
    @router.get("/example")
    async def example(
        auth_service: AuthService = Depends(get_auth_service),
        db: AsyncSession = Depends(get_db)
    ):
        ...
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends
from app.database.session import get_db
from app.services.auth_service import AuthService
from app.services.site_service import SiteService
from app.services.photo_service import PhotoMetadataService
from app.services.user_service import UserService


# ============================================================================
# Database Session Provider
# ============================================================================

async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide database session for dependency injection.
    
    Yields:
        AsyncSession: Database session
    """
    async for session in get_db():
        yield session


# ============================================================================
# Service Providers - Stateless Services
# ============================================================================

def get_auth_service() -> AuthService:
    """
    Provide AuthService instance.
    
    AuthService is stateless and uses static methods, so we can
    return the class itself or create a new instance each time.
    
    Returns:
        AuthService instance
    """
    return AuthService


def get_site_service() -> SiteService:
    """
    Provide SiteService instance.
    
    SiteService is stateless and uses static methods.
    
    Returns:
        SiteService instance
    """
    return SiteService


def get_photo_metadata_service() -> PhotoMetadataService:
    """
    Provide PhotoMetadataService instance.
    
    Returns:
        PhotoMetadataService instance
    """
    return PhotoMetadataService()


def get_user_service() -> UserService:
    """
    Provide UserService instance.
    
    UserService is stateless and uses static methods.
    
    Returns:
        UserService instance
    """
    return UserService


# ============================================================================
# Service Providers - Stateful Services (with dependencies)
# ============================================================================

# For services that require initialization with dependencies,
# we'll add providers as needed. Example:

# from app.services.storage_service import StorageService
# 
# def get_storage_service() -> StorageService:
#     """Provide StorageService instance."""
#     from app.core.config import get_settings
#     settings = get_settings()
#     return StorageService(settings)


# ============================================================================
# Combined Dependencies
# ============================================================================

class ServiceContainer:
    """
    Container for commonly used service combinations.
    
    This can be used as a dependency to inject multiple services at once.
    
    Usage:
        @router.get("/example")
        async def example(services: ServiceContainer = Depends(get_services)):
            user = await services.auth_service.authenticate_user(...)
            sites = await services.site_service.get_user_sites(...)
    """
    
    def __init__(
        self,
        auth_service: AuthService,
        site_service: SiteService,
        photo_metadata_service: PhotoMetadataService,
        user_service: UserService,
    ):
        self.auth_service = auth_service
        self.site_service = site_service
        self.photo_metadata_service = photo_metadata_service
        self.user_service = user_service


def get_services(
    auth_service: AuthService = Depends(get_auth_service),
    site_service: SiteService = Depends(get_site_service),
    photo_metadata_service: PhotoMetadataService = Depends(get_photo_metadata_service),
    user_service: UserService = Depends(get_user_service),
) -> ServiceContainer:
    """
    Provide a container with all core services.
    
    This is a convenience function for routes that need multiple services.
    
    Returns:
        ServiceContainer with all services
    """
    return ServiceContainer(
        auth_service=auth_service,
        site_service=site_service,
        photo_metadata_service=photo_metadata_service,
        user_service=user_service,
    )


# ============================================================================
# Utility Dependencies
# ============================================================================

async def get_current_user_id(
    # This would typically extract user_id from JWT token
    # For now, this is a placeholder
    # TODO: Implement actual JWT token extraction
) -> str:
    """
    Extract current user ID from request context.
    
    This should be implemented to extract the user ID from the
    JWT token in the Authorization header.
    
    Returns:
        User ID string
    """
    # Placeholder implementation
    raise NotImplementedError("get_current_user_id needs JWT implementation")


# ============================================================================
# Usage Examples
# ============================================================================

"""
Example 1: Using individual service dependencies

@router.post("/login")
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_database_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.authenticate_user(
        db, 
        credentials.email, 
        credentials.password
    )
    return await auth_service.create_login_response(db, user)


Example 2: Using service container

@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_database_session),
    services: ServiceContainer = Depends(get_services),
    user_id: str = Depends(get_current_user_id)
):
    sites = await services.site_service.get_user_sites(db, user_id)
    return {"sites": sites}


Example 3: Using class-based dependencies (for complex routes)

class UserDashboardDependencies:
    def __init__(
        self,
        db: AsyncSession = Depends(get_database_session),
        auth_service: AuthService = Depends(get_auth_service),
        site_service: SiteService = Depends(get_site_service),
        user_id: str = Depends(get_current_user_id)
    ):
        self.db = db
        self.auth_service = auth_service
        self.site_service = site_service
        self.user_id = user_id

@router.get("/complex-dashboard")
async def complex_dashboard(deps: UserDashboardDependencies = Depends()):
    sites = await deps.site_service.get_user_sites(deps.db, deps.user_id)
    return {"sites": sites}
"""