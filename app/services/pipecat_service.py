"""
Pipecat Voice Assistant Service

Main service for managing voice assistant sessions using the Pipecat framework.
Integrates STT (Deepgram), LLM (OpenAI), and TTS (OpenAI/Cartesia) for
real-time voice conversations in the FastZoom archaeological documentation system.
"""

import asyncio
import json
from typing import Any, Callable, Optional
from uuid import UUID
from loguru import logger

try:
    from pipecat.frames.frames import (
        Frame,
        LLMMessagesFrame,
        TextFrame,
        EndFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask, PipelineParams
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
    from pipecat.services.deepgram import DeepgramSTTService
    from pipecat.services.openai import OpenAILLMService, OpenAITTSService
    # Note: Using FastAPI WebSocket transport, not Daily
    PIPECAT_AVAILABLE = True
except ImportError as e:
    PIPECAT_AVAILABLE = False
    logger.warning(f"Pipecat not fully installed: {e}. Voice assistant features disabled.")

from app.core.pipecat_settings import pipecat_settings


# System prompt for the archaeological assistant
SYSTEM_PROMPT = """Sei un assistente vocale per FastZoom, un sistema di documentazione archeologica.
Puoi aiutare gli utenti con le seguenti attività:

1. **Ricerca foto**: Cerca foto nei siti archeologici
2. **Informazioni siti**: Fornisci informazioni sui siti archeologici
3. **Giornale di cantiere**: Aiuta a compilare giornali di cantiere
4. **Navigazione**: Guida l'utente attraverso l'applicazione
5. **Statistiche**: Fornisci statistiche su foto e attività

Rispondi sempre in italiano e in modo conciso. Se non capisci una richiesta, chiedi chiarimenti.
Usa un tono professionale ma amichevole, adatto al contesto museale e archeologico.
"""

# Function definitions for the LLM
FUNCTION_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_photos",
            "description": "Cerca foto in un sito archeologico per parole chiave o filtri",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termine di ricerca per le foto"
                    },
                    "site_name": {
                        "type": "string",
                        "description": "Nome del sito archeologico (opzionale)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_site_info",
            "description": "Ottieni informazioni su un sito archeologico",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_name": {
                        "type": "string",
                        "description": "Nome del sito archeologico"
                    }
                },
                "required": ["site_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "Ottieni statistiche su foto, siti o attività",
            "parameters": {
                "type": "object",
                "properties": {
                    "stat_type": {
                        "type": "string",
                        "enum": ["photos", "sites", "uploads", "users"],
                        "description": "Tipo di statistica da recuperare"
                    },
                    "time_range": {
                        "type": "string",
                        "enum": ["today", "week", "month", "year", "all"],
                        "description": "Intervallo temporale"
                    }
                },
                "required": ["stat_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Naviga a una pagina specifica dell'applicazione",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "string",
                        "enum": ["dashboard", "sites", "photos", "giornale", "admin", "profile"],
                        "description": "Pagina di destinazione"
                    },
                    "site_id": {
                        "type": "string",
                        "description": "ID del sito (opzionale, per navigazione specifica)"
                    }
                },
                "required": ["page"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_giornale",
            "description": "Crea un nuovo giornale di cantiere",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_id": {
                        "type": "string",
                        "description": "ID del sito archeologico"
                    },
                    "date": {
                        "type": "string",
                        "description": "Data del giornale (YYYY-MM-DD)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Descrizione delle attività"
                    }
                },
                "required": ["site_id"]
            }
        }
    }
]


