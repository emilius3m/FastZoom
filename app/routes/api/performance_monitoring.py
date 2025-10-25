# app/routes/api/performance_monitoring.py - Performance Monitoring API Routes

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger

from app.services.performance_monitoring_service import (
    performance_monitoring_service,
    MetricType,
    AlertLevel
)
from app.core.security import get_current_user_id_with_blacklist

router = APIRouter()


@router.get("/status")
async def get_monitoring_status(
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get overall monitoring system status"""
    try:
        health_score = performance_monitoring_service.get_system_health_score()
        active_alerts = performance_monitoring_service.get_active_alerts()
        
        return {
            "status": "running" if performance_monitoring_service._running else "stopped",
            "health_score": health_score,
            "active_alerts_count": len(active_alerts),
            "total_metrics_collected": len(performance_monitoring_service.metrics_history),
            "total_alerts_configured": len(performance_monitoring_service.alerts),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get monitoring status")


@router.get("/health-score")
async def get_health_score(
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get detailed system health score"""
    try:
        health_score = performance_monitoring_service.get_system_health_score()
        return health_score
        
    except Exception as e:
        logger.error(f"Error getting health score: {e}")
        raise HTTPException(status_code=500, detail="Failed to get health score")


@router.get("/metrics")
async def get_metrics(
    metric_type: Optional[str] = Query(None, description="Filter by metric type"),
    time_range: Optional[str] = Query("1h", description="Time range (1h, 6h, 24h, 7d)"),
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get performance metrics summary"""
    try:
        # Parse metric type
        parsed_metric_type = None
        if metric_type:
            try:
                parsed_metric_type = MetricType(metric_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_type}")
        
        # Parse time range
        time_ranges = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7)
        }
        
        parsed_time_range = time_ranges.get(time_range, timedelta(hours=1))
        
        # Get metrics summary
        summary = performance_monitoring_service.get_metrics_summary(
            metric_type=parsed_metric_type,
            time_range=parsed_time_range
        )
        
        return {
            "metric_type": metric_type,
            "time_range": time_range,
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@router.get("/metrics/history")
async def get_metrics_history(
    metric_type: str = Query(..., description="Metric type"),
    time_range: str = Query("1h", description="Time range (1h, 6h, 24h, 7d)"),
    tags: Optional[str] = Query(None, description="Filter by tags (JSON format)"),
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get detailed metrics history"""
    try:
        # Parse metric type
        try:
            parsed_metric_type = MetricType(metric_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_type}")
        
        # Parse time range
        time_ranges = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7)
        }
        
        parsed_time_range = time_ranges.get(time_range, timedelta(hours=1))
        cutoff_time = datetime.now() - parsed_time_range
        
        # Parse tags filter
        tags_filter = None
        if tags:
            try:
                import json
                tags_filter = json.loads(tags)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid tags JSON format")
        
        # Filter metrics
        filtered_metrics = []
        for metric in performance_monitoring_service.metrics_history:
            if metric.metric_type != parsed_metric_type:
                continue
            
            if metric.timestamp < cutoff_time:
                continue
            
            if tags_filter:
                match = True
                for key, value in tags_filter.items():
                    if metric.tags.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            filtered_metrics.append({
                "value": metric.value,
                "unit": metric.unit,
                "timestamp": metric.timestamp.isoformat(),
                "tags": metric.tags,
                "metadata": metric.metadata
            })
        
        return {
            "metric_type": metric_type,
            "time_range": time_range,
            "tags_filter": tags_filter,
            "data": filtered_metrics,
            "count": len(filtered_metrics),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting metrics history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics history")


@router.get("/comparison")
async def get_performance_comparison(
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get performance comparison with baselines"""
    try:
        comparison = performance_monitoring_service.get_performance_comparison()
        return comparison
        
    except Exception as e:
        logger.error(f"Error getting performance comparison: {e}")
        raise HTTPException(status_code=500, detail="Failed to get performance comparison")


@router.get("/alerts")
async def get_alerts(
    active_only: bool = Query(True, description="Show only active alerts"),
    level: Optional[str] = Query(None, description="Filter by alert level"),
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get performance alerts"""
    try:
        # Parse alert level filter
        level_filter = None
        if level:
            try:
                level_filter = AlertLevel(level)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid alert level: {level}")
        
        # Get alerts
        all_alerts = performance_monitoring_service.get_active_alerts()
        
        # Filter alerts
        filtered_alerts = []
        for alert in all_alerts:
            if active_only and not alert.get("is_active", True):
                continue
            
            if level_filter and alert.get("level") != level_filter.value:
                continue
            
            filtered_alerts.append(alert)
        
        return {
            "alerts": filtered_alerts,
            "count": len(filtered_alerts),
            "filters": {
                "active_only": active_only,
                "level": level
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get alerts")


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Resolve a specific alert"""
    try:
        if alert_id not in performance_monitoring_service.alerts:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        
        alert = performance_monitoring_service.alerts[alert_id]
        if not alert.is_active:
            raise HTTPException(status_code=400, detail=f"Alert {alert_id} is already resolved")
        
        # Resolve alert
        alert.resolved_at = datetime.now()
        alert.is_active = False
        
        logger.info(f"Alert {alert_id} resolved by user {current_user_id}")
        
        return {
            "alert_id": alert_id,
            "status": "resolved",
            "resolved_at": alert.resolved_at.isoformat(),
            "resolved_by": current_user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve alert")


@router.post("/alerts")
async def create_alert(
    alert_data: Dict[str, Any],
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Create a new custom alert"""
    try:
        # Validate required fields
        required_fields = ["alert_id", "level", "metric_type", "threshold", "operator", "message"]
        for field in required_fields:
            if field not in alert_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Parse alert level
        try:
            level = AlertLevel(alert_data["level"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid alert level: {alert_data['level']}")
        
        # Parse metric type
        try:
            metric_type = MetricType(alert_data["metric_type"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid metric type: {alert_data['metric_type']}")
        
        # Validate operator
        valid_operators = [">", "<", ">=", "<=", "=="]
        if alert_data["operator"] not in valid_operators:
            raise HTTPException(status_code=400, detail=f"Invalid operator: {alert_data['operator']}")
        
        # Create alert
        alert = performance_monitoring_service.create_alert(
            alert_id=alert_data["alert_id"],
            level=level,
            metric_type=metric_type,
            threshold=float(alert_data["threshold"]),
            operator=alert_data["operator"],
            message=alert_data["message"]
        )
        
        logger.info(f"Custom alert {alert_data['alert_id']} created by user {current_user_id}")
        
        return {
            "alert_id": alert.alert_id,
            "status": "created",
            "created_at": alert.created_at.isoformat(),
            "created_by": current_user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to create alert")


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: str,
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Delete an alert"""
    try:
        if alert_id not in performance_monitoring_service.alerts:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        
        # Delete alert
        del performance_monitoring_service.alerts[alert_id]
        
        logger.info(f"Alert {alert_id} deleted by user {current_user_id}")
        
        return {
            "alert_id": alert_id,
            "status": "deleted",
            "deleted_by": current_user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete alert")


@router.get("/dashboard")
async def get_dashboard_data(
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Get comprehensive dashboard data"""
    try:
        # Get health score
        health_score = performance_monitoring_service.get_system_health_score()
        
        # Get recent metrics summary
        recent_metrics = performance_monitoring_service.get_metrics_summary(
            time_range=timedelta(hours=1)
        )
        
        # Get active alerts
        active_alerts = performance_monitoring_service.get_active_alerts()
        
        # Get performance comparison
        comparison = performance_monitoring_service.get_performance_comparison()
        
        # Get system status
        system_status = {
            "monitoring_running": performance_monitoring_service._running,
            "total_metrics": len(performance_monitoring_service.metrics_history),
            "total_alerts": len(performance_monitoring_service.alerts),
            "active_alerts": len(active_alerts)
        }
        
        return {
            "health_score": health_score,
            "recent_metrics": recent_metrics,
            "active_alerts": active_alerts,
            "performance_comparison": comparison,
            "system_status": system_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard data")


@router.post("/metrics/record")
async def record_custom_metric(
    metric_data: Dict[str, Any],
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Record a custom metric"""
    try:
        # Validate required fields
        required_fields = ["metric_type", "value", "unit"]
        for field in required_fields:
            if field not in metric_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Parse metric type
        try:
            metric_type = MetricType(metric_data["metric_type"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_data['metric_type']}")
        
        # Record metric
        performance_monitoring_service.record_metric(
            metric_type=metric_type,
            value=float(metric_data["value"]),
            unit=metric_data["unit"],
            tags=metric_data.get("tags", {}),
            metadata=metric_data.get("metadata", {})
        )
        
        logger.info(f"Custom metric {metric_data['metric_type']} recorded by user {current_user_id}")
        
        return {
            "status": "recorded",
            "metric_type": metric_data["metric_type"],
            "value": metric_data["value"],
            "unit": metric_data["unit"],
            "recorded_by": current_user_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording custom metric: {e}")
        raise HTTPException(status_code=500, detail="Failed to record custom metric")


@router.get("/report")
async def get_performance_report(
    time_range: str = Query("24h", description="Time range (1h, 6h, 24h, 7d, 30d)"),
    format: str = Query("json", description="Report format (json, html)"),
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Generate comprehensive performance report"""
    try:
        # Parse time range
        time_ranges = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30)
        }
        
        parsed_time_range = time_ranges.get(time_range, timedelta(hours=24))
        
        # Generate report data
        report_data = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "time_range": time_range,
                "generated_by": current_user_id,
                "format": format
            },
            "health_score": performance_monitoring_service.get_system_health_score(),
            "metrics_summary": performance_monitoring_service.get_metrics_summary(
                time_range=parsed_time_range
            ),
            "performance_comparison": performance_monitoring_service.get_performance_comparison(),
            "active_alerts": performance_monitoring_service.get_active_alerts(),
            "system_status": {
                "monitoring_running": performance_monitoring_service._running,
                "total_metrics": len(performance_monitoring_service.metrics_history),
                "total_alerts": len(performance_monitoring_service.alerts)
            }
        }
        
        if format == "html":
            # Generate HTML report (simplified)
            html_report = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>FastZoom Performance Report</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background: #f5f5f5; padding: 20px; border-radius: 5px; }}
                    .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                    .metric {{ display: inline-block; margin: 10px; padding: 10px; background: #e9ecef; border-radius: 3px; }}
                    .alert {{ padding: 10px; margin: 5px 0; border-radius: 3px; }}
                    .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; }}
                    .critical {{ background: #f8d7da; border: 1px solid #f5c6cb; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>FastZoom Performance Report</h1>
                    <p>Generated: {report_data['report_metadata']['generated_at']}</p>
                    <p>Time Range: {time_range}</p>
                    <p>Generated by: {current_user_id}</p>
                </div>
                
                <div class="section">
                    <h2>System Health Score</h2>
                    <div class="metric">
                        <strong>Score:</strong> {report_data['health_score']['score']}/100
                    </div>
                    <div class="metric">
                        <strong>Status:</strong> {report_data['health_score']['status']}
                    </div>
                </div>
                
                <div class="section">
                    <h2>Active Alerts</h2>
                    {"".join([f'<div class="alert {alert["level"]}">{alert["message"]}</div>' for alert in report_data['active_alerts']])}
                </div>
                
                <div class="section">
                    <h2>Performance Comparison</h2>
                    <table>
                        <tr><th>Metric</th><th>Baseline</th><th>Current</th><th>Improvement</th><th>Target Met</th></tr>
                        {"".join([f'''
                        <tr>
                            <td>{metric}</td>
                            <td>{data["baseline_value"]}</td>
                            <td>{data["current_value"]}</td>
                            <td>{data["improvement_percent"]}%</td>
                            <td>{"✅" if data["target_met"] else "❌"}</td>
                        </tr>
                        ''' for metric, data in report_data['performance_comparison']['metrics'].items()])}
                    </table>
                </div>
                
                <div class="section">
                    <h2>System Status</h2>
                    <div class="metric">
                        <strong>Monitoring Running:</strong> {report_data['system_status']['monitoring_running']}
                    </div>
                    <div class="metric">
                        <strong>Total Metrics:</strong> {report_data['system_status']['total_metrics']}
                    </div>
                    <div class="metric">
                        <strong>Active Alerts:</strong> {report_data['system_status']['active_alerts']}
                    </div>
                </div>
            </body>
            </html>
            """
            
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html_report)
        
        return report_data
        
    except Exception as e:
        logger.error(f"Error generating performance report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate performance report")


@router.post("/start")
async def start_monitoring(
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Start the monitoring service"""
    try:
        if performance_monitoring_service._running:
            return {"status": "already_running", "message": "Monitoring service is already running"}
        
        await performance_monitoring_service.start_monitoring()
        
        logger.info(f"Monitoring service started by user {current_user_id}")
        
        return {
            "status": "started",
            "message": "Monitoring service started successfully",
            "started_by": current_user_id,
            "started_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        raise HTTPException(status_code=500, detail="Failed to start monitoring service")


@router.post("/stop")
async def stop_monitoring(
    current_user_id: str = Depends(get_current_user_id_with_blacklist)
):
    """Stop the monitoring service"""
    try:
        if not performance_monitoring_service._running:
            return {"status": "already_stopped", "message": "Monitoring service is already stopped"}
        
        await performance_monitoring_service.stop_monitoring()
        
        logger.info(f"Monitoring service stopped by user {current_user_id}")
        
        return {
            "status": "stopped",
            "message": "Monitoring service stopped successfully",
            "stopped_by": current_user_id,
            "stopped_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop monitoring service")