"""
Tests for UserService.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.user_service import UserService
from app.models import User
from app.core.domain_exceptions import ResourceAlreadyExistsError, ValidationError


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_user(test_db: AsyncSession):
    """Test user registration."""
    # Arrange
    user_service = UserService()
    
    # Act
    user = await user_service.register_user(
        db=test_db,
        email="newuser@example.com",
        password="securepass123",
        first_name="New",
        last_name="User"
    )
    
    # Assert
    assert user is not None
    assert user.email == "newuser@example.com"
    assert user.full_name == "New User"
    assert user.is_active is True
    assert user.hashed_password is not None
    assert user.hashed_password != "securepass123"  # Should be hashed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_user_duplicate_email(test_db: AsyncSession, mock_user: User):
    """Test registration with duplicate email raises error."""
    # Arrange
    user_service = UserService()
    
    # Act & Assert
    with pytest.raises(ResourceAlreadyExistsError):
        await user_service.register_user(
            db=test_db,
            email=mock_user.email,  # Same email as existing user
            password="password123",
            first_name="Duplicate",
            last_name="User"
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_user_profile(test_db: AsyncSession, mock_user: User):
    """Test user profile update."""
    # Arrange
    user_service = UserService()
    profile_data = {
        "first_name": "Updated",
        "last_name": "Name",
        "phone": "+1234567890",
        "city": "Test City"
    }
    
    # Act
    updated_profile = await user_service.update_user_profile(
        db=test_db,
        user_id=mock_user.id,
        current_user_id=mock_user.id,  # User updating their own profile
        is_superuser=False,
        profile_data=profile_data
    )
    
    # Assert
    assert updated_profile is not None
    assert updated_profile.first_name == "Updated"
    assert updated_profile.last_name == "Name"
    assert updated_profile.phone == "+1234567890"
    assert updated_profile.city == "Test City"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_by_id(test_db: AsyncSession, mock_user: User):
    """Test retrieving user by ID."""
    # Arrange
    user_service = UserService()
    
    # Act
    user = await user_service.get_user_by_id(db=test_db, user_id=mock_user.id)
    
    # Assert
    assert user is not None
    assert user.id == mock_user.id
    assert user.email == mock_user.email
