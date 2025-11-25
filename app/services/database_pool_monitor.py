import time
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import Pool
from loguru import logger
from app.core.config import get_settings

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
        
    @logger.catch(
        reraise=True,
        message="Failed to get pool status",
        level="ERROR"
    )
    def get_pool_status(self) -> Dict[str, Any]:
        """
        Ottiene lo stato attuale del connection pool.
        
        Returns:
            Dict con metriche del pool
        """
        with logger.contextualize(
            operation="get_pool_status",
            monitor_type="database_pool"
        ):
            try:
                logger.debug(
                    "Getting pool status metrics",
                    extra={
                        "last_check_time": self.last_check_time,
                        "history_length": len(self.pool_stats_history)
                    }
                )
                
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
                
                logger.debug(
                    "Pool status retrieved successfully",
                    extra={
                        "pool_size": status["pool_size"],
                        "checked_out": status["checked_out"],
                        "utilization_percentage": status["utilization_percentage"],
                        "available_connections": status["available_connections"],
                        "history_length": len(self.pool_stats_history)
                    }
                )
                
                return status
                
            except Exception as e:
                logger.error(
                    "Error monitoring pool status",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "pool_type": type(self.engine.pool).__name__ if self.engine.pool else None
                    },
                    exc_info=True
                )
                return {
                    "error": str(e),
                    "timestamp": time.time()
                }
    
    @logger.catch(
        reraise=True,
        message="Failed to calculate pool utilization",
        level="ERROR"
    )
    def _calculate_utilization(self, pool: Pool) -> float:
        """
        Calcola la percentuale di utilizzo del pool.
        
        Args:
            pool: SQLAlchemy pool instance
            
        Returns:
            Percentuale di utilizzo (0-100)
        """
        with logger.contextualize(
            operation="calculate_utilization",
            pool_type=type(pool).__name__
        ):
            try:
                total_capacity = self.settings.db_pool_size + self.settings.db_max_overflow
                if total_capacity == 0:
                    logger.warning(
                        "Total capacity is zero, cannot calculate utilization",
                        extra={
                            "db_pool_size": self.settings.db_pool_size,
                            "db_max_overflow": self.settings.db_max_overflow,
                            "total_capacity": total_capacity
                        }
                    )
                    return 0.0
                
                used_connections = pool.checkedout()
                utilization = (used_connections / total_capacity) * 100
                
                logger.debug(
                    "Pool utilization calculated",
                    extra={
                        "used_connections": used_connections,
                        "total_capacity": total_capacity,
                        "utilization_percentage": round(utilization, 2)
                    }
                )
                
                return round(utilization, 2)
            except Exception as e:
                logger.error(
                    "Error calculating pool utilization",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "db_pool_size": self.settings.db_pool_size,
                        "db_max_overflow": self.settings.db_max_overflow
                    },
                    exc_info=True
                )
                return 0.0
    
    @logger.catch(
        reraise=True,
        message="Failed to calculate available connections",
        level="ERROR"
    )
    def _calculate_available(self, pool: Pool) -> int:
        """
        Calcola le connessioni disponibili.
        
        Args:
            pool: SQLAlchemy pool instance
            
        Returns:
            Numero di connessioni disponibili
        """
        with logger.contextualize(
            operation="calculate_available",
            pool_type=type(pool).__name__
        ):
            try:
                total_capacity = self.settings.db_pool_size + self.settings.db_max_overflow
                used_connections = pool.checkedout()
                available = total_capacity - used_connections
                
                available_connections = max(0, available)
                
                logger.debug(
                    "Available connections calculated",
                    extra={
                        "total_capacity": total_capacity,
                        "used_connections": used_connections,
                        "available_connections": available_connections
                    }
                )
                
                return available_connections
            except Exception as e:
                logger.error(
                    "Error calculating available connections",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "db_pool_size": self.settings.db_pool_size,
                        "db_max_overflow": self.settings.db_max_overflow
                    },
                    exc_info=True
                )
                return 0
    
    @logger.catch(
        reraise=True,
        message="Failed to get pool health status",
        level="ERROR"
    )
    def get_pool_health_status(self) -> Dict[str, Any]:
        """
        Valuta lo stato di salute del pool.
        
        Returns:
            Dict con stato di salute e raccomandazioni
        """
        with logger.contextualize(
            operation="get_pool_health_status",
            monitor_type="database_pool"
        ):
            try:
                logger.debug("Evaluating pool health status")
                
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
                    critical_issue = f"Utilizzo pool critico: {utilization}%"
                    health["critical_issues"].append(critical_issue)
                    health["recommendations"].append(
                        "Aumentare db_pool_size o db_max_overflow"
                    )
                    
                    logger.critical(
                        "Critical pool utilization detected",
                        extra={
                            "utilization_percentage": utilization,
                            "critical_issue": critical_issue,
                            "available_connections": available,
                            "overflow": overflow
                        }
                    )
                elif utilization > 75:
                    health["status"] = "warning"
                    warning = f"Alto utilizzo pool: {utilization}%"
                    health["warnings"].append(warning)
                    health["recommendations"].append(
                        "Monitorare attentamente il carico"
                    )
                    
                    logger.warning(
                        "High pool utilization detected",
                        extra={
                            "utilization_percentage": utilization,
                            "warning": warning,
                            "available_connections": available
                        }
                    )
                
                if available < 5:
                    warning = f"Pochissime connessioni disponibili: {available}"
                    health["warnings"].append(warning)
                    
                    logger.warning(
                        "Low available connections",
                        extra={
                            "available_connections": available,
                            "warning": warning,
                            "utilization_percentage": utilization
                        }
                    )
                
                if overflow > 0:
                    warning = f"Overflow attivo: {overflow} connessioni extra"
                    health["warnings"].append(warning)
                    health["recommendations"].append(
                        "Considerare aumento del pool_size"
                    )
                    
                    logger.info(
                        "Pool overflow active",
                        extra={
                            "overflow_connections": overflow,
                            "warning": warning,
                            "utilization_percentage": utilization
                        }
                    )
                
                # Aggiungi metriche complete
                health.update(status)
                
                logger.info(
                    "Pool health status evaluated",
                    extra={
                        "health_status": health["status"],
                        "utilization_percentage": utilization,
                        "available_connections": available,
                        "warnings_count": len(health["warnings"]),
                        "critical_issues_count": len(health["critical_issues"]),
                        "recommendations_count": len(health["recommendations"])
                    }
                )
                
                return health
                
            except Exception as e:
                logger.error(
                    "Error evaluating pool health status",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                return {
                    "status": "error",
                    "error": str(e),
                    "timestamp": time.time()
                }
    
    @logger.catch(
        reraise=True,
        message="Failed to get trend analysis",
        level="ERROR"
    )
    def get_trend_analysis(self) -> Dict[str, Any]:
        """
        Analizza i trend del pool basati sulla storia.
        
        Returns:
            Dict con analisi trend
        """
        with logger.contextualize(
            operation="get_trend_analysis",
            monitor_type="database_pool",
            history_length=len(self.pool_stats_history)
        ):
            try:
                logger.debug(
                    "Analyzing pool trends",
                    extra={
                        "history_length": len(self.pool_stats_history),
                        "required_minimum": 2
                    }
                )
                
                if len(self.pool_stats_history) < 2:
                    logger.warning(
                        "Insufficient data for trend analysis",
                        extra={
                            "current_history_length": len(self.pool_stats_history),
                            "required_minimum": 2
                        }
                    )
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
                    recommendation = "Utilizzo medio elevato - considerare aumento pool"
                    analysis["recommendations"].append(recommendation)
                    
                    logger.warning(
                        "High average utilization detected",
                        extra={
                            "avg_utilization": avg_utilization,
                            "recommendation": recommendation,
                            "threshold": 80
                        }
                    )
                
                if trend_direction == "increasing" and trend > 10:
                    recommendation = "Trend crescita rapida - monitorare attentamente"
                    analysis["recommendations"].append(recommendation)
                    
                    logger.warning(
                        "Rapid increasing trend detected",
                        extra={
                            "trend_value": trend,
                            "trend_direction": trend_direction,
                            "recommendation": recommendation,
                            "threshold": 10
                        }
                    )
                
                if max_utilization > 95:
                    recommendation = "Picco utilizzo critico - aumentare capacità immediatamente"
                    analysis["recommendations"].append(recommendation)
                    
                    logger.critical(
                        "Critical peak utilization detected",
                        extra={
                            "max_utilization": max_utilization,
                            "recommendation": recommendation,
                            "threshold": 95
                        }
                    )
                
                logger.info(
                    "Pool trend analysis completed",
                    extra={
                        "period_samples": len(recent),
                        "avg_utilization": analysis["avg_utilization"],
                        "max_utilization": analysis["max_utilization"],
                        "trend_direction": analysis["trend_direction"],
                        "trend_value": analysis["trend_value"],
                        "recommendations_count": len(analysis["recommendations"])
                    }
                )
                
                return analysis
                
            except Exception as e:
                logger.error(
                    "Error analyzing pool trends",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "history_length": len(self.pool_stats_history)
                    },
                    exc_info=True
                )
                return {
                    "status": "error",
                    "error": str(e)
                }
    
    @logger.catch(
        reraise=True,
        message="Failed to log pool status",
        level="ERROR"
    )
    def log_pool_status(self):
        """
        Logga lo stato attuale del pool a intervalli regolari.
        """
        with logger.contextualize(
            operation="log_pool_status",
            monitor_type="database_pool"
        ):
            try:
                logger.debug("Logging current pool status")
                
                health = self.get_pool_health_status()
                status = health.get("status", "unknown")
                utilization = health.get("utilization_percentage", 0)
                available = health.get("available_connections", 0)
                overflow = health.get("overflow", 0)
                total_capacity = health.get("total_capacity", 0)
                
                log_extra = {
                    "pool_status": status,
                    "utilization_percentage": utilization,
                    "available_connections": available,
                    "overflow_connections": overflow,
                    "total_capacity": total_capacity,
                    "warnings_count": len(health.get("warnings", [])),
                    "critical_issues_count": len(health.get("critical_issues", []))
                }
                
                if status == "critical":
                    logger.critical(
                        "POOL CRITICAL - High utilization detected",
                        extra={
                            **log_extra,
                            "message": f"POOL CRITICO - Utilizzo: {utilization}%, Disponibili: {available}, Overflow: {overflow}"
                        }
                    )
                elif status == "warning":
                    logger.warning(
                        "POOL WARNING - High utilization or low connections",
                        extra={
                            **log_extra,
                            "message": f"POOL WARNING - Utilizzo: {utilization}%, Disponibili: {available}"
                        }
                    )
                else:
                    logger.info(
                        "Pool status healthy",
                        extra={
                            **log_extra,
                            "message": f"Pool OK - Utilizzo: {utilization}%, Disponibili: {available}/{total_capacity}"
                        }
                    )
                
            except Exception as e:
                logger.error(
                    "Error logging pool status",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )

