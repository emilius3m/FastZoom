"""
Pipecat Voice Assistant API Routes

WebSocket endpoint for real-time voice communication and
REST endpoints for assistant management.
"""

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.core.pipecat_settings import pipecat_settings
from app.services.pipecat_service import pipecat_service, PIPECAT_AVAILABLE
from app.services.pipecat_functions import register_all_handlers
from app.database.security import get_current_active_user
from app.database.db import get_async_session
from app.models.users import User
# Structured voice command system
from app.services.voice_tools_registry import (
    get_tool_descriptions_for_llm,
    is_tool_whitelisted,
    get_tool,
    validate_tool_args,
    log_voice_execution,
    NAVIGATION_TOOLS,
    ToolCategory,
)
from app.schemas.voice_commands import (
    VoiceCommand,
    VoiceCommandPlan,
    VoiceCommandResult,
    CommandIntent,
    UIAction,
    UIActionType,
)
from app.services.voice_execute import execute_voice_command, _handle_navigation_tool


router = APIRouter(prefix="/pipecat", tags=["Voice Assistant"])


# Response models
class StatusResponse(BaseModel):
    """Voice assistant status response."""
    available: bool
    pipecat_installed: bool
    configured: bool
    enabled: bool
    active_sessions: int
    language: str
    model: str


class FunctionCallRequest(BaseModel):
    """Request to execute a function via voice command."""
    function_name: str
    arguments: dict
    site_id: Optional[str] = None


class FunctionCallResponse(BaseModel):
    """Response from function execution."""
    success: bool
    data: Optional[dict] = None
    message: Optional[str] = None
    action: Optional[str] = None


# Register function handlers on module load
if PIPECAT_AVAILABLE:
    register_all_handlers()


@router.get("/status", response_model=StatusResponse)
async def get_voice_assistant_status():
    """
    Get the status of the voice assistant service.
    
    Returns:
        Status information including availability, configuration,
        and active sessions.
    """
    return StatusResponse(**pipecat_service.status)


