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
from app.models.users import User


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
        
        # Initialize services
        stt = LocalWhisperSTT(model="base", device="auto", language="it")
        llm = LocalOllamaLLM(model="llama3.2:3b")
        
        if not stt.is_ready:
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

        await websocket.send_json({
            "type": "ready",
            "session_id": session_id,
            "message": "Assistente Locale Pronto (Whisper/Ollama)"
        })
        
        # Message history for LLM context
        messages_history = [{"role": "system", "content": "Sei un assistente utile per FastZoom, un sistema di documentazione archeologica. Rispondi in italiano in modo conciso."}]
        
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
                            
                            # Check for voice commands first
                            from app.services.voice_commands import parse_voice_command
                            cmd = parse_voice_command(result.text)
                            
                            if cmd["is_command"]:
                                # Send command to frontend
                                await websocket.send_json({
                                    "type": "command",
                                    "action": cmd["action"],
                                    "target": cmd["target"],
                                    "params": cmd["params"]
                                })
                                # Send response text
                                await websocket.send_json({
                                    "type": "response",
                                    "text": cmd["response_text"]
                                })
                            else:
                                # Not a command - use LLM
                                messages_history.append({"role": "user", "content": result.text})
                                await websocket.send_json({"type": "status", "text": "Elaborazione..."})
                                response_text = await llm.simple_chat(messages_history)
                                messages_history.append({"role": "assistant", "content": response_text})
                                await websocket.send_json({
                                    "type": "response",
                                    "text": response_text
                                })
                            
                elif "text" in message:
                    # Handle text commands
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "close":
                        break
                    elif msg_type == "text":
                        # Direct text input (for testing)
                        text = data.get("text", "")
                        if text:
                            messages_history.append({"role": "user", "content": text})
                            response_text = await llm.simple_chat(messages_history)
                            messages_history.append({"role": "assistant", "content": response_text})
                            await websocket.send_json({
                                "type": "response",
                                "text": response_text
                            })
                        
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