class PipecatService:
    """
    Service for managing Pipecat voice assistant sessions.
    
    Handles:
    - Session lifecycle management
    - Pipeline configuration
    - Function calling integration with FastZoom services
    """
    
    def __init__(self):
        self._sessions: dict[str, PipelineTask] = {}
        self._function_handlers: dict[str, Callable] = {}
        self._is_initialized = False
        
    @property
    def is_available(self) -> bool:
        """Check if Pipecat is available and configured."""
        return PIPECAT_AVAILABLE and pipecat_settings.is_configured
    
    @property
    def status(self) -> dict:
        """Get service status."""
        return {
            "available": self.is_available,
            "pipecat_installed": PIPECAT_AVAILABLE,
            "configured": pipecat_settings.is_configured,
            "enabled": pipecat_settings.pipecat_enabled,
            "active_sessions": len(self._sessions),
            "language": pipecat_settings.pipecat_voice_language,
            "model": pipecat_settings.pipecat_model,
        }
    
    def register_function_handler(self, name: str, handler: Callable) -> None:
        """Register a function handler for LLM function calls."""
        self._function_handlers[name] = handler
        logger.debug(f"Registered Pipecat function handler: {name}")
    
    async def handle_function_call(
        self, 
        function_name: str, 
        arguments: dict,
        user_id: Optional[UUID] = None,
        site_id: Optional[UUID] = None
    ) -> dict:
        """
        Handle a function call from the LLM.
        
        Args:
            function_name: Name of the function to call
            arguments: Function arguments
            user_id: Current user ID for permission checks
            site_id: Current site context
            
        Returns:
            Function result as a dictionary
        """
        if function_name not in self._function_handlers:
            logger.warning(f"Unknown function called: {function_name}")
            return {
                "error": True,
                "message": f"Funzione '{function_name}' non disponibile"
            }
        
        try:
            handler = self._function_handlers[function_name]
            result = await handler(
                arguments=arguments,
                user_id=user_id,
                site_id=site_id
            )
            return result
        except Exception as e:
            logger.error(f"Error in function {function_name}: {e}")
            return {
                "error": True,
                "message": f"Errore nell'esecuzione: {str(e)}"
            }
    
    def create_llm_context(self) -> "OpenAILLMContext":
        """Create LLM context with system prompt and functions."""
        if not PIPECAT_AVAILABLE:
            raise RuntimeError("Pipecat not installed")
            
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        context = OpenAILLMContext(
            messages=messages,
            tools=FUNCTION_DEFINITIONS
        )
        
        return context
    
    async def create_stt_service(self):
        """Create Speech-to-Text service."""
        if not PIPECAT_AVAILABLE:
            raise RuntimeError("Pipecat not installed")
            
        provider = pipecat_settings.pipecat_stt_provider
        
        if provider == "whisper":
            try:
                from app.services.pipecat_local_services import LocalWhisperSTTService
                return LocalWhisperSTTService(model=pipecat_settings.whisper_model)
            except ImportError:
                logger.error("Local Whisper service not available")
                raise
        else:
            return DeepgramSTTService(
                api_key=pipecat_settings.deepgram_api_key,
                language=pipecat_settings.pipecat_voice_language,
            )
    
    async def create_llm_service(self):
        """Create LLM service."""
        if not PIPECAT_AVAILABLE:
            raise RuntimeError("Pipecat not installed")
            
        provider = pipecat_settings.pipecat_llm_provider
        
        if provider == "ollama":
            try:
                from app.services.pipecat_local_services import OllamaLLMService
                # Use custom create_context for local LLM if needed, otherwise generic
                return OllamaLLMService(
                    model=pipecat_settings.ollama_model, 
                    base_url=pipecat_settings.ollama_base_url
                )
            except ImportError:
                logger.error("Local Ollama service not available")
                raise
        else:
            return OpenAILLMService(
                api_key=pipecat_settings.openai_api_key,
                model=pipecat_settings.pipecat_model,
            )
    
    async def create_tts_service(self):
        """Create Text-to-Speech service."""
        if not PIPECAT_AVAILABLE:
            raise RuntimeError("Pipecat not installed")
            
        provider = pipecat_settings.pipecat_tts_provider
        
        if provider == "silero":
            # TODO: Implement connection to Silero
            # For now, fallback to generic or raise not implemented
            logger.warning("Silero TTS not fully implemented, falling back to OpenAI or placeholder")
            if pipecat_settings.openai_api_key:
                 return OpenAITTSService(
                    api_key=pipecat_settings.openai_api_key,
                    voice=pipecat_settings.pipecat_voice_id,
                )
            else:
                 # Local fallback strategies (e.g. system TTS handled by frontend)
                 return None 
        elif provider == "cartesia" and pipecat_settings.cartesia_api_key:
             # Import Cartesia service
             from pipecat.services.cartesia import CartesiaTTSService
             return CartesiaTTSService(
                 api_key=pipecat_settings.cartesia_api_key,
                 voice_id="..." # Add setting
             )
        else:
            return OpenAITTSService(
                api_key=pipecat_settings.openai_api_key,
                voice=pipecat_settings.pipecat_voice_id,
            )
    
    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)
    
    async def cleanup_session(self, session_id: str) -> None:
        """Clean up a voice session."""
        if session_id in self._sessions:
            task = self._sessions.pop(session_id)
            logger.info(f"Cleaned up Pipecat session: {session_id}")


# Global service instance
pipecat_service = PipecatService()
