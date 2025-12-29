# app/services/performance_monitoring_service.py - Centralized Performance Monitoring Service

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger
import psutil
import statistics

from app.core.config import get_settings
from app.services.database_pool_monitor import get_pool_monitor
from app.services.request_queue_service import request_queue_service
from app.services.deep_zoom_background_service import deep_zoom_background_service

settings = get_settings()


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class MetricType(Enum):
    """Types of performance metrics"""
    UPLOAD_TIME = "upload_time"
    CONCURRENT_REQUESTS = "concurrent_requests"
    SYSTEM_RESOURCES = "system_resources"
    DATABASE_POOL = "database_pool"
    QUEUE_PERFORMANCE = "queue_performance"
    DEEP_ZOOM_PROCESSING = "deep_zoom_processing"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"


@dataclass
class PerformanceMetric:
    """Single performance metric data point"""
    metric_type: MetricType
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAlert:
    """Performance alert definition"""
    alert_id: str
    level: AlertLevel
    metric_type: MetricType
    threshold: float
    operator: str  # ">", "<", ">=", "<=", "=="
    message: str
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    is_active: bool = True
    count: int = 1


@dataclass
class BaselineMetric:
    """Baseline metric for before/after comparison"""
    metric_type: MetricType
    baseline_value: float
    baseline_date: datetime
    description: str
    improvement_target: Optional[float] = None


