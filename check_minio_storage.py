#!/usr/bin/env python3
"""
Check MinIO storage for uploaded photo files
"""

import asyncio
import sys
from pathlib import Path
from loguru import logger

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.archaeological_minio_service import archaeological_minio_service
from app.database.base import async_session_maker
from app.models import Photo
from sqlalchemy import select


async def check_minio_files():
    """Check if photo files exist in MinIO storage"""
    logger.info("🔍 [MINIO] Checking file storage...")
    
    async with async_session_maker() as db:
        try:
            # Get all photos from database
            photos_query = select(Photo).order_by(Photo.created_at.desc())
            photos_result = await db.execute(photos_query)
            photos = photos_result.scalars().all()
            
            logger.info(f"📊 [MINIO] Checking {len(photos)} photo files...")
            
            missing_files = []
            found_files = []
            
            for photo in photos:
                try:
                    # Check if file exists in MinIO
                    file_exists = await archaeological_minio_service.file_exists(photo.filepath)
                    
                    if file_exists:
                        logger.info(f"✅ [MINIO] Found: {photo.filepath}")
                        found_files.append(photo.filepath)
                    else:
                        logger.error(f"❌ [MINIO] Missing: {photo.filepath}")
                        missing_files.append(photo.filepath)
                        
                except Exception as e:
                    logger.error(f"❌ [MINIO] Error checking {photo.filepath}: {e}")
                    missing_files.append(photo.filepath)
            
            logger.info(f"📊 [MINIO] Storage summary:")
            logger.info(f"   Found files: {len(found_files)}")
            logger.info(f"   Missing files: {len(missing_files)}")
            
            if missing_files:
                logger.warning("⚠️ [MINIO] Missing files:")
                for file_path in missing_files:
                    logger.warning(f"   - {file_path}")
            
            return {
                'total_photos': len(photos),
                'found_files': len(found_files),
                'missing_files': len(missing_files)
            }
            
        except Exception as e:
            logger.error(f"❌ [MINIO] Error checking MinIO storage: {e}")
            return None


async def main():
    """Main function"""
    logger.info("🚀 [MINIO] Starting MinIO storage check...")
    
    results = await check_minio_files()
    
    if results:
        logger.info("📋 [SUMMARY] MinIO storage results:")
        logger.info(f"   Total photos: {results['total_photos']}")
        logger.info(f"   Files found: {results['found_files']}")
        logger.info(f"   Files missing: {results['missing_files']}")
        
        if results['missing_files'] > 0:
            logger.error(f"❌ [MINIO] {results['missing_files']} files are missing from storage!")
        else:
            logger.info("✅ [MINIO] All photo files are properly stored in MinIO")
    
    logger.info("🏁 [MINIO] MinIO storage check completed")


if __name__ == "__main__":
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    asyncio.run(main())