"""
API v1 - System Monitoring
Endpoints per monitoring del sistema archeologico.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel
from datetime import datetime, timedelta

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.core.dependencies import get_database_session
from app.core.domain_exceptions import (
    InsufficientPermissionsError,
    ResourceNotFoundError,
    ValidationError as DomainValidationError,
    SiteNotFoundError
)

# Import existing monitoring functions for backward compatibility
from app.routes.api.v1.database_monitoring import (
    get_pool_status_api_database_pool_status_get,
    get_pool_health_api_database_pool_health_get,
    get_pool_trends_api_database_pool_trends_get,
    log_pool_status_api_database_pool_log_status_post,
    get_pool_metrics_api_database_pool_metrics_get
)
from app.routes.api.queue_monitoring import (
    get_queue_status_api_queue_queue_status_get,
    get_queue_requests_api_queue_queue_requests_get,
    get_request_details_api_queue_queue_request__request_id__get,
    cancel_request_api_queue_queue_request__request_id__cancel_post,
    get_queue_metrics_api_queue_queue_metrics_get,
    cleanup_old_requests_api_queue_queue_cleanup_post,
    adjust_queue_limits_api_queue_queue_adjust_limits_post,
    get_queue_health_api_queue_queue_health_get
)
from app.routes.api.performance_monitoring import (
    get_monitoring_status_api_performance_monitoring_status_get,
    get_health_score_api_performance_monitoring_health_score_get,
    get_metrics_api_performance_monitoring_metrics_get,
    get_metrics_history_api_performance_monitoring_metrics_history_get,
    get_performance_comparison_api_performance_monitoring_comparison_get,
    get_alerts_api_performance_monitoring_alerts_get,
    create_alert_api_performance_monitoring_alerts_post,
    resolve_alert_api_performance_monitoring_alerts__alert_id__resolve_post,
    delete_alert_api_performance_monitoring_alerts__alert_id__delete,
    get_dashboard_data_api_performance_monitoring_dashboard_get,
    record_custom_metric_api_performance_monitoring_metrics_record_post,
    get_performance_report_api_performance_monitoring_report_get,
    start_monitoring_api_performance_monitoring_start_post,
    stop_monitoring_api_performance_monitoring_stop_post
)

# Schemas
class AlertCreate(BaseModel):
    name: str
    description: str
    metric_type: str
    threshold_value: float
    comparison_operator: str  # gt, lt, eq, gte, lte
    severity: str  # low, medium, high, critical
    is_active: bool = True
    notification_channels: Optional[List[str]] = None

class CustomMetric(BaseModel):
    metric_name: str
    metric_value: float
    metric_type: str
    tags: Optional[Dict[str, str]] = None
    timestamp: Optional[datetime] = None

class QueueLimitsAdjust(BaseModel):
    max_concurrent_requests: Optional[int] = None
    max_queue_size: Optional[int] = None
    request_timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None

router = APIRouter()

def add_deprecation_headers(response: Response, new_endpoint: str):
    """Aggiunge headers di deprecazione per backward compatibility"""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecated-Reason"] = "Endpoint ristrutturato. Usa la nuova API v1."
    response.headers["X-API-New-Endpoint"] = new_endpoint
    response.headers["X-API-Sunset"] = "2025-12-31"  # Data rimozione vecchi endpoint

def verify_admin_access(user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica che l'utente abbia privilegi di amministrazione"""
    if not user_sites:
        raise InsufficientPermissionsError("Accesso monitoring richiede privilegi amministrativi")
    
    # Verifica se è superutente o ha permessi admin su qualche sito
    is_admin = any(
        site.get("is_superuser") or site.get("permission_level") == "admin"
        for site in user_sites
    )
    
    if not is_admin:
        raise InsufficientPermissionsError("Privilegi insufficienti per accesso monitoring")
    
    return True

# NUOVI ENDPOINTS V1

