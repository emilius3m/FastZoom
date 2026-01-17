"""
Voice Control API Endpoints

HTTP endpoints for voice command planning and execution.
These provide a REST interface to the voice control system,
complementing the WebSocket interface for real-time streaming.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from app.database.security import get_current_active_user
from app.models.users import User
from app.schemas.voice_commands import (
    VoiceCommand,
    VoiceCommandPlan,
    VoiceCommandResult,
    VoicePlanRequest,
    VoiceExecuteRequest,
    CommandIntent,
    UIAction,
    UIActionType,
)
from app.services.voice_tools_registry import (
    get_tool,
    is_tool_whitelisted,
    validate_tool_args,
    log_voice_execution,
    get_tool_descriptions_for_llm,
    VOICE_TOOLS_REGISTRY,
)
from app.services.voice_execute import execute_voice_command


router = APIRouter(prefix="/voice", tags=["Voice Control"])


# =============================================================================
# PLAN ENDPOINT
# =============================================================================

@router.post("/plan", response_model=VoiceCommandPlan)
async def plan_voice_command(
    request: VoicePlanRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Parse voice/text input and produce a structured command plan.
    
    This endpoint:
    1. Takes natural language input
    2. Uses LLM to interpret intent
    3. Returns a VoiceCommandPlan with the structured command
    
    The frontend can then:
    - Display the interpretation to the user
    - Request confirmation if required
    - Execute via /voice/execute
    """
    try:
        logger.info(f"Voice plan request from user {current_user.id}: {request.text[:100]}")
        
        # Import LLM service
        from app.services.pipecat_local_services import LocalOllamaLLM, LOCAL_AI_AVAILABLE
        
        if not LOCAL_AI_AVAILABLE:
            return VoiceCommandPlan(
                success=False,
                error="Local AI services not available"
            )
        
        # Initialize LLM
        llm = LocalOllamaLLM(model="qwen2.5:7b")
        
        # Build context for LLM
        context = {
            "site_id": request.site_id,
            "current_page": request.current_page,
            "current_entity": request.current_entity,
        }
        
        # Get tool descriptions for LLM
        tool_descriptions = get_tool_descriptions_for_llm()
        
        # Create system prompt with structured output constraint
        system_prompt = _build_planning_system_prompt(tool_descriptions, context)
        
        # Call LLM for interpretation
        llm_result = await llm.chat_with_functions(
            request.text,
            functions=[{
                "type": "function",
                "function": {
                    "name": "execute_voice_command",
                    "description": "Execute a voice command from the whitelist",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "intent": {
                                "type": "string",
                                "enum": ["api_call", "ui_action", "clarify"]
                            },
                            "tool": {
                                "type": "string",
                                "description": "operationId from the tool list"
                            },
                            "args": {
                                "type": "object",
                                "description": "Tool arguments"
                            },
                            "explain": {
                                "type": "string",
                                "description": "Brief explanation in Italian"
                            }
                        },
                        "required": ["intent"]
                    }
                }
            }],
            system_prompt=system_prompt
        )
        
        # Parse LLM response into VoiceCommand
        command = _parse_llm_to_command(llm_result, request.site_id)
        
        if command:
            # Validate tool if API call
            if command.intent == CommandIntent.API_CALL and command.tool:
                if not is_tool_whitelisted(command.tool):
                    return VoiceCommandPlan(
                        success=False,
                        error=f"Tool '{command.tool}' not in whitelist"
                    )
                
                # Validate args
                is_valid, error = validate_tool_args(command.tool, command.args)
                if not is_valid:
                    return VoiceCommandPlan(
                        success=False,
                        error=error
                    )
                
                # Set requires_confirmation from registry
                tool = get_tool(command.tool)
                if tool:
                    command.requires_confirmation = tool.requires_confirmation
            
            return VoiceCommandPlan(
                success=True,
                command=command,
                interpretation=command.explain
            )
        else:
            return VoiceCommandPlan(
                success=False,
                error="Could not interpret the command"
            )
        
    except Exception as e:
        logger.error(f"Voice plan error: {e}")
        return VoiceCommandPlan(
            success=False,
            error=str(e)
        )


# =============================================================================
# EXECUTE ENDPOINT
# =============================================================================

