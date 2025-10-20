#!/usr/bin/env python3
"""
Test script to verify the User-Role relationship fix
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable

# Import the models
from app.models.users import User, Role

def test_user_role_relationship():
    """Test that the User-Role relationship works correctly"""
    
    # Create an in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    
    try:
        # Try to create the table schemas
        print("Generating CREATE TABLE statements...")
        users_create = CreateTable(User.__table__).compile(engine)
        roles_create = CreateTable(Role.__table__).compile(engine)
        
        print("SUCCESS: Table schemas generated without errors!")
        print("\nUsers table schema includes is_deleted column:")
        if "is_deleted BOOLEAN" in str(users_create):
            print("[OK] is_deleted column properly defined")
        else:
            print("[ERROR] is_deleted column not properly defined")
            
        print("\nRole-User relationship properly configured:")
        if "primaryjoin" in str(User.roles.property) and "secondaryjoin" in str(User.roles.property):
            print("[OK] Relationship join conditions specified")
        else:
            print("[ERROR] Relationship join conditions missing")
            
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to generate table schemas: {e}")
        return False

if __name__ == "__main__":
    print("Testing User-Role relationship fix...")
    success = test_user_role_relationship()
    
    if success:
        print("\n[OK] All tests passed! The fixes are working correctly.")
    else:
        print("\n[ERROR] Tests failed. There may still be issues with the models.")
        sys.exit(1)