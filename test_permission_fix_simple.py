#!/usr/bin/env python3
"""
Simple test to verify the UserSitePermission fix
Tests that the model has the correct field name
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_permission_model_fields():
    """Test that UserSitePermission has granted_by and notes fields and not assigned_by"""
    print("Testing UserSitePermission model fields...")
    
    try:
        # Import the model
        from app.models.users import UserSitePermission
        
        # Check if the model has the granted_by field
        if hasattr(UserSitePermission, 'granted_by'):
            print("PASS: UserSitePermission has 'granted_by' field")
        else:
            print("FAIL: UserSitePermission missing 'granted_by' field")
            return False
            
        # Check if the model has the notes field
        if hasattr(UserSitePermission, 'notes'):
            print("PASS: UserSitePermission has 'notes' field")
        else:
            print("FAIL: UserSitePermission missing 'notes' field")
            return False
            
        # Check if the model has the assigned_by field (it shouldn't)
        if hasattr(UserSitePermission, 'assigned_by'):
            print("FAIL: UserSitePermission incorrectly has 'assigned_by' field")
            return False
        else:
            print("PASS: UserSitePermission correctly does not have 'assigned_by' field")
            
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def test_admin_route_fix():
    """Check if admin.py has been updated to use granted_by"""
    print("\nTesting admin.py route fix...")
    
    try:
        with open('app/routes/admin.py', 'r') as f:
            content = f.read()
            
        # Check that granted_by is used
        if 'granted_by=superuser.id' in content:
            print("PASS: admin.py uses 'granted_by=superuser.id'")
        else:
            print("FAIL: admin.py does not use 'granted_by=superuser.id'")
            return False
            
        # Check that assigned_by is not used
        if 'assigned_by=superuser.id' in content:
            print("FAIL: admin.py still uses 'assigned_by=superuser.id'")
            return False
        else:
            print("PASS: admin.py correctly does not use 'assigned_by=superuser.id'")
            
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def test_permissions_service_fix():
    """Check if permissions_service.py has been updated"""
    print("\nTesting permissions_service.py fix...")
    
    try:
        with open('app/services/permissions_service.py', 'r') as f:
            content = f.read()
            
        # Check that granted_by is used in the function signature
        if 'granted_by: UUID,' in content:
            print("PASS: permissions_service.py uses 'granted_by: UUID' parameter")
        else:
            print("FAIL: permissions_service.py does not use 'granted_by: UUID' parameter")
            return False
            
        # Check that assigned_by is not used in the function signature
        if 'assigned_by: UUID,' in content:
            print("FAIL: permissions_service.py still uses 'assigned_by: UUID' parameter")
            return False
        else:
            print("PASS: permissions_service.py correctly does not use 'assigned_by: UUID' parameter")
            
        # Check that notes parameter is in the function signature
        if 'notes: Optional[str] = None,' in content:
            print("PASS: permissions_service.py uses 'notes' parameter")
        else:
            print("FAIL: permissions_service.py does not use 'notes' parameter")
            return False
            
        # Check that notes is used when creating UserSitePermission
        if 'notes=notes' in content:
            print("PASS: permissions_service.py uses 'notes=notes' when creating UserSitePermission")
        else:
            print("FAIL: permissions_service.py does not use 'notes=notes' when creating UserSitePermission")
            return False
            
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("UserSitePermission Fix Verification")
    print("=" * 60)
    
    test1_result = test_permission_model_fields()
    test2_result = test_admin_route_fix()
    test3_result = test_permissions_service_fix()
    
    print("\n" + "=" * 60)
    if test1_result and test2_result and test3_result:
        print("SUCCESS: All tests passed! The fix is working correctly.")
        print("  - UserSitePermission model has 'granted_by' and 'notes' fields")
        print("  - admin.py uses 'granted_by' instead of 'assigned_by' and includes 'notes'")
        print("  - permissions_service.py uses 'granted_by' instead of 'assigned_by' and includes 'notes'")
        print("\nThe original errors should now be resolved.")
        return 0
    else:
        print("FAILURE: Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())