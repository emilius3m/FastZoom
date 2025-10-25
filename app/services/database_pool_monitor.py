import logging
import time
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import Pool
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class DatabasePoolMonitor:
    """
    Servizio di monitoring per il connection pool del database.
    Traccia l'utilizzo del pool e fornisce metriche in tempo reale.
    """
    
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.settings = get_settings()
        self.last_check_time = time.time()
        self.pool_stats_history = []
        
    def get_pool_status(self) -> Dict[str, Any]:
        """
        Ottiene lo stato attuale del connection pool.
        
        Returns:
            Dict con metriche del pool
        """
        try:
            pool = self.engine.pool
            
            # Metriche base del pool
            status = {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid() if hasattr(pool, 'invalid') else 0,
                
                # Configurazione del pool
                "configured_pool_size": self.settings.db_pool_size,
                "configured_max_overflow": self.settings.db_max_overflow,
                "configured_timeout": self.settings.db_pool_timeout,
                "configured_recycle": self.settings.db_pool_recycle,
                "configured_pre_ping": self.settings.db_pool_pre_ping,
                
                # Metriche calcolate
                "utilization_percentage": self._calculate_utilization(pool),
                "available_connections": self._calculate_available(pool),
                "total_capacity": self.settings.db_pool_size + self.settings.db_max_overflow,
                
                # Timestamp
                "timestamp": time.time(),
                "check_interval": time.time() - self.last_check_time
            }
            
            # Aggiorna timestamp
            self.last_check_time = time.time()
            
            # Salva nella storia per analisi trend
            self.pool_stats_history.append(status)
            
            # Mantiene solo le ultime 100 misurazioni
            if len(self.pool_stats_history) > 100:
                self.pool_stats_history.pop(0)
            
            return status
            
        except Exception as e:
            logger.error(f"Errore nel monitoraggio del pool: {e}")
            return {
                "error": str(e),
                "timestamp": time.time()
            }
    
    def _calculate_utilization(self, pool: Pool) -> float:
        """
        Calcola la percentuale di utilizzo del pool.
        
        Args:
            pool: SQLAlchemy pool instance
            
        Returns:
            Percentuale di utilizzo (0-100)
        """
        try:
            total_capacity = self.settings.db_pool_size + self.settings.db_max_overflow
            if total_capacity == 0:
                return 0.0
            
            used_connections = pool.checkedout()
            utilization = (used_connections / total_capacity) * 100
            
            return round(utilization, 2)
        except Exception:
            return 0.0
    
    def _calculate_available(self, pool: Pool) -> int:
        """
        Calcola le connessioni disponibili.
        
        Args:
            pool: SQLAlchemy pool instance
            
        Returns:
            Numero di connessioni disponibili
        """
        try:
            total_capacity = self.settings.db_pool_size + self.settings.db_max_overflow
            used_connections = pool.checkedout()
            available = total_capacity - used_connections
            
            return max(0, available)
        except Exception:
            return 0
    
    def get_pool_health_status(self) -> Dict[str, Any]:
        """
        Valuta lo stato di salute del pool.
        
        Returns:
            Dict con stato di salute e raccomandazioni
        """
        try:
            status = self.get_pool_status()
            
            # Valutazione soglie critiche
            utilization = status.get("utilization_percentage", 0)
            available = status.get("available_connections", 0)
            overflow = status.get("overflow", 0)
            
            health = {
                "status": "healthy",
                "warnings": [],
                "recommendations": [],
                "critical_issues": []
            }
            
            # Controlli di salute
            if utilization > 90:
                health["status"] = "critical"
                health["critical_issues"].append(
                    f"Utilizzo pool critico: {utilization}%"
                )
                health["recommendations"].append(
                    "Aumentare db_pool_size o db_max_overflow"
                )
            elif utilization > 75:
                health["status"] = "warning"
                health["warnings"].append(
                    f"Alto utilizzo pool: {utilization}%"
                )
                health["recommendations"].append(
                    "Monitorare attentamente il carico"
                )
            
            if available < 5:
                health["warnings"].append(
                    f"Pochissime connessioni disponibili: {available}"
                )
            
            if overflow > 0:
                health["warnings"].append(
                    f"Overflow attivo: {overflow} connessioni extra"
                )
                health["recommendations"].append(
                    "Considerare aumento del pool_size"
                )
            
            # Aggiungi metriche complete
            health.update(status)
            
            return health
            
        except Exception as e:
            logger.error(f"Errore valutazione salute pool: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time()
            }
    
    def get_trend_analysis(self) -> Dict[str, Any]:
        """
        Analizza i trend del pool basati sulla storia.
        
        Returns:
            Dict con analisi trend
        """
        try:
            if len(self.pool_stats_history) < 2:
                return {
                    "status": "insufficient_data",
                    "message": "Servono almeno 2 misurazioni per analizzare i trend"
                }
            
            recent = self.pool_stats_history[-10:]  # Ultime 10 misurazioni
            
            # Calcola trend utilizzo
            utilizations = [s.get("utilization_percentage", 0) for s in recent]
            avg_utilization = sum(utilizations) / len(utilizations)
            max_utilization = max(utilizations)
            
            # Trend crescita
            if len(utilizations) >= 2:
                trend = utilizations[-1] - utilizations[0]
                trend_direction = "increasing" if trend > 0 else "decreasing" if trend < 0 else "stable"
            else:
                trend = 0
                trend_direction = "unknown"
            
            analysis = {
                "period_samples": len(recent),
                "avg_utilization": round(avg_utilization, 2),
                "max_utilization": max_utilization,
                "trend_value": round(trend, 2),
                "trend_direction": trend_direction,
                
                # Raccomandazioni basate su trend
                "recommendations": []
            }
            
            # Genera raccomandazioni
            if avg_utilization > 80:
                analysis["recommendations"].append(
                    "Utilizzo medio elevato - considerare aumento pool"
                )
            
            if trend_direction == "increasing" and trend > 10:
                analysis["recommendations"].append(
                    "Trend crescita rapida - monitorare attentamente"
                )
            
            if max_utilization > 95:
                analysis["recommendations"].append(
                    "Picco utilizzo critico - aumentare capacità immediatamente"
                )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Errore analisi trend: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def log_pool_status(self):
        """
        Logga lo stato attuale del pool a intervalli regolari.
        """
        try:
            health = self.get_pool_health_status()
            status = health.get("status", "unknown")
            utilization = health.get("utilization_percentage", 0)
            available = health.get("available_connections", 0)
            
            if status == "critical":
                logger.critical(
                    f"POOL CRITICO - Utilizzo: {utilization}%, "
                    f"Disponibili: {available}, "
                    f"Overflow: {health.get('overflow', 0)}"
                )
            elif status == "warning":
                logger.warning(
                    f"POOL WARNING - Utilizzo: {utilization}%, "
                    f"Disponibili: {available}"
                )
            else:
                logger.info(
                    f"Pool OK - Utilizzo: {utilization}%, "
                    f"Disponibili: {available}/{health.get('total_capacity', 0)}"
                )
                
        except Exception as e:
            logger.error(f"Errore logging pool status: {e}")

# Istanza globale del monitor
_pool_monitor: Optional[DatabasePoolMonitor] = None

def get_pool_monitor() -> Optional[DatabasePoolMonitor]:
    """
    Ottiene l'istanza del pool monitor.
    
    Returns:
        DatabasePoolMonitor instance or None
    """
    return _pool_monitor

def initialize_pool_monitor(engine: AsyncEngine) -> DatabasePoolMonitor:
    """
    Inizializza il pool monitor globale.
    
    Args:
        engine: AsyncEngine instance
        
    Returns:
        DatabasePoolMonitor instance
    """
    global _pool_monitor
    _pool_monitor = DatabasePoolMonitor(engine)
    logger.info("Database Pool Monitor inizializzato")
    return _pool_monitor