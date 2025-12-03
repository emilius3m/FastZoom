#!/usr/bin/env python3
"""
Test script for enhanced bulk-create endpoint validation.

This script tests various validation scenarios to ensure that enhanced
validation properly handles problematic requests that were causing 422 errors.
"""

import asyncio
import json
import requests
import time
from typing import Dict, Any, List
from uuid import uuid4

# Test configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Login credentials (using the format from CLAUDE.md)
LOGIN_URL = f"{BASE_URL}/api/v1/auth/login/json"
LOGIN_CREDENTIALS = {
    "username": "user@user.com",
    "password": "user@user.com"
}

def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers for API requests."""
    try:
        response = requests.post(LOGIN_URL, json=LOGIN_CREDENTIALS)
        response.raise_for_status()
        tokens = response.json()
        access_token = tokens["access_token"]
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return {}

def log_test_result(test_name: str, success: bool, details: str = ""):
    """Log test result with formatting."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"    {details}")
    print()

async def test_empty_units_request(site_id: str, headers: Dict[str, str]) -> bool:
    """Test request with empty units list."""
    print("🧪 Testing: Empty units list request")
    
    request_data = {
        "units": [],
        "relationships": []
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        # Should return 422 with validation error
        if response.status_code == 422:
            error_data = response.json()
            print(f"   Expected 422 error received: {error_data.get('detail', {}).get('error', 'Unknown error')}")
            return True
        else:
            print(f"   ❌ Expected 422, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_duplicate_temp_ids(site_id: str, headers: Dict[str, str]) -> bool:
    """Test request with duplicate temporary IDs."""
    print("🧪 Testing: Duplicate temporary IDs")
    
    request_data = {
        "units": [
            {
                "temp_id": "duplicate_unit",
                "unit_type": "us",
                "code": "US001",
                "definition": "First unit",
                "tipo": "positiva"
            },
            {
                "temp_id": "duplicate_unit",  # Duplicate!
                "unit_type": "usm",
                "code": "USM001",
                "definition": "Second unit",
                "tecnica_costruttiva": "Muratura"
            }
        ],
        "relationships": []
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        if response.status_code == 422:
            error_data = response.json()
            validation_errors = error_data.get('detail', {}).get('validation_errors', [])
            print(f"   Expected 422 with duplicate ID errors: {validation_errors}")
            return True
        else:
            print(f"   ❌ Expected 422, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_invalid_unit_codes(site_id: str, headers: Dict[str, str]) -> bool:
    """Test request with invalid unit codes."""
    print("🧪 Testing: Invalid unit codes")
    
    request_data = {
        "units": [
            {
                "temp_id": "invalid_code_unit",
                "unit_type": "us",
                "code": "us001",  # Should be US001 (uppercase)
                "definition": "Unit with invalid code format",
                "tipo": "positiva"
            },
            {
                "temp_id": "short_code_unit",
                "unit_type": "us",
                "code": "U",  # Too short
                "definition": "Unit with too short code"
            }
        ],
        "relationships": []
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        if response.status_code == 422:
            error_data = response.json()
            print(f"   Expected 422 with code validation errors")
            # Check for field-specific errors
            field_errors = error_data.get('detail', {}).get('field_errors', {})
            if field_errors:
                print(f"   Field errors: {field_errors}")
            return True
        else:
            print(f"   ❌ Expected 422, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_invalid_relationships(site_id: str, headers: Dict[str, str]) -> bool:
    """Test request with invalid relationships."""
    print("🧪 Testing: Invalid relationships")
    
    request_data = {
        "units": [
            {
                "temp_id": "unit1",
                "unit_type": "us",
                "code": "US001",
                "definition": "First unit",
                "tipo": "positiva"
            },
            {
                "temp_id": "unit2",
                "unit_type": "us",
                "code": "US002",
                "definition": "Second unit",
                "tipo": "positiva"
            }
        ],
        "relationships": [
            {
                "temp_id": "invalid_rel1",
                "from_temp_id": "unit1",
                "to_temp_id": "nonexistent_unit",  # Invalid reference
                "relation_type": "copre"
            },
            {
                "temp_id": "invalid_rel2",
                "from_temp_id": "unit2",
                "to_temp_id": "unit2",  # Self-reference
                "relation_type": "taglia"
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        if response.status_code == 422:
            error_data = response.json()
            print(f"   Expected 422 with relationship validation errors")
            field_errors = error_data.get('detail', {}).get('field_errors', {})
            if field_errors:
                print(f"   Relationship field errors: {field_errors}")
            return True
        else:
            print(f"   ❌ Expected 422, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_business_rule_violations(site_id: str, headers: Dict[str, str]) -> bool:
    """Test request with business rule violations."""
    print("🧪 Testing: Business rule violations")
    
    request_data = {
        "units": [
            {
                "temp_id": "positive_cutting_unit",
                "unit_type": "us",
                "code": "US003",
                "definition": "Positive unit that tries to cut",
                "tipo": "positiva"  # Positive but using cutting relationship
            },
            {
                "temp_id": "negative_covering_unit",
                "unit_type": "us",
                "code": "US004",
                "definition": "Negative unit that tries to cover",
                "tipo": "negativa"  # Negative but using covering relationship
            }
        ],
        "relationships": [
            {
                "temp_id": "business_violation1",
                "from_temp_id": "positive_cutting_unit",
                "to_temp_id": "negative_covering_unit",
                "relation_type": "taglia"  # Only negative US should cut
            },
            {
                "temp_id": "business_violation2",
                "from_temp_id": "negative_covering_unit",
                "to_temp_id": "positive_cutting_unit",
                "relation_type": "copre"  # Only positive US should cover
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        if response.status_code == 422:
            error_data = response.json()
            print(f"   Expected 422 with business rule violations")
            business_errors = [e for e in error_data.get('detail', {}).get('validation_errors', []) 
                              if 'Business rule' in e or 'Only' in e]
            if business_errors:
                print(f"   Business rule errors: {business_errors}")
            return True
        else:
            print(f"   ❌ Expected 422, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_usm_with_tipo_field(site_id: str, headers: Dict[str, str]) -> bool:
    """Test USM unit with tipo field (should be invalid)."""
    print("🧪 Testing: USM unit with tipo field")
    
    request_data = {
        "units": [
            {
                "temp_id": "usm_with_tipo",
                "unit_type": "usm",
                "code": "USM001",
                "definition": "USM unit with invalid tipo field",
                "tipo": "positiva"  # USM units should not have tipo
            }
        ],
        "relationships": []
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        if response.status_code == 422:
            error_data = response.json()
            print(f"   Expected 422 with USM tipo field error")
            field_errors = error_data.get('detail', {}).get('field_errors', {})
            if 'tipo' in str(field_errors):
                print(f"   Correctly identified USM tipo field issue")
            return True
        else:
            print(f"   ❌ Expected 422, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_valid_request(site_id: str, headers: Dict[str, str]) -> bool:
    """Test a valid request to ensure it still works."""
    print("🧪 Testing: Valid request")
    
    request_data = {
        "units": [
            {
                "temp_id": "valid_us_unit",
                "unit_type": "us",
                "code": "US005",
                "definition": "Valid US unit for testing",
                "tipo": "positiva",
                "localita": "Test Area"
            },
            {
                "temp_id": "valid_usm_unit",
                "unit_type": "usm",
                "code": "USM002",
                "definition": "Valid USM unit for testing",
                "tecnica_costruttiva": "Muratura a sacco"
            }
        ],
        "relationships": [
            {
                "temp_id": "valid_relationship",
                "from_temp_id": "valid_us_unit",
                "to_temp_id": "valid_usm_unit",
                "relation_type": "si_appoggia_a"
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers
        )
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"   ✅ Valid request succeeded")
            print(f"   Created {response_data.get('created_units', 0)} units and {response_data.get('created_relationships', 0)} relationships")
            if 'warnings' in response_data:
                print(f"   Warnings: {response_data['warnings']}")
            return True
        else:
            print(f"   ❌ Expected 200, got {response.status_code}")
            if response.text:
                print(f"   Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def test_large_request(site_id: str, headers: Dict[str, str]) -> bool:
    """Test request with many units to check performance warnings."""
    print("🧪 Testing: Large request (performance warning)")
    
    # Create 50 units (above warning threshold)
    units = []
    for i in range(50):
        units.append({
            "temp_id": f"perf_test_unit_{i}",
            "unit_type": "us" if i % 2 == 0 else "usm",
            "definition": f"Performance test unit {i}",
            "tipo": "positiva" if i % 2 == 0 else None
        })
    
    request_data = {
        "units": units,
        "relationships": []
    }
    
    try:
        start_time = time.time()
        response = requests.post(
            f"{API_BASE}/harris-matrix/sites/{site_id}/bulk-create",
            json=request_data,
            headers=headers,
            timeout=30  # 30 second timeout
        )
        end_time = time.time()
        
        processing_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"   ✅ Large request succeeded in {processing_time:.0f}ms")
            if 'processing_time_ms' in response_data:
                print(f"   Server reported processing time: {response_data['processing_time_ms']:.0f}ms")
            if response_data.get('warnings'):
                print(f"   Performance warnings: {response_data['warnings']}")
            return True
        elif response.status_code == 422:
            error_data = response.json()
            warnings = error_data.get('detail', {}).get('validation_warnings', [])
            if warnings:
                print(f"   ✅ Got performance warnings: {warnings}")
                return True
            else:
                print(f"   ❌ Expected performance warnings, got other validation errors")
                return False
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"   ❌ Request timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"   ❌ Test failed with exception: {e}")
        return False

async def main():
    """Run all validation tests."""
    print("🚀 Starting Enhanced Bulk-Create Validation Tests")
    print("=" * 60)
    
    # Get authentication
    headers = get_auth_headers()
    if not headers:
        print("❌ Cannot proceed without authentication")
        return
    
    # Test with a sample site ID (you may need to update this)
    site_id = "e8b88e11-74e3-46d3-8e86-81f926c01cab"  # Example UUID
    
    # Run tests
    tests = [
        ("Empty Units Request", test_empty_units_request),
        ("Duplicate Temporary IDs", test_duplicate_temp_ids),
        ("Invalid Unit Codes", test_invalid_unit_codes),
        ("Invalid Relationships", test_invalid_relationships),
        ("Business Rule Violations", test_business_rule_violations),
        ("USM with Tipo Field", test_usm_with_tipo_field),
        ("Valid Request", test_valid_request),
        ("Large Request Performance", test_large_request),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}")
        try:
            success = await test_func(site_id, headers)
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test_name} crashed: {e}")
            failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {(passed / (passed + failed)) * 100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Enhanced validation is working correctly.")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review the validation implementation.")

if __name__ == "__main__":
    asyncio.run(main())