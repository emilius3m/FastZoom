# app/core/middleware.py - Middleware per Cross-Cutting Concerns

"""
Centralizza logging, audit, performance monitoring e security headers.
"""

import time
import json
from typing import Callable, Optional, Dict, Any
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

# Import per audit from centralized engine
from app.database.engine import AsyncSessionLocal as async_session_maker
from app.models import UserActivity
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# CONFIGURAZIONE MIDDLEWARE
# ============================================================================

class MiddlewareConfig:
    """Configurazione centralizzata per middleware"""
    
    # Performance monitoring
    SLOW_REQUEST_THRESHOLD = 2.0  # secondi
    LOG_METRICS_EVERY_N_REQUESTS = 100
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE = 1000
    RATE_LIMIT_WINDOW_SIZE = 5  # finestre da mantenere
    
    # Audit
    AUDIT_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}
    EXCLUDE_AUDIT_PATHS = {'/health', '/metrics', '/docs', '/redoc', '/openapi.json', '/api/v1/deepzoom/'}
    
    # Security Headers
    CSP_POLICY = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net blob:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self' data: https://cdn.jsdelivr.net https://tessdata.projectnaptha.com; "
        "media-src 'self'; "
        "object-src 'none'; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none';"
    )
    
    # CORS
    CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:8000"]
    CORS_MAX_AGE = 86400  # 24 ore
    
    # Request ID
    REQUEST_ID_HEADER = "X-Request-ID"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_request_state(request: Request, key: str, default: Any = None) -> Any:
    """Helper per estrarre valori da request.state in modo sicuro"""
    if not hasattr(request, 'state'):
        return default
    return getattr(request.state, key, default)


def get_client_ip(request: Request) -> str:
    """Estrai IP client considerando proxy"""
    # Check for forwarded headers
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get('x-real-ip')
    if real_ip:
        return real_ip
    
    # Fallback to direct client
    return request.client.host if request.client else 'unknown'


def get_client_identifier(request: Request) -> str:
    """Estrai identificatore univoco del client"""
    # Prima controlla se utente autenticato
    user_id = get_request_state(request, 'user_id')
    if user_id:
        return f"user_{user_id}"
    
    # Fallback a IP
    return f"ip_{get_client_ip(request)}"


def format_request_log(
    method: str,
    path: str,
    status_code: int = None,
    duration: float = None,
    user_id: str = None,
    request_id: str = None
) -> str:
    """Formatta log richiesta in modo consistente"""
    parts = [f"{method} {path}"]
    
    if request_id:
        parts.append(f"[{request_id[:8]}]")
    
    if user_id:
        parts.append(f"User:{user_id}")
    
    if status_code:
        parts.append(str(status_code))
    
    if duration is not None:
        parts.append(f"{duration:.3f}s")
        if duration > MiddlewareConfig.SLOW_REQUEST_THRESHOLD:
            parts.append("⚠️ SLOW")
    
    return " - ".join(parts)


# ============================================================================
# REQUEST ID MIDDLEWARE
# ============================================================================

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware per tracciamento richieste con ID univoco
    Aggiunge X-Request-ID a ogni richiesta/risposta
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Genera o usa request ID esistente
        request_id = request.headers.get(
            MiddlewareConfig.REQUEST_ID_HEADER,
            str(uuid4())
        )
        
        # Salva in request.state per altri middleware
        request.state.request_id = request_id
        
        # Processa richiesta
        response = await call_next(request)
        
        # Aggiungi header alla risposta
        response.headers[MiddlewareConfig.REQUEST_ID_HEADER] = request_id
        
        return response


# ============================================================================
# UNIFIED LOGGING & PERFORMANCE MIDDLEWARE
# ============================================================================

class UnifiedLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware unificato per logging e performance monitoring
    Combina RequestLoggingMiddleware e PerformanceMonitoringMiddleware
    """
    
    def __init__(
        self,
        app: Callable,
        slow_threshold: float = MiddlewareConfig.SLOW_REQUEST_THRESHOLD
    ):
        super().__init__(app)
        self.slow_threshold = slow_threshold
        
        # Metriche (in produzione: usare Redis o Prometheus)
        self.metrics = {
            'total_requests': 0,
            'slow_requests': 0,
            'failed_requests': 0,
            'total_duration': 0.0,
            'requests_by_method': defaultdict(int),
            'requests_by_status': defaultdict(int)
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # Estrai info comuni
        user_id = get_request_state(request, 'user_id')
        request_id = get_request_state(request, 'request_id')
        
        # Log richiesta entrante (solo INFO, non per ogni richiesta)
        if request.url.path not in MiddlewareConfig.EXCLUDE_AUDIT_PATHS:
            logger.debug(f"→ {format_request_log(request.method, request.url.path, user_id=user_id, request_id=request_id)}")
        
        try:
            # Processa richiesta
            response = await call_next(request)
            
            # Calcola metriche
            duration = time.time() - start_time
            self._update_metrics(request.method, response.status_code, duration, failed=False)
            
            # Log risposta con livello appropriato
            self._log_response(
                request.method,
                request.url.path,
                response.status_code,
                duration,
                user_id,
                request_id
            )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            self._update_metrics(request.method, 500, duration, failed=True)
            
            # Log errore
            error_msg = str(e) if e else "Unknown error"
            logger.error(
                f"❌ {format_request_log(request.method, request.url.path, 500, duration, user_id, request_id)} "
                f"Error: {error_msg}"
            )
            raise
    
    def _update_metrics(self, method: str, status_code: int, duration: float, failed: bool):
        """Aggiorna metriche performance"""
        self.metrics['total_requests'] += 1
        self.metrics['total_duration'] += duration
        self.metrics['requests_by_method'][method] += 1
        self.metrics['requests_by_status'][status_code] += 1
        
        if duration > self.slow_threshold:
            self.metrics['slow_requests'] += 1
        
        if failed or status_code >= 500:
            self.metrics['failed_requests'] += 1
        
        # Log metriche periodicamente
        if self.metrics['total_requests'] % MiddlewareConfig.LOG_METRICS_EVERY_N_REQUESTS == 0:
            self._log_metrics()
    
    def _log_response(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        user_id: str,
        request_id: str
    ):
        """Log risposta con livello appropriato"""
        log_msg = format_request_log(method, path, status_code, duration, user_id, request_id)
        
        # Escludi endpoint tecnici da log normale
        if path in MiddlewareConfig.EXCLUDE_AUDIT_PATHS:
            return
        
        # Determina livello log
        if status_code >= 500:
            logger.error(f"❌ {log_msg}")
        elif status_code >= 400:
            logger.warning(f"⚠️ {log_msg}")
        elif duration > MiddlewareConfig.SLOW_REQUEST_THRESHOLD:
            logger.warning(f"🐌 {log_msg}")
        elif duration > 1.0:
            logger.info(f"← {log_msg}")
        else:
            logger.debug(f"← {log_msg}")
    
    def _log_metrics(self):
        """Log metriche aggregate"""
        avg_duration = (
            self.metrics['total_duration'] / self.metrics['total_requests']
            if self.metrics['total_requests'] > 0
            else 0
        )
        
        logger.info(
            f"📊 Metrics - Requests: {self.metrics['total_requests']}, "
            f"Avg: {avg_duration:.3f}s, "
            f"Slow: {self.metrics['slow_requests']}, "
            f"Failed: {self.metrics['failed_requests']}"
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Restituisce snapshot metriche correnti"""
        metrics = self.metrics.copy()
        metrics['requests_by_method'] = dict(metrics['requests_by_method'])
        metrics['requests_by_status'] = dict(metrics['requests_by_status'])
        
        if metrics['total_requests'] > 0:
            metrics['average_duration'] = metrics['total_duration'] / metrics['total_requests']
        else:
            metrics['average_duration'] = 0.0
        
        return metrics


# ============================================================================
# AUDIT MIDDLEWARE
# ============================================================================

