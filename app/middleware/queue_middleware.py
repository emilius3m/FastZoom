# app/middleware/queue_middleware.py - Middleware for Request Queueing and Rate Limiting

import time
import asyncio
from typing import Dict, Any, Optional, Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from loguru import logger
import json
from uuid import uuid4

from app.services.request_queue_service import (
    request_queue_service, 
    RequestPriority, 
    RequestStatus
)


class QueueMiddleware(BaseHTTPMiddleware):
    """Middleware for request queueing and rate limiting"""
    
    def __init__(self, app, queue_config: Dict[str, Any] = None):
        super().__init__(app)
        self.queue_config = queue_config or {}
        
        # Rate limiting settings
        self.rate_limits = self.queue_config.get('rate_limits', {
            'upload': {'requests': 30, 'window': 60, 'burst': 50},  # 30 uploads per minute with burst of 50
            'default': {'requests': 100, 'window': 60}  # 100 requests per minute
        })
        
        # Queue settings per endpoint
        self.queue_settings = self.queue_config.get('queue_settings', {
            '/api/site/{site_id}/photos/upload': {
                'enable_queue': True,
                'priority': RequestPriority.NORMAL,
                'timeout': 600,  # 10 minutes
                'max_retries': 3
            },
            '/api/site/{site_id}/photos/bulk-upload': {
                'enable_queue': True,
                'priority': RequestPriority.LOW,
                'timeout': 1800,  # 30 minutes
                'max_retries': 5
            },
            '/api/site/{site_id}/photos/deep-zoom/start-background': {
                'enable_queue': True,
                'priority': RequestPriority.LOW,
                'timeout': 300,
                'max_retries': 2
            }
        })
        
        # CRITICO: User rate limiting con lock per race conditions
        self.user_requests: Dict[str, Dict[str, Any]] = {}
        self._user_requests_lock = asyncio.Lock()
        
        # CRITICO: Distributed rate limiting con Redis fallback
        self._distributed_rate_limiting = True
        self._redis_available = False
        self._redis_client = None
        
        # Bypass paths (not queued)
        self.bypass_paths = {
            '/health', '/login', '/logout', '/auth-test',
            '/static/', '/docs', '/openapi.json', '/favicon.ico',
            '/api/v1/deepzoom/'  # Remove rate limiting for deepzoom endpoints
        }
        
        # Initialize queue service (moved to app.py startup)
        # asyncio.create_task(self._initialize_queue_service())
        
        # Initialize distributed rate limiting
        asyncio.create_task(self._initialize_distributed_rate_limiting())
    
    async def _initialize_queue_service(self):
        """Initialize the queue service"""
        try:
            await request_queue_service.start()
            logger.info("Queue service initialized by middleware")
        except Exception as e:
            logger.error(f"Failed to initialize queue service: {e}")
    
    async def _initialize_distributed_rate_limiting(self):
        """Initialize distributed rate limiting with Redis fallback"""
        
        try:
            # Try to import Redis
            import redis
            from app.core.config import get_settings
            
            settings = get_settings()
            
            # Try to connect to Redis
            try:
                self._redis_client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                
                # Test connection
                self._redis_client.ping()
                self._redis_available = True
                self._distributed_rate_limiting = True
                
                logger.info("Distributed rate limiting initialized with Redis")
                
            except Exception as e:
                logger.warning(f"Redis not available for distributed rate limiting: {e}")
                self._redis_available = False
                self._distributed_rate_limiting = False
                
        except ImportError:
            logger.warning("Redis not installed, falling back to local rate limiting")
            self._redis_available = False
            self._distributed_rate_limiting = False
    
    async def _check_distributed_rate_limit(self, request: Request):
        """Check distributed rate limiting with Redis fallback"""
        
        if not self._distributed_rate_limiting or not self._redis_available:
            # Fallback to local rate limiting
            return await self._check_rate_limit(request)
        
        # Get user identifier
        user_id = await self._get_user_id(request)
        if not user_id:
            return  # No rate limiting for unauthenticated requests
        
        # Get rate limit for this request type
        request_type = self._get_request_type(request)
        rate_limit = self.rate_limits.get(request_type, self.rate_limits['default'])
        
        # Redis key for this user and request type
        redis_key = f"rate_limit:{user_id}:{request_type}"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self._redis_client.pipeline()
            
            # Get current count and window start
            current_time = time.time()
            window_start = current_time - rate_limit['window']
            
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            pipe.expire(redis_key, rate_limit['window'] + 60)  # Add extra time for safety
            
            results = pipe.execute()
            current_count = results[1] if len(results) > 1 else 0
            
            # Check if under limit
            if current_count < rate_limit['requests']:
                # Add current request
                self._redis_client.zadd(redis_key, {str(current_time): str(current_time)})
                self._redis_client.expire(redis_key, rate_limit['window'] + 60)
            else:
                logger.warning(f"Distributed rate limit exceeded for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Distributed rate limit exceeded. Maximum {rate_limit['requests']} requests per {rate_limit['window']} seconds."
                )
                
        except Exception as e:
            logger.error(f"Distributed rate limiting error: {e}")
            # Fallback to local rate limiting on error
            return await self._check_rate_limit(request)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through queue if needed"""
        
        # Check if path should bypass queue
        if self._should_bypass_queue(request):
            return await call_next(request)
        
        # Get queue settings for this path
        queue_setting = self._get_queue_setting(request)
        
        if not queue_setting or not queue_setting.get('enable_queue', False):
            # No queueing, apply rate limiting only
            await self._check_rate_limit(request)
            return await call_next(request)
        
        # Apply rate limiting (distributed or local)
        if self._distributed_rate_limiting and self._redis_available:
            await self._check_distributed_rate_limit(request)
        else:
            await self._check_rate_limit(request)
        
        # Check if we should queue this request
        if await self._should_queue_request(request):
            return await self._handle_queued_request(request, queue_setting)
        
        # Check if system is overloaded ONLY for immediate processing
        # (not for queued requests which are designed to handle overload)
        system_overloaded = request_queue_service.system_monitor.is_system_overloaded()
        if system_overloaded:
            logger.warning(f"System overloaded, rejecting request to {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="System temporarily overloaded. Please try again later."
            )
        
        # Process immediately
        return await call_next(request)
    
    def _should_bypass_queue(self, request: Request) -> bool:
        """Check if request should bypass queue"""
        
        path = request.url.path
        
        # Check exact matches
        if path in self.bypass_paths:
            return True
        
        # Check prefix matches
        for bypass_path in self.bypass_paths:
            if bypass_path.endswith('/') and path.startswith(bypass_path):
                return True
        
        # Check for WebSocket
        if request.headers.get("upgrade", "").lower() == "websocket":
            return True
        
        # Only queue POST, PUT, PATCH requests
        if request.method not in ['POST', 'PUT', 'PATCH']:
            return True
        
        return False
    
    def _get_queue_setting(self, request: Request) -> Optional[Dict[str, Any]]:
        """Get queue setting for request path"""
        
        path = request.url.path
        
        # Exact match
        if path in self.queue_settings:
            return self.queue_settings[path]
        
        # Pattern match for path parameters
        for pattern, setting in self.queue_settings.items():
            if self._path_matches_pattern(path, pattern):
                return setting
        
        return None
    
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
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
    
    async def _check_rate_limit(self, request: Request):
        """Check rate limiting for user with burst capacity support"""
        
        # Get user identifier
        user_id = await self._get_user_id(request)
        if not user_id:
            return  # No rate limiting for unauthenticated requests
        
        # Get rate limit for this request type
        request_type = self._get_request_type(request)
        rate_limit = self.rate_limits.get(request_type, self.rate_limits['default'])
        
        # Initialize user tracking if needed
        if user_id not in self.user_requests:
            self.user_requests[user_id] = {}
        
        user_type_requests = self.user_requests[user_id]
        
        # Initialize request type tracking
        if request_type not in user_type_requests:
            user_type_requests[request_type] = {
                'requests': [],
                'burst_tokens': rate_limit.get('burst', rate_limit['requests']),  # Start with full burst capacity
                'last_refill': time.time()
            }
        
        # Clean old requests outside window
        current_time = time.time()
        window_start = current_time - rate_limit['window']
        
        user_type_requests[request_type]['requests'] = [
            req_time for req_time in user_type_requests[request_type]['requests']
            if req_time > window_start
        ]
        
        # Refill burst tokens based on time elapsed
        time_since_last_refill = current_time - user_type_requests[request_type]['last_refill']
        refill_rate = rate_limit['requests'] / rate_limit['window']  # Tokens per second
        tokens_to_add = time_since_last_refill * refill_rate
        max_burst = rate_limit.get('burst', rate_limit['requests'])
        
        user_type_requests[request_type]['burst_tokens'] = min(
            max_burst,
            user_type_requests[request_type]['burst_tokens'] + tokens_to_add
        )
        user_type_requests[request_type]['last_refill'] = current_time
        
        # Check if we have enough burst tokens or are within the base rate limit
        base_requests = len(user_type_requests[request_type]['requests'])
        has_burst_token = user_type_requests[request_type]['burst_tokens'] > 0
        
        if base_requests >= rate_limit['requests'] and not has_burst_token:
            logger.warning(f"Rate limit exceeded for user {user_id} on {request_type}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {rate_limit['requests']} requests per {rate_limit['window']} seconds."
            )
        
        # Consume a burst token if we're over the base rate limit
        if base_requests >= rate_limit['requests'] and has_burst_token:
            user_type_requests[request_type]['burst_tokens'] -= 1
            logger.info(f"Using burst token for user {user_id} on {request_type}. Tokens remaining: {user_type_requests[request_type]['burst_tokens']}")
        
        # Add current request
        user_type_requests[request_type]['requests'].append(current_time)
    
    async def _get_user_id(self, request: Request) -> Optional[str]:
        """Get user ID from request, prioritizing authenticated user ID"""
        
        # Try to get authenticated user ID from request state or headers
        try:
            # Check if user ID is available in request state (set by auth middleware)
            if hasattr(request.state, 'user_id') and request.state.user_id:
                return str(request.state.user_id)
            
            # Check for user ID in headers (for API requests)
            user_id_header = request.headers.get('X-User-ID')
            if user_id_header:
                return user_id_header
                
            # Check for authorization header and try to extract user info
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                # In a real implementation, you would decode the JWT token
                # For now, we'll use a placeholder approach
                try:
                    from app.core.security import decode_access_token
                    token = auth_header.split(' ')[1]
                    payload = decode_access_token(token)
                    if payload and 'sub' in payload:
                        return str(payload['sub'])
                except Exception:
                    # Token decode failed, fall back to IP
                    pass
            
            # Fallback to IP address for unauthenticated requests
            return request.client.host
            
        except Exception:
            return request.client.host
    
    def _get_request_type(self, request: Request) -> str:
        """Get request type for rate limiting"""
        
        path = request.url.path
        
        if 'upload' in path:
            return 'upload'
        else:
            return 'default'
    
    async def _should_queue_request(self, request: Request) -> bool:
        """Determine if request should be queued"""
        
        # Check system load
        load_factor = request_queue_service.system_monitor.get_load_factor()
        
        # Queue if system is under moderate load (lowered threshold for better responsiveness)
        if load_factor > 0.2:
            return True
        
        # Check if system is overloaded - always queue in this case
        if request_queue_service.system_monitor.is_system_overloaded():
            logger.info(f"System overloaded, queueing request to {request.url.path}")
            return True
        
        # Check queue sizes
        queue_status = await request_queue_service.get_queue_status()
        
        # Queue if there are already many requests (production threshold)
        queue_threshold = 3  # Lowered threshold for better load management
        
        if queue_status['active_requests'] > queue_threshold:
            return True
        
        # Check if this is a bulk operation
        if 'bulk' in request.url.path:
            return True
        
        # Always queue upload requests during high load periods
        if 'upload' in request.url.path and load_factor > 0.1:
            return True
        
        # Production behavior - no special handling for stress tests
        
        return False
    
    async def _handle_queued_request(self, request: Request, queue_setting: Dict[str, Any]) -> Response:
        """Handle request through queue"""
        
        # Extract request data
        request_data = await self._extract_request_data(request)
        
        # Get user and site info
        user_id = await self._get_user_id(request)
        site_id = request_data.get('site_id')
        
        # Determine priority
        priority = queue_setting.get('priority', RequestPriority.NORMAL)
        
        # Override priority based on system load
        if request_queue_service.system_monitor.is_system_overloaded():
            priority = RequestPriority.LOW
        
        # Enqueue request
        try:
            request_id = await request_queue_service.enqueue_request(
                request_type=f"{request.method}_{request.url.path}",
                payload=request_data,
                priority=priority,
                user_id=user_id,
                site_id=site_id,
                timeout_seconds=queue_setting.get('timeout', 300),
                max_retries=queue_setting.get('max_retries', 3),
                callback_url=request_data.get('callback_url')
            )
            
            logger.info(f"Queued request {request_id} for {request.url.path}")
            
            # Return immediate response with request ID
            return JSONResponse({
                'message': 'Request queued for processing',
                'request_id': request_id,
                'status': 'queued',
                'priority': priority.name,
                'estimated_wait': await self._estimate_wait_time(priority)
            }, status_code=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Failed to queue request: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to queue request: {str(e)}"
            )
    
    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """Extract data from request for queue processing"""
        
        request_data = {
            'method': request.method,
            'path': request.url.path,
            'query_params': dict(request.query_params),
            'headers': dict(request.headers),
            'client': {
                'host': request.client.host,
                'port': request.client.port
            }
        }
        
        # Extract body for POST/PUT/PATCH
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                # Handle form data
                if request.headers.get('content-type', '').startswith('multipart/form-data'):
                    form_data = await request.form()
                    request_data['form_data'] = {
                        key: value.filename if hasattr(value, 'filename') else str(value)
                        for key, value in form_data.items()
                    }
                else:
                    # Handle JSON data
                    body = await request.body()
                    if body:
                        try:
                            request_data['json_data'] = json.loads(body.decode())
                        except json.JSONDecodeError:
                            request_data['body'] = body.decode()
            except Exception as e:
                logger.warning(f"Failed to extract request body: {e}")
        
        # Extract path parameters
        path_params = request.path_params
        if path_params:
            request_data['path_params'] = path_params
            if 'site_id' in path_params:
                request_data['site_id'] = str(path_params['site_id'])
        
        return request_data
    
    async def _estimate_wait_time(self, priority: RequestPriority) -> float:
        """Estimate wait time for priority level"""
        
        queue_status = await request_queue_service.get_queue_status()
        
        # Get queue size for this priority and lower priorities
        total_waiting = 0
        for p in RequestPriority:
            if p.value >= priority.value:
                total_waiting += queue_status['queue_sizes'].get(p.name, 0)
        
        # Estimate based on average processing time
        avg_processing_time = queue_status['metrics']['average_processing_time']
        concurrent_limit = queue_status['concurrent_limit']
        
        # Rough estimate: (total_waiting / concurrent_limit) * avg_processing_time
        estimated_wait = (total_waiting / max(1, concurrent_limit)) * avg_processing_time
        
        return max(0, estimated_wait)


class QueueStatusMiddleware(BaseHTTPMiddleware):
    """Middleware to add queue status to responses"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add queue status headers to response"""
        
        response = await call_next(request)
        
        # Add queue status headers
        try:
            queue_status = await request_queue_service.get_queue_status()
            
            response.headers['X-Queue-Active'] = str(queue_status['active_requests'])
            response.headers['X-Queue-Completed'] = str(queue_status['completed_requests'])
            response.headers['X-Queue-Failed'] = str(queue_status['failed_requests'])
            response.headers['X-System-Load'] = f"{queue_status['system_load']['cpu_percent']:.1f}%"
            response.headers['X-Concurrent-Limit'] = str(queue_status['concurrent_limit'])
            
        except Exception as e:
            logger.warning(f"Failed to add queue status headers: {e}")
        
        return response


