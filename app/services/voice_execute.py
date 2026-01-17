"""
Voice Command Execution Service

Executes validated voice commands by calling existing API endpoints
via ASGI transport (in-process). This ensures:
- No network dependency (works with reverse proxy, multiprocess, etc.)
- All authorization is handled by the endpoint
- No direct database access
- Code reuse of existing validation logic
"""

from typing import Optional, Dict, Any
from uuid import UUID

import httpx
from loguru import logger

from app.schemas.voice_commands import (
    VoiceCommand,
    VoiceCommandResult,
    CommandIntent,
    UIAction,
    UIActionType,
)
from app.services.voice_tools_registry import (
    get_tool,
    build_path,
    VoiceTool,
    ToolCategory,
)
from app.models.users import User


def _get_asgi_client() -> httpx.AsyncClient:
    """
    Create an httpx client using ASGI transport for in-process calls.
    
    This avoids network dependency and works correctly with:
    - Reverse proxies
    - Uvicorn multiprocess
    - Docker deployments
    """
    from app.app import app as fastapi_app
    
    transport = httpx.ASGITransport(app=fastapi_app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def execute_voice_command(
    command: VoiceCommand,
    user: User,
    site_id: Optional[UUID],
    auth_token: str,
) -> VoiceCommandResult:
    """
    Execute a validated voice command via ASGI call to existing endpoint.
    
    This function:
    1. Gets the tool from registry
    2. Builds the API path
    3. Makes in-process call to existing endpoint (with user's auth)
    4. Returns result with optional UI actions
    
    Args:
        command: The validated VoiceCommand
        user: Current user (for logging)
        site_id: Current site context
        auth_token: User's JWT token for authorization
    """
    if command.intent != CommandIntent.API_CALL:
        return VoiceCommandResult(
            success=False,
            error="Only API_CALL intent is supported for execution"
        )
    
    if not command.tool:
        return VoiceCommandResult(
            success=False,
            error="No tool specified"
        )
    
    tool = get_tool(command.tool)
    if not tool:
        return VoiceCommandResult(
            success=False,
            error=f"Tool '{command.tool}' not found"
        )
    
    # Handle navigation tools (no API call, just UI actions)
    if tool.category == ToolCategory.NAVIGATION:
        return _handle_navigation_tool(tool, command.args, site_id)
    
    # Security: Only allow whitelisted methods (no DELETE)
    if tool.http_method not in ("GET", "POST", "PUT"):
        return VoiceCommandResult(
            success=False,
            error=f"HTTP method '{tool.http_method}' not allowed for voice commands"
        )
    
    try:
        # Add site_id to args if site-scoped and not present
        args = dict(command.args)
        if tool.site_scoped and site_id and "site_id" not in args:
            args["site_id"] = str(site_id)
        
        # Build the API path
        path = build_path(command.tool, args)
        if not path:
            return VoiceCommandResult(
                success=False,
                error=f"Could not build path for tool '{command.tool}'"
            )
        
        # Execute via ASGI transport (in-process)
        result = await _execute_asgi_request(tool, path, args, auth_token)
        
        # Build UI actions based on tool and result
        ui_actions = _build_ui_actions(tool, result, site_id)
        
        logger.info(
            f"Voice command executed: user={user.id}, tool={command.tool}, "
            f"success={result.get('_success', True)}"
        )
        
        return VoiceCommandResult(
            success=result.get("_success", True),
            data=result.get("data", result),
            message=_format_result_message(tool, result),
            error=result.get("_error"),
            ui_actions=ui_actions if ui_actions else None,
        )
        
    except Exception as e:
        logger.error(f"Voice command execution error: {e}")
        return VoiceCommandResult(
            success=False,
            error=str(e)
        )


async def _execute_asgi_request(
    tool: VoiceTool,
    path: str,
    args: Dict[str, Any],
    auth_token: str,
) -> Dict[str, Any]:
    """
    Execute request via ASGI transport (in-process, no network).
    
    Uses the user's auth token to ensure proper authorization.
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    
    # Also set cookie for endpoints that check cookies
    cookies = {"access_token": auth_token}
    
    # Build query params (non-path, non-body args)
    query_params = {}
    for param in tool.query_params:
        if param in args:
            query_params[param] = args[param]
    
    # Get body if present
    body = args.get("body")
    
    async with _get_asgi_client() as client:
        client.cookies = cookies
        
        try:
            if tool.http_method == "GET":
                response = await client.get(path, headers=headers, params=query_params)
            elif tool.http_method == "POST":
                response = await client.post(path, headers=headers, json=body, params=query_params)
            elif tool.http_method == "PUT":
                response = await client.put(path, headers=headers, json=body, params=query_params)
            else:
                # Should not reach here due to earlier check
                return {"_success": False, "_error": f"Method not allowed: {tool.http_method}"}
            
            # Parse response
            if response.status_code >= 400:
                error_detail = _extract_error_detail(response)
                return {
                    "_success": False,
                    "_error": error_detail,
                    "_status_code": response.status_code
                }
            
            # Parse JSON response
            try:
                data = response.json()
            except Exception:
                data = {"raw": response.text}
            
            return {
                "_success": True,
                "data": data,
                "_status_code": response.status_code
            }
            
        except httpx.TimeoutException:
            return {"_success": False, "_error": "Request timeout"}


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract error message from HTTP response."""
    try:
        data = response.json()
        if isinstance(data, dict):
            return data.get("detail", data.get("message", str(data)))
        return str(data)
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:200]}"


# =============================================================================
# NAVIGATION TOOL HANDLER
# =============================================================================