class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware per audit trail delle operazioni
    Registra automaticamente attività utente nel database.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Estrai informazioni per audit
        user_id = get_request_state(request, 'user_id')
        site_id = get_request_state(request, 'site_id')
        request_id = get_request_state(request, 'request_id')
        
        # Log attività se utente autenticato e richiesta deve essere auditata
        should_audit = (
            user_id and 
            self._should_audit_request(request)
        )
        
        if should_audit:
            # Non bloccare la risposta per l'audit - fire and forget
            # In produzione: usa task queue (Celery, ARQ, ecc.)
            try:
                await self._log_request_activity(
                    user_id=user_id,
                    site_id=site_id,
                    method=request.method,
                    path=request.url.path,
                    query=str(request.url.query) if request.url.query else None,
                    user_agent=request.headers.get('user-agent'),
                    ip=get_client_ip(request),
                    request_id=request_id
                )
            except Exception as e:
                # Non fallire la richiesta se audit fallisce
                logger.warning(f"Audit logging failed for request {request_id}: {e}")
        
        response = await call_next(request)
        return response
    
    def _should_audit_request(self, request: Request) -> bool:
        """Determina se la richiesta deve essere auditata"""
        # Audit solo per operazioni di scrittura/modifica
        if request.method not in MiddlewareConfig.AUDIT_METHODS:
            return False
        
        # Escludi endpoint tecnici
        if any(request.url.path.startswith(path) for path in MiddlewareConfig.EXCLUDE_AUDIT_PATHS):
            return False
        
        return True
    
    async def _log_request_activity(
        self,
        user_id: UUID,
        site_id: Optional[UUID] = None,
        method: str = None,
        path: str = None,
        query: str = None,
        user_agent: str = None,
        ip: str = None,
        request_id: str = None
    ):
        """Registra attività nel database"""
        try:
            async with async_session_maker() as db:
                activity = UserActivity(
                    user_id=user_id,
                    site_id=site_id,
                    activity_type="API_ACCESS",
                    activity_desc=f"{method} {path}",
                    extra_data={
                        "method": method,
                        "path": path,
                        "query": query,
                        "user_agent": user_agent,
                        "ip": ip,
                        "request_id": request_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
                
                db.add(activity)
                await db.commit()
                
        except Exception as e:
            logger.error(f"Failed to log audit activity: {e}")
            # Non propagare l'errore


# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware per security headers
    Aggiunge headers di sicurezza standard a tutte le risposte.
    """
    
    def __init__(self, app: Callable, strict_csp: bool = False):
        super().__init__(app)
        self.strict_csp = strict_csp
    
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Security headers base
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Content Security Policy
        if self.strict_csp:
            # CSP più restrittivo per produzione
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none';"
            )
        else:
            csp = MiddlewareConfig.CSP_POLICY
        
        response.headers['Content-Security-Policy'] = csp
        
        # HSTS per HTTPS (solo se su HTTPS)
        if request.url.scheme == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response


# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

class CORSMiddleware(BaseHTTPMiddleware):
    """
    Middleware CORS personalizzato
    Gestisce CORS con configurazione specifica per archeological API.
    """
    
    def __init__(
        self,
        app: Callable,
        allow_origins: list = None,
        allow_credentials: bool = True,
        allow_methods: list = None,
        allow_headers: list = None,
        expose_headers: list = None,
        max_age: int = MiddlewareConfig.CORS_MAX_AGE
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or MiddlewareConfig.CORS_ALLOWED_ORIGINS
        self.allow_credentials = allow_credentials
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
        self.allow_headers = allow_headers or [
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            MiddlewareConfig.REQUEST_ID_HEADER
        ]
        self.expose_headers = expose_headers or [MiddlewareConfig.REQUEST_ID_HEADER]
        self.max_age = max_age
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)
        
        # Add CORS headers
        origin = request.headers.get('origin')
        
        if origin and self._is_allowed_origin(origin):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = str(self.allow_credentials).lower()
            response.headers['Access-Control-Allow-Methods'] = ', '.join(self.allow_methods)
            response.headers['Access-Control-Allow-Headers'] = ', '.join(self.allow_headers)
            response.headers['Access-Control-Expose-Headers'] = ', '.join(self.expose_headers)
            response.headers['Access-Control-Max-Age'] = str(self.max_age)
        
        return response
    
    def _is_allowed_origin(self, origin: str) -> bool:
        """Verifica se l'origine è consentita"""
        return origin in self.allow_origins or '*' in self.allow_origins


# ============================================================================
# RATE LIMIT MIDDLEWARE
# ============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware per rate limiting con sliding window
    Implementazione in-memory (per produzione usare Redis).
    """
    
    def __init__(
        self,
        app: Callable,
        requests_per_minute: int = MiddlewareConfig.RATE_LIMIT_PER_MINUTE,
        redis_client = None  # Opzionale: passa client Redis per persistent storage
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.redis_client = redis_client
        
        # Storage in-memory (fallback se Redis non disponibile)
        self.requests: Dict[str, Dict[int, int]] = defaultdict(dict)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting per endpoint tecnici
        if any(request.url.path.startswith(path) for path in MiddlewareConfig.EXCLUDE_AUDIT_PATHS):
            return await call_next(request)
        
        # Identifica client
        client_id = get_client_identifier(request)
        
        # Verifica rate limit
        if not await self._check_rate_limit(client_id):
            retry_after = 60  # secondi
            
            logger.warning(
                f"⛔ Rate limit exceeded for {client_id} - "
                f"{request.method} {request.url.path}"
            )
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "message": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )
        
        response = await call_next(request)
        
        # Aggiungi headers informativi
        response.headers['X-RateLimit-Limit'] = str(self.requests_per_minute)
        # TODO: aggiungere X-RateLimit-Remaining e X-RateLimit-Reset
        
        return response
    
    async def _check_rate_limit(self, client_id: str) -> bool:
        """Verifica se il client è entro i limiti (sliding window)"""
        if self.redis_client:
            return await self._check_rate_limit_redis(client_id)
        else:
            return self._check_rate_limit_memory(client_id)
    
    async def _check_rate_limit_redis(self, client_id: str) -> bool:
        """Rate limiting con Redis (implementazione futura)"""
        # TODO: Implementare con Redis INCR + EXPIRE
        # Vedi: https://redis.io/commands/incr/#pattern-rate-limiter
        pass
    
    def _check_rate_limit_memory(self, client_id: str) -> bool:
        """Rate limiting in-memory (non persistente)"""
        current_window = int(time.time() / 60)  # Finestra per minuto
        
        # Pulisce vecchie finestre
        self.requests[client_id] = {
            window: count
            for window, count in self.requests[client_id].items()
            if window >= current_window - MiddlewareConfig.RATE_LIMIT_WINDOW_SIZE
        }
        
        # Conta richieste nella finestra corrente
        current_count = self.requests[client_id].get(current_window, 0)
        
        if current_count >= self.requests_per_minute:
            return False
        
        # Incrementa contatore
        self.requests[client_id][current_window] = current_count + 1
        return True


# ============================================================================
# HEALTH CHECK UTILITY
# ============================================================================

def create_health_check_endpoint(
    logging_middleware: UnifiedLoggingMiddleware = None,
    rate_limit_middleware: RateLimitMiddleware = None
):
    """
    Factory per creare endpoint health check
    
    Usage in main.py:
        from app.core.middleware import create_health_check_endpoint
        
        @app.get("/health")
        async def health_check():
            return create_health_check_endpoint(
                logging_middleware=app.state.logging_middleware
            )()
    """
    
    def health_check():
        response = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "archaeological-catalog-api"
        }
        
        # Aggiungi metriche se disponibili
        if logging_middleware:
            response["metrics"] = logging_middleware.get_metrics()
        
        return response
    
    return health_check


# ============================================================================
# MIDDLEWARE SETUP HELPER
# ============================================================================

def setup_middleware(app, config: dict = None):
    """
    Helper per configurare tutti i middleware in ordine corretto
    
    Usage in main.py:
        from app.core.middleware import setup_middleware
        
        app = FastAPI()
        setup_middleware(app, {
            'enable_rate_limit': True,
            'enable_audit': True,
            'requests_per_minute': 100
        })
    """
    config = config or {}
    
    # Ordine corretto dei middleware (LIFO - Last In First Out)
    # L'ultimo aggiunto è il primo ad essere eseguito
    
    # 1. Rate limiting (primo check)
    if config.get('enable_rate_limit', True):
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=config.get('requests_per_minute', 2000)  # Increased for development
        )
    
    # 2. CORS
    if config.get('enable_cors', True):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.get('cors_origins')
        )
    
    # 3. Security headers
    if config.get('enable_security_headers', True):
        app.add_middleware(
            SecurityHeadersMiddleware,
            strict_csp=config.get('strict_csp', False)
        )
    
    # 4. Audit logging
    if config.get('enable_audit', True):
        app.add_middleware(AuditMiddleware)
    
    # 5. Unified logging & performance
    logging_mw = UnifiedLoggingMiddleware(
        app,
        slow_threshold=config.get('slow_threshold', 2.0)
    )
    app.add_middleware(UnifiedLoggingMiddleware)
    
    # Salva riferimento per health check
    app.state.logging_middleware = logging_mw
    
    # 6. Request ID (ultimo - eseguito per primo)
    app.add_middleware(RequestIDMiddleware)
    
    logger.debug("Middleware configured")
