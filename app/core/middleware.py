# app/core/middleware.py - Middleware per Cross-Cutting Concerns
"""
Middleware per FastAPI - Implementazione tecnica #8

Centralizza logging, audit, performance monitoring e security headers.
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

# Import per audit
from app.database.session import get_async_session
from app.models import UserActivity
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware per logging centralizzato delle richieste

    Registra tutte le richieste HTTP con timing e informazioni utente.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        # Log richiesta entrante
        user_id = getattr(request.state, 'user_id', None) if hasattr(request, 'state') else None
        logger.info(f"→ {request.method} {request.url.path} - User: {user_id}")

        try:
            # Processa richiesta
            response = await call_next(request)

            # Calcola tempo processamento
            process_time = time.time() - start_time

            # Log risposta
            if process_time > 5.0:
                logger.warning(f"→ {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s (SLOW)")
            elif process_time > 1.0:
                logger.info(f"→ {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
            else:
                logger.debug(f"→ {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
            return response

        except Exception as e:
            process_time = time.time() - start_time
            
            # Safe error logging with null checking and fallback
            error_msg = "Unknown error"
            if e is not None:
                try:
                    error_msg = str(e)
                except Exception:
                    # If string conversion fails, use exception type
                    error_msg = f"{type(e).__name__} (string conversion failed)"
            
            logger.error(f"❌ Request failed: {request.method} {request.url.path} - {process_time:.3f}s - Error: {error_msg}")
            raise


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware per audit trail delle operazioni

    Registra automaticamente attività utente nel database.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Estrai informazioni per audit
        user_id = getattr(request.state, 'user_id', None) if hasattr(request, 'state') else None
        site_id = getattr(request.state, 'site_id', None) if hasattr(request, 'state') else None

        # Log attività se utente autenticato
        if user_id and self._should_audit_request(request):
            await self._log_request_activity(
                user_id=user_id,
                site_id=site_id,
                method=request.method,
                path=request.url.path,
                query=str(request.url.query),
                user_agent=request.headers.get('user-agent'),
                ip=self._get_client_ip(request)
            )

        response = await call_next(request)
        return response

    def _should_audit_request(self, request: Request) -> bool:
        """Determina se la richiesta deve essere auditata"""
        # Audit solo per operazioni di scrittura/modifica
        audit_methods = {'POST', 'PUT', 'DELETE', 'PATCH'}
        if request.method not in audit_methods:
            return False

        # Escludi endpoint tecnici
        exclude_paths = {'/health', '/metrics', '/docs', '/redoc', '/openapi.json'}
        if any(request.url.path.startswith(path) for path in exclude_paths):
            return False

        return True

    async def _log_request_activity(
        self,
        user_id: UUID,
        site_id: UUID = None,
        method: str = None,
        path: str = None,
        query: str = None,
        user_agent: str = None,
        ip: str = None
    ):
        """Registra attività nel database"""
        try:
            # Ottieni sessione DB
            # Nota: In middleware non abbiamo accesso diretto a Depends,
            # quindi creiamo una sessione temporanea
            from app.database.base import async_session_maker as async_session_factory

            async with async_session_factory() as db:
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
                        "timestamp": time.time()
                    }
                )

                db.add(activity)
                await db.commit()

        except Exception as e:
            logger.warning(f"Audit logging failed: {e}")

    def _get_client_ip(self, request: Request) -> str:
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


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware per monitoraggio performance

    Traccia richieste lente e raccoglie metriche.
    """

    def __init__(self, app: Callable, slow_query_threshold: float = 2.0):
        super().__init__(app)
        self.slow_query_threshold = slow_query_threshold
        self.metrics = {
            'request_count': 0,
            'slow_requests': 0,
            'average_response_time': 0.0,
            'total_response_time': 0.0
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        self.metrics['request_count'] += 1

        response = await call_next(request)

        process_time = time.time() - start_time

        # Aggiorna metriche
        self.metrics['total_response_time'] += process_time
        self.metrics['average_response_time'] = (
            self.metrics['total_response_time'] / self.metrics['request_count']
        )

        # Log richieste lente
        if process_time > self.slow_query_threshold:
            self.metrics['slow_requests'] += 1
            logger.warning(
                f"SLOW REQUEST: {request.method} {request.url.path} "
                f"- {process_time:.3f}s (threshold: {self.slow_query_threshold}s)"
            )

        # Log metriche ogni 100 richieste
        if self.metrics['request_count'] % 100 == 0:
            self._log_performance_metrics()

        return response

    def _log_performance_metrics(self):
        """Log metriche performance"""
        logger.info(
            f"Performance metrics - Requests: {self.metrics['request_count']}, "
            f"Avg response time: {self.metrics['average_response_time']:.3f}s, "
            f"Slow requests: {self.metrics['slow_requests']}"
        )

    def get_metrics(self) -> dict:
        """Restituisce metriche correnti"""
        return self.metrics.copy()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware per security headers

    Aggiunge headers di sicurezza standard a tutte le risposte.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        # Content Security Policy base
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "media-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )
        response.headers['Content-Security-Policy'] = csp

        return response


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
        max_age: int = 86400
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or ["http://localhost:3000", "http://localhost:8000"]
        self.allow_credentials = allow_credentials
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allow_headers = allow_headers or [
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With"
        ]
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
            response.headers['Access-Control-Max-Age'] = str(self.max_age)

        return response

    def _is_allowed_origin(self, origin: str) -> bool:
        """Verifica se l'origine è consentita"""
        return origin in self.allow_origins or '*' in self.allow_origins


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware per rate limiting base

    Implementazione semplice in-memory (per produzione usare Redis).
    """

    def __init__(self, app: Callable, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = {}  # In produzione: usare Redis

    async def dispatch(self, request: Request, call_next) -> Response:
        # Identifica client (IP-based per semplicità)
        client_id = self._get_client_identifier(request)

        # Verifica rate limit
        if not self._check_rate_limit(client_id):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "message": "Rate limit exceeded. Try again later.",
                    "retry_after": 60
                }
            )

        response = await call_next(request)
        return response

    def _get_client_identifier(self, request: Request) -> str:
        """Estrai identificatore client"""
        # Prima controlla se utente autenticato (da state o user)
        user_id = None
        if hasattr(request, 'state') and hasattr(request.state, 'user_id'):
            user_id = request.state.user_id
        elif hasattr(request, 'user') and request.user:
            user_id = getattr(request.user, 'id', None)

        if user_id:
            return f"user_{user_id}"

        # Fallback a IP
        return f"ip_{request.client.host if request.client else 'unknown'}"

    def _check_rate_limit(self, client_id: str) -> bool:
        """Verifica se il client è entro i limiti"""
        import time

        current_time = int(time.time() / 60)  # Finestra per minuto

        if client_id not in self.requests:
            self.requests[client_id] = {}

        # Pulisce vecchie richieste
        self.requests[client_id] = {
            window: count
            for window, count in self.requests[client_id].items()
            if window >= current_time - 5  # Mantieni ultime 5 finestre
        }

        # Conta richieste nella finestra corrente
        current_count = self.requests[client_id].get(current_time, 0)

        if current_count >= self.requests_per_minute:
            return False

        # Incrementa contatore
        self.requests[client_id][current_time] = current_count + 1
        return True