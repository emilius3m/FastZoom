#!/usr/bin/env python3
"""
DeepZoom Service Auto-Restart Monitor
Continuously monitors the DeepZoom background service and restarts it if it fails
"""

import asyncio
import sys
import signal
import time
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class DeepZoomAutoRestartMonitor:
    """Auto-restart monitor for DeepZoom background service"""
    
    def __init__(self, check_interval=30, max_restart_attempts=5, restart_cooldown=60):
        self.check_interval = check_interval  # seconds
        self.max_restart_attempts = max_restart_attempts
        self.restart_cooldown = restart_cooldown  # seconds between restart attempts
        self.service_manager = None
        self.running = False
        self.last_restart_time = None
        self.restart_attempts = 0
        self.start_time = datetime.now()
        self.healthy_checks = 0
        self.unhealthy_checks = 0
        
    async def initialize(self):
        """Initialize the service manager"""
        try:
            from start_deepzoom_service import DeepZoomServiceManager
            self.service_manager = DeepZoomServiceManager()
            
            success = await self.service_manager.initialize()
            if success:
                logger.info("✅ [AUTO-RESTART] Service manager initialized successfully")
                return True
            else:
                logger.error("❌ [AUTO-RESTART] Failed to initialize service manager")
                return False
                
        except Exception as e:
            logger.error(f"❌ [AUTO-RESTART] Error initializing: {e}")
            return False
    
    async def check_service_health_with_retry(self, max_retries=3):
        """Check service health with retry logic"""
        for attempt in range(max_retries):
            try:
                health = await self.service_manager.check_service_health()
                return health
            except Exception as e:
                logger.warning(f"⚠️ [AUTO-RESTART] Health check attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise
    
    async def is_service_healthy(self):
        """Check if the service is healthy"""
        try:
            health = await self.check_service_health_with_retry()
            
            if health.get("health", {}).get("status") == "healthy":
                # Additional checks for critical conditions
                queue_status = health.get("queue", {})
                
                # Check for stuck tasks
                stuck_tasks = health.get("health", {}).get("stuck_tasks", [])
                if len(stuck_tasks) > 5:  # Too many stuck tasks
                    logger.warning(f"⚠️ [AUTO-RESTART] Too many stuck tasks: {len(stuck_tasks)}")
                    return False
                
                # Check if service is actually running
                if not health.get("queue", {}).get("is_running", False):
                    logger.warning("⚠️ [AUTO-RESTART] Service reports not running")
                    return False
                
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ [AUTO-RESTART] Error checking service health: {e}")
            return False
    
    async def restart_service_if_needed(self):
        """Restart the service if it's unhealthy and conditions allow"""
        current_time = datetime.now()
        
        # Check if we're within cooldown period
        if (self.last_restart_time and 
            (current_time - self.last_restart_time).total_seconds() < self.restart_cooldown):
            logger.info(f"ℹ️ [AUTO-RESTART] Within cooldown period, skipping restart attempt")
            return False
        
        # Check if we've exceeded max restart attempts
        if self.restart_attempts >= self.max_restart_attempts:
            logger.error(f"❌ [AUTO-RESTART] Max restart attempts ({self.max_restart_attempts}) exceeded")
            return False
        
        logger.warning("🔄 [AUTO-RESTART] Attempting to restart DeepZoom service...")
        
        try:
            # Stop the service
            await self.service_manager.stop_service()
            await asyncio.sleep(3)  # Wait for clean shutdown
            
            # Start the service
            success = await self.service_manager.start_service()
            
            if success:
                self.last_restart_time = current_time
                self.restart_attempts += 1
                logger.info(f"✅ [AUTO-RESTART] Service restarted successfully (attempt {self.restart_attempts}/{self.max_restart_attempts})")
                
                # Verify it's healthy after restart
                await asyncio.sleep(5)  # Wait for service to stabilize
                if await self.is_service_healthy():
                    logger.info("✅ [AUTO-RESTART] Service is healthy after restart")
                    return True
                else:
                    logger.warning("⚠️ [AUTO-RESTART] Service restarted but still unhealthy")
                    return False
            else:
                self.restart_attempts += 1
                logger.error(f"❌ [AUTO-RESTART] Failed to restart service (attempt {self.restart_attempts}/{self.max_restart_attempts})")
                return False
                
        except Exception as e:
            self.restart_attempts += 1
            logger.error(f"❌ [AUTO-RESTART] Error during restart: {e}")
            return False
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info(f"🔍 [AUTO-RESTART] Starting monitoring loop (interval: {self.check_interval}s)")
        
        while self.running:
            try:
                is_healthy = await self.is_service_healthy()
                
                if is_healthy:
                    self.healthy_checks += 1
                    if self.unhealthy_checks > 0:
                        logger.info(f"✅ [AUTO-RESTART] Service recovered! Healthy checks: {self.healthy_checks}")
                    self.unhealthy_checks = 0
                    
                    # Reset restart attempts if service has been stable for a while
                    if (self.healthy_checks > 10 and self.restart_attempts > 0):
                        logger.info("🔄 [AUTO-RESTART] Service stable, resetting restart attempts")
                        self.restart_attempts = 0
                else:
                    self.unhealthy_checks += 1
                    logger.warning(f"⚠️ [AUTO-RESTART] Service unhealthy! Unhealthy checks: {self.unhealthy_checks}")
                    
                    # Restart after 3 consecutive unhealthy checks
                    if self.unhealthy_checks >= 3:
                        logger.warning("🔄 [AUTO-RESTART] Multiple unhealthy checks, attempting restart...")
                        await self.restart_service_if_needed()
                        self.unhealthy_checks = 0  # Reset counter after restart attempt
                
                # Show periodic status
                if self.healthy_checks > 0 and self.healthy_checks % 10 == 0:
                    uptime = (datetime.now() - self.start_time).total_seconds()
                    logger.info(f"📊 [AUTO-RESTART] Status: healthy for {uptime:.0f}s (checks: {self.healthy_checks})")
                
            except Exception as e:
                logger.error(f"❌ [AUTO-RESTART] Error in monitoring loop: {e}")
            
            # Wait for next check
            await asyncio.sleep(self.check_interval)
    
    async def start_monitoring(self):
        """Start the auto-restart monitor"""
        try:
            logger.info("🚀 [AUTO-RESTART] Starting DeepZoom auto-restart monitor...")
            
            # Initialize service manager
            if not await self.initialize():
                return False
            
            # Start the service if not running
            if not await self.is_service_healthy():
                logger.info("🔄 [AUTO-RESTART] Starting DeepZoom service...")
                success = await self.service_manager.start_service()
                if not success:
                    logger.error("❌ [AUTO-RESTART] Failed to start initial service")
                    return False
                
                await asyncio.sleep(5)  # Wait for service to stabilize
            
            self.running = True
            
            # Start monitoring loop
            await self.monitor_loop()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [AUTO-RESTART] Error starting monitor: {e}")
            return False
    
    async def stop_monitoring(self):
        """Stop the auto-restart monitor"""
        logger.info("🛑 [AUTO-RESTART] Stopping monitoring...")
        self.running = False
        
        # Show final statistics
        uptime = (datetime.now() - self.start_time).total_seconds()
        logger.info(f"📊 [AUTO-RESTART] Final statistics:")
        logger.info(f"   Uptime: {uptime:.0f}s")
        logger.info(f"   Healthy checks: {self.healthy_checks}")
        logger.info(f"   Unhealthy checks: {self.unhealthy_checks}")
        logger.info(f"   Restart attempts: {self.restart_attempts}")


# Global monitor instance
monitor = DeepZoomAutoRestartMonitor()


async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepZoom Service Auto-Restart Monitor")
    parser.add_argument("--interval", type=int, default=30, 
                       help="Health check interval in seconds (default: 30)")
    parser.add_argument("--max-attempts", type=int, default=5,
                       help="Maximum restart attempts (default: 5)")
    parser.add_argument("--cooldown", type=int, default=60,
                       help="Cooldown between restart attempts in seconds (default: 60)")
    
    args = parser.parse_args()
    
    # Configure monitor settings
    monitor.check_interval = args.interval
    monitor.max_restart_attempts = args.max_attempts
    monitor.restart_cooldown = args.cooldown
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    logger.info(f"🚀 [AUTO-RESTART] DeepZoom Auto-Restart Monitor")
    logger.info(f"   Check interval: {args.interval}s")
    logger.info(f"   Max restart attempts: {args.max_attempts}")
    logger.info(f"   Restart cooldown: {args.cooldown}s")
    
    # Start monitoring
    try:
        success = await monitor.start_monitoring()
        if not success:
            return 1
        return 0
        
    except KeyboardInterrupt:
        logger.info("🛑 [AUTO-RESTART] Interrupted by user")
        await monitor.stop_monitoring()
        return 0
    except Exception as e:
        logger.error(f"❌ [AUTO-RESTART] Unexpected error: {e}")
        return 1


def signal_handler(signum, frame):
    """Handle interrupt signals"""
    logger.info("🛑 [AUTO-RESTART] Interrupt received, stopping monitor...")
    if monitor.running:
        asyncio.create_task(monitor.stop_monitoring())
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
        logger.info("🛑 [AUTO-RESTART] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ [AUTO-RESTART] Unexpected error: {e}")
        sys.exit(1)