@router.post("/function", response_model=FunctionCallResponse)
async def execute_function(
    request: FunctionCallRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Execute a voice command function directly (for testing).
    
    Args:
        request: Function name and arguments
        current_user: Authenticated user
        
    Returns:
        Function execution result
    """
    if not pipecat_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Voice assistant not available. Check configuration."
        )
    
    site_id = UUID(request.site_id) if request.site_id else None
    
    result = await pipecat_service.handle_function_call(
        function_name=request.function_name,
        arguments=request.arguments,
        user_id=current_user.id,
        site_id=site_id
    )
    
    if result.get("error"):
        return FunctionCallResponse(
            success=False,
            message=result.get("message", "Unknown error")
        )
    
    return FunctionCallResponse(
        success=True,
        data=result,
        message=result.get("message"),
        action=result.get("action")
    )


def _build_voice_system_prompt(tool_descriptions: list, site_id: Optional[str]) -> str:
    """
    Build the system prompt for voice command interpretation.
    Forces the LLM to use tools instead of responding with text.
    """
    # Separate navigation and API tools
    nav_tools = [t for t in tool_descriptions if t.get('category') == 'navigation']
    api_tools = [t for t in tool_descriptions if t.get('category') != 'navigation'][:20]
    
    # Helper to format tool string
    def fmt(t):
        base = f"  - {t['name']}: {t['description']}"
        params = t.get('parameters', {})
        if params:
            # Flatten params for concise prompt
            p_list = [f"{k}" for k, v in params.items()]
            base += f" (richiede: {', '.join(p_list)})"
        return base

    nav_list = "\n".join([fmt(t) for t in nav_tools])
    api_list = "\n".join([fmt(t) for t in api_tools])
    
    return f"""Sei un INTERPRETE DI COMANDI per FastZoom. Traduci comandi vocali in JSON strutturato.

⚠️ REGOLE:
1. NON rispondere MAI con testo libero o con la tua conoscenza
2. OGNI risposta DEVE essere un JSON strutturato
3. Se l'utente chiede dati dell'app, USA il tool appropriato

CONTESTO: Sito ID = {site_id or 'NESSUNO'}

NAVIGAZIONE (action_type: "navigate"):
{nav_list}

API (action_type: "api_call"):
{api_list}

MAPPATURA COMANDI:
"vai ai siti" / "mostrami i siti" → {{"action_type": "navigate", "tool": "nav_goto_sites"}}
"vai alle foto" → {{"action_type": "navigate", "tool": "nav_goto_photos"}}
"vai al giornale" → {{"action_type": "navigate", "tool": "nav_goto_giornale"}}
"lista siti" / "quali siti ci sono" → {{"action_type": "api_call", "tool": "v1_get_sites_list"}}
"aggiorna" → {{"action_type": "navigate", "tool": "nav_refresh"}}
"torna indietro" → {{"action_type": "navigate", "tool": "nav_go_back"}}
"seleziona tutto" → {{"action_type": "navigate", "tool": "ui_select_all"}}
"carica foto" → {{"action_type": "navigate", "tool": "nav_create_element", "args": {{"element_type": "photo"}} }}
"elimina selezionati" → {{"action_type": "navigate", "tool": "ui_delete_selected"}}

FORMATO RISPOSTA (obbligatorio):
{{"action_type": "navigate"|"api_call", "tool": "tool_name", "args": {{}}, "explain": "breve descrizione"}}"""


async def _process_voice_input(
    websocket: WebSocket,
    llm,
    messages_history: list,
    text: str,
    site_id: Optional[str]
) -> None:
    """
    Process voice/text input using the structured command system.
    
    1. Send input to LLM with structured system prompt
    2. Parse JSON response to get tool/action
    3. Execute navigation or API call
    4. Send result back to frontend
    """
    import re
    
    messages_history.append({"role": "user", "content": text})
    await websocket.send_json({"type": "status", "text": "Elaborazione..."})
    
    try:
        # Get LLM response (should be JSON)
        response_text = await llm.simple_chat(messages_history)
        
        # Try to parse JSON from response
        command = _parse_llm_json_response(response_text)
        
        if command:
            action_type = command.get("action_type")
            tool_name = command.get("tool")
            args = command.get("args", {})
            explain = command.get("explain", "Comando eseguito")
            
            # Add site_id to args if needed
            if site_id and "site_id" not in args:
                args["site_id"] = site_id
            
            if action_type == "navigate" and tool_name:
                # Handle navigation
                tool = get_tool(tool_name)
                if tool and tool.category == ToolCategory.NAVIGATION:
                    result = _handle_navigation_tool(tool, args, UUID(site_id) if site_id else None)
                    
                    # Send full result to frontend (handled by handleCommandResult -> executeUIAction)
                    await websocket.send_json({
                        "type": "command_result",
                        "result": result.model_dump()
                    })
                    
                    await websocket.send_json({
                        "type": "response",
                        "text": result.message or explain
                    })
                else:
                    await websocket.send_json({
                        "type": "response", 
                        "text": f"Navigazione: {explain}"
                    })
            
            elif action_type == "api_call" and tool_name:
                # Handle API call via execute_voice_command
                if is_tool_whitelisted(tool_name):
                    voice_cmd = VoiceCommand(
                        intent=CommandIntent.API_CALL,
                        tool=tool_name,
                        args=args,
                        explain=explain
                    )
                    
                    # Note: For now, just describe what we would do
                    # Full execution requires auth token which we don't have in WS
                    await websocket.send_json({
                        "type": "response",
                        "text": f"Comando: {explain} (usa HTTP /voice/execute per eseguire)"
                    })
                else:
                    await websocket.send_json({
                        "type": "response",
                        "text": f"Tool non disponibile: {tool_name}"
                    })
            else:
                # Unknown action, send explanation
                await websocket.send_json({
                    "type": "response",
                    "text": explain or response_text[:200]
                })
        else:
            # Could not parse JSON, send raw response
            messages_history.append({"role": "assistant", "content": response_text})
            await websocket.send_json({
                "type": "response",
                "text": response_text
            })
            
    except Exception as e:
        logger.error(f"Voice input processing error: {e}")
        await websocket.send_json({
            "type": "response",
            "text": f"Errore: {str(e)}"
        })


def _parse_llm_json_response(response: str) -> Optional[dict]:
    """Try to extract JSON from LLM response."""
    import re
    import json as json_lib
    
    # Try direct JSON parse
    try:
        return json_lib.loads(response.strip())
    except:
        pass
    
    # Try to find JSON in response
    json_match = re.search(r'\{[^{}]*\}', response)
    if json_match:
        try:
            return json_lib.loads(json_match.group())
        except:
            pass
    
    return None


@router.websocket("/stream")
async def voice_stream(
    websocket: WebSocket,
    token: Optional[str] = None
):
    """
    WebSocket endpoint for real-time voice streaming.
    Uses local AI services (Whisper STT + Ollama LLM).
    """
    await websocket.accept()
    session_id = str(id(websocket))
    
    logger.info(f"Voice assistant WebSocket connected: {session_id}")
    
    if not pipecat_service.is_available:
        await websocket.send_json({
            "type": "error",
            "message": "Voice assistant not configured."
        })
        await websocket.close(code=1008)
        return
    
    try:
        # Import local services
        from app.services.pipecat_local_services import LocalWhisperSTT, LocalOllamaLLM, LOCAL_AI_AVAILABLE
        
        if not LOCAL_AI_AVAILABLE:
            await websocket.send_json({
                "type": "error",
                "message": "Local AI dependencies not installed (ollama, whisper)"
            })
            await websocket.close(code=1008)
            return
        
        # Initialize services - medium model for quality/speed balance
        stt = LocalWhisperSTT(model="medium", device="auto", language="it")
        llm = LocalOllamaLLM(model="qwen2.5:7b")  # Good for function calling + Italian
        
        # Load model asynchronously (singleton, non-blocking)
        model_ready = await stt.ensure_model_loaded()
        if not model_ready:
            await websocket.send_json({
                "type": "error", 
                "message": "Whisper model failed to load"
            })
            await websocket.close(code=1008)
            return
        
        # Wait for init message
        init_msg = await websocket.receive_json()
        if init_msg.get("type") != "init":
            await websocket.close(code=1002)
            return
        
        # Extract site_id from init message (sent by frontend)
        current_site_id = init_msg.get("site_id")
        logger.info(f"Voice session {session_id} - site_id: {current_site_id}")

        await websocket.send_json({
            "type": "ready",
            "session_id": session_id,
            "message": "Assistente Locale Pronto (Whisper/Ollama)"
        })
        
        # Build structured system prompt for function calling
        tool_descriptions = get_tool_descriptions_for_llm()
        messages_history = [{"role": "system", "content": _build_voice_system_prompt(tool_descriptions, current_site_id)}]
        
        while True:
            try:
                message = await websocket.receive()
                
                if "bytes" in message:
                    # Process Audio
                    audio_data = message["bytes"]
                    
                    # Add to STT buffer
                    ready = stt.add_audio(audio_data)
                    
                    if ready:
                        # Transcribe
                        result = await stt.transcribe()
                        
                        if result and result.text:
                            # Send transcript
                            await websocket.send_json({
                                "type": "transcript",
                                "text": result.text,
                                "is_final": True
                            })
                            
                            # Process with new structured command system
                            await _process_voice_input(
                                websocket, llm, messages_history, 
                                result.text, current_site_id
                            )
                            
                elif "text" in message:
                    # Handle text commands
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "close":
                        break
                    elif msg_type == "text":
                        # Direct text input - process with structured commands
                        text = data.get("text", "")
                        if text:
                            await _process_voice_input(
                                websocket, llm, messages_history,
                                text, current_site_id
                            )
                        
            except WebSocketDisconnect:
                break
                
    except Exception as e:
        logger.error(f"Voice loop error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        await pipecat_service.cleanup_session(session_id)
        logger.info(f"Voice session closed: {session_id}")
