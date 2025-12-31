"""
Centralized Exception Handlers for FastZoom Application

This module provides handlers that convert domain exceptions to appropriate
HTTP responses, following the presentation layer separation principle.
"""

from typing import Union
from fastapi import Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger

from app.core.domain_exceptions import (
    DomainException,
    get_status_code,
    AuthenticationError,
    AuthorizationError,
)


async def domain_exception_handler(
    request: Request, 
    exc: DomainException
) -> Union[JSONResponse, RedirectResponse]:
    """
    Handle domain exceptions and convert them to appropriate HTTP responses.
    
    This handler:
    1. Logs the exception with context
    2. Determines if it's an API or web request
    3. Returns JSON for API routes, redirects/HTML for web routes
    4. Uses the exception's status code mapping
    
    Args:
        request: FastAPI request object
        exc: Domain exception instance
        
    Returns:
        JSONResponse for API routes, RedirectResponse for web routes
    """
    # Get request context
    route_path = request.scope.get("path", "")
    method = request.scope.get("method", "")
    
    # Get status code from exception
    status_code = get_status_code(exc)
    
    # Log the exception with full context
    logger.error(
        f"Domain exception in {method} {route_path}",
        extra={
            "exception_type": type(exc).__name__,
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "status_code": status_code,
            "route": route_path,
            "method": method,
        },
        exc_info=True
    )
    
    # Check if it's an API route
    is_api_route = route_path.startswith("/api/")
    
    if is_api_route:
        # API routes: return JSON response
        return JSONResponse(
            status_code=status_code,
            content={
                "valid": False,
                "error_code": exc.error_code,
                "errors": [exc.message],
                "details": exc.details,
            }
        )
    else:
        # Web routes: handle based on exception type
        return await handle_web_route_exception(request, exc, status_code)


async def handle_web_route_exception(
    request: Request,
    exc: DomainException,
    status_code: int
) -> Union[JSONResponse, RedirectResponse]:
    """
    Handle exceptions for web routes (non-API).
    
    Args:
        request: FastAPI request object
        exc: Domain exception instance
        status_code: HTTP status code
        
    Returns:
        Appropriate response for web routes
    """
    # Authentication errors: redirect to login
    if isinstance(exc, AuthenticationError):
        logger.info(f"Authentication failed, redirecting to login: {exc.message}")
        return RedirectResponse(
            url="/login",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Authorization errors: show forbidden page or redirect
    if isinstance(exc, AuthorizationError):
        logger.warning(f"Authorization failed: {exc.message}")
        # You could render a 403 template here
        return JSONResponse(
            status_code=status_code,
            content={
                "error": exc.message,
                "error_code": exc.error_code
            }
        )
    
    # Other exceptions: return JSON for now
    # TODO: Render appropriate HTML templates based on exception type
    return JSONResponse(
        status_code=status_code,
        content={
            "error": exc.message,
            "error_code": exc.error_code,
            "details": exc.details
        }
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle Pydantic validation exceptions.
    
    This converts Pydantic's RequestValidationError to a consistent format.
    
    Args:
        request: FastAPI request object
        exc: Validation exception
        
    Returns:
        JSONResponse with validation errors
    """
    from fastapi.exceptions import RequestValidationError
    
    if isinstance(exc, RequestValidationError):
        route_path = request.scope.get("path", "")
        
        logger.warning(
            f"Validation error in {route_path}",
            extra={
                "errors": exc.errors(),
                "body": exc.body if hasattr(exc, 'body') else None,
            }
        )
        
        # Format validation errors
        errors = []
        for error in exc.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            errors.append(f"{field}: {error['msg']}")
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "valid": False,
                "error_code": "VALIDATION_ERROR",
                "errors": errors,
                "details": {"validation_errors": exc.errors()}
            }
        )
    
    # Fallback for other validation errors
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "valid": False,
            "error_code": "VALIDATION_ERROR",
            "errors": [str(exc)],
        }
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle unexpected exceptions that aren't domain exceptions.
    
    This is a safety net for exceptions that slip through.
    
    Args:
        request: FastAPI request object
        exc: Exception instance
        
    Returns:
        JSONResponse with generic error
    """
    route_path = request.scope.get("path", "")
    method = request.scope.get("method", "")
    
    logger.exception(
        f"Unexpected exception in {method} {route_path}",
        extra={
            "exception_type": type(exc).__name__,
            "route": route_path,
            "method": method,
        }
    )
    
    # Check if it's an API route
    is_api_route = route_path.startswith("/api/")
    
    if is_api_route:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "valid": False,
                "error_code": "INTERNAL_ERROR",
                "errors": ["An unexpected error occurred"],
                "details": {
                    "exception_type": type(exc).__name__
                }
            }
        )
    else:
        # For web routes, could render an error template
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "An unexpected error occurred",
                "error_code": "INTERNAL_ERROR"
            }
        )


def register_exception_handlers(app):
    """
    Register all exception handlers with the FastAPI app.
    
    This should be called during app initialization.
    
    Args:
        app: FastAPI application instance
    """
    from fastapi.exceptions import RequestValidationError
    
    # Register domain exception handler
    app.add_exception_handler(DomainException, domain_exception_handler)
    
    # Register validation exception handler
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # Register generic exception handler (catches all Exception)
    # NOTE: This should be registered last as it's the most generic
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("Exception handlers registered successfully")