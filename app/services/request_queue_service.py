# app/services/request_queue_service.py - Request Queueing System for Load Management

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
from uuid import uuid4
from loguru import logger
import psutil
import asyncio

from app.core.config import get_settings

settings = get_settings()


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches pattern with parameters"""
    
    # Simple pattern matching for {param} style
    pattern_parts = pattern.split('/')
    path_parts = path.split('/')
    
    if len(pattern_parts) != len(path_parts):
        return False
    
    for pattern_part, path_part in zip(pattern_parts, path_parts):
        if pattern_part.startswith('{') and pattern_part.endswith('}'):
            continue  # Parameter matches anything
        elif pattern_part != path_part:
            return False
    
    return True


class RequestPriority(Enum):
    """Priority levels for requests"""
    CRITICAL = 1    # System critical operations
    HIGH = 2        # User interactive operations
    NORMAL = 3      # Standard operations
    LOW = 4         # Background operations
    BULK = 5        # Bulk operations


class RequestStatus(Enum):
    """Status of queued requests"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class QueuedRequest:
    """A queued request with metadata"""
    request_id: str
    priority: RequestPriority
    request_type: str
    payload: Dict[str, Any]
    user_id: Optional[str] = None
    site_id: Optional[str] = None
    status: RequestStatus = RequestStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    estimated_duration: float = 0.0
    actual_duration: float = 0.0
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    callback_url: Optional[str] = None
    
    def __post_init__(self):
        if not self.request_id:
            self.request_id = str(uuid4())


