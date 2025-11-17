#!/usr/bin/env python3
"""
Targeted diagnostic script for DeepZoom tiles functionality

This script focuses on identifying specific issues:
1. Permission problems with tile access
2. Authentication token validation in DeepZoom endpoints
3. MinIO presigned URL generation
4. Backend service dependencies
5. Photo ID 9fa6c15b-dd9e-4e9b-8b20-dab592fdbbc7 status
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger
from datetime import datetime, timedelta
import uuid

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import project modules
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.database.base import async_session_maker
from app.models import Photo
from sqlalchemy import select


class DeepZoomDiagnostic:
    """Comprehensive diagnostic tool for DeepZoom tiles issues"""
    
    def __init__(self):
        self.start_time = time.time()
        self.diagnostics = {}
        self.site_id = "553088aa-f2c3-4799-badc-8ed8f5c41751"
        self.photo_id = "9fa6c15b-dd9e-4e9b-8b20-dab592fdbbc7"
        
    async def run_comprehensive_diagnosis(self):
        """Run all diagnostic tests"""
        logger.info("🏥 Starting comprehensive DeepZoom diagnosis...")
        
        try:
            # Test 1: Database connectivity and photo existence
            await self.test_database_and_photo()
            
            # Test 2: MinIO service connectivity
            await self.test_minio_connectivity()
            
            # Test 3: DeepZoom service initialization
            await self.test_deepzoom_service()
            
            # Test 4: Tile generation status
            await self.test_tile_generation_status()
            
            # Test 5: MinIO presigned URL generation
            await self.test_presigned_url_generation()
            
            # Test 6: Background service status
            await self.test_background_service()
            
            # Test 7: Permission and access simulation
            await self.test_permission_simulation()
            
            # Generate diagnostic report
            await self.generate_diagnostic_report()
            
        except Exception as e:
            logger.error(f"❌ Diagnostic process failed: {e}")
            raise
    
    async def test_database_and_photo(self):
        """Test database connectivity and photo existence"""
        logger.info("🗄️ Testing database connectivity and photo existence...")
        
        start_time = time.time()
        
        try:
            async with async_session_maker() as db:
                # Test database connection
                await db.execute("SELECT 1")
                logger.info("✅ Database connection successful")
                
                # Test photo existence
                photo_query = select(Photo).where(Photo.id == self.photo_id)
                photo_result = await db.execute(photo_query)
                photo = photo_result.scalar_one_or_none()
                
                if photo:
                    self.diagnostics['database_photo'] = {
                        'status': 'success',
                        'photo_exists': True,
                        'photo_data': {
                            'id': str(photo.id),
                            'filename': photo.filename,
                            'file_size': photo.file_size,
                            'width': photo.width,
                            'height': photo.height,
                            'site_id': photo.site_id,
                            'deepzoom_status': photo.deepzoom_status,
                            'has_deep_zoom': photo.has_deep_zoom,
                            'tile_count': photo.tile_count,
                            'max_zoom_level': photo.max_zoom_level,
                            'deepzoom_processed_at': photo.deepzoom_processed_at.isoformat() if photo.deepzoom_processed_at else None
                        },
                        'duration': time.time() - start_time
                    }
                    
                    logger.info(f"✅ Photo found: {photo.filename} ({photo.width}x{photo.height})")
                    logger.info(f"   DeepZoom status: {photo.deepzoom_status}")
                    logger.info(f"   Has tiles: {photo.has_deep_zoom}")
                    
                else:
                    self.diagnostics['database_photo'] = {
                        'status': 'photo_not_found',
                        'photo_exists': False,
                        'photo_id': self.photo_id,
                        'duration': time.time() - start_time
                    }
                    
                    logger.error(f"❌ Photo {self.photo_id} not found in database")
                    
        except Exception as e:
            self.diagnostics['database_photo'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ Database test failed: {e}")
    
    async def test_minio_connectivity(self):
        """Test MinIO service connectivity"""
        logger.info("🗄️ Testing MinIO service connectivity...")
        
        start_time = time.time()
        
        try:
            # Test archaeological_minio_service
            buckets = archaeological_minio_service.buckets
            logger.info(f"✅ Connected to MinIO buckets: {list(buckets.keys())}")
            
            # Test tile bucket existence
            tile_bucket = buckets.get('tiles')
            if tile_bucket:
                self.diagnostics['minio_connectivity'] = {
                    'status': 'success',
                    'buckets': list(buckets.keys()),
                    'tile_bucket': tile_bucket,
                    'duration': time.time() - start_time
                }
                
                logger.info(f"✅ Tile bucket found: {tile_bucket}")
                
            else:
                self.diagnostics['minio_connectivity'] = {
                    'status': 'no_tile_bucket',
                    'buckets': list(buckets.keys()),
                    'duration': time.time() - start_time
                }
                
                logger.warning("⚠️ No tile bucket found in MinIO configuration")
                
        except Exception as e:
            self.diagnostics['minio_connectivity'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ MinIO connectivity test failed: {e}")
    
    async def test_deepzoom_service(self):
        """Test DeepZoom service initialization"""
        logger.info("🔧 Testing DeepZoom service initialization...")
        
        start_time = time.time()
        
        try:
            # Test service initialization
            service_info = {
                'tile_size': deep_zoom_minio_service.tile_size,
                'overlap': deep_zoom_minio_service.overlap,
                'format': deep_zoom_minio_service.format
            }
            
            self.diagnostics['deepzoom_service'] = {
                'status': 'success',
                'service_info': service_info,
                'duration': time.time() - start_time
            }
            
            logger.info(f"✅ DeepZoom service initialized: {service_info}")
            
        except Exception as e:
            self.diagnostics['deepzoom_service'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ DeepZoom service test failed: {e}")
    
    async def test_tile_generation_status(self):
        """Test tile generation status for the specific photo"""
        logger.info(f"📊 Testing tile generation status for photo {self.photo_id}...")
        
        start_time = time.time()
        
        try:
            # Test DeepZoom info
            deepzoom_info = await deep_zoom_minio_service.get_deep_zoom_info(
                self.site_id, self.photo_id
            )
            
            if deepzoom_info:
                self.diagnostics['tile_status'] = {
                    'status': 'tiles_available',
                    'deepzoom_info': deepzoom_info,
                    'duration': time.time() - start_time
                }
                
                logger.info(f"✅ DeepZoom tiles available: {deepzoom_info['total_tiles']} tiles, {deepzoom_info['levels']} levels")
                
            else:
                # Test processing status
                processing_status = await deep_zoom_minio_service.get_processing_status(
                    self.site_id, self.photo_id
                )
                
                self.diagnostics['tile_status'] = {
                    'status': 'tiles_not_generated',
                    'processing_status': processing_status,
                    'deepzoom_info': None,
                    'duration': time.time() - start_time
                }
                
                logger.info(f"ℹ️ Tiles not generated, processing status: {processing_status}")
                
        except Exception as e:
            self.diagnostics['tile_status'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ Tile status test failed: {e}")
    
    async def test_presigned_url_generation(self):
        """Test MinIO presigned URL generation"""
        logger.info("🔗 Testing MinIO presigned URL generation...")
        
        start_time = time.time()
        
        try:
            # Test tile URL generation (level 0, tile 0_0)
            tile_url = await deep_zoom_minio_service.get_tile_url(
                self.site_id, self.photo_id, 0, 0, 0
            )
            
            if tile_url:
                self.diagnostics['presigned_url'] = {
                    'status': 'success',
                    'tile_url': tile_url[:100] + "..." if len(tile_url) > 100 else tile_url,
                    'url_length': len(tile_url),
                    'duration': time.time() - start_time
                }
                
                logger.info(f"✅ Presigned URL generated successfully ({len(tile_url)} chars)")
                
            else:
                self.diagnostics['presigned_url'] = {
                    'status': 'no_url_generated',
                    'reason': 'Tile not found or not generated',
                    'duration': time.time() - start_time
                }
                
                logger.warning("⚠️ No presigned URL generated - tiles may not exist")
                
        except Exception as e:
            self.diagnostics['presigned_url'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ Presigned URL test failed: {e}")
    
    async def test_background_service(self):
        """Test background service status"""
        logger.info("⚙️ Testing background service status...")
        
        start_time = time.time()
        
        try:
            # Test background service queue status
            queue_status = await deep_zoom_background_service.get_queue_status()
            
            # Test task status for the specific photo
            task_status = await deep_zoom_background_service.get_task_status(self.photo_id)
            
            # Test if background processor is running
            is_running = deep_zoom_background_service._running
            
            self.diagnostics['background_service'] = {
                'status': 'success',
                'queue_status': queue_status,
                'task_status': task_status,
                'is_running': is_running,
                'duration': time.time() - start_time
            }
            
            logger.info(f"✅ Background service status: running={is_running}, queue_size={queue_status.get('queue_size', 'unknown')}")
            
            if task_status:
                logger.info(f"   Task status for photo {self.photo_id}: {task_status}")
            
        except Exception as e:
            self.diagnostics['background_service'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ Background service test failed: {e}")
    
    async def test_permission_simulation(self):
        """Simulate permission checks and access validation"""
        logger.info("🔐 Testing permission simulation...")
        
        start_time = time.time()
        
        try:
            # This simulates the permission check that happens in the API
            # We'll check if the photo belongs to the specified site
            
            async with async_session_maker() as db:
                photo_query = select(Photo).where(Photo.id == self.photo_id)
                photo_result = await db.execute(photo_query)
                photo = photo_result.scalar_one_or_none()
                
                if photo:
                    photo_site_id = photo.site_id
                    
                    # Check if photo belongs to the specified site
                    if str(photo_site_id) == self.site_id:
                        permission_status = 'valid_access'
                        message = f"Photo {self.photo_id} belongs to site {self.site_id}"
                    else:
                        permission_status = 'site_mismatch'
                        message = f"Photo {self.photo_id} belongs to site {photo_site_id}, not {self.site_id}"
                    
                    self.diagnostics['permission_simulation'] = {
                        'status': 'success',
                        'permission_status': permission_status,
                        'photo_site_id': str(photo_site_id),
                        'target_site_id': self.site_id,
                        'message': message,
                        'duration': time.time() - start_time
                    }
                    
                    logger.info(f"✅ Permission check: {message}")
                    
                else:
                    self.diagnostics['permission_simulation'] = {
                        'status': 'photo_not_found',
                        'message': f"Photo {self.photo_id} not found",
                        'duration': time.time() - start_time
                    }
                    
                    logger.error(f"❌ Permission check failed: Photo not found")
                    
        except Exception as e:
            self.diagnostics['permission_simulation'] = {
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }
            
            logger.error(f"❌ Permission simulation failed: {e}")
    
    async def generate_diagnostic_report(self):
        """Generate comprehensive diagnostic report"""
        logger.info("📋 Generating diagnostic report...")
        
        total_time = time.time() - self.start_time
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_duration': total_time,
            'site_id': self.site_id,
            'photo_id': self.photo_id,
            'diagnostics': self.diagnostics,
            'summary': {
                'total_tests': len(self.diagnostics),
                'successful_tests': len([d for d in self.diagnostics.values() if d.get('status') == 'success']),
                'failed_tests': len([d for d in self.diagnostics.values() if d.get('status') == 'error']),
                'warning_tests': len([d for d in self.diagnostics.values() if d.get('status') in ['not_found', 'no_tile_bucket', 'tiles_not_generated']]),
            },
            'issues_identified': [],
            'recommendations': []
        }
        
        # Identify issues
        if self.diagnostics.get('database_photo', {}).get('status') == 'photo_not_found':
            report['issues_identified'].append("Target photo not found in database")
            report['recommendations'].append("Verify photo ID and check if photo exists")
        
        if self.diagnostics.get('minio_connectivity', {}).get('status') == 'no_tile_bucket':
            report['issues_identified'].append("No tile bucket configured in MinIO")
            report['recommendations'].append("Configure tile bucket in MinIO service")
        
        if self.diagnostics.get('tile_status', {}).get('status') == 'tiles_not_generated':
            report['issues_identified'].append("DeepZoom tiles not generated for target photo")
            report['recommendations'].append("Trigger tile generation for the photo using the process endpoint")
        
        if self.diagnostics.get('presigned_url', {}).get('status') == 'no_url_generated':
            report['issues_identified'].append("Unable to generate presigned URLs")
            report['recommendations'].append("Check MinIO permissions and bucket configuration")
        
        if self.diagnostics.get('background_service', {}).get('is_running') is False:
            report['issues_identified'].append("Background service not running")
            report['recommendations'].append("Start background service for tile processing")
        
        if self.diagnostics.get('permission_simulation', {}).get('permission_status') == 'site_mismatch':
            report['issues_identified'].append("Photo belongs to different site than specified")
            report['recommendations'].append("Use correct site ID for the photo")
        
        # Save report
        report_file = f"deepzoom_diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📄 Diagnostic report saved to: {report_file}")
        
        # Print summary
        logger.info("🎯 DIAGNOSTIC SUMMARY:")
        logger.info(f"  Total tests: {report['summary']['total_tests']}")
        logger.info(f"  Successful: {report['summary']['successful_tests']}")
        logger.info(f"  Failed: {report['summary']['failed_tests']}")
        logger.info(f"  Warnings: {report['summary']['warning_tests']}")
        logger.info(f"  Total duration: {total_time:.2f}s")
        
        if report['issues_identified']:
            logger.info("🔍 ISSUES IDENTIFIED:")
            for issue in report['issues_identified']:
                logger.info(f"  • {issue}")
        
        if report['recommendations']:
            logger.info("💡 RECOMMENDATIONS:")
            for rec in report['recommendations']:
                logger.info(f"  • {rec}")
        
        return report


async def main():
    """Main diagnostic function"""
    logger.info("🏥 Starting DeepZoom comprehensive diagnosis...")
    
    diagnostic = DeepZoomDiagnostic()
    
    try:
        report = await diagnostic.run_comprehensive_diagnosis()
        
        logger.info("✅ Diagnostic completed!")
        
        # Return appropriate exit code based on results
        failed_tests = report['summary']['failed_tests']
        if failed_tests > 0:
            logger.warning(f"⚠️ {failed_tests} diagnostic tests failed")
            return 1
        else:
            logger.info("🎉 All diagnostic tests passed or have warnings")
            return 0
            
    except Exception as e:
        logger.error(f"❌ Diagnostic execution failed: {e}")
        return 2


if __name__ == "__main__":
    # Configure logging
    logger.add(
        "deepzoom_diagnostic.log",
        rotation="10 MB",
        retention="1 week",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )
    
    # Run the diagnostic
    exit_code = asyncio.run(main())
    sys.exit(exit_code)