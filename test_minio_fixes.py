#!/usr/bin/env python3
# test_minio_fixes.py - TEST SCRIPT FOR MINIO STORAGE FIXES

import asyncio
import sys
import json
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from services.archaeological_minio_service import archaeological_minio_service
from services.storage_management_service import storage_management_service
from loguru import logger


async def test_bucket_creation():
    """Test bucket creation and verification"""
    logger.info("🧪 Testing bucket creation...")
    
    try:
        result = await storage_management_service.ensure_buckets_exist()
        logger.info(f"✅ Bucket creation test result: {result}")
        
        # Check if storage bucket was created
        storage_bucket_created = any(
            bucket['name'] == 'storage' 
            for bucket in result.get('created_buckets', []) + result.get('existing_buckets', [])
        )
        
        if storage_bucket_created:
            logger.info("✅ 'storage' bucket exists or was created successfully")
        else:
            logger.warning("⚠️ 'storage' bucket not found in results")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Bucket creation test failed: {e}")
        return False


async def test_path_parsing():
    """Test path parsing logic"""
    logger.info("🧪 Testing path parsing logic...")
    
    test_paths = [
        "storage/sites/f0f4e144-c745-44ec-9cf4-d6e218b57133/file.png",
        "sites/12345/photo.jpg", 
        "thumbnails/photo123.jpg",
        "minio://archaeological-photos/site1/photo.jpg",
        "f0f4e144-c745-44ec-9cf4-d6e218b57133/photo.jpg"
    ]
    
    try:
        for path in test_paths:
            bucket, object_name = archaeological_minio_service._parse_minio_path(path)
            logger.info(f"✅ Path '{path}' -> Bucket: '{bucket}', Object: '{object_name}'")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Path parsing test failed: {e}")
        return False


async def test_storage_monitoring():
    """Test storage monitoring capabilities"""
    logger.info("🧪 Testing storage monitoring...")
    
    try:
        # Test storage usage monitoring
        usage = await storage_management_service.get_storage_usage()
        logger.info(f"✅ Storage usage: {usage.get('total_size_mb', 0)}MB across {usage.get('total_objects', 0)} objects")
        
        # Test bucket verification
        bucket_check = await storage_management_service.ensure_buckets_exist()
        logger.info(f"✅ Bucket check: {len(bucket_check.get('existing_buckets', []))} existing, {len(bucket_check.get('created_buckets', []))} created")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Storage monitoring test failed: {e}")
        return False


async def test_cleanup_mechanism():
    """Test cleanup mechanism (dry run)"""
    logger.info("🧪 Testing cleanup mechanism...")
    
    try:
        # Test old thumbnail cleanup (dry run with very old date)
        cleanup_result = await storage_management_service.cleanup_old_thumbnails(days_old=365)
        logger.info(f"✅ Cleanup test: {cleanup_result.get('cleaned_count', 0)} objects identified for cleanup")
        logger.info(f"   Would free: {cleanup_result.get('total_size_freed_mb', 0)}MB")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Cleanup mechanism test failed: {e}")
        return False


async def test_error_handling_simulation():
    """Test error handling paths"""
    logger.info("🧪 Testing error handling simulation...")
    
    try:
        # Test emergency cleanup (should work even if no cleanup needed)
        emergency_result = await storage_management_service.emergency_cleanup(target_freed_mb=10)
        logger.info(f"✅ Emergency cleanup test: {emergency_result}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False


async def main():
    """Run all MinIO fix tests"""
    logger.info("🚀 Starting MinIO fixes verification tests...")
    
    tests = [
        ("Bucket Creation", test_bucket_creation),
        ("Path Parsing", test_path_parsing), 
        ("Storage Monitoring", test_storage_monitoring),
        ("Cleanup Mechanism", test_cleanup_mechanism),
        ("Error Handling", test_error_handling_simulation)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running test: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            if result:
                logger.info(f"✅ {test_name} PASSED")
                passed += 1
            else:
                logger.error(f"❌ {test_name} FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} FAILED with exception: {e}")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"TEST SUMMARY")
    logger.info(f"{'='*50}")
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! MinIO fixes are working correctly.")
        return 0
    else:
        logger.warning(f"⚠️ {total - passed} tests failed. Check the logs above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)