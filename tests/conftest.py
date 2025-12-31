"""
Test fixtures for FastZoom application.
Provides shared fixtures for database, services, and test data.
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

from app.database.db import Base
from app.models import User, ArchaeologicalSite, UserSitePermission
from app.core.security import SecurityService
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.site_service import SiteService


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    # Use in-memory SQLite for tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=NullPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


# ============================================================================
# Service Fixtures
# ============================================================================

@pytest.fixture
def auth_service() -> AuthService:
    """Create AuthService instance."""
    return AuthService()


@pytest.fixture
def user_service() -> UserService:
    """Create UserService instance."""
    return UserService()


@pytest.fixture
def site_service() -> SiteService:
    """Create SiteService instance."""
    return SiteService()


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
async def mock_user(test_db: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    # Set password
    user.hashed_password = SecurityService.get_password_hash("testpass123")
    
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    
    return user


@pytest.fixture
async def mock_superuser(test_db: AsyncSession) -> User:
    """Create test superuser."""
    user = User(
        id=str(uuid4()),
        email="admin@example.com",
        username="admin",
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
    )
    user.hashed_password = SecurityService.get_password_hash("adminpass123")
    
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    
    return user


@pytest.fixture
async def mock_site(test_db: AsyncSession) -> ArchaeologicalSite:
    """Create test archaeological site."""
    site = ArchaeologicalSite(
        id=str(uuid4()),
        name="Test Archaeological Site",
        location="Test Location",
        description="Test site for unit testing",
        is_active=True,
    )
    
    test_db.add(site)
    await test_db.commit()
    await test_db.refresh(site)
    
    return site


@pytest.fixture
async def mock_user_with_site_access(
    test_db: AsyncSession,
    mock_user: User,
    mock_site: ArchaeologicalSite
) -> tuple[User, ArchaeologicalSite, UserSitePermission]:
    """Create user with site access permission."""
    permission = UserSitePermission(
        id=str(uuid4()),
        user_id=str(mock_user.id),
        site_id=str(mock_site.id),
        permission_level="site_admin",
        is_active=True,
    )
    
    test_db.add(permission)
    await test_db.commit()
    await test_db.refresh(permission)
    
    return mock_user, mock_site, permission


# ============================================================================
# API Client Fixtures
# ============================================================================

@pytest.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    from app.app import app
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def authenticated_client(
    test_client: AsyncClient,
    mock_user: User,
) -> AsyncClient:
    """Create authenticated test client."""
    # Create access token for user
    token = SecurityService.create_site_aware_token(
        user_id=mock_user.id,
        is_superuser=mock_user.is_superuser
    )
    
    # Set authorization header
    test_client.headers["Authorization"] = f"Bearer {token}"
    
    return test_client
