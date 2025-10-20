"""
Test script to verify the OAuth2 login fix for update_last_login method
"""
import asyncio
import uuid
from datetime import datetime
from app.database.db import async_session_maker
from app.models import User  # This will import all related models
from app.models.user_profiles import UserProfile  # Explicitly import UserProfile
from app.models.archaeological_plans import ArchaeologicalPlan  # Import this model
from app.models.sites import ArchaeologicalSite  # Import this model
async def test_update_last_login():
    """Test that update_last_login works with db parameter"""
    async with async_session_maker() as db:
        # Create a test user with a simple hashed password
        test_user = User(
            email="test@example.com",
            username="testuser",
            hashed_password="$2b$12$dummy.hashed.password.for.test",  # Dummy hash for testing
            first_name="Test",
            last_name="User",
            is_active=True,
            is_verified=True
        )
        
        # Add user to database
        db.add(test_user)
        await db.commit()
        await db.refresh(test_user)
        
        print(f"Created test user: {test_user.id}")
        print(f"Initial last_login_at: {test_user.last_login_at}")
        print(f"Initial login_count: {test_user.login_count}")
        
        # Test update_last_login with db parameter
        await test_user.update_last_login(db)
        
        print(f"After update_last_login:")
        print(f"  last_login_at: {test_user.last_login_at}")
        print(f"  login_count: {test_user.login_count}")
        
        # Verify the changes were saved
        assert test_user.last_login_at is not None, "last_login_at should be set"
        assert test_user.login_count == 1, "login_count should be 1"
        
        # Test update_last_login without db parameter (should still work)
        old_login_time = test_user.last_login_at
        await asyncio.sleep(0.1)  # Small delay to ensure different timestamp
        await test_user.update_last_login()
        
        print(f"After second update_last_login (without db):")
        print(f"  last_login_at: {test_user.last_login_at}")
        print(f"  login_count: {test_user.login_count}")
        
        # Verify the changes were made locally
        assert test_user.last_login_at > old_login_time, "last_login_at should be updated"
        assert test_user.login_count == 2, "login_count should be 2"
        
        # Clean up - delete test user
        await db.delete(test_user)
        await db.commit()
        
        print("Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_update_last_login())