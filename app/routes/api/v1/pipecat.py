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
    
    Protocol:
    1. Client connects and sends {"type": "init", "token": "..."}
    2. Server responds with {"type": "ready"} or {"type": "error"}
    3. Client sends audio chunks as binary data
    4. Server sends back:
       - {"type": "transcript", "text": "..."} for STT results
       - {"type": "response", "text": "..."} for LLM text
       - {"type": "audio", "data": "..."} for TTS audio (base64)
       - {"type": "function", "name": "...", "result": {...}}
    5. Either party can close the connection
    """
    await websocket.accept()
    session_id = str(id(websocket))
    
    logger.info(f"Voice assistant WebSocket connected: {session_id}")
    
    # Check if service is available
    if not pipecat_service.is_available:
        await websocket.send_json({
            "type": "error",
            "message": "Voice assistant not configured. Please set API keys in .env"
        })
        await websocket.close(code=1008, reason="Service not configured")
        return
    
    try:
        # Wait for initialization message
        init_msg = await websocket.receive_json()
        
        if init_msg.get("type") != "init":
            await websocket.send_json({
                "type": "error",
                "message": "Expected init message"
            })
            await websocket.close(code=1002)
            return
        
        # TODO: Validate token and get user
        # For now, accept connection without auth validation
        # In production, verify the token against the auth system
        
        await websocket.send_json({
            "type": "ready",
            "session_id": session_id,
            "language": pipecat_settings.pipecat_voice_language,
            "message": "Assistente vocale pronto. Parla pure!"
        })
        
        # Main message loop
        while True:
            try:
                # Handle both text and binary messages
                message = await websocket.receive()
                
                if "text" in message:
                    # Text message (commands, control)
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "text":
                        # Process text input (for testing without mic)
                        text = data.get("text", "")
                        await websocket.send_json({
                            "type": "transcript",
                            "text": text,
                            "is_final": True
                        })
                        
                        # TODO: Send to LLM and get response
                        # For now, echo back as placeholder
                        await websocket.send_json({
                            "type": "response",
                            "text": f"Hai detto: {text}. L'elaborazione vocale completa sarà disponibile quando configurerai le API keys."
                        })
                        
                    elif msg_type == "function":
                        # Direct function call
                        result = await pipecat_service.handle_function_call(
                            function_name=data.get("function"),
                            arguments=data.get("arguments", {}),
                            user_id=None,  # TODO: Get from auth
                            site_id=None
                        )
                        await websocket.send_json({
                            "type": "function",
                            "name": data.get("function"),
                            "result": result
                        })
                        
                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                        
                    elif msg_type == "close":
                        break
                        
                elif "bytes" in message:
                    # Binary audio data
                    audio_data = message["bytes"]
                    
                    # TODO: When Pipecat pipeline is fully configured,
                    # send audio to STT service
                    # For now, acknowledge receipt
                    await websocket.send_json({
                        "type": "audio_received",
                        "size": len(audio_data)
                    })
                    
            except WebSocketDisconnect:
                logger.info(f"Voice assistant client disconnected: {session_id}")
                break
            except json.JSONDecodeError as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Invalid JSON: {str(e)}"
                })
                
    except WebSocketDisconnect:
        logger.info(f"Voice assistant disconnected during init: {session_id}")
    except Exception as e:
        logger.error(f"Voice assistant error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        await pipecat_service.cleanup_session(session_id)
        logger.info(f"Voice assistant session cleaned up: {session_id}")