class PerformanceMonitoringService:
    """Centralized performance monitoring service for FastZoom"""
    
    def __init__(self):
        self.metrics_history: List[PerformanceMetric] = []
        self.alerts: Dict[str, PerformanceAlert] = {}
        self.baselines: Dict[MetricType, BaselineMetric] = {}
        self.active_monitors = {}
        
        # Configuration
        self.max_history_size = 10000
        self.alert_check_interval = 30  # seconds
        self.metrics_retention_days = 30
        
        # Performance targets (from optimization reports)
        self.performance_targets = {
            MetricType.UPLOAD_TIME: {"target": 2.0, "unit": "seconds"},  # < 2s
            MetricType.RESPONSE_TIME: {"target": 2.0, "unit": "seconds"},  # < 2s
            MetricType.ERROR_RATE: {"target": 5.0, "unit": "percent"},  # < 5%
            MetricType.THROUGHPUT: {"target": 100.0, "unit": "req/s"},  # > 100 req/s
            MetricType.CONCURRENT_REQUESTS: {"target": 50.0, "unit": "count"},  # > 50
            MetricType.SYSTEM_RESOURCES: {"target": 80.0, "unit": "percent"},  # < 80%
        }
        
        # Background tasks
        self.monitoring_task = None
        self.alert_task = None
        self.cleanup_task = None
        self._running = False
        
        # Initialize baselines from reports
        self._initialize_baselines()
        
        # Initialize default alerts
        self._initialize_default_alerts()
    
    def _initialize_baselines(self):
        """Initialize baseline metrics from optimization reports"""
        # Baseline values from FASTZOOM_CONCURRENCY_ANALYSIS_REPORT.md
        self.baselines[MetricType.UPLOAD_TIME] = BaselineMetric(
            metric_type=MetricType.UPLOAD_TIME,
            baseline_value=12.5,  # seconds
            baseline_date=datetime(2025, 10, 24),
            description="Average upload time before optimizations",
            improvement_target=2.0  # target after optimization
        )
        
        self.baselines[MetricType.RESPONSE_TIME] = BaselineMetric(
            metric_type=MetricType.RESPONSE_TIME,
            baseline_value=12.5,  # seconds
            baseline_date=datetime(2025, 10, 24),
            description="Average response time before optimizations",
            improvement_target=2.0
        )
        
        self.baselines[MetricType.ERROR_RATE] = BaselineMetric(
            metric_type=MetricType.ERROR_RATE,
            baseline_value=65.0,  # percent (100% - 35% success rate)
            baseline_date=datetime(2025, 10, 24),
            description="Error rate before optimizations (65% failure rate)",
            improvement_target=5.0
        )
        
        self.baselines[MetricType.THROUGHPUT] = BaselineMetric(
            metric_type=MetricType.THROUGHPUT,
            baseline_value=15.0,  # req/s
            baseline_date=datetime(2025, 10, 24),
            description="Throughput before optimizations",
            improvement_target=100.0
        )
        
        self.baselines[MetricType.CONCURRENT_REQUESTS] = BaselineMetric(
            metric_type=MetricType.CONCURRENT_REQUESTS,
            baseline_value=10.0,  # count
            baseline_date=datetime(2025, 10, 24),
            description="Concurrent requests supported before optimizations",
            improvement_target=50.0
        )
    
    def _initialize_default_alerts(self):
        """Initialize default performance alerts"""
        default_alerts = [
            {
                "id": "high_upload_time",
                "level": AlertLevel.WARNING,
                "metric": MetricType.UPLOAD_TIME,
                "threshold": 5.0,
                "operator": ">",
                "message": "Upload time exceeding 5 seconds"
            },
            {
                "id": "critical_upload_time",
                "level": AlertLevel.CRITICAL,
                "metric": MetricType.UPLOAD_TIME,
                "threshold": 10.0,
                "operator": ">",
                "message": "Upload time exceeding 10 seconds"
            },
            {
                "id": "high_response_time",
                "level": AlertLevel.WARNING,
                "metric": MetricType.RESPONSE_TIME,
                "threshold": 3.0,
                "operator": ">",
                "message": "Response time exceeding 3 seconds"
            },
            {
                "id": "critical_response_time",
                "level": AlertLevel.CRITICAL,
                "metric": MetricType.RESPONSE_TIME,
                "threshold": 5.0,
                "operator": ">",
                "message": "Response time exceeding 5 seconds"
            },
            {
                "id": "high_error_rate",
                "level": AlertLevel.WARNING,
                "metric": MetricType.ERROR_RATE,
                "threshold": 10.0,
                "operator": ">",
                "message": "Error rate exceeding 10%"
            },
            {
                "id": "critical_error_rate",
                "level": AlertLevel.CRITICAL,
                "metric": MetricType.ERROR_RATE,
                "threshold": 20.0,
                "operator": ">",
                "message": "Error rate exceeding 20%"
            },
            {
                "id": "low_throughput",
                "level": AlertLevel.WARNING,
                "metric": MetricType.THROUGHPUT,
                "threshold": 50.0,
                "operator": "<",
                "message": "Throughput below 50 req/s"
            },
            {
                "id": "critical_low_throughput",
                "level": AlertLevel.CRITICAL,
                "metric": MetricType.THROUGHPUT,
                "threshold": 25.0,
                "operator": "<",
                "message": "Throughput below 25 req/s"
            },
            {
                "id": "high_cpu_usage",
                "level": AlertLevel.WARNING,
                "metric": MetricType.SYSTEM_RESOURCES,
                "threshold": 75.0,
                "operator": ">",
                "message": "CPU usage exceeding 75%"
            },
            {
                "id": "critical_cpu_usage",
                "level": AlertLevel.CRITICAL,
                "metric": MetricType.SYSTEM_RESOURCES,
                "threshold": 90.0,
                "operator": ">",
                "message": "CPU usage exceeding 90%"
            },
            {
                "id": "high_memory_usage",
                "level": AlertLevel.WARNING,
                "metric": MetricType.SYSTEM_RESOURCES,
                "threshold": 80.0,
                "operator": ">",
                "message": "Memory usage exceeding 80%"
            },
            {
                "id": "critical_memory_usage",
                "level": AlertLevel.CRITICAL,
                "metric": MetricType.SYSTEM_RESOURCES,
                "threshold": 95.0,
                "operator": ">",
                "message": "Memory usage exceeding 95%"
            }
        ]
        
        for alert_config in default_alerts:
            self.create_alert(
                alert_id=alert_config["id"],
                level=alert_config["level"],
                metric_type=alert_config["metric"],
                threshold=alert_config["threshold"],
                operator=alert_config["operator"],
                message=alert_config["message"],
                _silent=True  # Don't log individual alerts
            )
        
        logger.debug(f"Initialized {len(default_alerts)} default performance alerts")
    
    async def start_monitoring(self):
        """Start the performance monitoring service"""
        if self._running:
            logger.warning("Performance monitoring service already running")
            return
        
        self._running = True
        
        # Start background tasks
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.alert_task = asyncio.create_task(self._alert_check_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.debug("Performance monitoring service started")
    
    async def stop_monitoring(self):
        """Stop the performance monitoring service"""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel background tasks
        tasks = [self.monitoring_task, self.alert_task, self.cleanup_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("🛑 Performance monitoring service stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Performance monitoring loop started")
        
        while self._running:
            try:
                # Collect metrics from all components
                await self._collect_all_metrics()
                
                # Sleep before next collection
                await asyncio.sleep(10)  # Collect every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause on error
        
        logger.info("Performance monitoring loop stopped")
    
    async def _alert_check_loop(self):
        """Alert checking loop"""
        logger.info("Alert checking loop started")
        
        while self._running:
            try:
                # Check all active alerts
                await self._check_alerts()
                
                # Sleep before next check
                await asyncio.sleep(self.alert_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert check loop: {e}")
                await asyncio.sleep(10)  # Brief pause on error
        
        logger.info("Alert checking loop stopped")
    
    async def _cleanup_loop(self):
        """Cleanup old metrics and resolved alerts"""
        logger.info("Cleanup loop started")
        
        while self._running:
            try:
                # Clean old metrics
                cutoff_time = datetime.now() - timedelta(days=self.metrics_retention_days)
                self.metrics_history = [
                    m for m in self.metrics_history 
                    if m.timestamp > cutoff_time
                ]
                
                # Limit history size
                if len(self.metrics_history) > self.max_history_size:
                    self.metrics_history = self.metrics_history[-self.max_history_size:]
                
                # Clean old resolved alerts
                alert_cutoff = datetime.now() - timedelta(days=7)
                resolved_alerts_to_remove = [
                    alert_id for alert_id, alert in self.alerts.items()
                    if not alert.is_active and alert.resolved_at and alert.resolved_at < alert_cutoff
                ]
                
                for alert_id in resolved_alerts_to_remove:
                    del self.alerts[alert_id]
                
                # Sleep for an hour before next cleanup
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(300)  # 5 minutes pause on error
        
        logger.info("Cleanup loop stopped")
    
    async def _collect_all_metrics(self):
        """Collect metrics from all system components"""
        try:
            # System resources
            await self._collect_system_metrics()
            
            # Database pool metrics
            await self._collect_database_metrics()
            
            # Queue metrics
            await self._collect_queue_metrics()
            
            # Deep zoom processing metrics
            await self._collect_deep_zoom_metrics()
            
            # Application performance metrics
            await self._collect_application_metrics()
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    async def _collect_system_metrics(self):
        """Collect system resource metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.record_metric(
                metric_type=MetricType.SYSTEM_RESOURCES,
                value=cpu_percent,
                unit="percent",
                tags={"resource": "cpu"}
            )
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.record_metric(
                metric_type=MetricType.SYSTEM_RESOURCES,
                value=memory.percent,
                unit="percent",
                tags={"resource": "memory"}
            )
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            self.record_metric(
                metric_type=MetricType.SYSTEM_RESOURCES,
                value=disk_percent,
                unit="percent",
                tags={"resource": "disk"}
            )
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    async def _collect_database_metrics(self):
        """Collect database pool metrics"""
        try:
            pool_monitor = get_pool_monitor()
            if pool_monitor:
                pool_status = pool_monitor.get_pool_status()
                
                # Pool utilization
                utilization = pool_status.get("utilization_percentage", 0)
                self.record_metric(
                    metric_type=MetricType.DATABASE_POOL,
                    value=utilization,
                    unit="percent",
                    tags={"metric": "utilization"}
                )
                
                # Available connections
                available = pool_status.get("available_connections", 0)
                self.record_metric(
                    metric_type=MetricType.DATABASE_POOL,
                    value=available,
                    unit="count",
                    tags={"metric": "available_connections"}
                )
                
                # Overflow connections
                overflow = pool_status.get("overflow", 0)
                self.record_metric(
                    metric_type=MetricType.DATABASE_POOL,
                    value=overflow,
                    unit="count",
                    tags={"metric": "overflow"}
                )
                
        except Exception as e:
            logger.error(f"Error collecting database metrics: {e}")
    
    async def _collect_queue_metrics(self):
        """Collect request queue metrics"""
        try:
            if hasattr(request_queue_service, 'get_queue_status'):
                queue_status = await request_queue_service.get_queue_status()
                
                # Active requests
                active_requests = queue_status.get("active_requests", 0)
                self.record_metric(
                    metric_type=MetricType.CONCURRENT_REQUESTS,
                    value=active_requests,
                    unit="count",
                    tags={"source": "queue"}
                )
                
                # Queue sizes by priority
                queue_sizes = queue_status.get("queue_sizes", {})
                for priority_name, size in queue_sizes.items():
                    self.record_metric(
                        metric_type=MetricType.QUEUE_PERFORMANCE,
                        value=size,
                        unit="count",
                        tags={"priority": priority_name, "metric": "queue_size"}
                    )
                
                # System load
                system_load = queue_status.get("system_load", {})
                if isinstance(system_load, dict):
                    cpu_load = system_load.get("cpu_percent", 0)
                    memory_load = system_load.get("memory_percent", 0)
                    
                    self.record_metric(
                        metric_type=MetricType.QUEUE_PERFORMANCE,
                        value=cpu_load,
                        unit="percent",
                        tags={"metric": "system_cpu_load"}
                    )
                    
                    self.record_metric(
                        metric_type=MetricType.QUEUE_PERFORMANCE,
                        value=memory_load,
                        unit="percent",
                        tags={"metric": "system_memory_load"}
                    )
                
                # Average wait time
                avg_wait_time = queue_status.get("metrics", {}).get("average_wait_time", 0)
                self.record_metric(
                    metric_type=MetricType.QUEUE_PERFORMANCE,
                    value=avg_wait_time,
                    unit="seconds",
                    tags={"metric": "average_wait_time"}
                )
                
        except Exception as e:
            logger.error(f"Error collecting queue metrics: {e}")
    
    async def _collect_deep_zoom_metrics(self):
        """Collect deep zoom processing metrics"""
        try:
            if hasattr(deep_zoom_background_service, 'get_queue_status'):
                dz_status = await deep_zoom_background_service.get_queue_status()
                
                # Queue size
                queue_size = dz_status.get("queue_size", 0)
                self.record_metric(
                    metric_type=MetricType.DEEP_ZOOM_PROCESSING,
                    value=queue_size,
                    unit="count",
                    tags={"metric": "queue_size"}
                )
                
                # Processing tasks
                processing_tasks = dz_status.get("processing_tasks", 0)
                self.record_metric(
                    metric_type=MetricType.DEEP_ZOOM_PROCESSING,
                    value=processing_tasks,
                    unit="count",
                    tags={"metric": "processing_tasks"}
                )
                
                # Completed tasks
                completed_tasks = dz_status.get("completed_tasks", 0)
                self.record_metric(
                    metric_type=MetricType.DEEP_ZOOM_PROCESSING,
                    value=completed_tasks,
                    unit="count",
                    tags={"metric": "completed_tasks"}
                )
                
                # Failed tasks
                failed_tasks = dz_status.get("failed_tasks", 0)
                self.record_metric(
                    metric_type=MetricType.DEEP_ZOOM_PROCESSING,
                    value=failed_tasks,
                    unit="count",
                    tags={"metric": "failed_tasks"}
                )
                
        except Exception as e:
            logger.error(f"Error collecting deep zoom metrics: {e}")
    
    async def _collect_application_metrics(self):
        """Collect application-level metrics"""
        try:
            # Calculate recent metrics from history
            recent_metrics = [
                m for m in self.metrics_history
                if m.timestamp > datetime.now() - timedelta(minutes=5)
            ]
            
            # Calculate error rate (simulated - would come from actual error tracking)
            total_requests = len([m for m in recent_metrics if m.metric_type == MetricType.RESPONSE_TIME])
            error_requests = len([m for m in recent_metrics if m.tags.get("status") == "error"])
            
            if total_requests > 0:
                error_rate = (error_requests / total_requests) * 100
                self.record_metric(
                    metric_type=MetricType.ERROR_RATE,
                    value=error_rate,
                    unit="percent"
                )
            
            # Calculate throughput (requests per second)
            if recent_metrics:
                time_span = (recent_metrics[-1].timestamp - recent_metrics[0].timestamp).total_seconds()
                if time_span > 0:
                    throughput = len(recent_metrics) / time_span
                    self.record_metric(
                        metric_type=MetricType.THROUGHPUT,
                        value=throughput,
                        unit="req/s"
                    )
                
        except Exception as e:
            logger.error(f"Error collecting application metrics: {e}")
    
    def record_metric(
        self,
        metric_type: MetricType,
        value: float,
        unit: str,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a performance metric"""
        metric = PerformanceMetric(
            metric_type=metric_type,
            value=value,
            unit=unit,
            tags=tags or {},
            metadata=metadata or {}
        )
        
        self.metrics_history.append(metric)
        
        # Limit history size
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history = self.metrics_history[-self.max_history_size:]
    
    def create_alert(
        self,
        alert_id: str,
        level: AlertLevel,
        metric_type: MetricType,
        threshold: float,
        operator: str,
        message: str,
        _silent: bool = False
    ) -> PerformanceAlert:
        """Create a new performance alert"""
        alert = PerformanceAlert(
            alert_id=alert_id,
            level=level,
            metric_type=metric_type,
            threshold=threshold,
            operator=operator,
            message=message
        )
        
        self.alerts[alert_id] = alert
        if not _silent:
            logger.debug(f"Created alert: {alert_id} - {message}")
        
        return alert
    
    async def _check_alerts(self):
        """Check all alerts against current metrics"""
        for alert in self.alerts.values():
            if not alert.is_active:
                continue
            
            # Get latest metric for this alert's metric type
            latest_metrics = [
                m for m in self.metrics_history
                if m.metric_type == alert.metric_type
                and m.timestamp > datetime.now() - timedelta(minutes=5)
            ]
            
            if not latest_metrics:
                continue
            
            latest_metric = latest_metrics[-1]
            current_value = latest_metric.value
            
            # Check if alert condition is met
            alert_triggered = self._evaluate_condition(
                current_value, alert.threshold, alert.operator
            )
            
            if alert_triggered:
                if alert.count == 1:  # First time triggered
                    logger.warning(
                        f"🚨 ALERT TRIGGERED: {alert.message} "
                        f"(current: {current_value}{latest_metric.unit}, "
                        f"threshold: {alert.threshold}{latest_metric.unit})"
                    )
                
                alert.count += 1
            else:
                if alert.count > 1:  # Was triggered, now resolved
                    alert.resolved_at = datetime.now()
                    alert.is_active = False
                    
                    logger.info(
                        f"✅ ALERT RESOLVED: {alert.message} "
                        f"(was: {current_value}{latest_metric.unit}, "
                        f"threshold: {alert.threshold}{latest_metric.unit})"
                    )
    
    def _evaluate_condition(self, value: float, threshold: float, operator: str) -> bool:
        """Evaluate alert condition"""
        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        else:
            return False
    
    def get_metrics_summary(
        self,
        metric_type: Optional[MetricType] = None,
        time_range: Optional[timedelta] = None
    ) -> Dict[str, Any]:
        """Get summary of metrics"""
        # Filter metrics
        filtered_metrics = self.metrics_history
        
        if metric_type:
            filtered_metrics = [m for m in filtered_metrics if m.metric_type == metric_type]
        
        if time_range:
            cutoff_time = datetime.now() - time_range
            filtered_metrics = [m for m in filtered_metrics if m.timestamp > cutoff_time]
        
        if not filtered_metrics:
            return {"error": "No metrics found for the specified criteria"}
        
        # Group by metric type and tags
        summary = {}
        for metric in filtered_metrics:
            key = f"{metric.metric_type.value}_{json.dumps(metric.tags, sort_keys=True)}"
            
            if key not in summary:
                summary[key] = {
                    "metric_type": metric.metric_type.value,
                    "tags": metric.tags,
                    "values": [],
                    "unit": metric.unit,
                    "count": 0,
                    "latest": None,
                    "min": None,
                    "max": None,
                    "avg": None,
                    "p50": None,
                    "p95": None,
                    "p99": None
                }
            
            summary[key]["values"].append(metric.value)
            summary[key]["count"] += 1
            summary[key]["latest"] = {
                "value": metric.value,
                "timestamp": metric.timestamp.isoformat()
            }
        
        # Calculate statistics
        for key, data in summary.items():
            if data["values"]:
                values = sorted(data["values"])
                data["min"] = min(values)
                data["max"] = max(values)
                data["avg"] = statistics.mean(values)
                data["p50"] = statistics.median(values)
                data["p95"] = values[int(len(values) * 0.95)] if len(values) > 20 else None
                data["p99"] = values[int(len(values) * 0.99)] if len(values) > 100 else None
                
                # Remove raw values to reduce response size
                del data["values"]
        
        return summary
    
    def get_performance_comparison(self) -> Dict[str, Any]:
        """Get performance comparison with baselines"""
        comparison = {
            "baseline_date": None,
            "current_date": datetime.now().isoformat(),
            "metrics": {}
        }
        
        for metric_type, baseline in self.baselines.items():
            # Get current metrics for this type
            current_metrics = [
                m for m in self.metrics_history
                if m.metric_type == metric_type
                and m.timestamp > datetime.now() - timedelta(hours=1)
            ]
            
            if current_metrics:
                current_value = statistics.mean([m.value for m in current_metrics])
                
                # Calculate improvement
                if baseline.baseline_value > 0:
                    if metric_type in [MetricType.UPLOAD_TIME, MetricType.RESPONSE_TIME, MetricType.ERROR_RATE]:
                        # Lower is better
                        improvement = ((baseline.baseline_value - current_value) / baseline.baseline_value) * 100
                    else:
                        # Higher is better
                        improvement = ((current_value - baseline.baseline_value) / baseline.baseline_value) * 100
                else:
                    improvement = 0
                
                comparison["metrics"][metric_type.value] = {
                    "baseline_value": baseline.baseline_value,
                    "baseline_date": baseline.baseline_date.isoformat(),
                    "current_value": current_value,
                    "improvement_percent": round(improvement, 2),
                    "improvement_target": baseline.improvement_target,
                    "target_met": current_value <= baseline.improvement_target if metric_type in [MetricType.UPLOAD_TIME, MetricType.RESPONSE_TIME, MetricType.ERROR_RATE] else current_value >= baseline.improvement_target,
                    "unit": current_metrics[0].unit,
                    "description": baseline.description
                }
                
                if not comparison["baseline_date"]:
                    comparison["baseline_date"] = baseline.baseline_date.isoformat()
        
        return comparison
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        active_alerts = []
        
        for alert in self.alerts.values():
            if alert.is_active:
                active_alerts.append({
                    "alert_id": alert.alert_id,
                    "level": alert.level.value,
                    "metric_type": alert.metric_type.value,
                    "threshold": alert.threshold,
                    "operator": alert.operator,
                    "message": alert.message,
                    "created_at": alert.created_at.isoformat(),
                    "count": alert.count
                })
        
        return active_alerts
    
    def get_system_health_score(self) -> Dict[str, Any]:
        """Calculate overall system health score"""
        try:
            # Get recent metrics
            recent_metrics = [
                m for m in self.metrics_history
                if m.timestamp > datetime.now() - timedelta(minutes=10)
            ]
            
            if not recent_metrics:
                return {"score": 0, "status": "no_data", "factors": {}}
            
            # Calculate scores for different factors
            factors = {}
            
            # Response time score (0-100)
            response_times = [m.value for m in recent_metrics if m.metric_type == MetricType.RESPONSE_TIME]
            if response_times:
                avg_response_time = statistics.mean(response_times)
                response_score = max(0, 100 - (avg_response_time / 5) * 100)  # 5s = 0 score
                factors["response_time"] = round(response_score, 2)
            
            # Error rate score (0-100)
            error_rates = [m.value for m in recent_metrics if m.metric_type == MetricType.ERROR_RATE]
            if error_rates:
                avg_error_rate = statistics.mean(error_rates)
                error_score = max(0, 100 - avg_error_rate)  # 100% error = 0 score
                factors["error_rate"] = round(error_score, 2)
            
            # System resources score (0-100)
            cpu_metrics = [m for m in recent_metrics if m.metric_type == MetricType.SYSTEM_RESOURCES and m.tags.get("resource") == "cpu"]
            memory_metrics = [m for m in recent_metrics if m.metric_type == MetricType.SYSTEM_RESOURCES and m.tags.get("resource") == "memory"]
            
            if cpu_metrics and memory_metrics:
                avg_cpu = statistics.mean([m.value for m in cpu_metrics])
                avg_memory = statistics.mean([m.value for m in memory_metrics])
                resource_score = max(0, 100 - ((avg_cpu + avg_memory) / 2))  # 100% avg = 0 score
                factors["system_resources"] = round(resource_score, 2)
            
            # Database pool score (0-100)
            pool_metrics = [m for m in recent_metrics if m.metric_type == MetricType.DATABASE_POOL and m.tags.get("metric") == "utilization"]
            if pool_metrics:
                avg_pool_utilization = statistics.mean([m.value for m in pool_metrics])
                pool_score = max(0, 100 - avg_pool_utilization)  # 100% utilization = 0 score
                factors["database_pool"] = round(pool_score, 2)
            
            # Calculate overall score (weighted average)
            weights = {
                "response_time": 0.3,
                "error_rate": 0.3,
                "system_resources": 0.2,
                "database_pool": 0.2
            }
            
            overall_score = 0
            total_weight = 0
            
            for factor, score in factors.items():
                if factor in weights:
                    overall_score += score * weights[factor]
                    total_weight += weights[factor]
            
            if total_weight > 0:
                overall_score = overall_score / total_weight
            else:
                overall_score = 0
            
            # Determine status
            if overall_score >= 90:
                status = "excellent"
            elif overall_score >= 75:
                status = "good"
            elif overall_score >= 60:
                status = "fair"
            elif overall_score >= 40:
                status = "poor"
            else:
                status = "critical"
            
            return {
                "score": round(overall_score, 2),
                "status": status,
                "factors": factors,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating health score: {e}")
            return {"score": 0, "status": "error", "error": str(e)}


# Global instance
performance_monitoring_service = PerformanceMonitoringService()