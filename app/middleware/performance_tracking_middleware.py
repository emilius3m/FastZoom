# app/middleware/performance_tracking_middleware.py - Performance Tracking Middleware

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.services.performance_monitoring_service import (
    performance_monitoring_service,
    MetricType
)


class PerformanceTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track performance metrics for HTTP requests.
    Records response times, error rates, and throughput metrics.
    """
    
    def __init__(self, app: Callable, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics",
            "/static/",
            "/favicon.ico"
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip tracking for excluded paths
        if self._should_exclude_path(request.url.path):
            return await call_next(request)
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Record start time
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Record metrics
            self._record_request_metrics(
                request=request,
                response=response,
                response_time=response_time,
                request_id=request_id,
                is_error=False
            )
            
            # Add performance headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{response_time:.3f}s"
            
            return response
            
        except Exception as e:
            # Calculate response time for failed requests
            response_time = time.time() - start_time
            
            # Record error metrics
            self._record_request_metrics(
                request=request,
                response=None,
                response_time=response_time,
                request_id=request_id,
                is_error=True,
                error=str(e)
            )
            
            # Re-raise the exception
            raise
    
    def _should_exclude_path(self, path: str) -> bool:
        """Check if path should be excluded from tracking"""
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    def _record_request_metrics(
        self,
        request: Request,
        response: Response,
        response_time: float,
        request_id: str,
        is_error: bool,
        error: str = None
    ):
        """Record metrics for the request"""
        try:
            # Record response time
            performance_monitoring_service.record_metric(
                metric_type=MetricType.RESPONSE_TIME,
                value=response_time,
                unit="seconds",
                tags={
                    "method": request.method,
                    "path": self._normalize_path(request.url.path),
                    "status": "error" if is_error else str(response.status_code) if response else "500"
                },
                metadata={
                    "request_id": request_id,
                    "user_agent": request.headers.get("user-agent", ""),
                    "content_length": response.headers.get("content-length") if response else None
                }
            )
            
            # Record upload time for photo uploads
            if self._is_upload_request(request):
                performance_monitoring_service.record_metric(
                    metric_type=MetricType.UPLOAD_TIME,
                    value=response_time,
                    unit="seconds",
                    tags={
                        "method": request.method,
                        "path": self._normalize_path(request.url.path),
                        "upload_type": "photo"
                    },
                    metadata={
                        "request_id": request_id,
                        "content_length": request.headers.get("content-length")
                    }
                )
            
            # Record error metrics
            if is_error:
                performance_monitoring_service.record_metric(
                    metric_type=MetricType.ERROR_RATE,
                    value=1.0,  # Count as 1 error
                    unit="count",
                    tags={
                        "method": request.method,
                        "path": self._normalize_path(request.url.path),
                        "error_type": self._classify_error(error)
                    },
                    metadata={
                        "request_id": request_id,
                        "error_message": error
                    }
                )
            
            # Record throughput (as count of requests)
            performance_monitoring_service.record_metric(
                metric_type=MetricType.THROUGHPUT,
                value=1.0,  # Count as 1 request
                unit="count",
                tags={
                    "method": request.method,
                    "path": self._normalize_path(request.url.path),
                    "status": "error" if is_error else str(response.status_code) if response else "500"
                },
                metadata={
                    "request_id": request_id
                }
            )
            
        except Exception as e:
            # Don't let tracking errors affect the application
            logger.error(f"Error recording request metrics: {e}")
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for grouping similar requests"""
        # Replace UUIDs and IDs with placeholders
        import re
        
        # Replace UUID patterns
        path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path)
        
        # Replace numeric IDs
        path = re.sub(r'/\d+(?=/|$)', '/{id}', path)
        
        # Replace specific patterns
        path = re.sub(r'/site/[^/]+', '/site/{site_id}', path)
        path = re.sub(r'/photo/[^/]+', '/photo/{photo_id}', path)
        path = re.sub(r'/document/[^/]+', '/document/{document_id}', path)
        
        return path
    
    def _is_upload_request(self, request: Request) -> bool:
        """Check if this is an upload request"""
        return (
            "upload" in request.url.path.lower() or
            request.method in ["POST", "PUT"] and
            request.headers.get("content-type", "").startswith("multipart/form-data")
        )
    
    def _classify_error(self, error: str) -> str:
        """Classify error type for better tracking"""
        error_lower = error.lower() if error else ""
        
        if "timeout" in error_lower:
            return "timeout"
        elif "connection" in error_lower:
            return "connection"
        elif "database" in error_lower or "sql" in error_lower:
            return "database"
        elif "validation" in error_lower or "invalid" in error_lower:
            return "validation"
        elif "authentication" in error_lower or "authorization" in error_lower:
            return "auth"
        elif "permission" in error_lower or "forbidden" in error_lower:
            return "permission"
        elif "not found" in error_lower or "404" in error_lower:
            return "not_found"
        else:
            return "unknown"


class RequestCountMiddleware(BaseHTTPMiddleware):
    """
    Simple middleware to track concurrent requests count.
    """
    
    def __init__(self, app: Callable):
        super().__init__(app)
        self.active_requests = 0
        self.max_concurrent_requests = 0
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Increment active requests
        self.active_requests += 1
        
        # Update max concurrent requests
        if self.active_requests > self.max_concurrent_requests:
            self.max_concurrent_requests = self.active_requests
        
        # Record concurrent requests metric
        performance_monitoring_service.record_metric(
            metric_type=MetricType.CONCURRENT_REQUESTS,
            value=self.active_requests,
            unit="count",
            tags={"source": "middleware"},
            metadata={"max_concurrent": self.max_concurrent_requests}
        )
        
        try:
            response = await call_next(request)
            return response
        finally:
            # Decrement active requests
            self.active_requests -= 1
            
            # Record final concurrent requests
            performance_monitoring_service.record_metric(
                metric_type=MetricType.CONCURRENT_REQUESTS,
                value=self.active_requests,
                unit="count",
                tags={"source": "middleware"},
                metadata={"max_concurrent": self.max_concurrent_requests}
            )