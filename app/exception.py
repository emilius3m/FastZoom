from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from loguru import logger


async def http_exception_handler(request: Request, exc: HTTPException):
    if exc and exc.status_code == 401:
        return RedirectResponse("/login")
    # elif request.scope.get("path") == "/auth/jwt/login" and exc.status_code == 400:
    #     return templates.TemplateResponse("pages/login.html", {"request": request, "error": "Incorrect username or password"})
    else:
        route = request.scope.get("path")
        method = request.scope.get("method")
        logger.error(
            f"Error in route {method} {route}: {exc.detail} : {exc.status_code}"
        )

        # For API routes, return JSON response
        if route.startswith("/api/"):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "valid": False,
                    "errors": [exc.detail or "An error occurred"],
                    "schema_type": None,
                    "level": None,
                    "validation_timestamp": "2025-10-01T14:56:49.482Z"
                }
            )

        # For other routes, return plain text
        return Response(content="Error managed via HTTP module", status_code=exc.status_code)
