import sys
import os
import multiprocessing
import asyncio
from loguru import logger
import uvicorn
from app.core.config import get_settings

# Configure logging to preserve both Uvicorn access logs and enhanced Loguru formatting
import logging

# First, configure standard logging for Uvicorn access logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Then configure Loguru for enhanced application logging
logger.remove()  # Remove only Loguru's default handler
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG",  # Show all levels including DEBUG
    colorize=True
)

# Ensure Uvicorn access logger is properly configured
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.setLevel(logging.INFO)
uvicorn_access_logger.propagate = True

def get_worker_count():
    """
    Calcola il numero ottimale di worker basandosi sul numero di CPU cores.
    Formula raccomandata: (2 * CPU_CORES) + 1 per I/O bound applications
    """
    cpu_count = multiprocessing.cpu_count()
    # Per applicazioni I/O bound come FastAPI, usiamo (2 * CPU_CORES) + 1
    # Ma limitiamo a un massimo ragionevole per evitare esaurimento risorse
    optimal_workers = min((2 * cpu_count) + 1, 8)  # Max 8 workers per evitare problemi
    return optimal_workers

async def ensure_deepzoom_services():
    """Ensure DeepZoom services are started before main application starts"""
    try:
        logger.info("🚀 Checking DeepZoom background services...")
        
        # Import the service
        from app.services.deep_zoom_background_service import deep_zoom_background_service
        
        # Check if already running
        if not deep_zoom_background_service._running:
            logger.info("🔄 Starting DeepZoom background processor...")
            await deep_zoom_background_service.start_background_processor()
            
            # Verify status
            queue_status = await deep_zoom_background_service.get_queue_status()
            logger.info(f"📊 DeepZoom service status: {queue_status}")
            logger.info("✅ DeepZoom background processor started successfully")
        else:
            logger.info("ℹ️ DeepZoom background processor already running")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to start DeepZoom services: {e}")
        # Don't raise exception to prevent app startup failure
        # Log the error but continue with application startup
        logger.warning("⚠️ Continuing with application startup despite DeepZoom service failure")
        return False

def run_development():
    """Esegue uvicorn in modalità sviluppo con reload"""
    logger.info("Starting uvicorn in development mode with reload")
    
    # Pre-start DeepZoom services for development mode
    try:
        # Run the async function in the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ensure_deepzoom_services())
        loop.close()
    except Exception as e:
        logger.warning(f"Could not pre-start DeepZoom services in development mode: {e}")
    
    uvicorn.run(
        "app.app:app",
        host="127.0.0.1",
        reload=True,
        port=8000,
        log_level="debug",
        access_log=True  # Explicitly enable access logging in development mode
    )

async def pre_start_production_services():
    """Pre-start services in production mode before uvicorn starts"""
    try:
        logger.info("🔧 Pre-starting DeepZoom services for production mode...")
        success = await ensure_deepzoom_services()
        if success:
            logger.info("✅ Production services pre-start completed successfully")
        else:
            logger.warning("⚠️ Some production services failed to pre-start")
    except Exception as e:
        logger.error(f"❌ Production services pre-start failed: {e}")

def run_production():
    """Esegue uvicorn in modalità produzione con multi-worker"""
    settings = get_settings()
    worker_count = get_worker_count()
    
    logger.info(f"Starting uvicorn in production mode with {worker_count} workers")
    logger.info(f"Target: Support 15-20 concurrent requests as per FASTZOOM_CONCURRENCY_ANALYSIS_REPORT.md")
    
    # Pre-start DeepZoom services for production mode
    try:
        # Run the async function in the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(pre_start_production_services())
        loop.close()
    except Exception as e:
        logger.warning(f"Could not pre-start production services: {e}")
    
    # Configurazione ottimizzata per produzione
    config = {
        "app": "app.app:app",
        "host": "0.0.0.0",  # Ascolta su tutte le interfacce di rete
        "port": 8000,
        "workers": worker_count,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "worker_connections": 1000,  # Connessioni per worker
        "max_requests": 1000,       # Riavvia worker dopo N richieste (previene memory leak)
        "max_requests_jitter": 100,  # Aggiunge variazione casuale per evitare riavvii simultanei
        "timeout": 60,              # Timeout per le richieste
        "timeout_keep_alive": 30,   # Timeout keep-alive
        "preload": True,            # Pre-carica l'applicazione prima di forkare i worker
        "access_log": True,         # Abilita log di accesso
        "log_level": "debug",
        "loop": "uvloop",           # Event loop ad alte prestazioni
        "http": "httptools"         # HTTP parser ad alte prestazioni
    }
    
    # In ambiente Windows, usiamo una configurazione compatibile
    if os.name == 'nt':  # Windows
        logger.warning("Windows detected: using single worker mode for compatibility")
        config["workers"] = 1
        config["reload"] = False
        config["loop"] = "asyncio"  # uvloop non è completamente supportato su Windows
    
    uvicorn.run(**config)

if __name__ == "__main__":
    # Determina la modalità di esecuzione basandosi sulla variabile d'ambiente
    environment = os.getenv("FASTZOOM_ENV", "development").lower()
    
    logger.info(f"🚀 Starting FastZoom application in {environment} mode")
    logger.info("📋 DeepZoom background processor will be automatically started")
    
    if environment == "production":
        run_production()
    else:
        run_development()
