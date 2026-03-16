from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from loguru import logger


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    🔧 FIXED: Exception handler that properly handles API vs web routes
    
    BEFORE: API endpoints with 401 were redirected to /login (causing 307 redirect loop)
    NOW: API endpoints return JSON responses, only web routes redirect to /login
    """
    route = request.scope.get("path")
    method = request.scope.get("method")
    
    logger.error(
        f"Error in route {method} {route}: {exc.detail} : {exc.status_code}"
    )

    # 🔧 FIXED: Check if it's an API route FIRST before redirecting
    if route and route.startswith("/api/"):
        detail = exc.detail if getattr(exc, "detail", None) is not None else "An error occurred"

        # Manteniamo backward compatibility su "errors" e aggiungiamo "detail"
        # per i client che leggono errorData.detail
        if isinstance(detail, list):
            errors = [str(item) for item in detail]
        elif isinstance(detail, dict):
            errors = [str(detail.get("message") or detail)]
        else:
            errors = [str(detail)]

        # For API routes, return JSON response instead of redirecting
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "valid": False,
                "detail": detail,
                "errors": errors,
                "schema_type": None,
                "level": None,
                "validation_timestamp": "2025-10-01T14:56:49.482Z"
            }
        )
    
    # 🔧 FIXED: Only redirect to login for non-API routes with 401 status
    if exc and exc.status_code == 401:
        return RedirectResponse("/login")
    
    # 🔧 FIXED: Handle other exceptions for non-API routes
    # elif request.scope.get("path") == "/auth/jwt/login" and exc.status_code == 400:
    #     return templates.TemplateResponse("pages/login.html", {"request": request, "error": "Incorrect username or password"})
    
    # For other non-API routes, return plain text
    return Response(content="Error managed via HTTP module", status_code=exc.status_code)
