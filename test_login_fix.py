#!/usr/bin/env python3
"""
Test script to validate login functionality fixes
Tests the specific credentials mentioned in the issue:
{
  "username": "user@user.com",
  "password": "user@user.com"
}
"""

import asyncio
import sys
import os
import requests
import json
from loguru import logger

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logger.remove()
logger.add(sys.stdout, level="DEBUG", format="{time} | {level} | {message}")

async def test_bcrypt_version():
    """Test bcrypt version compatibility"""
    logger.info("=== Testing bcrypt version compatibility ===")
    
    try:
        import bcrypt
        logger.info(f"✓ bcrypt imported successfully")
        
        # Try to get version
        version = getattr(bcrypt, '__version__', 'unknown')
        logger.info(f"✓ bcrypt version: {version}")
        
        # Test basic bcrypt functionality
        test_password = "user@user.com"
        hashed = bcrypt.hashpw(test_password.encode('utf-8'), bcrypt.gensalt())
        logger.info(f"✓ bcrypt hash generated: {hashed[:20]}...")
        
        # Test verification
        result = bcrypt.checkpw(test_password.encode('utf-8'), hashed)
        logger.info(f"✓ bcrypt verification result: {result}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ bcrypt test failed: {str(e)}")
        return False

async def test_passlib_bcrypt():
    """Test passlib bcrypt configuration"""
    logger.info("=== Testing passlib bcrypt configuration ===")
    
    try:
        from passlib.context import CryptContext
        from app.core.security import SecurityService
        
        test_password = "user@user.com"
        logger.info(f"Testing password: '{test_password}' (length: {len(test_password)})")
        
        # Test password hashing
        hashed = SecurityService.get_password_hash(test_password)
        logger.info(f"✓ Password hashed: {hashed[:30]}...")
        
        # Test password verification
        result = SecurityService.verify_password(test_password, hashed)
        logger.info(f"✓ Password verification result: {result}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ passlib test failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def test_auth_service_methods():
    """Test AuthService methods exist and work"""
    logger.info("=== Testing AuthService methods ===")
    
    try:
        from app.services.auth_service import AuthService
        
        # Test if get_user_sites method exists
        if hasattr(AuthService, 'get_user_sites'):
            logger.info("✓ get_user_sites method exists")
        else:
            logger.error("✗ get_user_sites method missing")
            return False
            
        if hasattr(AuthService, 'get_user_sites_with_permissions'):
            logger.info("✓ get_user_sites_with_permissions method exists")
        else:
            logger.error("✗ get_user_sites_with_permissions method missing")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"✗ AuthService test failed: {str(e)}")
        return False

async def test_login_api():
    """Test the login API endpoint"""
    logger.info("=== Testing login API endpoint ===")
    
    base_url = "http://localhost:8000"
    login_url = f"{base_url}/api/v1/auth/login/json"
    
    credentials = {
        "username": "user@user.com",
        "password": "user@user.com"
    }
    
    try:
        logger.info(f"Testing login to: {login_url}")
        logger.info(f"Credentials: {credentials}")
        
        response = requests.post(
            login_url,
            json=credentials,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            logger.info("✓ Login successful")
            data = response.json()
            logger.info(f"Response data keys: {list(data.keys())}")
            return True
        else:
            logger.error(f"✗ Login failed with status {response.status_code}")
            try:
                error_data = response.json()
                logger.error(f"Error details: {error_data}")
            except:
                logger.error(f"Error text: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("✗ Could not connect to server - is it running?")
        return False
    except Exception as e:
        logger.error(f"✗ API test failed: {str(e)}")
        return False

async def main():
    """Run all tests"""
    logger.info("🔍 Starting login functionality diagnosis...")
    
    results = {
        "bcrypt_version": await test_bcrypt_version(),
        "passlib_bcrypt": await test_passlib_bcrypt(),
        "auth_service_methods": await test_auth_service_methods(),
        "login_api": await test_login_api()
    }
    
    logger.info("\n" + "="*50)
    logger.info("📊 TEST RESULTS SUMMARY")
    logger.info("="*50)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{test_name:20}: {status}")
    
    # Provide recommendations
    logger.info("\n🔧 RECOMMENDATIONS")
    logger.info("="*50)
    
    if not results["bcrypt_version"]:
        logger.info("• Consider downgrading bcrypt to version 4.2.0")
        logger.info("• Or update passlib to a compatible version")
    
    if not results["passlib_bcrypt"]:
        logger.info("• Check passlib configuration in SecurityService")
        logger.info("• Review bcrypt-specific parameters")
    
    if not results["auth_service_methods"]:
        logger.info("• Ensure AuthService.get_user_sites() method exists")
    
    if not results["login_api"]:
        logger.info("• Check server is running on localhost:8000")
        logger.info("• Verify database connection")
        logger.info("• Check user exists in database")
    
    # Overall assessment
    all_passed = all(results.values())
    if all_passed:
        logger.info("\n🎉 All tests passed! Login functionality should work correctly.")
    else:
        logger.info("\n⚠️  Some tests failed. Please address the issues above.")

if __name__ == "__main__":
    asyncio.run(main())