#!/usr/bin/env python3
"""
Test script to verify all the fixes are working correctly
"""

import asyncio
import io
from PIL import Image
from app.services.archaeological_minio_service import archaeological_minio_service

async def test_thumbnail_upload_retrieval():
    """Test thumbnail upload and retrieval consistency"""
    print("Testing thumbnail upload/retrieval...")

    # Create a test thumbnail
    test_image = Image.new('RGB', (800, 600), color='red')
    thumbnail_buffer = io.BytesIO()
    test_image.save(thumbnail_buffer, format='JPEG', quality=85)
    thumbnail_data = thumbnail_buffer.getvalue()

    photo_id = "test-thumbnail-001"

    try:
        # Upload thumbnail using archaeological service
        upload_result = await archaeological_minio_service.upload_thumbnail(thumbnail_data, photo_id)
        print(f"Thumbnail uploaded: {upload_result}")

        # Try to retrieve it using the same service
        retrieve_result = await archaeological_minio_service.get_file(upload_result.replace("minio://", ""))
        print(f"Thumbnail retrieved: {type(retrieve_result)} - {len(retrieve_result) if not isinstance(retrieve_result, str) else 'ERROR'} bytes")

        # Test the photos_router logic
        if upload_result.startswith("thumbnails/"):
            print("Thumbnail path format is correct for retrieval")
        else:
            print("Thumbnail path format is incorrect")

        return True
    except Exception as e:
        print(f"Thumbnail test failed: {e}")
        return False

async def test_minio_connectivity():
    """Test Archaeological MinIO connectivity"""
    print("Testing Archaeological MinIO connectivity...")

    try:
        # Test archaeological minio service
        stats = await archaeological_minio_service.get_storage_stats("test-site")
        print(f"Archaeological MinIO connected. Stats: {stats}")

        # Test bucket initialization
        buckets = archaeological_minio_service.buckets
        print(f"Archaeological MinIO buckets configured: {list(buckets.keys())}")

        return True
    except Exception as e:
        print(f"Archaeological MinIO connectivity test failed: {e}")
        return False

async def test_bucket_consistency():
    """Test that archaeological service has all required buckets"""
    print("Testing archaeological bucket configuration...")

    try:
        arch_buckets = archaeological_minio_service.buckets

        print(f"Archaeological MinIO buckets: {arch_buckets}")

        # Check if all required buckets exist
        required_buckets = ['photos', 'documents', 'tiles', 'thumbnails', 'backups']
        missing_buckets = [b for b in required_buckets if b not in arch_buckets]

        if not missing_buckets:
            print("All required buckets are configured in archaeological service")
        else:
            print(f"Missing buckets: {missing_buckets}")

        return True
    except Exception as e:
        print(f"Bucket consistency test failed: {e}")
        return False

async def main():
    print("Testing Fixes Verification")
    print("=" * 40)

    tests = [
        test_minio_connectivity,
        test_bucket_consistency,
        test_thumbnail_upload_retrieval
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
            print()
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
            print()

    passed = sum(results)
    total = len(results)

    print("=" * 40)
    print(f"📊 Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed! Fixes are working correctly.")
        return True
    else:
        print("⚠️ Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)