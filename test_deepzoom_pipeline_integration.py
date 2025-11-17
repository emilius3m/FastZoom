#!/usr/bin/env python3
"""
Comprehensive test of the DeepZoom photo processing pipeline
Tests the complete integration from upload to tile generation
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime
from loguru import logger
from typing import Optional, Dict, Any

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class DeepZoomPipelineTester:
    """Comprehensive test suite for DeepZoom pipeline"""
    
    def __init__(self):
        self.test_site_id = None
        self.test_photo_id = None
        self.test_file_content = None
        self.upload_result = None
        self.tile_generation_result = None
        
    async def setup_test_environment(self):
        """Setup test environment with dependencies"""
        try:
            logger.info("🔧 [SETUP] Initializing test environment...")
            
            # Import dependencies
            from app.database.base import async_session_maker
            from app.models import ArchaeologicalSite, User, Photo, UserSitePermission
            from app.services.deep_zoom_background_service import deep_zoom_background_service
            from app.services.archaeological_minio_service import archaeological_minio_service
            from app.core.security import SecurityService
            
            # Store in instance for later use
            self.async_session_maker = async_session_maker
            self.deep_zoom_background_service = deep_zoom_background_service
            self.archaeological_minio_service = archaeological_minio_service
            self.SecurityService = SecurityService
            
            logger.info("✅ [SETUP] Dependencies imported successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SETUP] Failed to initialize test environment: {e}")
            return False
    
    async def create_test_site_and_user(self):
        """Create a test site and user for testing"""
        try:
            logger.info("🏗️ [SETUP] Creating test site and user...")
            
            async with self.async_session_maker() as db:
                from app.models import User, Role
                from sqlalchemy import select
                
                # Create test user
                test_user = await db.execute(
                    select(User).where(User.email == "deepzoom_test@example.com")
                )
                test_user = test_user.scalar_one_or_none()
                
                if not test_user:
                    test_user = User(
                        email="deepzoom_test@example.com",
                        username="deepzoom_test_user",
                        is_active=True,
                        is_superuser=False
                    )
                    db.add(test_user)
                    await db.flush()
                else:
                    logger.info("ℹ️ [SETUP] Using existing test user")
                
                # Create test site
                test_site = await db.execute(
                    select(ArchaeologicalSite).where(ArchaeologicalSite.name == "DeepZoom Test Site")
                )
                test_site = test_site.scalar_one_or_none()
                
                if not test_site:
                    test_site = ArchaeologicalSite(
                        name="DeepZoom Test Site",
                        description="Test site for DeepZoom pipeline",
                        location="Test Location",
                        site_code="DZ-TEST-001"
                    )
                    db.add(test_site)
                    await db.flush()
                else:
                    logger.info("ℹ️ [SETUP] Using existing test site")
                
                # Create user permission
                permission = await db.execute(
                    select(UserSitePermission).where(
                        UserSitePermission.user_id == test_user.id,
                        UserSitePermission.site_id == test_site.id
                    )
                )
                permission = permission.scalar_one_or_none()
                
                if not permission:
                    permission = UserSitePermission(
                        user_id=test_user.id,
                        site_id=test_site.id,
                        permission_level="admin"
                    )
                    db.add(permission)
                
                await db.commit()
                
                self.test_site_id = str(test_site.id)
                self.test_user_id = str(test_user.id)
                
                logger.info(f"✅ [SETUP] Test environment ready - Site: {self.test_site_id}, User: {self.test_user_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ [SETUP] Failed to create test environment: {e}")
            return False
    
    async def create_test_image_content(self):
        """Create test image content for upload"""
        try:
            logger.info("🖼️ [SETUP] Creating test image...")
            
            from PIL import Image
            import io
            
            # Create a test image (4000x3000 to ensure it needs tiles)
            width, height = 4000, 3000
            image = Image.new('RGB', (width, height), color='blue')
            
            # Add some pattern to make it more realistic
            for x in range(0, width, 100):
                for y in range(0, height, 100):
                    image.paste((255, 255, 255), (x, y, x+50, y+50))
            
            # Convert to bytes
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            self.test_file_content = buffer.getvalue()
            
            logger.info(f"✅ [SETUP] Test image created ({len(self.test_file_content)} bytes, {width}x{height})")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SETUP] Failed to create test image: {e}")
            return False
    
    async def test_deepzoom_service_health(self):
        """Test if DeepZoom service is running and healthy"""
        try:
            logger.info("🏥 [TEST] Checking DeepZoom service health...")
            
            health_status = await self.deep_zoom_background_service.get_health_status()
            queue_status = await self.deep_zoom_background_service.get_queue_status()
            
            logger.info(f"📊 [TEST] Service status: {health_status['status']}")
            logger.info(f"📊 [TEST] Queue size: {queue_status['queue_size']}")
            logger.info(f"📊 [TEST] Is running: {queue_status['is_running']}")
            
            if health_status['status'] == 'healthy':
                logger.info("✅ [TEST] DeepZoom service is healthy")
                return True
            else:
                logger.error(f"❌ [TEST] DeepZoom service unhealthy: {health_status['health_issues']}")
                return False
                
        except Exception as e:
            logger.error(f"❌ [TEST] Error checking service health: {e}")
            return False
    
    async def test_photo_upload(self):
        """Test photo upload to trigger DeepZoom processing"""
        try:
            logger.info("📤 [TEST] Testing photo upload...")
            
            # Simulate photo upload
            test_filename = f"test_deepzoom_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # Upload file to MinIO
            file_path = f"sites/{self.test_site_id}/photos/{test_filename}"
            
            result = await asyncio.to_thread(
                self.archaeological_minio_service.client.put_object,
                bucket_name=self.archaeological_minio_service.buckets['photos'],
                object_name=file_path,
                data=io.BytesIO(self.test_file_content),
                length=len(self.test_file_content),
                content_type='image/jpeg',
                metadata={
                    'x-amz-meta-site-id': self.test_site_id,
                    'x-amz-meta-filename': test_filename,
                    'x-amz-meta-uploaded-by': self.test_user_id
                }
            )
            
            # Create database record
            async with self.async_session_maker() as db:
                from sqlalchemy import select
                
                photo = Photo(
                    id=uuid.uuid4(),
                    site_id=uuid.UUID(self.test_site_id),
                    filename=test_filename,
                    original_filename=test_filename,
                    filepath=file_path,
                    file_size=len(self.test_file_content),
                    mime_type='image/jpeg',
                    width=4000,
                    height=3000,
                    format='JPEG',
                    photo_type='excavation_photo',
                    deepzoom_status='scheduled',
                    has_deep_zoom=False,
                    uploaded_by=uuid.UUID(self.test_user_id),
                    created_by=uuid.UUID(self.test_user_id)
                )
                
                db.add(photo)
                await db.commit()
                await db.refresh(photo)
                
                self.test_photo_id = str(photo.id)
                
            self.upload_result = {
                'photo_id': self.test_photo_id,
                'site_id': self.test_site_id,
                'file_path': file_path,
                'filename': test_filename
            }
            
            logger.info(f"✅ [TEST] Photo uploaded successfully - ID: {self.test_photo_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [TEST] Photo upload failed: {e}")
            return False
    
    async def test_tile_processing_scheduling(self):
        """Test scheduling of tile processing"""
        try:
            logger.info("⏰ [TEST] Testing tile processing scheduling...")
            
            # Schedule the photo for DeepZoom processing
            result = await self.deep_zoom_background_service.schedule_tile_processing(
                photo_id=self.test_photo_id,
                site_id=self.test_site_id,
                file_path=self.upload_result['file_path'],
                original_file_content=self.test_file_content,
                archaeological_metadata={
                    'inventory_number': f'TEST-{datetime.now().strftime("%Y%m%d")}',
                    'excavation_area': 'Test Area',
                    'material': 'Test Material'
                }
            )
            
            self.tile_generation_result = result
            
            logger.info(f"✅ [TEST] Tile processing scheduled: {result['status']}")
            
            # Check if task was added to queue
            queue_status = await self.deep_zoom_background_service.get_queue_status()
            logger.info(f"📊 [TEST] Queue size after scheduling: {queue_status['queue_size']}")
            
            return result['status'] in ['scheduled', 'already_scheduled']
            
        except Exception as e:
            logger.error(f"❌ [TEST] Tile processing scheduling failed: {e}")
            return False
    
    async def monitor_tile_processing(self, timeout_seconds=300):
        """Monitor tile processing until completion or timeout"""
        try:
            logger.info(f"⏱️ [TEST] Monitoring tile processing (timeout: {timeout_seconds}s)...")
            
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                # Check task status
                task_status = await self.deep_zoom_background_service.get_task_status(self.test_photo_id)
                
                if task_status:
                    logger.info(f"📊 [TEST] Task status: {task_status['status']}")
                    
                    if task_status['status'] == 'completed':
                        logger.info("✅ [TEST] Tile processing completed successfully!")
                        return True
                    elif task_status['status'] == 'failed':
                        logger.error(f"❌ [TEST] Tile processing failed: {task_status.get('error_message', 'Unknown error')}")
                        return False
                
                # Check queue status
                queue_status = await self.deep_zoom_background_service.get_queue_status()
                logger.info(f"📊 [TEST] Queue: {queue_status['queue_size']} items, {queue_status['processing_tasks']} processing")
                
                # Wait before next check
                await asyncio.sleep(10)
            
            logger.error(f"❌ [TEST] Tile processing timed out after {timeout_seconds}s")
            return False
            
        except Exception as e:
            logger.error(f"❌ [TEST] Error monitoring tile processing: {e}")
            return False
    
    async def verify_tile_generation(self):
        """Verify that tiles were generated and stored correctly"""
        try:
            logger.info("🔍 [TEST] Verifying tile generation...")
            
            # Check database record
            async with self.async_session_maker() as db:
                from sqlalchemy import select
                
                photo = await db.execute(
                    select(Photo).where(Photo.id == uuid.UUID(self.test_photo_id))
                )
                photo = photo.scalar_one_or_none()
                
                if not photo:
                    logger.error("❌ [TEST] Photo record not found")
                    return False
                
                logger.info(f"📊 [TEST] Photo deepzoom_status: {photo.deepzoom_status}")
                logger.info(f"📊 [TEST] Photo has_deep_zoom: {photo.has_deep_zoom}")
                logger.info(f"📊 [TEST] Photo tile_count: {photo.tile_count}")
                logger.info(f"📊 [TEST] Photo max_zoom_level: {photo.max_zoom_level}")
                
                if not photo.has_deep_zoom or photo.deepzoom_status != 'completed':
                    logger.error("❌ [TEST] Photo doesn't have completed DeepZoom tiles")
                    return False
            
            # Check MinIO tiles bucket
            tiles_prefix = f"{self.test_site_id}/tiles/{self.test_photo_id}/"
            
            # List tile objects
            tile_objects = []
            try:
                for obj in self.archaeological_minio_service.client.list_objects(
                    bucket_name=self.archaeological_minio_service.buckets['tiles'],
                    prefix=tiles_prefix,
                    recursive=True
                ):
                    tile_objects.append(obj.object_name)
            except Exception as e:
                logger.warning(f"⚠️ [TEST] Error listing tiles: {e}")
                return False
            
            logger.info(f"📊 [TEST] Found {len(tile_objects)} tile objects")
            
            # Check for metadata.json
            metadata_path = f"{tiles_prefix}metadata.json"
            has_metadata = any(obj == metadata_path for obj in tile_objects)
            
            if has_metadata:
                logger.info("✅ [TEST] Metadata file found")
                
                try:
                    # Get and check metadata
                    metadata_data = await asyncio.to_thread(
                        self.archaeological_minio_service.client.get_object,
                        bucket_name=self.archaeological_minio_service.buckets['tiles'],
                        object_name=metadata_path
                    )
                    
                    metadata_content = metadata_data.read().decode('utf-8')
                    logger.info(f"📊 [TEST] Metadata content length: {len(metadata_content)} chars")
                except Exception as e:
                    logger.warning(f"⚠️ [TEST] Error reading metadata: {e}")
                
            else:
                logger.warning("⚠️ [TEST] Metadata file not found")
            
            # Check for actual tile files
            tile_files = [obj for obj in tile_objects if obj.endswith('.jpg') or obj.endswith('.png')]
            logger.info(f"📊 [TEST] Found {len(tile_files)} tile files")
            
            if len(tile_files) > 0:
                logger.info("✅ [TEST] Tile files generated successfully")
                return True
            else:
                logger.error("❌ [TEST] No tile files found")
                return False
                
        except Exception as e:
            logger.error(f"❌ [TEST] Error verifying tile generation: {e}")
            return False
    
    async def cleanup_test_data(self):
        """Clean up test data"""
        try:
            logger.info("🧹 [CLEANUP] Cleaning up test data...")
            
            # Delete tile objects from MinIO
            try:
                tiles_prefix = f"{self.test_site_id}/tiles/{self.test_photo_id}/"
                objects_to_delete = []
                
                for obj in self.archaeological_minio_service.client.list_objects(
                    bucket_name=self.archaeological_minio_service.buckets['tiles'],
                    prefix=tiles_prefix,
                    recursive=True
                ):
                    objects_to_delete.append(obj.object_name)
                
                if objects_to_delete:
                    await asyncio.to_thread(
                        self.archaeological_minio_service.client.remove_objects,
                        self.archaeological_minio_service.buckets['tiles'],
                        objects_to_delete
                    )
                    logger.info(f"🧹 [CLEANUP] Deleted {len(objects_to_delete)} tile objects")
            except Exception as e:
                logger.warning(f"⚠️ [CLEANUP] Error deleting tiles: {e}")
            
            # Delete photo file from MinIO
            try:
                if self.upload_result:
                    await asyncio.to_thread(
                        self.archaeological_minio_service.client.remove_object,
                        self.archaeological_minio_service.buckets['photos'],
                        self.upload_result['file_path']
                    )
                    logger.info("🧹 [CLEANUP] Deleted photo file")
            except Exception as e:
                logger.warning(f"⚠️ [CLEANUP] Error deleting photo file: {e}")
            
            # Delete database record
            try:
                async with self.async_session_maker() as db:
                    from sqlalchemy import select
                    
                    photo = await db.execute(
                        select(Photo).where(Photo.id == uuid.UUID(self.test_photo_id))
                    )
                    photo = photo.scalar_one_or_none()
                    
                    if photo:
                        await db.delete(photo)
                        await db.commit()
                        logger.info("🧹 [CLEANUP] Deleted photo record")
            except Exception as e:
                logger.warning(f"⚠️ [CLEANUP] Error deleting photo record: {e}")
            
            logger.info("✅ [CLEANUP] Cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ [CLEANUP] Error during cleanup: {e}")
    
    async def run_full_test(self):
        """Run the complete pipeline test"""
        logger.info("🚀 [TEST] Starting DeepZoom pipeline integration test...")
        
        test_results = {
            'setup': False,
            'service_health': False,
            'photo_upload': False,
            'tile_scheduling': False,
            'tile_processing': False,
            'tile_verification': False
        }
        
        try:
            # Setup
            test_results['setup'] = await self.setup_test_environment()
            if not test_results['setup']:
                return False
            
            # Create test environment
            test_results['setup'] &= await self.create_test_site_and_user()
            test_results['setup'] &= await self.create_test_image_content()
            
            if not test_results['setup']:
                return False
            
            # Test service health
            test_results['service_health'] = await self.test_deepzoom_service_health()
            
            if not test_results['service_health']:
                logger.error("❌ [TEST] DeepZoom service is not healthy - cannot continue")
                return False
            
            # Test photo upload
            test_results['photo_upload'] = await self.test_photo_upload()
            
            if not test_results['photo_upload']:
                logger.error("❌ [TEST] Photo upload failed - cannot continue")
                return False
            
            # Test tile processing scheduling
            test_results['tile_scheduling'] = await self.test_tile_processing_scheduling()
            
            if not test_results['tile_scheduling']:
                logger.error("❌ [TEST] Tile scheduling failed")
                return False
            
            # Monitor tile processing
            test_results['tile_processing'] = await self.monitor_tile_processing()
            
            if test_results['tile_processing']:
                # Verify tile generation
                test_results['tile_verification'] = await self.verify_tile_generation()
            
            # Print results
            logger.info("📋 [TEST] Test Results:")
            for test_name, result in test_results.items():
                status = "✅ PASS" if result else "❌ FAIL"
                logger.info(f"   {test_name}: {status}")
            
            # Overall result
            all_passed = all(test_results.values())
            if all_passed:
                logger.info("🎉 [TEST] ALL TESTS PASSED! DeepZoom pipeline is working correctly.")
            else:
                failed_tests = [name for name, result in test_results.items() if not result]
                logger.error(f"❌ [TEST] TESTS FAILED: {failed_tests}")
            
            return all_passed
            
        except Exception as e:
            logger.error(f"❌ [TEST] Unexpected error during testing: {e}")
            return False
        
        finally:
            # Cleanup
            try:
                await self.cleanup_test_data()
            except Exception as e:
                logger.warning(f"⚠️ [TEST] Error during cleanup: {e}")


async def main():
    """Main test function"""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    logger.info("🚀 [MAIN] DeepZoom Pipeline Integration Test")
    
    # Create and run tester
    tester = DeepZoomPipelineTester()
    
    try:
        success = await tester.run_full_test()
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logger.info("🛑 [MAIN] Test interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"❌ [MAIN] Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    # Run the test
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 [MAIN] Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ [MAIN] Unexpected error: {e}")
        sys.exit(1)