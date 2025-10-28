#!/usr/bin/env python3
"""
Script di avvio ottimizzato per FastZoom in modalità produzione.
Configura uvicorn con multi-worker per supportare 15-20 richieste concorrenti.
"""

import os
import sys
import signal
import multiprocessing
from loguru import logger
import uvicorn
from app.core.config import get_settings

class ProductionServer:
    """Gestore del server di produzione con graceful shutdown"""
    
    def __init__(self):
        self.settings = get_settings()
        self.worker_count = self._calculate_optimal_workers()
        self.server = None
        
    def _calculate_optimal_workers(self):
        """
        Calcola il numero ottimale di worker basandosi sul numero di CPU cores.
        Formula raccomandata: (2 * CPU_CORES) + 1 per I/O bound applications
        """
        cpu_count = multiprocessing.cpu_count()
        # Per applicazioni I/O bound come FastAPI, usiamo (2 * CPU_CORES) + 1
        # Ma limitiamo a un massimo ragionevole per evitare esaurimento risorse
        optimal_workers = min((2 * cpu_count) + 1, 8)  # Max 8 workers per evitare problemi
        
        logger.info(f"CPU cores detected: {cpu_count}")
        logger.info(f"Optimal worker count calculated: {optimal_workers}")
        logger.info(f"Target: Support 15-20 concurrent requests as per FASTZOOM_CONCURRENCY_ANALYSIS_REPORT.md")
        
        return optimal_workers
    
    def _get_config(self):
        """Restituisce la configurazione ottimizzata per produzione"""
        config = {
            "app": "app.app:app",
            "host": "0.0.0.0",  # Ascolta su tutte le interfacce di rete
            "port": int(os.getenv("PORT", 8000)),
            "workers": self.worker_count,
            "worker_class": "uvicorn.workers.UvicornWorker",
            "worker_connections": 1000,  # Connessioni per worker
            "max_requests": 1000,       # Riavvia worker dopo N richieste (previene memory leak)
            "max_requests_jitter": 100,  # Aggiunge variazione casuale per evitare riavvii simultanei
            "timeout": 60,              # Timeout per le richieste
            "timeout_keep_alive": 30,   # Timeout keep-alive
            "preload": True,            # Pre-carica l'applicazione prima di forkare i worker
            "access_log": True,         # Abilita log di accesso
            "log_level": os.getenv("LOG_LEVEL", "info").lower(),
            "loop": "uvloop",           # Event loop ad alte prestazioni
            "http": "httptools"         # HTTP parser ad alte prestazioni
        }
        
        # In ambiente Windows, usiamo una configurazione compatibile
        if os.name == 'nt':  # Windows
            logger.warning("Windows detected: using single worker mode for compatibility")
            config["workers"] = 1
            config["reload"] = False
            config["loop"] = "asyncio"  # uvloop non è completamente supportato su Windows
        
        return config
    
    def setup_signal_handlers(self):
        """Configura i gestori di segnali per graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            if self.server:
                self.server.should_exit = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if hasattr(signal, 'SIGHUP'):  # Unix-only
            signal.signal(signal.SIGHUP, signal_handler)
    
    def start(self):
        """Avvia il server di produzione"""
        try:
            # Imposta la variabile d'ambiente per produzione
            os.environ["FASTZOOM_ENV"] = "production"
            
            logger.info("🚀 Starting FastZoom Production Server")
            logger.info(f"📊 Worker count: {self.worker_count}")
            logger.info(f"🌐 Host: 0.0.0.0:{os.getenv('PORT', 8000)}")
            logger.info(f"🔧 Database pool size: {self.settings.db_pool_size}")
            logger.info(f"🔧 Database max overflow: {self.settings.db_max_overflow}")
            
            # Configura i gestori di segnali
            self.setup_signal_handlers()
            
            # Ottieni la configurazione
            config = self._get_config()
            
            logger.info("✅ Server configuration complete, starting...")
            
            # Su Windows, usa il metodo diretto per evitare problemi con multi-worker
            if os.name == 'nt':  # Windows
                logger.info("🪟 Starting server with single worker on Windows...")
                
                # Costruisci i parametri dinamicamente basandosi sulla disponibilità delle dipendenze
                run_params = {
                    "app": config["app"],
                    "host": config["host"],
                    "port": config["port"],
                    "loop": config["loop"],
                    "log_level": config["log_level"],
                    "access_log": config["access_log"],
                    "timeout_keep_alive": config["timeout_keep_alive"]
                }
                
                # Aggiungi http parser solo se disponibile
                try:
                    import httptools
                    run_params["http"] = config["http"]
                    logger.info("✅ Using httptools for HTTP parsing")
                except ImportError:
                    logger.warning("⚠️ httptools not available, using standard HTTP parser")
                
                uvicorn.run(**run_params)
            else:
                # Su Unix, usa la configurazione completa con multi-worker
                self.server = uvicorn.Server(config)
                self.server.run()
            
        except KeyboardInterrupt:
            logger.info("🛑 Received keyboard interrupt, shutting down...")
        except Exception as e:
            logger.error(f"❌ Server error: {e}")
            sys.exit(1)
        finally:
            logger.info("🏁 FastZoom Production Server stopped")

def main():
    """Funzione principale per l'avvio del server di produzione"""
    # Verifica che le dipendenze siano installate in base alla piattaforma
    if os.name != 'nt':  # Non Windows (Linux/macOS)
        try:
            import uvloop
            import httptools
            logger.info("✅ uvloop and httptools available for high performance")
        except ImportError as e:
            logger.warning(f"Optional production dependency not available: {e}")
            logger.warning("For optimal performance on Unix systems, install with: pip install uvloop httptools")
            logger.warning("Continuing with standard asyncio event loop...")
    else:  # Windows
        logger.info("🪟 Windows detected: using standard asyncio event loop (uvloop not supported)")
        try:
            import httptools
            logger.info("✅ httptools available for HTTP parsing")
        except ImportError:
            logger.warning("httptools not available, using standard HTTP parser")
            logger.warning("For better performance, install with: pip install httptools")
    
    # Crea e avvia il server
    server = ProductionServer()
    server.start()

if __name__ == "__main__":
    main()