# Istanza globale del monitor
_pool_monitor: Optional[DatabasePoolMonitor] = None

def get_pool_monitor() -> Optional[DatabasePoolMonitor]:
    """
    Ottiene l'istanza del pool monitor.
    
    Returns:
        DatabasePoolMonitor instance or None
    """
    return _pool_monitor

@logger.catch(
    reraise=True,
    message="Failed to initialize pool monitor",
    level="ERROR"
)
def initialize_pool_monitor(engine: AsyncEngine) -> DatabasePoolMonitor:
    """
    Inizializza il pool monitor globale.
    
    Args:
        engine: AsyncEngine instance
        
    Returns:
        DatabasePoolMonitor instance
    """
    with logger.contextualize(
        operation="initialize_pool_monitor",
        engine_type=type(engine).__name__,
        pool_type=type(engine.pool).__name__ if engine.pool else None
    ):
        try:
            global _pool_monitor
            _pool_monitor = DatabasePoolMonitor(engine)
            
            logger.success(
                "Database Pool Monitor initialized successfully",
                extra={
                    "engine_type": type(engine).__name__,
                    "pool_type": type(engine.pool).__name__ if engine.pool else None,
                    "db_pool_size": _pool_monitor.settings.db_pool_size,
                    "db_max_overflow": _pool_monitor.settings.db_max_overflow,
                    "monitor_instance": _pool_monitor is not None
                }
            )
            
            return _pool_monitor
            
        except Exception as e:
            logger.error(
                "Error initializing pool monitor",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "engine_type": type(engine).__name__
                },
                exc_info=True
            )
            raise