# URL mappings for navigation tools
NAVIGATION_URL_MAP: Dict[str, str] = {
    "nav_goto_sites": "/",
    "nav_goto_giornale": "/giornale",
    "nav_goto_cantieri": "/cantieri",
    "nav_goto_analisi": "/analisi",
    "nav_refresh": "/_refresh",
    "nav_go_back": "/_back",
}


def _handle_navigation_tool(
    tool: VoiceTool,
    args: Dict[str, Any],
    site_id: Optional[UUID],
) -> VoiceCommandResult:
    """
    Handle navigation tools - return UI actions without HTTP call.
    """
    operation_id = tool.operation_id
    
    # Special handling for site-specific navigation
    if operation_id == "nav_goto_site":
        site_name = args.get("site_name", "")
        return VoiceCommandResult(
            success=True,
            message=f"Navigazione al sito: {site_name}",
            ui_actions=[
                UIAction(action=UIActionType.TOAST, message=f"Cercando sito: {site_name}", level="info"),
                # Frontend will search and navigate
            ]
        )
    
    # Site-scoped navigation (photos, us, harris, documents, dashboard)
    if operation_id in ("nav_goto_photos", "nav_goto_us", "nav_goto_harris", 
                        "nav_goto_documents", "nav_goto_dashboard"):
        nav_site_id = args.get("site_id") or (str(site_id) if site_id else None)
        if not nav_site_id:
            return VoiceCommandResult(
                success=False,
                error="Nessun sito selezionato. Prima seleziona un sito."
            )
        
        path_map = {
            "nav_goto_photos": "/photos",
            "nav_goto_us": "/us",
            "nav_goto_harris": "/harris-matrix",
            "nav_goto_documents": "/documents",
            "nav_goto_dashboard": "/dashboard",
        }
        path = path_map[operation_id]
        url = f"/view/{nav_site_id}{path}"
        
        return VoiceCommandResult(
            success=True,
            message=tool.description,
            ui_actions=[
                UIAction(action=UIActionType.NAVIGATE, url=url),
            ]
        )
    
    # Global navigation
    if operation_id in NAVIGATION_URL_MAP:
        url = NAVIGATION_URL_MAP[operation_id]
        
        # Special cases
        if url == "/_refresh":
            return VoiceCommandResult(
                success=True,
                message="Aggiornamento pagina",
                ui_actions=[UIAction(action=UIActionType.NAVIGATE, url="javascript:location.reload()")]
            )
        if url == "/_back":
            return VoiceCommandResult(
                success=True,
                message="Torno indietro",
                ui_actions=[UIAction(action=UIActionType.NAVIGATE, url="javascript:history.back()")]
            )
        
        return VoiceCommandResult(
            success=True,
            message=tool.description,
            ui_actions=[
                UIAction(action=UIActionType.NAVIGATE, url=url),
            ]
        )
    
    return VoiceCommandResult(
        success=False,
        error=f"Navigation tool '{operation_id}' not implemented"
    )


# =============================================================================
# UI ACTIONS - Enhanced with navigation
# =============================================================================

# API Tools that should trigger navigation after execution
API_TOOLS_WITH_NAVIGATION: Dict[str, str] = {
    "get_site_photos": "/photos",
    "search_photos_by_metadata": "/photos",
    "v1_get_site_documents": "/documents",
    "v1_list_us": "/us",
    "v1_get_us": "/us/{us_id}",
    "v1_list_usm": "/usm",
    "v1_get_usm": "/usm/{usm_id}",
    "v1_generate_harris_matrix": "/harris-matrix",
    "v1_get_matrix_statistics": "/harris-matrix",
    "get_form_schemas": "/form-schemas",
}


def _build_ui_actions(
    tool: VoiceTool, 
    result: Dict[str, Any],
    site_id: Optional[UUID],
) -> list:
    """
    Build UI actions based on tool and result.
    
    Includes:
    - Toast notification (success/error)
    - Navigation for specific tools
    """
    actions = []
    
    if result.get("_success", True):
        # Toast success
        actions.append(UIAction(
            action=UIActionType.TOAST,
            message=f"✓ {tool.description}",
            level="success"
        ))
        
        # Add navigation for specific tools
        if tool.operation_id in API_TOOLS_WITH_NAVIGATION and site_id:
            nav_path = API_TOOLS_WITH_NAVIGATION[tool.operation_id]
            
            # Substitute placeholders from result data
            data = result.get("data", {})
            if "{us_id}" in nav_path and "id" in data:
                nav_path = nav_path.replace("{us_id}", data["id"])
            if "{usm_id}" in nav_path and "id" in data:
                nav_path = nav_path.replace("{usm_id}", data["id"])
            
            actions.append(UIAction(
                action=UIActionType.NAVIGATE,
                url=f"/view/{site_id}{nav_path}"
            ))
    else:
        # Toast error
        actions.append(UIAction(
            action=UIActionType.TOAST,
            message=f"✗ {result.get('_error', 'Errore')}",
            level="error"
        ))
    
    return actions


def _format_result_message(tool: VoiceTool, result: Dict[str, Any]) -> str:
    """Format a human-readable result message."""
    
    if not result.get("_success", True):
        return result.get("_error", "Operazione fallita")
    
    data = result.get("data", result)
    
    if isinstance(data, dict):
        if "count" in data:
            return f"Trovati {data['count']} risultati"
        
        if "sites" in data:
            return f"Trovati {len(data['sites'])} siti"
        
        if "photos" in data:
            return f"Trovate {len(data['photos'])} foto"
        
        if "documents" in data:
            return f"Trovati {len(data['documents'])} documenti"
        
        if "us" in data:
            return f"Trovate {len(data['us'])} unità stratigrafiche"
        
        if "valid" in data:
            return "Validazione completata" if data["valid"] else "Validazione fallita"
        
        if "updated" in data or "id" in data:
            return "Operazione completata con successo"
    
    return f"{tool.description} completato"
