#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify that the user creation fixes work correctly
"""

import asyncio
import sys
import os

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.db import async_session_maker
from app.models import User
from app.core.security import SecurityService
from sqlalchemy import select, func
from uuid import uuid4


async def test_user_creation():
    """Test user creation with all required fields"""

    print("Testing user creation with required fields...")

    db = None
    try:
        async with async_session_maker() as db:
            # Test data
            test_email = f"testuser_{uuid4().hex[:8]}@example.com"
            test_password = "TestPass123!"[:72]  # Truncate to 72 bytes for bcrypt
            
            print(f"Creating test user: {test_email}")
            
            # Hash password
            hashed_password = SecurityService.get_password_hash(test_password)
            
            # Create user with all required fields
            user = User(
                email=test_email,
                username=test_email.split("@")[0],  # Generate username from email
                hashed_password=hashed_password,
                first_name="Test",
                last_name="User",
                is_active=True,
                is_superuser=False,
                is_verified=False
            )
            
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            print(f"User created successfully!")
            print(f"   ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Username: {user.username}")
            print(f"   First Name: {user.first_name}")
            print(f"   Last Name: {user.last_name}")
            
            # Verify user can be retrieved
            retrieved_user = await db.execute(
                select(User).where(User.email == test_email)
            )
            retrieved_user = retrieved_user.scalar_one_or_none()
            
            if retrieved_user:
                print("User verified in database")
                print(f"   Retrieved username: {retrieved_user.username}")
                return True
            else:
                print("User not found after creation")
                return False
                
    except Exception as e:
        print(f"Error creating user: {e}")
        if db:
            await db.rollback()
        return False


async def test_superuser_creation():
    """Test superuser creation with all required fields"""

    print("\nTesting superuser creation with required fields...")

    db = None
    try:
        async with async_session_maker() as db:
            # Test data
            test_email = f"testsuper_{uuid4().hex[:8]}@example.com"
            test_password = "SuperPass123!"[:72]  # Truncate to 72 bytes for bcrypt
            
            print(f"Creating test superuser: {test_email}")
            
            # Hash password
            hashed_password = SecurityService.get_password_hash(test_password)
            
            # Create superuser with all required fields
            user = User(
                email=test_email,
                username="admin",  # Fixed username
                hashed_password=hashed_password,
                first_name="Admin",
                last_name="User",
                is_active=True,
                is_superuser=True,
                is_verified=True
            )
            
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            print(f"Superuser created successfully!")
            print(f"   ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Username: {user.username}")
            print(f"   Is Superuser: {user.is_superuser}")
            
            # Verify superuser can be retrieved
            retrieved_user = await db.execute(
                select(User).where(User.email == test_email)
            )
            retrieved_user = retrieved_user.scalar_one_or_none()
            
            if retrieved_user:
                print("Superuser verified in database")
                return True
            else:
                print("Superuser not found after creation")
                return False
                
    except Exception as e:
        print(f"Error creating superuser: {e}")
        if db:
            await db.rollback()
        return False


async def main():
    """Run all tests"""
    print("Starting user creation tests...")
    print("="*50)
    
    test1_result = await test_user_creation()
    test2_result = await test_superuser_creation()
    
    print("\n" + "="*50)
    if test1_result and test2_result:
        print("All tests passed! User creation is working correctly.")
        sys.exit(0)
    else:
        print("Some tests failed! There are still issues with user creation.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())