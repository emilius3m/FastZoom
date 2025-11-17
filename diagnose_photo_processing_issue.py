#!/usr/bin/env python3
"""
Diagnostic script to investigate why only 3 out of 5 photos are being processed for tiles
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.database.base import async_session_maker
from app.models import Photo
from sqlalchemy import select, and_, func, or_, desc
from uuid import UUID


async def check_database_photos():
    """Check database for photo records and their processing status"""
    logger.info("🔍 [DATABASE] Checking photo records...")
    
    async with async_session_maker() as db:
        try:
            # Check total photo count
            total_photos_query = select(func.count(Photo.id))
            total_result = await db.execute(total_photos_query)
            total_photos = total_result.scalar()
            logger.info(f"📊 [DATABASE] Total photos in database: {total_photos}")
            
            # Check photos by deepzoom status
            status_query = select(
                Photo.deepzoom_status,
                func.count(Photo.id).label('count')
            ).group_by(Photo.deepzoom_status)
            
            status_result = await db.execute(status_query)
            status_counts = status_result.all()
            
            logger.info("📊 [DATABASE] Photos by deepzoom status:")
            for status, count in status_counts:
                logger.info(f"   - {status or 'NULL'}: {count} photos")
            
            # Check recent photos (last 24 hours)
            recent_photos_query = select(Photo).where(
                Photo.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).order_by(desc(Photo.created_at)).limit(10)
            
            recent_result = await db.execute(recent_photos_query)
            recent_photos = recent_result.scalars().all()
            
            logger.info(f"📋 [DATABASE] Recent photos ({len(recent_photos)}):")
            for photo in recent_photos:
                logger.info(f"   - ID: {photo.id}")
                logger.info(f"     Filename: {photo.filename}")
                logger.info(f"     Site: {photo.site_id}")
                logger.info(f"     DeepZoom Status: {photo.deepzoom_status}")
                logger.info(f"     Has DeepZoom: {photo.has_deep_zoom}")
                logger.info(f"     Dimensions: {photo.width}x{photo.height}")
                logger.info(f"     File Size: {photo.file_size}")
                logger.info(f"     Created: {photo.created_at}")
                logger.info("")
            
            # Check photos scheduled for processing but not started
            scheduled_not_processing_query = select(Photo).where(
                and_(
                    Photo.deepzoom_status == 'scheduled',
                    Photo.has_deep_zoom == False
                )
            ).order_by(desc(Photo.created_at)).limit(5)
            
            scheduled_result = await db.execute(scheduled_not_processing_query)
            scheduled_photos = scheduled_result.scalars().all()
            
            if scheduled_photos:
                logger.warning(f"⚠️ [DATABASE] {len(scheduled_photos)} photos scheduled but not processed:")
                for photo in scheduled_photos:
                    logger.warning(f"   - ID: {photo.id}, Filename: {photo.filename}, Created: {photo.created_at}")
            
            # Check photos with failed status
            failed_photos_query = select(Photo).where(
                Photo.deepzoom_status == 'failed'
            ).order_by(desc(Photo.created_at)).limit(5)
            
            failed_result = await db.execute(failed_photos_query)
            failed_photos = failed_result.scalars().all()
            
            if failed_photos:
                logger.error(f"❌ [DATABASE] {len(failed_photos)} photos with failed status:")
                for photo in failed_photos:
                    logger.error(f"   - ID: {photo.id}, Filename: {photo.filename}, Created: {photo.created_at}")
            
            return {
                'total_photos': total_photos,
                'status_counts': dict(status_counts),
                'recent_photos': len(recent_photos),
                'scheduled_not_processed': len(scheduled_photos),
                'failed_photos': len(failed_photos)
            }
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Error checking database: {e}")
            return None


async def check_background_service_status():
    """Check the background service status and queue"""
    logger.info("🔍 [BACKGROUND] Checking deep zoom background service...")
    
    try:
        from app.services.deep_zoom_background_service import deep_zoom_background_service
        
        # Get queue status
        queue_status = await deep_zoom_background_service.get_queue_status()
        logger.info(f"📊 [BACKGROUND] Queue status: {queue_status}")
        
        # Get health status
        health_status = await deep_zoom_background_service.get_health_status()
        logger.info(f"📊 [BACKGROUND] Health status: {health_status}")
        
        return {
            'queue_status': queue_status,
            'health_status': health_status
        }
        
    except Exception as e:
        logger.error(f"❌ [BACKGROUND] Error checking background service: {e}")
        return None


async def check_processing_pipeline():
    """Check the processing pipeline for bottlenecks"""
    logger.info("🔍 [PIPELINE] Checking processing pipeline...")
    
    async with async_session_maker() as db:
        try:
            # Find photos that should need tiles but don't have them
            large_photos_query = select(Photo).where(
                and_(
                    or_(
                        Photo.width > 2000,
                        Photo.height > 2000
                    ),
                    Photo.has_deep_zoom == False,
                    Photo.deepzoom_status.in_([None, ''])
                )
            ).order_by(desc(Photo.created_at)).limit(10)
            
            large_photos_result = await db.execute(large_photos_query)
            large_photos = large_photos_result.scalars().all()
            
            if large_photos:
                logger.warning(f"⚠️ [PIPELINE] {len(large_photos)} large photos without deep zoom:")
                for photo in large_photos:
                    logger.warning(f"   - ID: {photo.id}, {photo.width}x{photo.height}, Status: {photo.deepzoom_status}")
            
            # Check photos with dimensions under 2000 that might have been incorrectly processed
            small_photos_with_tiles_query = select(Photo).where(
                and_(
                    Photo.width <= 2000,
                    Photo.height <= 2000,
                    Photo.has_deep_zoom == True
                )
            ).limit(5)
            
            small_photos_result = await db.execute(small_photos_with_tiles_query)
            small_photos = small_photos_result.scalars().all()
            
            if small_photos:
                logger.info(f"ℹ️ [PIPELINE] {len(small_photos)} small photos with deep zoom:")
                for photo in small_photos:
                    logger.info(f"   - ID: {photo.id}, {photo.width}x{photo.height}, Has tiles: {photo.has_deep_zoom}")
            
            return {
                'large_photos_without_tiles': len(large_photos),
                'small_photos_with_tiles': len(small_photos)
            }
            
        except Exception as e:
            logger.error(f"❌ [PIPELINE] Error checking processing pipeline: {e}")
            return None


async def analyze_site_specific(site_id: str = None):
    """Analyze photos for a specific site"""
    if not site_id:
        # Try to find a site with recent activity
        async with async_session_maker() as db:
            recent_site_query = select(Photo.site_id, func.count(Photo.id).label('photo_count')).where(
                Photo.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).group_by(Photo.site_id).order_by(desc('photo_count')).limit(1)
            
            recent_site_result = await db.execute(recent_site_query)
            site_data = recent_site_result.first()
            
            if site_data:
                site_id = site_data.site_id
                logger.info(f"🎯 [SITE] Analyzing site with most recent activity: {site_id}")
            else:
                logger.warning("⚠️ [SITE] No recent activity found")
                return None
    
    logger.info(f"🔍 [SITE] Analyzing site: {site_id}")
    
    async with async_session_maker() as db:
        try:
            # Get all photos for this site
            site_photos_query = select(Photo).where(Photo.site_id == site_id).order_by(desc(Photo.created_at))
            site_photos_result = await db.execute(site_photos_query)
            site_photos = site_photos_result.scalars().all()
            
            logger.info(f"📊 [SITE] Site {site_id} has {len(site_photos)} photos")
            
            # Analyze by status
            status_counts = {}
            dimension_analysis = {'small': 0, 'medium': 0, 'large': 0}
            
            for photo in site_photos:
                status = photo.deepzoom_status or 'none'
                status_counts[status] = status_counts.get(status, 0) + 1
                
                max_dim = max(photo.width or 0, photo.height or 0)
                if max_dim <= 2000:
                    dimension_analysis['small'] += 1
                elif max_dim <= 4000:
                    dimension_analysis['medium'] += 1
                else:
                    dimension_analysis['large'] += 1
            
            logger.info(f"📊 [SITE] Status breakdown: {status_counts}")
            logger.info(f"📊 [SITE] Size breakdown: {dimension_analysis}")
            
            # Find potential issues
            issues = []
            
            # Photos that should have tiles but don't
            for photo in site_photos:
                if max(photo.width or 0, photo.height or 0) > 2000 and not photo.has_deep_zoom:
                    if photo.deepzoom_status not in ['processing', 'scheduled']:
                        issues.append({
                            'type': 'missing_tiles',
                            'photo_id': str(photo.id),
                            'filename': photo.filename,
                            'dimensions': f"{photo.width}x{photo.height}",
                            'status': photo.deepzoom_status
                        })
            
            if issues:
                logger.warning(f"⚠️ [SITE] Found {len(issues)} potential issues:")
                for issue in issues[:5]:  # Show first 5
                    logger.warning(f"   - {issue}")
            
            return {
                'site_id': site_id,
                'total_photos': len(site_photos),
                'status_counts': status_counts,
                'dimension_analysis': dimension_analysis,
                'issues_found': len(issues)
            }
            
        except Exception as e:
            logger.error(f"❌ [SITE] Error analyzing site {site_id}: {e}")
            return None


async def main():
    """Main diagnostic function"""
    logger.info("🚀 [DIAGNOSTIC] Starting photo processing investigation...")
    
    # Check database
    db_results = await check_database_photos()
    
    # Check background service
    bg_results = await check_background_service_status()
    
    # Check processing pipeline
    pipeline_results = await check_processing_pipeline()
    
    # Analyze specific site
    site_results = await analyze_site_specific()
    
    # Summary
    logger.info("📋 [SUMMARY] Diagnostic Results:")
    logger.info(f"   Database Photos: {db_results['total_photos'] if db_results else 'ERROR'}")
    logger.info(f"   Scheduled but not processed: {db_results['scheduled_not_processed'] if db_results else 'ERROR'}")
    logger.info(f"   Failed photos: {db_results['failed_photos'] if db_results else 'ERROR'}")
    logger.info(f"   Background service queue: {bg_results['queue_status']['queue_size'] if bg_results else 'ERROR'}")
    logger.info(f"   Background service health: {bg_results['health_status']['status'] if bg_results else 'ERROR'}")
    logger.info(f"   Large photos without tiles: {pipeline_results['large_photos_without_tiles'] if pipeline_results else 'ERROR'}")
    
    # Potential root causes
    logger.info("🔍 [ROOT CAUSE ANALYSIS] Potential issues:")
    
    if db_results and db_results['scheduled_not_processed'] > 0:
        logger.warning("   ⚠️ Photos scheduled but not processed - background service may not be running properly")
    
    if bg_results and bg_results['health_status']['status'] != 'healthy':
        logger.warning("   ⚠️ Background service not healthy - may be causing processing failures")
    
    if pipeline_results and pipeline_results['large_photos_without_tiles'] > 0:
        logger.warning("   ⚠️ Large photos without tiles - processing pipeline may have filtering issues")
    
    logger.info("🏁 [DIAGNOSTIC] Investigation completed")


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Run the diagnostic
    asyncio.run(main())