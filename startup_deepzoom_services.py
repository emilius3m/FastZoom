"""
Startup script for FastZoom DeepZoom background services

This script should be called when the FastZoom application starts
to ensure all background services are properly initialized.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.deep_zoom_background_service import deep_zoom_background_service
from loguru import logger


async def startup_deepzoom_services():
    """Initialize DeepZoom background services"""
    try:
        logger.info("🚀 Starting DeepZoom background services...")
        
        # Start the background processor
        if not deep_zoom_background_service._running:
            await deep_zoom_background_service.start_background_processor()
            logger.info("✅ DeepZoom background processor started")
        else:
            logger.info("ℹ️ DeepZoom background processor already running")
        
        # Verify status
        queue_status = await deep_zoom_background_service.get_queue_status()
        logger.info(f"📊 Background service status: {queue_status}")
        
        logger.info("✅ DeepZoom services initialization completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to start DeepZoom services: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(startup_deepzoom_services())
