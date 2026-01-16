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
SILERO_VAD_AVAILABLE = False
WEBRTC_VAD_AVAILABLE = False

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

try:
    import torch
    SILERO_VAD_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyTorch not found for Silero VAD: {e}")

try:
    import webrtcvad
    WEBRTC_VAD_AVAILABLE = True
except ImportError as e:
    logger.debug(f"webrtcvad not found: {e}")

LOCAL_AI_AVAILABLE = FASTER_WHISPER_AVAILABLE and OLLAMA_AVAILABLE


# Singleton Whisper model to avoid reloading on each session
_whisper_model = None
_whisper_model_lock = asyncio.Lock()

# Singleton VAD model
_silero_vad_model = None
_silero_vad_utils = None
_webrtc_vad = None


async def get_whisper_model(model_name: str = "base", device: str = "auto"):
    """Get or create the singleton Whisper model (thread-safe, async)."""
    global _whisper_model
    
    if _whisper_model is not None:
        return _whisper_model
    
    async with _whisper_model_lock:
        # Double-check after acquiring lock
        if _whisper_model is not None:
            return _whisper_model
            
        if not FASTER_WHISPER_AVAILABLE:
            logger.warning("Faster-Whisper not available")
            return None
            
        try:
            # Auto-detect best device
            if device == "auto":
                if SILERO_VAD_AVAILABLE and torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"
            
            # Use int8 for medium model - good quality/speed balance
            compute_type = "int8"  # Works on both CPU and GPU
            logger.info(f"Loading Faster-Whisper model: {model_name} on {device} ({compute_type})...")
            
            # Load in thread to avoid blocking
            _whisper_model = await asyncio.to_thread(
                WhisperModel, model_name, device=device, compute_type=compute_type
            )
            logger.info("✅ Faster-Whisper model loaded successfully.")
            
            # Pre-warm the model with dummy audio
            await prewarm_whisper_model()
            
        except Exception as e:
            logger.error(f"Error loading Faster-Whisper: {e}")
            _whisper_model = None
            
    return _whisper_model


async def prewarm_whisper_model():
    """Pre-warm the model to avoid cold start latency."""
    global _whisper_model
    if _whisper_model is None:
        return
    
    try:
        logger.info("🔥 Pre-warming Whisper model...")
        dummy_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
        await asyncio.to_thread(
            lambda: list(_whisper_model.transcribe(dummy_audio, beam_size=1))
        )
        logger.info("✅ Whisper model pre-warmed")
    except Exception as e:
        logger.warning(f"Pre-warming failed (non-critical): {e}")


