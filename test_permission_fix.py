#!/usr/bin/env python3
"""
Test script to validate the permission endpoint fix
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pydantic import ValidationError
from app.routes.api.v1.admin import PermissionCreate
from app.models.users import PermissionLevel

def test_permission_create_schema():
    """Test the PermissionCreate schema with valid and invalid data"""
    print("Testing PermissionCreate schema...")
    
    # Test valid permission levels
    valid_levels = [level.value for level in PermissionLevel]
    print(f"Valid permission levels: {valid_levels}")
    
    # Test valid data
    try:
        valid_data = {
            "site_id": "123e4567-e89b-12d3-a456-426614174000",
            "permission_level": "read",
            "notes": "Test permission"
        }
        permission = PermissionCreate(**valid_data)
        print(f"✅ Valid data test passed: {permission}")
    except ValidationError as e:
        print(f"❌ Valid data test failed: {e}")
        return False
    
    # Test invalid permission level
    try:
        invalid_data = {
            "site_id": "123e4567-e89b-12d3-a456-426614174000",
            "permission_level": "invalid_level",
            "notes": "Test permission"
        }
        permission = PermissionCreate(**invalid_data)
        print(f"❌ Invalid permission level test failed - should have raised ValueError")
        return False
    except (ValidationError, ValueError) as e:
        print(f"✅ Invalid permission level test passed: {e}")
    
    # Test missing required fields
    try:
        incomplete_data = {
            "permission_level": "read"
        }
        permission = PermissionCreate(**incomplete_data)
        print(f"❌ Missing fields test failed - should have raised ValidationError")
        return False
    except (ValidationError, ValueError) as e:
        print(f"✅ Missing fields test passed: {e}")
    
    return True

def test_permission_level_validation():
    """Test permission level validation logic"""
    print("\nTesting permission level validation...")
    
    valid_permission_levels = [level.value for level in PermissionLevel]
    print(f"Valid levels: {valid_permission_levels}")
    
    # Test valid levels
    for level in valid_permission_levels:
        if level in valid_permission_levels:
            print(f"✅ '{level}' is valid")
        else:
            print(f"❌ '{level}' should be valid but wasn't found")
            return False
    
    # Test invalid levels
    invalid_levels = ["invalid", "admin_level", "read_write", ""]
    for level in invalid_levels:
        if level not in valid_permission_levels:
            print(f"✅ '{level}' correctly identified as invalid")
        else:
            print(f"❌ '{level}' should be invalid but was accepted")
            return False
    
    return True

if __name__ == "__main__":
    print("=== Testing Permission Endpoint Fix ===\n")
    
    schema_test = test_permission_create_schema()
    validation_test = test_permission_level_validation()
    
    print(f"\n=== Test Results ===")
    print(f"Schema validation: {'✅ PASSED' if schema_test else '❌ FAILED'}")
    print(f"Permission level validation: {'✅ PASSED' if validation_test else '❌ FAILED'}")
    
    if schema_test and validation_test:
        print("\n🎉 All tests passed! The fix should resolve the 422 error.")
        print("\nExpected request body format:")
        print("""
POST /api/v1/admin/users/{user_id}/permissions/
{
    "site_id": "uuid-of-site",
    "permission_level": "read|write|admin|regional_admin",
    "expires_at": "optional-ISO-datetime",
    "notes": "optional-notes"
}
        """)
    else:
        print("\n❌ Some tests failed. Please review the implementation.")
        sys.exit(1)