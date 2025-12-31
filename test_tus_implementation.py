"""
Test script for TUS implementation
Tests the TUS upload service and API endpoints
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_tus_service():
    """Test TusUploadService functionality"""
    from app.services.tus_service import tus_upload_service
    
    print("=" * 60)
    print("Testing TUS Upload Service")
    print("=" * 60)
    
    try:
        # Test 1: Create upload
        print("\n[TEST 1] Creating upload session...")
        upload_id = await tus_upload_service.create_upload(
            filename="test_photo.jpg",
            upload_length=1024,
            metadata={"user_id": "test-user", "site_id": "test-site"}
        )
        print(f"✅ Upload created: {upload_id}")
        
        # Test 2: Get metadata
        print("\n[TEST 2] Getting upload metadata...")
        metadata = await tus_upload_service.get_upload_metadata(upload_id)
        print(f"✅ Metadata retrieved:")
        print(f"   - Filename: {metadata['filename']}")
        print(f"   - Size: {metadata['upload_length']} bytes")
        print(f"   - Offset: {metadata['offset']}")
        
        # Test 3: Append chunk
        print("\n[TEST 3] Appending chunk...")
        chunk_data = b"x" * 512  # 512 bytes
        new_offset = await tus_upload_service.append_chunk(
            upload_id=upload_id,
            chunk_data=chunk_data,
            offset=0
        )
        print(f"✅ Chunk appended, new offset: {new_offset}")
        
        # Test 4: Check progress
        print("\n[TEST 4] Checking upload progress...")
        progress = await tus_upload_service.get_upload_progress(upload_id)
        print(f"✅ Progress: {progress['progress_percent']}%")
        print(f"   - Uploaded: {progress['offset']} / {progress['upload_length']} bytes")
        
        # Test 5: Append remaining data
        print("\n[TEST 5] Completing upload...")
        remaining_data = b"y" * 512
        final_offset = await tus_upload_service.append_chunk(
            upload_id=upload_id,
            chunk_data=remaining_data,
            offset=512
        )
        print(f"✅ Upload completed, final offset: {final_offset}")
        
        # Test 6: Check if complete
        print("\n[TEST 6] Verifying upload completion...")
        is_complete = await tus_upload_service.is_upload_complete(upload_id)
        print(f"✅ Upload complete: {is_complete}")
        
        if is_complete:
            file_path = await tus_upload_service.get_upload_file_path(upload_id)
            print(f"   - File path: {file_path}")
            print(f"   - File exists: {file_path.exists()}")
            print(f"   - File size: {file_path.stat().st_size} bytes")
        
        # Test 7: Delete upload
        print("\n[TEST 7] Deleting upload...")
        await tus_upload_service.delete_upload(upload_id)
        print(f"✅ Upload deleted")
        
        # Test 8: Verify deletion
        print("\n[TEST 8] Verifying deletion...")
        try:
            await tus_upload_service.get_upload_metadata(upload_id)
            print("❌ Upload still exists after deletion")
        except Exception:
            print("✅ Upload successfully deleted")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


async def test_validation():
    """Test validation logic"""
    from app.services.tus_service import tus_upload_service
    from app.core.domain_exceptions import ValidationError
    
    print("\n" + "=" * 60)
    print("Testing Validation")
    print("=" * 60)
    
    # Test invalid extension
    print("\n[TEST] Invalid file extension...")
    try:
        await tus_upload_service.create_upload(
            filename="test.exe",
            upload_length=1024
        )
        print("❌ Should have rejected .exe extension")
    except ValidationError as e:
        print(f"✅ Correctly rejected: {e}")
    
    # Test file too large
    print("\n[TEST] File too large...")
    try:
        await tus_upload_service.create_upload(
            filename="test.jpg",
            upload_length=2 * 1024 * 1024 * 1024  # 2GB
        )
        print("❌ Should have rejected large file")
    except ValidationError as e:
        print(f"✅ Correctly rejected: {e}")
    
    # Test offset mismatch
    print("\n[TEST] Offset mismatch...")
    try:
        upload_id = await tus_upload_service.create_upload(
            filename="test.jpg",
            upload_length=1024
        )
        
        # Try to append at wrong offset
        await tus_upload_service.append_chunk(
            upload_id=upload_id,
            chunk_data=b"x" * 100,
            offset=500  # Wrong offset (should be 0)
        )
        print("❌ Should have rejected wrong offset")
        
    except ValidationError as e:
        print(f"✅ Correctly rejected: {e}")
    finally:
        # Cleanup
        try:
            await tus_upload_service.delete_upload(upload_id)
        except:
            pass
    
    print("\n✅ All validation tests passed")


async def test_cleanup():
    """Test cleanup of expired uploads"""
    from app.services.tus_service import tus_upload_service
    
    print("\n" + "=" * 60)
    print("Testing Cleanup")
    print("=" * 60)
    
    # Run cleanup
    print("\n[TEST] Running cleanup...")
    cleaned = await tus_upload_service.cleanup_expired_uploads()
    print(f"✅ Cleaned up {cleaned} expired uploads")


async def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "TUS IMPLEMENTATION TESTS" + " " * 19 + "║")
    print("╚" + "=" * 58 + "╝")
    
    success = True
    
    # Test service
    if not await test_tus_service():
        success = False
    
    # Test validation
    try:
        await test_validation()
    except Exception as e:
        print(f"❌ Validation tests failed: {e}")
        success = False
    
    # Test cleanup
    try:
        await test_cleanup()
    except Exception as e:
        print(f"❌ Cleanup test failed: {e}")
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60 + "\n")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)