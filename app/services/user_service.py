"""
User Service - Business Logic for User Management

This service handles user registration, profile management, and user-related operations.
"""

from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models import User
from app.models.user_profiles import UserProfile
from app.core.security import SecurityService
from app.core.domain_exceptions import (
    ResourceAlreadyExistsError,
    ValidationError,
    ResourceNotFoundError,
    InsufficientPermissionsError,
)


class UserService:
    """Service for user management operations."""
    
    @staticmethod
    async def register_user(
        db: AsyncSession,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        **kwargs
    ) -> User:
        """
        Register a new user.
        
        Args:
            db: Database session
            email: User email
            password: Plain text password
            first_name: User first name (optional)
            last_name: User last name (optional)
            **kwargs: Additional user fields
            
        Returns:
            Created user
            
        Raises:
            ValidationError: If email or password is invalid
            ResourceAlreadyExistsError: If user already exists
        """
        with logger.contextualize(
            operation="register_user",
            email=email,
            has_password=bool(password)
        ):
            try:
                # Validate input
                if not email or not email.strip():
                    raise ValidationError(
                        "Email is required",
                        field="email"
                    )
                
                if not password or len(password) < 8:
                    raise ValidationError(
                        "Password must be at least 8 characters",
                        field="password"
                    )
                
                # Check if user already exists
                existing_user = await db.execute(
                    select(User).where(User.email == email)
                )
                if existing_user.scalar_one_or_none():
                    raise ResourceAlreadyExistsError(
                        "User",
                        email,
                        details={"email": email}
                    )
                
                # Hash password
                hashed_password = SecurityService.get_password_hash(password)
                
                # Generate default values
                if not first_name:
                    first_name = email.split("@")[0].capitalize()
                if not last_name:
                    last_name = "User"
                
                # Create user
                user = User(
                    id=str(uuid4()),
                    email=email,
                    username=email.split("@")[0],
                    hashed_password=hashed_password,
                    is_active=True,
                    is_superuser=False,
                    is_verified=False,
                    **kwargs
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                
                # Create user profile
                profile = UserProfile(
                    user_id=user.id,
                    first_name=first_name,
                    last_name=last_name
                )
                db.add(profile)
                await db.commit()
                
                logger.success(
                    "User registered successfully",
                    extra={
                        "user_id": str(user.id),
                        "email": user.email,
                        "has_profile": True
                    }
                )
                
                return user
                
            except (ValidationError, ResourceAlreadyExistsError):
                # Re-raise domain exceptions
                raise
            except Exception as e:
                logger.error(
                    "Error registering user",
                    extra={
                        "email": email,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
    
    @staticmethod
    async def update_user_profile(
        db: AsyncSession,
        user_id: UUID,
        current_user_id: UUID,
        is_superuser: bool,
        profile_data: Dict[str, Any]
    ) -> UserProfile:
        """
        Update user profile.
        
        Args:
            db: Database session
            user_id: Target user ID
            current_user_id: Current user ID (for permission check)
            is_superuser: Whether current user is superuser
            profile_data: Profile data to update
            
        Returns:
            Updated user profile
            
        Raises:
            InsufficientPermissionsError: If user lacks permission
            ResourceNotFoundError: If user not found
        """
        with logger.contextualize(
            operation="update_user_profile",
            user_id=str(user_id),
            current_user_id=str(current_user_id)
        ):
            try:
                # Check permissions: allow self-update or superuser
                if user_id != current_user_id and not is_superuser:
                    raise InsufficientPermissionsError(
                        "Not authorized to update this user profile",
                        details={
                            "user_id": str(user_id),
                            "current_user_id": str(current_user_id)
                        }
                    )
                
                # Get user profile
                result = await db.execute(
                    select(UserProfile).where(UserProfile.user_id == str(user_id))
                )
                profile = result.scalar_one_or_none()
                
                if not profile:
                    # Create new profile if doesn't exist
                    profile = UserProfile(
                        user_id=str(user_id),
                        **profile_data
                    )
                    db.add(profile)
                else:
                    # Update existing profile
                    for key, value in profile_data.items():
                        if hasattr(profile, key):
                            setattr(profile, key, value)
                
                await db.commit()
                await db.refresh(profile)
                
                logger.info(
                    "User profile updated",
                    extra={
                        "user_id": str(user_id),
                        "profile_id": str(profile.id),
                        "updated_by": str(current_user_id)
                    }
                )
                
                return profile
                
            except (InsufficientPermissionsError, ResourceNotFoundError):
                # Re-raise domain exceptions
                raise
            except Exception as e:
                logger.error(
                    "Error updating user profile",
                    extra={
                        "user_id": str(user_id),
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
    
    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: UUID
    ) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            User if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.id == str(user_id))
        )
        return result.scalar_one_or_none()