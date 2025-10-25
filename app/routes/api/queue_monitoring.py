# app/routes/api/queue_monitoring.py - API endpoints for queue monitoring and management

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from uuid import UUID

from app.database.session import get_async_session
from app.core.security import get_current_user_id_with_blacklist
from app.services.request_queue_service import (
    request_queue_service, 
    RequestPriority,
    RequestStatus
)
from app.services.database_pool_monitor import get_pool_monitor

queue_monitoring_router = APIRouter()


@queue_monitoring_router.get("/queue/status")
async def get_queue_status(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Get overall queue status and metrics"""
    
    try:
        # Get queue status
        queue_status = await request_queue_service.get_queue_status()
        
        # Get database pool status
        pool_monitor = get_pool_monitor()
        if pool_monitor:
            pool_status = pool_monitor.get_pool_status()
        else:
            pool_status = {"error": "Pool monitor not initialized"}
        
        # Get system load
        system_load = request_queue_service.system_monitor.get_current_load()
        avg_load = request_queue_service.system_monitor.get_average_load(minutes=5)
        
        # Calculate health score
        health_score = _calculate_health_score(queue_status, pool_status, system_load)
        
        return JSONResponse({
            'timestamp': datetime.now().isoformat(),
            'health_score': health_score,
            'queue': queue_status,
            'database_pool': pool_status,
            'system_load': {
                'current': system_load,
                'average_5min': avg_load
            },
            'recommendations': _generate_recommendations(queue_status, pool_status, system_load)
        })
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue status: {str(e)}"
        )


@queue_monitoring_router.get("/queue/requests")
async def get_queue_requests(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    priority_filter: Optional[str] = Query(None, description="Filter by priority"),
    user_filter: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of requests"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Get list of queued requests with filtering"""
    
    try:
        # Get all requests from queue service
        all_requests = []
        
        # Collect from all request collections
        for request_dict in [
            request_queue_service.active_requests,
            request_queue_service.completed_requests,
            request_queue_service.failed_requests
        ]:
            for request_id, request in request_dict.items():
                request_data = {
                    'request_id': request.request_id,
                    'priority': request.priority.name,
                    'request_type': request.request_type,
                    'status': request.status.value,
                    'user_id': request.user_id,
                    'site_id': request.site_id,
                    'created_at': request.created_at.isoformat(),
                    'started_at': request.started_at.isoformat() if request.started_at else None,
                    'completed_at': request.completed_at.isoformat() if request.completed_at else None,
                    'retry_count': request.retry_count,
                    'max_retries': request.max_retries,
                    'estimated_duration': request.estimated_duration,
                    'actual_duration': request.actual_duration,
                    'error_message': request.error_message
                }
                all_requests.append(request_data)
        
        # Apply filters
        filtered_requests = all_requests
        
        if status_filter:
            filtered_requests = [r for r in filtered_requests if r['status'] == status_filter]
        
        if priority_filter:
            filtered_requests = [r for r in filtered_requests if r['priority'] == priority_filter]
        
        if user_filter:
            filtered_requests = [r for r in filtered_requests if r['user_id'] == user_filter]
        
        # Sort by created_at (newest first)
        filtered_requests.sort(key=lambda x: x['created_at'], reverse=True)
        
        # Apply pagination
        total = len(filtered_requests)
        paginated_requests = filtered_requests[offset:offset + limit]
        
        return JSONResponse({
            'requests': paginated_requests,
            'pagination': {
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < total
            },
            'filters': {
                'status': status_filter,
                'priority': priority_filter,
                'user': user_filter
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting queue requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue requests: {str(e)}"
        )


@queue_monitoring_router.get("/queue/request/{request_id}")
async def get_request_details(
    request_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Get detailed information about a specific request"""
    
    try:
        request_status = await request_queue_service.get_request_status(request_id)
        
        if not request_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_id} not found"
            )
        
        return JSONResponse(request_status)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting request details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get request details: {str(e)}"
        )


@queue_monitoring_router.post("/queue/request/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Cancel a pending request"""
    
    try:
        success = await request_queue_service.cancel_request(request_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_id} not found or cannot be cancelled"
            )
        
        return JSONResponse({
            'message': f'Request {request_id} cancelled successfully',
            'request_id': request_id,
            'cancelled_at': datetime.now().isoformat()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel request: {str(e)}"
        )


@queue_monitoring_router.get("/queue/metrics")
async def get_queue_metrics(
    period_minutes: int = Query(60, ge=1, le=1440, description="Period in minutes"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Get detailed queue metrics for a time period"""
    
    try:
        # Get current queue status
        queue_status = await request_queue_service.get_queue_status()
        
        # Get system load history
        load_history = request_queue_service.system_monitor.load_history
        cutoff_time = datetime.now().timestamp() - (period_minutes * 60)
        
        recent_load = [
            load for load in load_history 
            if load['timestamp'] > cutoff_time
        ]
        
        # Calculate metrics
        metrics = {
            'period_minutes': period_minutes,
            'timestamp': datetime.now().isoformat(),
            
            # Queue metrics
            'queue_metrics': {
                'total_requests': queue_status['metrics']['total_requests'],
                'completed_requests': queue_status['metrics']['completed_requests'],
                'failed_requests': queue_status['metrics']['failed_requests'],
                'cancelled_requests': queue_status['metrics']['cancelled_requests'],
                'active_requests': queue_status['active_requests'],
                'success_rate': _calculate_success_rate(queue_status),
                'average_wait_time': queue_status['metrics']['average_wait_time'],
                'average_processing_time': queue_status['metrics']['average_processing_time']
            },
            
            # Queue sizes by priority
            'queue_sizes': queue_status['queue_sizes'],
            
            # System load metrics
            'system_metrics': {
                'current_load': request_queue_service.system_monitor.get_current_load(),
                'average_load': request_queue_service.system_monitor.get_average_load(period_minutes),
                'load_factor': request_queue_service.system_monitor.get_load_factor(),
                'is_overloaded': request_queue_service.system_monitor.is_system_overloaded()
            },
            
            # Load history
            'load_history': recent_load,
            
            # Performance metrics
            'performance_metrics': {
                'concurrent_limit': queue_status['concurrent_limit'],
                'throughput_per_minute': _calculate_throughput(queue_status, period_minutes),
                'estimated_capacity': _estimate_capacity(queue_status)
            }
        }
        
        return JSONResponse(metrics)
        
    except Exception as e:
        logger.error(f"Error getting queue metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue metrics: {str(e)}"
        )


@queue_monitoring_router.post("/queue/cleanup")
async def cleanup_old_requests(
    days: int = Query(7, ge=1, le=30, description="Days to keep requests"),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Clean up old completed and failed requests"""
    
    try:
        await request_queue_service.cleanup_old_requests(days=days)
        
        return JSONResponse({
            'message': f'Cleaned up requests older than {days} days',
            'cleanup_date': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error cleaning up requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup requests: {str(e)}"
        )


@queue_monitoring_router.post("/queue/adjust-limits")
async def adjust_queue_limits(
    limits_data: Dict[str, Any],
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Adjust queue limits and settings"""
    
    try:
        # Validate limits
        if 'base_concurrent_limit' in limits_data:
            new_limit = limits_data['base_concurrent_limit']
            if not isinstance(new_limit, int) or new_limit < 1 or new_limit > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="base_concurrent_limit must be an integer between 1 and 100"
                )
            request_queue_service.base_concurrent_limit = new_limit
        
        if 'max_concurrent_limit' in limits_data:
            new_limit = limits_data['max_concurrent_limit']
            if not isinstance(new_limit, int) or new_limit < 1 or new_limit > 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="max_concurrent_limit must be an integer between 1 and 200"
                )
            request_queue_service.max_concurrent_limit = new_limit
        
        if 'cpu_threshold' in limits_data:
            new_threshold = limits_data['cpu_threshold']
            if not isinstance(new_threshold, (int, float)) or new_threshold < 0 or new_threshold > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="cpu_threshold must be a number between 0 and 100"
                )
            request_queue_service.system_monitor.cpu_threshold = new_threshold
        
        if 'memory_threshold' in limits_data:
            new_threshold = limits_data['memory_threshold']
            if not isinstance(new_threshold, (int, float)) or new_threshold < 0 or new_threshold > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="memory_threshold must be a number between 0 and 100"
                )
            request_queue_service.system_monitor.memory_threshold = new_threshold
        
        # Force adjustment
        await request_queue_service._adjust_concurrent_limit()
        
        return JSONResponse({
            'message': 'Queue limits adjusted successfully',
            'adjusted_at': datetime.now().isoformat(),
            'new_limits': {
                'base_concurrent_limit': request_queue_service.base_concurrent_limit,
                'max_concurrent_limit': request_queue_service.max_concurrent_limit,
                'current_concurrent_limit': request_queue_service.current_concurrent_limit,
                'cpu_threshold': request_queue_service.system_monitor.cpu_threshold,
                'memory_threshold': request_queue_service.system_monitor.memory_threshold
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adjusting queue limits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to adjust queue limits: {str(e)}"
        )


@queue_monitoring_router.get("/queue/health")
async def get_queue_health(
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    db: AsyncSession = Depends(get_async_session)
):
    """Get simplified health status for monitoring"""
    
    try:
        queue_status = await request_queue_service.get_queue_status()
        system_load = request_queue_service.system_monitor.get_current_load()
        
        # Determine health status
        health_status = "healthy"
        if system_load['cpu_percent'] > 90 or system_load['memory_percent'] > 90:
            health_status = "critical"
        elif system_load['cpu_percent'] > 75 or system_load['memory_percent'] > 75:
            health_status = "warning"
        elif queue_status['active_requests'] > queue_status['concurrent_limit'] * 0.8:
            health_status = "warning"
        
        return JSONResponse({
            'status': health_status,
            'timestamp': datetime.now().isoformat(),
            'active_requests': queue_status['active_requests'],
            'concurrent_limit': queue_status['concurrent_limit'],
            'system_load_percent': max(system_load['cpu_percent'], system_load['memory_percent']),
            'is_overloaded': request_queue_service.system_monitor.is_system_overloaded()
        })
        
    except Exception as e:
        logger.error(f"Error getting queue health: {e}")
        return JSONResponse({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }, status_code=500)


def _calculate_health_score(queue_status: Dict, pool_status: Dict, system_load: Dict) -> float:
    """Calculate overall health score (0-100)"""
    
    score = 100.0
    
    # Deduct for high system load
    cpu_load = system_load.get('cpu_percent', 0)
    memory_load = system_load.get('memory_percent', 0)
    
    if cpu_load > 80:
        score -= 20
    elif cpu_load > 60:
        score -= 10
    
    if memory_load > 80:
        score -= 20
    elif memory_load > 60:
        score -= 10
    
    # Deduct for high queue usage
    active_requests = queue_status.get('active_requests', 0)
    concurrent_limit = queue_status.get('concurrent_limit', 10)
    
    if active_requests > concurrent_limit * 0.9:
        score -= 20
    elif active_requests > concurrent_limit * 0.7:
        score -= 10
    
    # Deduct for database pool issues
    pool_usage = pool_status.get('pool_usage_percent', 0)
    if pool_usage > 80:
        score -= 15
    elif pool_usage > 60:
        score -= 5
    
    # Deduct for failed requests
    total_requests = queue_status.get('metrics', {}).get('total_requests', 1)
    failed_requests = queue_status.get('metrics', {}).get('failed_requests', 0)
    
    if total_requests > 0:
        failure_rate = (failed_requests / total_requests) * 100
        if failure_rate > 10:
            score -= 20
        elif failure_rate > 5:
            score -= 10
    
    return max(0, score)


def _generate_recommendations(queue_status: Dict, pool_status: Dict, system_load: Dict) -> List[str]:
    """Generate recommendations based on system status"""
    
    recommendations = []
    
    # System load recommendations
    cpu_load = system_load.get('cpu_percent', 0)
    memory_load = system_load.get('memory_percent', 0)
    
    if cpu_load > 80:
        recommendations.append("High CPU usage detected. Consider scaling up or optimizing processing.")
    
    if memory_load > 80:
        recommendations.append("High memory usage detected. Consider increasing memory or optimizing memory usage.")
    
    # Queue recommendations
    active_requests = queue_status.get('active_requests', 0)
    concurrent_limit = queue_status.get('concurrent_limit', 10)
    
    if active_requests > concurrent_limit * 0.8:
        recommendations.append("Queue approaching capacity. Consider increasing concurrent limits.")
    
    # Database pool recommendations
    pool_usage = pool_status.get('pool_usage_percent', 0)
    if pool_usage > 80:
        recommendations.append("Database pool usage high. Consider increasing pool size.")
    
    # Failed requests recommendations
    total_requests = queue_status.get('metrics', {}).get('total_requests', 1)
    failed_requests = queue_status.get('metrics', {}).get('failed_requests', 0)
    
    if total_requests > 0:
        failure_rate = (failed_requests / total_requests) * 100
        if failure_rate > 5:
            recommendations.append("High failure rate detected. Check error logs and retry logic.")
    
    if not recommendations:
        recommendations.append("System operating normally.")
    
    return recommendations


def _calculate_success_rate(queue_status: Dict) -> float:
    """Calculate success rate percentage"""
    
    total_requests = queue_status.get('metrics', {}).get('total_requests', 0)
    completed_requests = queue_status.get('metrics', {}).get('completed_requests', 0)
    failed_requests = queue_status.get('metrics', {}).get('failed_requests', 0)
    
    if total_requests == 0:
        return 100.0
    
    successful_requests = completed_requests
    total_processed = completed_requests + failed_requests
    
    if total_processed == 0:
        return 100.0
    
    return (successful_requests / total_processed) * 100


def _calculate_throughput(queue_status: Dict, period_minutes: int) -> float:
    """Calculate requests per minute"""
    
    completed_requests = queue_status.get('metrics', {}).get('completed_requests', 0)
    
    return completed_requests / max(1, period_minutes)


def _estimate_capacity(queue_status: Dict) -> Dict[str, Any]:
    """Estimate system capacity"""
    
    avg_processing_time = queue_status.get('metrics', {}).get('average_processing_time', 1.0)
    concurrent_limit = queue_status.get('concurrent_limit', 10)
    
    # Estimate requests per minute
    requests_per_minute = (60 / avg_processing_time) * concurrent_limit
    
    return {
        'estimated_requests_per_minute': requests_per_minute,
        'estimated_requests_per_hour': requests_per_minute * 60,
        'current_utilization_percent': (queue_status.get('active_requests', 0) / max(1, concurrent_limit)) * 100
    }