@router.post("/execute", response_model=VoiceCommandResult)
async def execute_planned_command(
    request: VoiceExecuteRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """
    Execute a planned voice command.
    
    This endpoint:
    1. Validates the command is whitelisted
    2. Checks user authorization
    3. Enforces confirmation for write operations
    4. Executes the command
    5. Returns result with UI actions
    """
    command = request.command
    site_id = UUID(request.site_id) if request.site_id else None
    
    logger.info(
        f"Voice execute: user={current_user.id}, "
        f"intent={command.intent}, tool={command.tool}"
    )
    
    try:
        # Handle different intents
        if command.intent == CommandIntent.API_CALL:
            # Validate tool
            if not command.tool or not is_tool_whitelisted(command.tool):
                log_voice_execution(
                    user_id=current_user.id,
                    site_id=site_id,
                    transcript="",
                    operation_id=command.tool or "unknown",
                    args=command.args,
                    success=False,
                    error="Tool not whitelisted"
                )
                return VoiceCommandResult(
                    success=False,
                    error=f"Tool '{command.tool}' not allowed"
                )
            
            # Get tool definition
            tool = get_tool(command.tool)
            
            # Enforce confirmation
            if tool.requires_confirmation and not request.confirmed:
                return VoiceCommandResult(
                    success=False,
                    error="Confirmation required for this operation",
                    message=f"Conferma richiesta: {command.explain}"
                )
            
            # Get auth token from request
            auth_token = _extract_auth_token(http_request)
            
            # Execute the tool via HTTP
            result = await execute_voice_command(
                command=command,
                user=current_user,
                site_id=site_id,
                auth_token=auth_token,
            )
            
            # Log execution
            log_voice_execution(
                user_id=current_user.id,
                site_id=site_id,
                transcript=command.explain,
                operation_id=command.tool,
                args=command.args,
                success=result.success,
                error=result.error
            )
            
            return result
            
        elif command.intent == CommandIntent.UI_ACTION:
            # UI actions are executed by frontend, just return them
            return VoiceCommandResult(
                success=True,
                ui_actions=command.ui_actions,
                message=command.explain
            )
            
        elif command.intent == CommandIntent.CLARIFY:
            return VoiceCommandResult(
                success=True,
                message=command.clarification_prompt or "Puoi essere più specifico?"
            )
        
        else:
            return VoiceCommandResult(
                success=False,
                error=f"Unknown intent: {command.intent}"
            )
            
    except Exception as e:
        logger.error(f"Voice execute error: {e}")
        log_voice_execution(
            user_id=current_user.id,
            site_id=site_id,
            transcript=command.explain if command else "",
            operation_id=command.tool if command else "unknown",
            args=command.args if command else {},
            success=False,
            error=str(e)
        )
        return VoiceCommandResult(
            success=False,
            error=str(e)
        )


# =============================================================================
# TOOLS LIST ENDPOINT
# =============================================================================

@router.get("/tools")
async def list_voice_tools(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    List available voice command tools.
    
    Useful for debugging and understanding what commands are available.
    """
    tools = []
    for tool_id, tool in VOICE_TOOLS_REGISTRY.items():
        if category and tool.category.value != category:
            continue
        tools.append({
            "operation_id": tool.operation_id,
            "description": tool.description,
            "category": tool.category.value,
            "http_method": tool.http_method,
            "requires_confirmation": tool.requires_confirmation,
            "read_only": tool.read_only,
        })
    
    return {
        "tools": tools,
        "total": len(tools)
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_auth_token(request: Request) -> str:
    """
    Extract the auth token from the request.
    
    Checks both cookie and Authorization header.
    """
    # Try cookie first (browser requests)
    token = request.cookies.get("access_token")
    if token:
        return token
    
    # Try Authorization header (API requests)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Return empty string - the HTTP call will fail with 401
    return ""


def _build_planning_system_prompt(tool_descriptions: list, context: dict) -> str:
    """Build system prompt for command planning."""
    
    # Format tool list
    tool_list = "\n".join([
        f"- {t['name']}: {t['description']}"
        for t in tool_descriptions[:30]  # Limit to avoid token overflow
    ])
    
    site_context = f"Site ID: {context.get('site_id', 'nessuno')}"
    page_context = f"Current page: {context.get('current_page', 'unknown')}"
    
    return f"""Sei un interprete di comandi vocali per FastZoom, un sistema di documentazione archeologica.

CONTESTO:
{site_context}
{page_context}

STRUMENTI DISPONIBILI:
{tool_list}

ISTRUZIONI:
1. Interpreta il comando dell'utente in italiano
2. Se l'utente vuole navigare, usa intent="ui_action"
3. Se l'utente vuole dati, usa intent="api_call" con il tool appropriato
4. Se non capisci, usa intent="clarify"
5. Rispondi SOLO con la function call, non con testo

IMPORTANTE: Il campo 'explain' deve essere una breve descrizione in italiano di cosa farai."""


def _parse_llm_to_command(llm_result: dict, site_id: Optional[str]) -> Optional[VoiceCommand]:
    """Parse LLM function call result into VoiceCommand."""
    
    if "function_call" in llm_result:
        func = llm_result["function_call"]
        params = func.get("parameters", {})
        
        intent_str = params.get("intent", "clarify")
        try:
            intent = CommandIntent(intent_str)
        except ValueError:
            intent = CommandIntent.CLARIFY
        
        # Build args with site_id if needed
        args = params.get("args", {})
        if site_id and "site_id" not in args:
            args["site_id"] = site_id
        
        return VoiceCommand(
            intent=intent,
            tool=params.get("tool"),
            args=args,
            explain=params.get("explain", ""),
            requires_confirmation=False,  # Will be set from registry
        )
    
    elif "response" in llm_result:
        # LLM responded with text instead of function call
        # Treat as clarification or navigation
        response_text = llm_result["response"]
        
        # Check for navigation keywords
        nav_keywords = {
            "foto": "/photos",
            "dashboard": "/dashboard",
            "giornale": "/giornale",
            "mappa": "/map",
            "matrix": "/harris-matrix",
            "us": "/us",
        }
        
        for keyword, path in nav_keywords.items():
            if keyword in response_text.lower():
                return VoiceCommand(
                    intent=CommandIntent.UI_ACTION,
                    explain=response_text,
                    ui_actions=[
                        UIAction(
                            action=UIActionType.NAVIGATE,
                            url=f"/view/{site_id}{path}" if site_id else path
                        )
                    ]
                )
        
        # Default to clarification
        return VoiceCommand(
            intent=CommandIntent.CLARIFY,
            explain=response_text,
            clarification_prompt=response_text
        )
    
    return None