@router.get("/overview", summary="Status generale sistema", tags=["System Monitoring"])
async def v1_get_system_overview(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni status generale del sistema archeologico.
    
    Include database, queue, storage e performance metrics.
    """
    verify_admin_access(user_sites)
    
    # Aggrega dati da diverse fonti
    overview = {
        "timestamp": datetime.utcnow().isoformat(),
        "system_status": "healthy",
        "components": {
            "database": {},
            "queue": {},
            "performance": {},
            "storage": {}
        },
        "alerts_count": {
            "active": 0,
            "critical": 0,
            "total": 0
        }
    }
    
    try:
        # Database status
        pool_status = await get_pool_status_api_database_pool_status_get(db)
        overview["components"]["database"] = {
            "status": "healthy" if pool_status.get("healthy") else "degraded",
            "connections": pool_status.get("total_connections", 0),
            "active_connections": pool_status.get("active_connections", 0)
        }
    except Exception as e:
        overview["components"]["database"] = {"status": "error", "error": str(e)}
    
    try:
        # Queue status
        queue_status = await get_queue_status_api_queue_queue_status_get()
        overview["components"]["queue"] = {
            "status": "healthy" if queue_status.get("healthy") else "degraded",
            "pending_requests": queue_status.get("pending_requests", 0),
            "processing_requests": queue_status.get("processing_requests", 0)
        }
    except Exception as e:
        overview["components"]["queue"] = {"status": "error", "error": str(e)}
    
    try:
        # Performance status
        perf_status = await get_monitoring_status_api_performance_monitoring_status_get()
        overview["components"]["performance"] = {
            "status": "healthy" if perf_status.get("status") == "running" else "stopped",
            "uptime_seconds": perf_status.get("uptime_seconds", 0)
        }
    except Exception as e:
        overview["components"]["performance"] = {"status": "error", "error": str(e)}
    
    try:
        # Alerts
        alerts = await get_alerts_api_performance_monitoring_alerts_get(active_only=True)
        overview["alerts_count"] = {
            "active": len(alerts.get("alerts", [])),
            "critical": len([a for a in alerts.get("alerts", []) if a.get("severity") == "critical"]),
            "total": len(alerts.get("alerts", []))
        }
    except Exception as e:
        overview["alerts"]["error"] = str(e)
    
    # Determina status generale
    component_statuses = [comp.get("status") for comp in overview["components"].values() if isinstance(comp, dict)]
    if "error" in component_statuses or "degraded" in component_statuses:
        overview["system_status"] = "degraded"
    
    return overview

@router.get("/database", summary="Status database connection pool", tags=["Database Monitoring"])
async def v1_get_database_status(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni status completo del connection pool database.
    """
    verify_admin_access(user_sites)
    
    return await get_pool_status_api_database_pool_status_get(db)

@router.get("/database/health", summary="Health score database", tags=["Database Monitoring"])
async def v1_get_database_health(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni health score del database con raccomandazioni.
    """
    verify_admin_access(user_sites)
    
    return await get_pool_health_api_database_pool_health_get(db)

@router.get("/database/metrics", summary="Metriche database", tags=["Database Monitoring"])
async def v1_get_database_metrics(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni metriche complete del database per dashboard monitoring.
    """
    verify_admin_access(user_sites)
    
    return await get_pool_metrics_api_database_pool_metrics_get(db)

@router.get("/queue", summary="Status coda processing", tags=["Queue Monitoring"])
async def v1_get_queue_status(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni status generale della coda di processing.
    """
    verify_admin_access(user_sites)
    
    return await get_queue_status_api_queue_queue_status_get()

@router.get("/queue/requests", summary="Richieste in coda", tags=["Queue Monitoring"])
async def v1_get_queue_requests(
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni lista richieste in coda con filtri.
    """
    verify_admin_access(user_sites)
    
    # Simula request con query params
    class MockRequest:
        def __init__(self, query_params: dict):
            self.query_params = query_params
    
    mock_request = MockRequest({
        "status_filter": status_filter,
        "priority_filter": priority_filter,
        "limit": limit,
        "offset": offset
    })
    
    return await get_queue_requests_api_queue_queue_requests_get(mock_request)

@router.get("/performance/metrics", summary="Metriche performance", tags=["Performance Monitoring"])
async def v1_get_performance_metrics(
    metric_type: Optional[str] = None,
    time_range: str = "1h",
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni metriche performance del sistema.
    """
    verify_admin_access(user_sites)
    
    # Simula request con query params
    class MockRequest:
        def __init__(self, query_params: dict):
            self.query_params = query_params
    
    mock_request = MockRequest({
        "metric_type": metric_type,
        "time_range": time_range
    })
    
    return await get_metrics_api_performance_monitoring_metrics_get(mock_request)

@router.get("/performance/alerts", summary="Alert performance", tags=["Performance Monitoring"])
async def v1_get_performance_alerts(
    active_only: bool = True,
    level: Optional[str] = None,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni alert performance del sistema.
    """
    verify_admin_access(user_sites)
    
    # Simula request con query params
    class MockRequest:
        def __init__(self, query_params: dict):
            self.query_params = query_params
    
    mock_request = MockRequest({
        "active_only": active_only,
        "level": level
    })
    
    return await get_alerts_api_performance_monitoring_alerts_get(mock_request)

@router.post("/performance/alerts", summary="Crea alert", tags=["Performance Monitoring"])
async def v1_create_performance_alert(
    alert_data: AlertCreate,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Crea nuovo alert performance personalizzato.
    """
    verify_admin_access(user_sites)
    
    # Simula request JSON data
    class MockRequest:
        def __init__(self, data: dict):
            self._data = data
        
        async def json(self):
            return self._data
    
    mock_request = MockRequest(alert_data.model_dump())
    return await create_alert_api_performance_monitoring_alerts_post(mock_request)

@router.get("/dashboard", summary="Dashboard monitoring", tags=["System Monitoring"])
async def v1_get_monitoring_dashboard(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ottieni dati completi per dashboard monitoring.
    """
    verify_admin_access(user_sites)
    
    return await get_dashboard_data_api_performance_monitoring_dashboard_get()

@router.post("/metrics/custom", summary="Registra metrica personalizzata", tags=["Performance Monitoring"])
async def v1_record_custom_metric(
    metric_data: CustomMetric,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Registra metrica personalizzata per monitoring custom.
    """
    verify_admin_access(user_sites)
    
    # Simula request JSON data
    class MockRequest:
        def __init__(self, data: dict):
            self._data = data
        
        async def json(self):
            return self._data
    
    mock_request = MockRequest(metric_data.model_dump())
    return await record_custom_metric_api_performance_monitoring_metrics_record_post(mock_request)

# ENDPOINT DI BACKWARD COMPATIBILITY CON DEPRECAZIONE

@router.get("/legacy/database/status", summary="[DEPRECATED] Status database legacy", tags=["Database Monitoring - Legacy"])
async def legacy_get_database_status(
    db: AsyncSession = Depends(get_database_session)
):
    """
    ⚠️ DEPRECATED: Status database endpoint legacy.
    
    Usa /api/v1/monitoring/database invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning("Legacy database status endpoint used - deprecated")
    response = await get_pool_status_api_database_pool_status_get(db)
    if hasattr(response, 'headers'):
        add_deprecation_headers(response, "/api/v1/monitoring/database")
    return response

@router.get("/legacy/queue/status", summary="[DEPRECATED] Status coda legacy", tags=["Queue Monitoring - Legacy"])
async def legacy_get_queue_status():
    """
    ⚠️ DEPRECATED: Status coda endpoint legacy.
    
    Usa /api/v1/monitoring/queue invece di questo endpoint.
    Questo endpoint sarà rimosso il 31/12/2025.
    """
    logger.warning("Legacy queue status endpoint used - deprecated")
    response = await get_queue_status_api_queue_queue_status_get()
    if hasattr(response, 'headers'):
        add_deprecation_headers(response, "/api/v1/monitoring/queue")
    return response

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API monitoring", tags=["System Monitoring - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per monitoring.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/database/pool/status": "/api/v1/monitoring/database",
                "/api/queue/queue/status": "/api/v1/monitoring/queue",
                "/api/performance-monitoring/metrics": "/api/v1/monitoring/performance/metrics",
                "/api/performance-monitoring/alerts": "/api/v1/monitoring/performance/alerts",
                "/api/performance-monitoring/dashboard": "/api/v1/monitoring/dashboard"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints monitoring in dominio unico",
                "Nuovo endpoint overview sistema",
                "Headers di deprecazione automatici",
                "Documentazione migliorata"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints monitoring"
        }
    }