#!/usr/bin/env python3
"""
DeepZoom Background Service Manager
Stops, starts, and manages the DeepZoom background processing service
"""

import asyncio
import sys
import signal
import time
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class DeepZoomServiceManager:
    """Manager for DeepZoom background service"""
    
    def __init__(self):
        self.service = None
        self.running = False
        self.start_time = None
        
    async def initialize(self):
        """Initialize the service and its dependencies"""
        try:
            logger.info("🔧 [INIT] Initializing DeepZoom service manager...")
            
            # Import the service
            from app.services.deep_zoom_background_service import deep_zoom_background_service
            self.service = deep_zoom_background_service
            
            logger.info("✅ [INIT] DeepZoom service imported successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ [INIT] Failed to initialize service: {e}")
            return False
    
    async def check_service_health(self):
        """Check the current health of the DeepZoom service"""
        try:
            if not self.service:
                return {"status": "not_initialized", "issues": ["Service not initialized"]}
            
            health_status = await self.service.get_health_status()
            queue_status = await self.service.get_queue_status()
            
            return {
                "health": health_status,
                "queue": queue_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [HEALTH] Error checking service health: {e}")
            return {"status": "error", "issues": [str(e)]}
    
    async def start_service(self):
        """Start the DeepZoom background service"""
        try:
            logger.info("🚀 [START] Starting DeepZoom background service...")
            
            if not self.service:
                await self.initialize()
            
            if not self.service:
                logger.error("❌ [START] Cannot start service - initialization failed")
                return False
            
            # Check if already running
            if self.service._running:
                logger.info("ℹ️ [START] DeepZoom service is already running")
                self.running = True
                return True
            
            # Start the service
            await self.service.start_background_processor()
            
            # Wait a moment for startup to complete
            await asyncio.sleep(2)
            
            # Verify it started successfully
            health = await self.check_service_health()
            
            if health["health"]["status"] == "healthy":
                logger.info("✅ [START] DeepZoom service started successfully")
                logger.info(f"📊 [START] Service uptime: {health['health']['uptime_seconds']:.2f}s")
                self.running = True
                self.start_time = datetime.now()
                return True
            else:
                logger.error(f"❌ [START] Service not healthy after start: {health['health']['health_issues']}")
                return False
                
        except Exception as e:
            logger.error(f"❌ [START] Failed to start DeepZoom service: {e}")
            return False
    
    async def stop_service(self):
        """Stop the DeepZoom background service"""
        try:
            logger.info("🛑 [STOP] Stopping DeepZoom background service...")
            
            if not self.service or not self.service._running:
                logger.info("ℹ️ [STOP] DeepZoom service is not running")
                self.running = False
                return True
            
            await self.service.stop_background_processor()
            
            # Wait a moment for shutdown to complete
            await asyncio.sleep(2)
            
            logger.info("✅ [STOP] DeepZoom service stopped successfully")
            self.running = False
            return True
            
        except Exception as e:
            logger.error(f"❌ [STOP] Failed to stop DeepZoom service: {e}")
            return False
    
    async def reset_service(self):
        """Reset the DeepZoom service (emergency recovery)"""
        try:
            logger.warning("🔄 [RESET] Resetting DeepZoom service...")
            
            if not self.service:
                await self.initialize()
            
            result = await self.service.reset_service()
            
            logger.info(f"🔄 [RESET] Service reset completed: {result['status']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ [RESET] Failed to reset service: {e}")
            return {"status": "reset_failed", "error": str(e)}
    
    async def monitor_service(self, duration_seconds=60, check_interval=10):
        """Monitor the service health for a specified duration"""
        try:
            logger.info(f"📊 [MONITOR] Starting service monitoring for {duration_seconds} seconds...")
            
            end_time = time.time() + duration_seconds
            
            while time.time() < end_time:
                health = await self.check_service_health()
                
                status = health["health"]["status"]
                queue_size = health["queue"]["queue_size"]
                processing_tasks = health["queue"]["processing_tasks"]
                
                logger.info(f"📊 [MONITOR] Status: {status}, Queue: {queue_size}, Processing: {processing_tasks}")
                
                if status != "healthy":
                    logger.warning(f"⚠️ [MONITOR] Service unhealthy: {health['health']['health_issues']}")
                
                await asyncio.sleep(check_interval)
            
            logger.info("✅ [MONITOR] Service monitoring completed")
            
        except Exception as e:
            logger.error(f"❌ [MONITOR] Error during monitoring: {e}")
    
    async def show_service_status(self):
        """Show detailed service status"""
        try:
            health = await self.check_service_health()
            
            logger.info("📋 [STATUS] DeepZoom Service Status:")
            logger.info(f"   Status: {health['health']['status']}")
            logger.info(f"   Uptime: {health['health']['uptime_seconds']:.2f}s")
            logger.info(f"   Queue Size: {health['queue']['queue_size']}")
            logger.info(f"   Processing Tasks: {health['queue']['processing_tasks']}")
            logger.info(f"   Completed Tasks: {health['queue']['completed_tasks']}")
            logger.info(f"   Failed Tasks: {health['queue']['failed_tasks']}")
            logger.info(f"   Total Processed: {health['queue']['total_tasks_processed']}")
            logger.info(f"   Total Failed: {health['queue']['total_tasks_failed']}")
            
            if health['health']['health_issues']:
                logger.warning("⚠️ [STATUS] Health Issues:")
                for issue in health['health']['health_issues']:
                    logger.warning(f"   - {issue}")
            
            if health['health']['stuck_tasks']:
                logger.warning(f"⚠️ [STATUS] Stuck Tasks: {len(health['health']['stuck_tasks'])}")
            
            return health
            
        except Exception as e:
            logger.error(f"❌ [STATUS] Error getting status: {e}")
            return None


# Global service manager instance
service_manager = DeepZoomServiceManager()


async def main():
    """Main function with command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepZoom Background Service Manager")
    parser.add_argument("command", choices=["start", "stop", "restart", "status", "monitor", "reset"], 
                       help="Command to execute")
    parser.add_argument("--duration", type=int, default=60, 
                       help="Monitoring duration in seconds (for monitor command)")
    parser.add_argument("--interval", type=int, default=10, 
                       help="Monitoring check interval in seconds (for monitor command)")
    
    args = parser.parse_args()
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    logger.info(f"🚀 [MAIN] DeepZoom Service Manager - Command: {args.command}")
    
    # Initialize the manager
    if not await service_manager.initialize():
        logger.error("❌ [MAIN] Failed to initialize service manager")
        return 1
    
    # Execute command
    if args.command == "start":
        success = await service_manager.start_service()
        if success:
            await service_manager.show_service_status()
            return 0
        else:
            return 1
    
    elif args.command == "stop":
        success = await service_manager.stop_service()
        return 0 if success else 1
    
    elif args.command == "restart":
        logger.info("🔄 [MAIN] Restarting DeepZoom service...")
        await service_manager.stop_service()
        await asyncio.sleep(2)
        success = await service_manager.start_service()
        if success:
            await service_manager.show_service_status()
            return 0
        else:
            return 1
    
    elif args.command == "status":
        await service_manager.show_service_status()
        return 0
    
    elif args.command == "monitor":
        # Start service if not running
        if not service_manager.running:
            await service_manager.start_service()
        
        await service_manager.monitor_service(args.duration, args.interval)
        return 0
    
    elif args.command == "reset":
        result = await service_manager.reset_service()
        return 0 if result["status"] == "reset_completed" else 1
    
    else:
        logger.error(f"❌ [MAIN] Unknown command: {args.command}")
        return 1


def signal_handler(signum, frame):
    """Handle interrupt signals"""
    logger.info("🛑 [SIGNAL] Interrupt received, stopping service...")
    if service_manager.running:
        asyncio.create_task(service_manager.stop_service())
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the main function
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 [MAIN] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ [MAIN] Unexpected error: {e}")
        sys.exit(1)