# Request handlers for queued requests
async def upload_request_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handler for queued upload requests - CALLS REAL UPLOAD LOGIC"""

    logger.info(f"Processing queued upload request: {payload.get('path')}")

    try:
        # Import the real upload handler from sites_photos
        from app.routes.api.sites_photos import process_queued_upload

        # Call the real upload processing logic
        result = await process_queued_upload(payload)

        logger.info(f"Queued upload completed successfully: {result.get('message', 'No message')}")
        return result

    except Exception as e:
        logger.error(f"Error in queued upload handler: {e}")
        raise Exception(f"Upload processing failed: {str(e)}")


async def bulk_upload_request_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handler for queued bulk upload requests - CALLS REAL BULK UPLOAD LOGIC"""

    logger.info(f"Processing queued bulk upload request: {payload.get('path')}")

    try:
        # Import the real bulk upload handler from bulk_upload_handler module
        from app.routes.api.bulk_upload_handler import process_queued_bulk_upload

        # Call the real bulk upload processing logic
        result = await process_queued_bulk_upload(payload)

        logger.info(f"Queued bulk upload completed successfully: {result.get('message', 'No message')}")
        return result

    except Exception as e:
        logger.error(f"Error in queued bulk upload handler: {e}")
        raise Exception(f"Bulk upload processing failed: {str(e)}")


# Register handlers
def register_queue_handlers():
    """Register request handlers with queue service"""

    request_queue_service.register_handler('POST_/api/site/{site_id}/photos/upload', upload_request_handler)
    request_queue_service.register_handler('POST_/api/site/{site_id}/photos/bulk-upload', bulk_upload_request_handler)

    # Register deep zoom processing handler
    from app.services.deep_zoom_background_service import deep_zoom_background_service
    if hasattr(deep_zoom_background_service, 'process_queued_deep_zoom'):
        request_queue_service.register_handler('POST_/api/site/{site_id}/photos/deep-zoom/start-background', deep_zoom_background_service.process_queued_deep_zoom)

    logger.info("Queue request handlers registered")
    