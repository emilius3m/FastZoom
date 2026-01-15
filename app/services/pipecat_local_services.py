"""
Local AI Services for Pipecat Voice Assistant

Simple implementations of STT (Faster-Whisper) and LLM (Ollama) services
for local AI processing without cloud dependencies.
"""

import asyncio
import io
from typing import AsyncGenerator, Optional
from dataclasses import dataclass

from loguru import logger


# Check for local AI dependencies
FASTER_WHISPER_AVAILABLE = False
OLLAMA_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    import numpy as np
    FASTER_WHISPER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Faster-Whisper not found: {e}. Install faster-whisper.")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Ollama not found: {e}. Install ollama.")

LOCAL_AI_AVAILABLE = FASTER_WHISPER_AVAILABLE and OLLAMA_AVAILABLE


@dataclass
class TranscriptionResult:
    """Result of a transcription operation."""
    text: str
    language: str = "it"


@dataclass 
class LLMResponse:
    """Response from the LLM."""
    text: str
    is_complete: bool = False


class LocalWhisperSTT:
    """
    Local STT service using Faster-Whisper.
    Buffers audio and transcribes when enough data is accumulated.
    Much faster than OpenAI Whisper, especially on CPU.
    """
    
    def __init__(self, model: str = "base", device: str = "cpu", language: str = "it"):
        """
        Initialize Faster-Whisper STT.
        
        Args:
            model: Model size - tiny, base, small, medium, large-v2, large-v3
            device: cpu or cuda
            language: Language code (it for Italian)
        """
        self._model_name = model
        self._device = device
        self._language = language
        self._model = None
        self._buffer = io.BytesIO()
        self._buffer_threshold = 48000  # ~1.5 seconds at 16kHz, 16-bit mono (faster with faster-whisper)
        
        if FASTER_WHISPER_AVAILABLE:
            self._load_model()
        
    def _load_model(self):
        """Load Faster-Whisper model."""
        try:
            compute_type = "int8" if self._device == "cpu" else "float16"
            logger.info(f"Loading Faster-Whisper model: {self._model_name} on {self._device} ({compute_type})...")
            self._model = WhisperModel(
                self._model_name, 
                device=self._device,
                compute_type=compute_type
            )
            logger.info("Faster-Whisper model loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading Faster-Whisper: {e}")
            self._model = None
            
    @property
    def is_ready(self) -> bool:
        """Check if the service is ready for use."""
        return self._model is not None
    
    def add_audio(self, audio_bytes: bytes) -> bool:
        """
        Add audio data to the buffer.
        Returns True if buffer is ready for transcription.
        """
        self._buffer.write(audio_bytes)
        return self._buffer.tell() >= self._buffer_threshold
    
    async def transcribe(self) -> Optional[TranscriptionResult]:
        """
        Transcribe buffered audio and clear the buffer.
        Returns None if transcription fails or no speech detected.
        """
        if not self._model:
            logger.warning("Faster-Whisper model not loaded")
            return None
            
        buffer_data = self._buffer.getvalue()
        self._buffer = io.BytesIO()  # Reset buffer
        
        if len(buffer_data) < 16000:  # Less than 0.5 second
            return None
            
        try:
            # Convert bytes to float32 numpy array
            audio_data = np.frombuffer(buffer_data, np.int16).flatten().astype(np.float32) / 32768.0
            
            # Run transcription in executor to avoid blocking
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self._transcribe_sync(audio_data)
            )
            
            if result:
                logger.debug(f"Faster-Whisper transcribed: {result}")
                return TranscriptionResult(text=result, language=self._language)
                
        except Exception as e:
            logger.error(f"Faster-Whisper transcription error: {e}")
            
        return None
    
    def _transcribe_sync(self, audio_data) -> Optional[str]:
        """Synchronous transcription for executor."""
        segments, info = self._model.transcribe(
            audio_data, 
            language=self._language,
            beam_size=5,
            vad_filter=True,  # Filter out non-speech parts
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            )
        )
        
        # Collect all segments
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())
            
        full_text = " ".join(text_parts).strip()
        return full_text if full_text else None
    
    def clear_buffer(self):
        """Clear the audio buffer."""
        self._buffer = io.BytesIO()


class LocalOllamaLLM:
    """
    Local LLM service using Ollama.
    Provides streaming chat completions.
    """
    
    def __init__(self, model: str = "llama3.2:3b", base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url
        self._client = None
        
        if OLLAMA_AVAILABLE:
            try:
                self._client = ollama.Client(host=base_url)
                logger.info(f"Ollama client initialized for model: {model}")
            except Exception as e:
                logger.error(f"Error initializing Ollama client: {e}")
                
    @property
    def is_ready(self) -> bool:
        """Check if the service is ready for use."""
        return self._client is not None
    
    async def chat(self, messages: list) -> AsyncGenerator[LLMResponse, None]:
        """
        Send messages to Ollama and yield response chunks.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            
        Yields:
            LLMResponse objects with text chunks
        """
        if not self._client:
            logger.error("Ollama client not initialized")
            yield LLMResponse(text="Errore: Ollama non disponibile", is_complete=True)
            return
            
        try:
            # Run in executor since ollama.Client.chat is blocking
            loop = asyncio.get_running_loop()
            
            def stream_chat():
                return self._client.chat(
                    model=self._model,
                    messages=messages,
                    stream=True
                )
            
            # Get the stream iterator
            stream = await loop.run_in_executor(None, stream_chat)
            
            full_text = ""
            for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    full_text += content
                    yield LLMResponse(text=content, is_complete=False)
                    
            # Yield final complete response
            yield LLMResponse(text=full_text, is_complete=True)
            
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            yield LLMResponse(text=f"Errore Ollama: {str(e)}", is_complete=True)
    
    async def simple_chat(self, messages: list) -> str:
        """
        Send messages and get complete response (non-streaming).
        
        Args:
            messages: List of message dicts
            
        Returns:
            Complete response text
        """
        full_response = ""
        async for response in self.chat(messages):
            if response.is_complete:
                return response.text
            full_response += response.text
        return full_response
