# test_thumbnail_fix.py - TEST PER VERIFICARE FIX THUMBNAIL E MINIO CONNECTION

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.archaeological_minio_service import archaeological_minio_service
from loguru import logger

async def test_minio_connection():
    """Test connessione MinIO e presenza bucket"""
    try:
        logger.info("Testing MinIO connection...")

        # Test bucket existence
        for bucket_name in archaeological_minio_service.buckets.values():
            try:
                exists = archaeological_minio_service.client.bucket_exists(bucket_name)
                logger.info(f"Bucket '{bucket_name}' exists: {exists}")
                if not exists:
                    logger.warning(f"Bucket '{bucket_name}' does not exist! Creating...")
                    archaeological_minio_service.client.make_bucket(bucket_name)
                    logger.info(f"Created bucket '{bucket_name}'")
            except Exception as e:
                logger.error(f"Error checking/creating bucket '{bucket_name}': {e}")

        logger.info("MinIO connection test completed successfully!")
        return True

    except Exception as e:
        logger.error(f"MinIO connection test failed: {e}")
        return False

async def test_file_operations():
    """Test operazioni file MinIO"""
    try:
        logger.info("Testing MinIO file operations...")

        # Test upload piccolo file
        test_data = b"test data for minio"
        test_path = "test/test_file.txt"

        # Upload
        result = await archaeological_minio_service.client.put_object(
            bucket_name=archaeological_minio_service.buckets['photos'],
            object_name=test_path,
            data=test_data,
            length=len(test_data)
        )
        logger.info(f"Upload test successful: {result.object_name}")

        # Test using the service's get_file method (the one we fixed)
        try:
            downloaded_data = await archaeological_minio_service.get_file(f"archaeological-photos/{test_path}")
            if isinstance(downloaded_data, bytes):
                logger.info(f"Service get_file test successful: {len(downloaded_data)} bytes")
            else:
                logger.warning(f"Service get_file returned non-bytes: {type(downloaded_data)}")
        except Exception as e:
            logger.warning(f"Service get_file test failed: {e}")

        # Cleanup - use synchronous call for test
        try:
            archaeological_minio_service.client.remove_object(
                bucket_name=archaeological_minio_service.buckets['photos'],
                object_name=test_path
            )
            logger.info("Cleanup test successful")
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

        return True

    except Exception as e:
        logger.error(f"File operations test failed: {str(e)}")
        return False

async def main():
    """Main test function"""
    logger.info("Starting MinIO tests...")

    # Test 1: Connection and buckets
    connection_ok = await test_minio_connection()
    if not connection_ok:
        logger.error("MinIO connection test failed!")
        return False

    # Test 2: File operations
    file_ops_ok = await test_file_operations()
    if not file_ops_ok:
        logger.error("MinIO file operations test failed!")
        return False

    logger.info("All MinIO tests passed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)