def get_vad():
    """
    Get a VAD instance. Tries Silero first, falls back to webrtcvad.
    Returns (vad_type, vad_instance) where vad_type is 'silero', 'webrtc', or None.
    """
    global _silero_vad_model, _silero_vad_utils, _webrtc_vad
    
    # Try Silero VAD first (more accurate but requires network for first download)
    if _silero_vad_model is not None:
        return 'silero', (_silero_vad_model, _silero_vad_utils)
    
    if SILERO_VAD_AVAILABLE and _silero_vad_model is None:
        try:
            logger.info("Loading Silero VAD model...")
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            _silero_vad_model = model
            _silero_vad_utils = utils
            logger.info("✅ Silero VAD loaded")
            return 'silero', (model, utils)
        except Exception as e:
            logger.warning(f"Silero VAD failed: {e}, trying webrtcvad...")
    
    # Fall back to webrtcvad (works offline, faster but less accurate)
    if _webrtc_vad is not None:
        return 'webrtc', _webrtc_vad
        
    if WEBRTC_VAD_AVAILABLE:
        try:
            _webrtc_vad = webrtcvad.Vad(3)  # Aggressiveness 3 (highest)
            logger.info("✅ WebRTC VAD loaded (fallback)")
            return 'webrtc', _webrtc_vad
        except Exception as e:
            logger.error(f"webrtcvad failed: {e}")
    
    logger.warning("No VAD available - using buffer-based detection")
    return None, None


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
    Local STT service using Faster-Whisper with VAD.
    Uses VAD to detect when speech ends, then transcribes the full utterance.
    Supports Silero VAD (more accurate) or webrtcvad (offline fallback).
    """
    
    def __init__(self, model: str = "base", device: str = "cpu", language: str = "it"):
        """Initialize Faster-Whisper STT with VAD."""
        self._model_name = model
        self._device = device
        self._language = language
        self._model = None
        self._buffer = io.BytesIO()
        
        # VAD configuration
        self._vad_type = None
        self._vad = None
        self._speech_started = False
        self._silence_frames = 0
        self._silence_threshold = 15  # ~0.5 seconds of silence to trigger
        self._min_speech_frames = 10  # Minimum speech before considering end
        self._speech_frames = 0
        
        # Load VAD model (tries Silero, falls back to webrtc)
        self._vad_type, self._vad = get_vad()
        
    async def ensure_model_loaded(self):
        """Ensure the Whisper model is loaded (async, uses singleton)."""
        if self._model is None:
            self._model = await get_whisper_model(self._model_name, self._device)
        return self._model is not None
            
    @property
    def is_ready(self) -> bool:
        """Check if the service is ready for use."""
        return self._model is not None
    
    def add_audio(self, audio_bytes: bytes) -> bool:
        """
        Add audio data to the buffer.
        Uses VAD to detect end of speech.
        Returns True when speech has ended and buffer is ready for transcription.
        """
        self._buffer.write(audio_bytes)
        
        # If no VAD available, fall back to buffer threshold
        if self._vad is None:
            return self._buffer.tell() >= 128000  # ~4 seconds fallback
        
        try:
            if self._vad_type == 'silero':
                return self._process_silero_vad(audio_bytes)
            elif self._vad_type == 'webrtc':
                return self._process_webrtc_vad(audio_bytes)
        except Exception as e:
            logger.debug(f"VAD processing error: {e}")
            return self._buffer.tell() >= 128000
            
        return False
    
    def _process_silero_vad(self, audio_bytes: bytes) -> bool:
        """Process audio with Silero VAD."""
        vad_model, _ = self._vad
        audio_chunk = np.frombuffer(audio_bytes, np.int16).astype(np.float32) / 32768.0
        
        chunk_size = 512
        for i in range(0, len(audio_chunk) - chunk_size + 1, chunk_size):
            chunk = torch.from_numpy(audio_chunk[i:i+chunk_size])
            speech_prob = vad_model(chunk, 16000).item()
            
            if speech_prob > 0.5:
                self._speech_started = True
                self._speech_frames += 1
                self._silence_frames = 0
            elif self._speech_started:
                self._silence_frames += 1
                if self._silence_frames >= self._silence_threshold and self._speech_frames >= self._min_speech_frames:
                    return True
        return False
    
    def _process_webrtc_vad(self, audio_bytes: bytes) -> bool:
        """Process audio with WebRTC VAD."""
        # webrtcvad needs 10, 20, or 30ms frames at 16kHz
        # 16kHz * 0.03 = 480 samples = 960 bytes (16-bit)
        frame_duration = 30  # ms
        frame_size = int(16000 * frame_duration / 1000) * 2  # bytes
        
        for i in range(0, len(audio_bytes) - frame_size + 1, frame_size):
            frame = audio_bytes[i:i+frame_size]
            try:
                is_speech = self._vad.is_speech(frame, 16000)
            except:
                continue
                
            if is_speech:
                self._speech_started = True
                self._speech_frames += 1
                self._silence_frames = 0
            elif self._speech_started:
                self._silence_frames += 1
                if self._silence_frames >= self._silence_threshold and self._speech_frames >= self._min_speech_frames:
                    return True
        return False
    
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
        
        # Reset VAD state for next utterance
        self._speech_started = False
        self._silence_frames = 0
        self._speech_frames = 0
        
        if len(buffer_data) < 16000:  # Less than 0.5 second
            return None
            
        try:
            # Convert bytes to float32 numpy array
            audio_data = np.frombuffer(buffer_data, np.int16).flatten().astype(np.float32) / 32768.0
            
            # Run transcription in thread to avoid blocking (using optimized params)
            result = await asyncio.to_thread(self._transcribe_sync, audio_data)
            
            if result:
                logger.debug(f"Transcribed: {result}")
                return TranscriptionResult(text=result, language=self._language)
                
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            
        return None
    
    def _transcribe_sync(self, audio_data) -> Optional[str]:
        """Synchronous transcription - balanced speed/accuracy."""
        segments, _ = self._model.transcribe(
            audio_data, 
            language=self._language,
            beam_size=5,              # Better accuracy (was 1)
            temperature=0.0,          # Deterministic
            condition_on_previous_text=False,
            word_timestamps=False,
            vad_filter=True,
        )
        
        # Collect all segments
        text_parts = [segment.text.strip() for segment in segments]
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
