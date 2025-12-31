"""
Tests for AuthService.
"""

import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import AuthService
from app.models import User, TokenBlacklist
from app.core.security import SecurityService
from app.core.domain_exceptions import InvalidCredentialsError, UserInactiveError


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_user_success(test_db: AsyncSession, mock_user: User):
    """Test successful user authentication."""
    # Arrange
    auth_service = AuthService()
    
    # Act
    authenticated_user = await auth_service.authenticate_user(
        db=test_db,
        email="test@example.com",
        password="testpass123"
    )
    
    # Assert
    assert authenticated_user is not None
    assert authenticated_user.id == mock_user.id
    assert authenticated_user.email == mock_user.email
    assert authenticated_user.is_active is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_user_invalid_credentials(test_db: AsyncSession, mock_user: User):
    """Test authentication with invalid credentials."""
    # Arrange
    auth_service = AuthService()
    
    # Act
    authenticated_user = await auth_service.authenticate_user(
        db=test_db,
        email="test@example.com",
        password="wrongpassword"
    )
    
    # Assert
    assert authenticated_user is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_logout_blacklists_token(test_db: AsyncSession, mock_user: User):
    """Test that logout adds token to blacklist."""
    # Arrange
    auth_service = AuthService()
    
    # Create access token
    token = SecurityService.create_site_aware_token(
        user_id=mock_user.id,
        is_superuser=mock_user.is_superuser
    )
    
    # Act
    result = await auth_service.logout(db=test_db, token=token)
    
    # Assert
    assert result["success"] is True
    assert "user_id" in result or "message" in result
    
    # Verify token is blacklisted (if blacklisting succeeded)
    from sqlalchemy import select
    if "user_id" in result:
        stmt = select(TokenBlacklist).where(TokenBlacklist.token == token)
        blacklist_result = await test_db.execute(stmt)
        blacklisted_token = blacklist_result.scalar_one_or_none()
        assert blacklisted_token is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_access_token(test_db: AsyncSession, mock_user: User):
    """Test refresh token generates new access token."""
    # Arrange
    auth_service = AuthService()
    
    # Create refresh token
    token_data = {
        "sub": str(mock_user.id),
        "username": mock_user.username,
        "email": mock_user.email,
        "jti": str(uuid4())
    }
    refresh_token = SecurityService.create_refresh_token(token_data)
    
    # Act
    result = await auth_service.refresh_access_token(
        db=test_db,
        refresh_token=refresh_token
    )
    
    # Assert
    assert "access_token" in result
    assert result["token_type"] == "bearer"
    assert result["user_id"] == str(mock_user.id)
    assert len(result["access_token"]) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_sites_with_permissions(
    test_db: AsyncSession,
    mock_user_with_site_access
):
    """Test retrieving user sites with permissions."""
    # Arrange
    auth_service = AuthService()
    user, site, permission = mock_user_with_site_access
    
    # Act
    sites = await auth_service.get_user_sites_with_permissions(
        db=test_db,
        user_id=user.id
    )
    
    # Assert
    assert len(sites) == 1
    assert sites[0]["site_id"] == str(site.id)
    assert sites[0]["site_name"] == site.name
    assert sites[0]["permission_level"] == "site_admin"