class SystemLoadMonitor:
    """Monitor system load for dynamic rate limiting"""
    
    def __init__(self):
        # More lenient thresholds for stress testing
        self.cpu_threshold = 85.0  # Increased from 75.0
        self.memory_threshold = 90.0  # Increased from 80.0
        self.disk_threshold = 90.0   # Increased from 85.0
        self.load_history = []
        self.max_history = 60  # Keep 60 samples
        
    def get_current_load(self) -> Dict[str, float]:
        """Get current system load metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Windows-compatible load average
            load_average = 0
            try:
                if hasattr(psutil, 'getloadavg'):
                    load_average = psutil.getloadavg()[0]
                else:
                    # Fallback for Windows: use CPU as load indicator
                    load_average = cpu_percent / 100.0
            except Exception:
                load_average = cpu_percent / 100.0
            
            load_data = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': (disk.used / disk.total) * 100,
                'load_average': load_average,
                'timestamp': time.time()
            }
            
            # Keep history
            self.load_history.append(load_data)
            if len(self.load_history) > self.max_history:
                self.load_history.pop(0)
                
            return load_data
            
        except Exception as e:
            logger.error(f"Error getting system load: {e}")
            return {
                'cpu_percent': 0,
                'memory_percent': 0,
                'disk_percent': 0,
                'load_average': 0,
                'timestamp': time.time()
            }
    
    def is_system_overloaded(self) -> bool:
        """Check if system is overloaded"""
        load = self.get_current_load()
        
        # Be more permissive for stress testing
        cpu_overloaded = load['cpu_percent'] > self.cpu_threshold
        memory_overloaded = load['memory_percent'] > self.memory_threshold
        disk_overloaded = load['disk_percent'] > self.disk_threshold
        
        # Only consider system overloaded if at least 2 metrics are exceeded
        overload_count = sum([cpu_overloaded, memory_overloaded, disk_overloaded])
        
        return overload_count >= 2  # Require at least 2 metrics to be overloaded
    
    def get_load_factor(self) -> float:
        """Get load factor (0.0 to 1.0) for dynamic rate limiting"""
        load = self.get_current_load()
        
        # Calculate individual load factors
        cpu_factor = min(1.0, load['cpu_percent'] / self.cpu_threshold)
        memory_factor = min(1.0, load['memory_percent'] / self.memory_threshold)
        disk_factor = min(1.0, load['disk_percent'] / self.disk_threshold)
        
        # Return the maximum factor
        return max(cpu_factor, memory_factor, disk_factor)
    
    def get_average_load(self, minutes: int = 5) -> Dict[str, float]:
        """Get average load over specified minutes"""
        if not self.load_history:
            return self.get_current_load()
            
        cutoff_time = time.time() - (minutes * 60)
        recent_loads = [
            load for load in self.load_history 
            if load['timestamp'] > cutoff_time
        ]
        
        if not recent_loads:
            return self.get_current_load()
            
        avg_load = {
            'cpu_percent': sum(load['cpu_percent'] for load in recent_loads) / len(recent_loads),
            'memory_percent': sum(load['memory_percent'] for load in recent_loads) / len(recent_loads),
            'disk_percent': sum(load['disk_percent'] for load in recent_loads) / len(recent_loads),
            'load_average': sum(load['load_average'] for load in recent_loads) / len(recent_loads),
        }
        
        return avg_load


class RequestQueueService:
    """Main request queue service with priority handling and dynamic rate limiting"""
    
    def __init__(self):
        # Priority queues (lower number = higher priority)
        self.queues = {
            RequestPriority.CRITICAL: asyncio.Queue(),
            RequestPriority.HIGH: asyncio.Queue(),
            RequestPriority.NORMAL: asyncio.Queue(),
            RequestPriority.LOW: asyncio.Queue(),
            RequestPriority.BULK: asyncio.Queue()
        }
        
        # Request tracking
        self.active_requests: Dict[str, QueuedRequest] = {}
        self.completed_requests: Dict[str, QueuedRequest] = {}
        self.failed_requests: Dict[str, QueuedRequest] = {}
        
        # Rate limiting
        self.system_monitor = SystemLoadMonitor()
        self.base_concurrent_limit = 10
        self.max_concurrent_limit = 50
        self.current_concurrent_limit = self.base_concurrent_limit
        self.semaphore = asyncio.Semaphore(self.current_concurrent_limit)
        
        # Worker management
        self.workers = []
        self.max_workers = 5
        self.worker_task = None
        self.running = False
        
        # Request handlers
        self.request_handlers: Dict[str, Callable] = {}
        
        # Metrics
        self.metrics = {
            'total_requests': 0,
            'completed_requests': 0,
            'failed_requests': 0,
            'cancelled_requests': 0,
            'average_wait_time': 0.0,
            'average_processing_time': 0.0,
            'queue_sizes': {priority: 0 for priority in RequestPriority},
            'active_count': 0,
            'system_load': 0.0,
            'concurrent_limit': self.current_concurrent_limit
        }
        
        # Dynamic adjustment
        self.last_adjustment_time = time.time()
        self.adjustment_interval = 30  # seconds
        
    def register_handler(self, request_type: str, handler: Callable):
        """Register a handler for a specific request type"""
        self.request_handlers[request_type] = handler
        logger.info(f"Registered handler for request type: {request_type}")
    
    def get_handler(self, request_type: str) -> Optional[Callable]:
        """Get handler for a specific request type with pattern matching support"""
        
        # First try exact match
        if request_type in self.request_handlers:
            return self.request_handlers[request_type]
        
        # If no exact match, try pattern matching
        # Extract the path part from the request type (METHOD_path)
        if '_' in request_type:
            method, path = request_type.split('_', 1)
            
            # Try to match against registered handler patterns
            for registered_pattern, handler in self.request_handlers.items():
                if '_' in registered_pattern:
                    registered_method, registered_path = registered_pattern.split('_', 1)
                    
                    # Check if methods match and paths match with pattern
                    if method == registered_method and _path_matches_pattern(path, registered_path):
                        logger.info(f"Found pattern match: {request_type} -> {registered_pattern}")
                        return handler
        
        # No handler found
        return None
    
    async def start(self):
        """Start the queue service"""
        if self.running:
            logger.warning("Queue service already running")
            return
            
        self.running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Request queue service started")
    
    async def stop(self):
        """Stop the queue service"""
        if not self.running:
            return
            
        self.running = False
        
        # Cancel worker task
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        
        # Wait for active requests to complete or timeout
        if self.active_requests:
            logger.info(f"Waiting for {len(self.active_requests)} active requests to complete...")
            await asyncio.sleep(5)  # Give some time for graceful completion
            
        logger.info("Request queue service stopped")
    
    async def enqueue_request(
        self,
        request_type: str,
        payload: Dict[str, Any],
        priority: RequestPriority = RequestPriority.NORMAL,
        user_id: Optional[str] = None,
        site_id: Optional[str] = None,
        timeout_seconds: int = 300,
        max_retries: int = 3,
        estimated_duration: float = 0.0,
        callback_url: Optional[str] = None
    ) -> str:
        """Enqueue a request for processing"""
        
        # Check if handler exists using pattern matching
        handler = self.get_handler(request_type)
        if handler is None:
            raise ValueError(f"No handler registered for request type: {request_type}")
        
        # Create queued request
        request = QueuedRequest(
            request_id=str(uuid4()),
            priority=priority,
            request_type=request_type,
            payload=payload,
            user_id=user_id,
            site_id=site_id,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            estimated_duration=estimated_duration,
            callback_url=callback_url
        )
        
        # Add to appropriate priority queue
        await self.queues[priority].put(request)
        self.active_requests[request.request_id] = request
        
        # Update metrics
        self.metrics['total_requests'] += 1
        self.metrics['queue_sizes'][priority] += 1
        
        logger.info(f"Enqueued request {request.request_id} with priority {priority.name}")
        
        return request.request_id
    
    async def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific request"""
        
        # Check in all request collections
        for request_dict in [self.active_requests, self.completed_requests, self.failed_requests]:
            if request_id in request_dict:
                request = request_dict[request_id]
                return {
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
                    'error_message': request.error_message,
                    'result': request.result
                }
        
        return None
    
    async def cancel_request(self, request_id: str) -> bool:
        """Cancel a pending request"""
        
        if request_id in self.active_requests:
            request = self.active_requests[request_id]
            
            if request.status == RequestStatus.PENDING:
                request.status = RequestStatus.CANCELLED
                request.completed_at = datetime.now()
                
                # Move to failed requests
                self.failed_requests[request_id] = request
                del self.active_requests[request_id]
                
                # Update metrics
                self.metrics['cancelled_requests'] += 1
                
                logger.info(f"Cancelled request {request_id}")
                return True
        
        return False
    
    async def _worker_loop(self):
        """Main worker loop for processing requests"""
        
        logger.info("Request queue worker loop started")
        
        while self.running:
            try:
                # Adjust concurrent limit based on system load
                await self._adjust_concurrent_limit()
                
                # Get next request (priority-based)
                request = await self._get_next_request()
                
                if request:
                    # Process request with semaphore control
                    asyncio.create_task(
                        self._process_request_with_semaphore(request)
                    )
                else:
                    # No requests, brief sleep
                    await asyncio.sleep(0.1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(1)
        
        logger.info("Request queue worker loop stopped")
    
    async def _get_next_request(self) -> Optional[QueuedRequest]:
        """Get next request based on priority"""
        
        # Check queues in priority order
        for priority in sorted(RequestPriority, key=lambda p: p.value):
            queue = self.queues[priority]
            
            try:
                # Non-blocking get
                request = queue.get_nowait()
                self.metrics['queue_sizes'][priority] -= 1
                return request
            except asyncio.QueueEmpty:
                continue
        
        return None
    
    async def _process_request_with_semaphore(self, request: QueuedRequest):
        """Process request with semaphore control"""
        
        async with self.semaphore:
            await self._process_request(request)
    
    async def _process_request(self, request: QueuedRequest):
        """Process a single request"""
        
        request.status = RequestStatus.PROCESSING
        request.started_at = datetime.now()
        
        # Update metrics
        self.metrics['active_count'] += 1
        
        logger.info(f"Processing request {request.request_id} ({request.request_type})")
        
        try:
            # Get handler using pattern matching
            handler = self.get_handler(request.request_type)
            if handler is None:
                raise ValueError(f"No handler found for request type: {request.request_type}")
            
            # Process with timeout
            result = await asyncio.wait_for(
                handler(request.payload),
                timeout=request.timeout_seconds
            )
            
            # Success
            request.status = RequestStatus.COMPLETED
            request.result = result
            request.completed_at = datetime.now()
            request.actual_duration = (request.completed_at - request.started_at).total_seconds()
            
            # Move to completed
            self.completed_requests[request.request_id] = request
            del self.active_requests[request.request_id]
            
            # Update metrics
            self.metrics['completed_requests'] += 1
            self._update_timing_metrics(request)
            
            logger.info(f"Completed request {request.request_id} in {request.actual_duration:.2f}s")
            
            # Send callback if provided
            if request.callback_url:
                await self._send_callback(request)
            
        except asyncio.TimeoutError:
            await self._handle_request_failure(request, "Request timeout")
        except Exception as e:
            await self._handle_request_failure(request, str(e))
        
        finally:
            # Update metrics
            self.metrics['active_count'] -= 1
    
    async def _handle_request_failure(self, request: QueuedRequest, error_message: str):
        """Handle request failure with retry logic"""
        
        request.error_message = error_message
        request.retry_count += 1
        
        # Check if we should retry
        if request.retry_count <= request.max_retries:
            request.status = RequestStatus.RETRYING
            
            # Exponential backoff
            delay = min(300, 30 * (2 ** request.retry_count))  # Max 5 minutes
            logger.info(f"Retrying request {request.request_id} in {delay}s (attempt {request.retry_count})")
            
            await asyncio.sleep(delay)
            
            # Reset status and re-queue
            request.status = RequestStatus.PENDING
            request.started_at = None
            await self.queues[request.priority].put(request)
            
        else:
            # Max retries exceeded
            request.status = RequestStatus.FAILED
            request.completed_at = datetime.now()
            request.actual_duration = (request.completed_at - request.started_at).total_seconds() if request.started_at else 0
            
            # Move to failed
            self.failed_requests[request.request_id] = request
            del self.active_requests[request.request_id]
            
            # Update metrics
            self.metrics['failed_requests'] += 1
            
            logger.error(f"Request {request.request_id} failed permanently: {error_message}")
    
    async def _adjust_concurrent_limit(self):
        """Dynamically adjust concurrent limit based on system load"""
        
        current_time = time.time()
        if current_time - self.last_adjustment_time < self.adjustment_interval:
            return
        
        self.last_adjustment_time = current_time
        
        # Get system load factor
        load_factor = self.system_monitor.get_load_factor()
        self.metrics['system_load'] = load_factor
        
        # Calculate new limit
        if load_factor < 0.5:
            # Low load, can increase limit
            new_limit = min(self.max_concurrent_limit, int(self.base_concurrent_limit * 2))
        elif load_factor < 0.8:
            # Medium load, use base limit
            new_limit = self.base_concurrent_limit
        else:
            # High load, reduce limit
            new_limit = max(2, int(self.base_concurrent_limit * 0.5))
        
        # Update semaphore if limit changed
        if new_limit != self.current_concurrent_limit:
            self.current_concurrent_limit = new_limit
            self.semaphore = asyncio.Semaphore(self.current_concurrent_limit)
            self.metrics['concurrent_limit'] = self.current_concurrent_limit
            
            logger.info(f"Adjusted concurrent limit to {self.current_concurrent_limit} (load factor: {load_factor:.2f})")
    
    def _update_timing_metrics(self, request: QueuedRequest):
        """Update timing metrics"""
        
        if request.started_at and request.created_at:
            wait_time = (request.started_at - request.created_at).total_seconds()
            processing_time = request.actual_duration
            
            # Simple moving average
            alpha = 0.1  # Smoothing factor
            
            self.metrics['average_wait_time'] = (
                alpha * wait_time + 
                (1 - alpha) * self.metrics['average_wait_time']
            )
            
            self.metrics['average_processing_time'] = (
                alpha * processing_time + 
                (1 - alpha) * self.metrics['average_processing_time']
            )
    
    async def _send_callback(self, request: QueuedRequest):
        """Send callback notification"""
        
        try:
            # This would typically use HTTP client to send callback
            # For now, just log it
            logger.info(f"Callback for request {request.request_id}: {request.callback_url}")
            
        except Exception as e:
            logger.error(f"Failed to send callback for request {request.request_id}: {e}")
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get overall queue status"""
        
        # Update queue sizes
        for priority in RequestPriority:
            self.metrics['queue_sizes'][priority] = self.queues[priority].qsize()
        
        # Get system load
        system_load = self.system_monitor.get_current_load()
        
        return {
            'is_running': self.running,
            'metrics': self.metrics.copy(),
            'system_load': system_load,
            'active_requests': len(self.active_requests),
            'completed_requests': len(self.completed_requests),
            'failed_requests': len(self.failed_requests),
            'queue_sizes': {
                priority.name: queue.qsize() 
                for priority, queue in self.queues.items()
            },
            'concurrent_limit': self.current_concurrent_limit,
            'registered_handlers': list(self.request_handlers.keys())
        }
    
    async def cleanup_old_requests(self, days: int = 7):
        """Clean up old completed and failed requests"""
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Clean completed requests
        completed_to_remove = [
            request_id for request_id, request in self.completed_requests.items()
            if request.completed_at and request.completed_at < cutoff_date
        ]
        
        for request_id in completed_to_remove:
            del self.completed_requests[request_id]
        
        # Clean failed requests
        failed_to_remove = [
            request_id for request_id, request in self.failed_requests.items()
            if request.completed_at and request.completed_at < cutoff_date
        ]
        
        for request_id in failed_to_remove:
            del self.failed_requests[request_id]
        
        if completed_to_remove or failed_to_remove:
            logger.info(f"Cleaned up {len(completed_to_remove)} completed and {len(failed_to_remove)} failed requests")


# Global instance
request_queue_service = RequestQueueService()