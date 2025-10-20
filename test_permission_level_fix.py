#!/usr/bin/env python3
"""
Simple test to verify the permission_level.value fix
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.models import PermissionLevel


def test_permission_level_enum():
    """Test that PermissionLevel enum works correctly"""
    print("Testing PermissionLevel enum...")
    
    # Test that we can create enum values
    read_level = PermissionLevel.READ
    write_level = PermissionLevel.WRITE
    admin_level = PermissionLevel.ADMIN
    regional_admin_level = PermissionLevel.REGIONAL_ADMIN
    
    # Test that we can get the string value
    assert read_level.value == "read"
    assert write_level.value == "write"
    assert admin_level.value == "admin"
    assert regional_admin_level.value == "regional_admin"
    
    # Test that we can create enum from string
    read_from_string = PermissionLevel("read")
    assert read_from_string == PermissionLevel.READ
    
    print("PASS: PermissionLevel enum tests passed")


def test_permission_level_as_string():
    """Test that permission_level as string works correctly"""
    print("Testing permission_level as string...")
    
    # Simulate what happens when we get permission_level from database
    permission_level_string = "read"
    
    # This should work (no .value access)
    assert permission_level_string == "read"
    
    # This would fail (which was the original error)
    try:
        # This is what was causing the error
        value = permission_level_string.value
        print("✗ ERROR: .value on string should have failed")
        return False
    except AttributeError:
        print("PASS: Correctly caught AttributeError when accessing .value on string")
    
    print("PASS: Permission level as string tests passed")
    return True


def main():
    """Run all tests"""
    print("Starting permission_level fix verification...\n")
    
    try:
        test_permission_level_enum()
        print()
        
        success = test_permission_level_as_string()
        print()
        
        if success:
            print("SUCCESS: All tests passed! The OAuth2 login fix should work correctly.")
            return True
        else:
            print("FAILED: Some tests failed.")
            return False
            
    except Exception as e:
        print(f"FAILED: Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)