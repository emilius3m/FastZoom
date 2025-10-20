#!/usr/bin/env python3
"""
Test script to verify OAuth2 login fix
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from app.database.session import get_async_session
from app.models import User, UserSitePermission, PermissionLevel
from app.services.auth_service import AuthService


async def test_permission_level_access():
    """Test that permission_level can be accessed without .value"""
    print("Testing permission_level access fix...")
    
    try:
        # Get a database session
        async for db in get_async_session():
            # Find a user with permissions
            result = await db.execute(
                select(User).where(User.email == "user@user.com")
            )
            user = result.scalar_one_or_none()
            
            if not user:
                print("User not found, creating test user...")
                # Create a test user if needed
                from app.core.security import SecurityService
                hashed_password = SecurityService.get_password_hash("test123")
                
                user = User(
                    email="user@user.com",
                    username="testuser",
                    hashed_password=hashed_password,
                    first_name="Test",
                    last_name="User",
                    is_active=True,
                    is_superuser=False
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            # Test the get_user_sites_with_permissions method
            try:
                sites_data = await AuthService.get_user_sites_with_permissions(db, user.id)
                print(f"✅ Success: get_user_sites_with_permissions returned {len(sites_data)} sites")
                
                for site in sites_data:
                    print(f"  - Site: {site['name']}, Permission: {site['permission_level']}")
                    # Verify permission_level is a string, not an enum
                    assert isinstance(site['permission_level'], str), "permission_level should be a string"
                
            except AttributeError as e:
                if "'str' object has no attribute 'value'" in str(e):
                    print(f"❌ Failed: The original error still exists: {e}")
                    return False
                else:
                    raise
            
            print("✅ OAuth2 login fix verified successfully!")
            return True
            
    except Exception as e:
        print(f"FAILED: Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Starting OAuth2 login fix verification...")
    success = asyncio.run(test_permission_level_access())
    sys.exit(0 if success else 1)