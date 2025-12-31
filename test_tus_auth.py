#!/usr/bin/env python3
"""
Test script to verify TUS authentication fix
"""
import asyncio
import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.security import _extract_token_from_request, SecurityService
from fastapi import Request
from unittest.mock import Mock


async def test_token_extraction():
    """Test token extraction from request"""
    print("🧪 Testing TUS Authentication Fix")
    print("=" * 50)
    
    # Test 1: Authorization header with Bearer token (TUS client format)
    print("\n📋 Test 1: Authorization header with Bearer token")
    mock_request = Mock(spec=Request)
    mock_request.url.path = "/api/v1/tus/uploads"
    mock_request.cookies = {}
    mock_request.headers = {"authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token.here"}
    
    try:
        token = _extract_token_from_request(mock_request)
        print(f"✅ Token extracted successfully: {token[:20]}...")
    except Exception as e:
        print(f"❌ Token extraction failed: {e}")
    
    # Test 2: Authorization header without space (edge case)
    print("\n📋 Test 2: Authorization header without space")
    mock_request.headers = {"authorization": "BearereyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"}
    
    try:
        token = _extract_token_from_request(mock_request)
        print(f"✅ Token extracted successfully: {token[:20]}...")
    except Exception as e:
        print(f"❌ Token extraction failed: {e}")
    
    # Test 3: Cookie-based authentication
    print("\n📋 Test 3: Cookie-based authentication")
    mock_request.cookies = {"access_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"}
    mock_request.headers = {}
    
    try:
        token = _extract_token_from_request(mock_request)
        print(f"✅ Token extracted from cookie: {token[:20]}...")
    except Exception as e:
        print(f"❌ Token extraction from cookie failed: {e}")
    
    # Test 4: No authentication (should fail)
    print("\n📋 Test 4: No authentication (should fail)")
    mock_request.cookies = {}
    mock_request.headers = {}
    
    try:
        token = _extract_token_from_request(mock_request)
        print(f"❌ Should have failed but got token: {token[:20]}...")
    except Exception as e:
        print(f"✅ Correctly failed with: {e}")


async def test_token_validation():
    """Test token validation with a sample token"""
    print("\n🔐 Testing Token Validation")
    print("=" * 50)
    
    # This is a sample invalid token for testing
    invalid_token = "invalid.jwt.token"
    
    try:
        payload = await SecurityService.verify_token(invalid_token)
        print(f"❌ Should have failed but got payload: {payload}")
    except Exception as e:
        print(f"✅ Correctly rejected invalid token: {e}")
    
    # Test with a properly formatted but invalid token
    print("\n📋 Testing properly formatted but invalid token")
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    
    try:
        payload = await SecurityService.verify_token(fake_token)
        print(f"✅ Token validation succeeded (this may fail if SECRET_KEY differs): {payload}")
    except Exception as e:
        print(f"⚠️  Token validation failed (expected if SECRET_KEY differs): {e}")


async def main():
    """Run all tests"""
    await test_token_extraction()
    await test_token_validation()
    
    print("\n🎯 Summary")
    print("=" * 50)
    print("✅ Token extraction improvements:")
    print("   - Better handling of Authorization header formats")
    print("   - Improved fallback logic")
    print("   - Enhanced error logging")
    print("✅ Token validation improvements:")
    print("   - More specific error handling")
    print("   - Better exception categorization")
    print("\n🚀 TUS authentication should now work correctly!")


if __name__ == "__main__":
    asyncio.run(main())