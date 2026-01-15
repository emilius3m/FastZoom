import asyncio
import io
import json
from typing import AsyncGenerator, Optional

from loguru import logger

try:
    import ollama
    import whisper
    import torch
    import numpy as np
    from pipecat.services.ai_services import LLMService, STTService, TTSService
    from pipecat.frames.frames import (
        Frame, 
        ErrorFrame, 
        TextFrame, 
        LLMFullResponseFrame, 
        AudioFrame,
        StartFrame,
        EndFrame
    )
except ImportError:
    logger.warning("Local AI dependencies not found. Install ollama and openai-whisper.")

class OllamaLLMService(LLMService):
    """Local LLM service using Ollama."""
    
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        super().__init__()
        self._model = model
        self._client = ollama.Client(host=base_url)
        
    async def process_messages(self, messages: list) -> AsyncGenerator[Frame, None]:
        """Process messages and yield response frames."""
        try:
            # Convert Pipecat messages to Ollama format
            ollama_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                ollama_messages.append({"role": role, "content": content})
                
            # Stream response
            stream = self._client.chat(
                model=self._model,
                messages=ollama_messages,
                stream=True
            )
            
            full_text = ""
            for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    full_text += content
                    yield TextFrame(content)
                    
            yield LLMFullResponseFrame(full_text)
            
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield ErrorFrame(f"Ollama error: {str(e)}")


class LocalWhisperSTTService(STTService):
    """
    Local STT service using OpenAI Whisper.
    Note: This is not true streaming. It buffers audio and transcribes phrases.
    """
    
    def __init__(self, model: str = "base", device: str = "cpu"):
        super().__init__()
        self._model_name = model
        self._device = device
        self._model = None
        self._buffer = io.BytesIO()
        self._load_model()
        
    def _load_model(self):
        try:
            logger.info(f"Loading Whisper model: {self._model_name} on {self._device}...")
            self._model = whisper.load_model(self._model_name, device=self._device)
            logger.info("Whisper model loaded.")
        except Exception as e:
            logger.error(f"Error loading Whisper: {e}")
            
    async def process_audio(self, frame: AudioFrame) -> AsyncGenerator[Frame, None]:
        """Process audio frame."""
        if frame.data:
            self._buffer.write(frame.data)
            
        # Trigger transcription every ~2 seconds of audio (32000 bytes/s at 16kHz 16bit)
        # This is a simple blocking segmentation, not true VAD.
        if self._buffer.tell() > 64000: 
             async for f in self.transcribe_buffer():
                 yield f

    async def transcribe_buffer(self) -> AsyncGenerator[Frame, None]:
        """Transcribe accumulated audio."""
        if not self._model:
            return

        try:
            # Convert buffer to numpy array for Whisper
            audio_data = np.frombuffer(self._buffer.getvalue(), np.int16).flatten().astype(np.float32) / 32768.0
            
            # Reset buffer
            self._buffer = io.BytesIO()
            
            if len(audio_data) < 16000: # Ignore very short audio (< 1s)
                return

            result = self._model.transcribe(audio_data, language="it")
            text = result.get("text", "").strip()
            
            if text:
                logger.debug(f"Whisper transcribed: {text}")
                yield TextFrame(text)
                yield TextFrame(text)

        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            
