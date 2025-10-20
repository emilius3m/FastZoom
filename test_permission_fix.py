#!/usr/bin/env python3
"""
Test script to verify the UserSitePermission fix
Tests that the model can be instantiated with 'granted_by' instead of 'assigned_by'
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from uuid import uuid4
from datetime import datetime
from app.models.users import UserSitePermission, PermissionLevel

def test_permission_creation():
    """Test that UserSitePermission can be created with granted_by parameter"""
    print("Testing UserSitePermission creation...")
    
    # Test data
    user_id = uuid4()
    site_id = uuid4()
    granted_by_id = uuid4()
    
    try:
        # Try to create a UserSitePermission with the correct field name
        permission = UserSitePermission(
            id=uuid4(),
            user_id=user_id,
            site_id=site_id,
            permission_level=PermissionLevel.READ.value,
            granted_by=granted_by_id,
            is_active=True
        )
        
        print(f"✓ Successfully created UserSitePermission with granted_by={granted_by_id}")
        print(f"  - User ID: {user_id}")
        print(f"  - Site ID: {site_id}")
        print(f"  - Permission Level: {permission.permission_level}")
        print(f"  - Granted By: {permission.granted_by}")
        print(f"  - Is Active: {permission.is_active}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error creating UserSitePermission: {str(e)}")
        return False

def test_permission_creation_with_assigned_by():
    """Test that UserSitePermission fails with assigned_by parameter (as expected)"""
    print("\nTesting that assigned_by parameter fails as expected...")
    
    # Test data
    user_id = uuid4()
    site_id = uuid4()
    assigned_by_id = uuid4()
    
    try:
        # Try to create a UserSitePermission with the old field name
        permission = UserSitePermission(
            id=uuid4(),
            user_id=user_id,
            site_id=site_id,
            permission_level=PermissionLevel.READ.value,
            assigned_by=assigned_by_id,  # This should fail
            is_active=True
        )
        
        print(f"✗ Unexpectedly succeeded with assigned_by parameter")
        return False
        
    except TypeError as e:
        if "assigned_by" in str(e):
            print(f"✓ Expected error occurred: {str(e)}")
            return True
        else:
            print(f"✗ Unexpected TypeError: {str(e)}")
            return False
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("UserSitePermission Fix Verification")
    print("=" * 60)
    
    test1_result = test_permission_creation()
    test2_result = test_permission_creation_with_assigned_by()
    
    print("\n" + "=" * 60)
    if test1_result and test2_result:
        print("✓ All tests passed! The fix is working correctly.")
        print("  - UserSitePermission can be created with 'granted_by'")
        print("  - UserSitePermission fails with 'assigned_by' as expected")
        return 0
    else:
        print("✗ Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())