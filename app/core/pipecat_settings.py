"""
Pipecat Voice Assistant Settings

Configuration for the AI-powered voice assistant using Pipecat framework.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class PipecatSettings(BaseSettings):
    """Pipecat Voice Assistant configuration settings."""
    
    # Feature toggle
    pipecat_enabled: bool = False
    
    # Provider Configuration
    pipecat_stt_provider: str = "whisper"  # Options: "deepgram", "whisper"
    pipecat_llm_provider: str = "ollama"    # Options: "openai", "ollama"
    pipecat_tts_provider: str = "silero"    # Options: "openai", "cartesia", "silero"

    # Speech-to-Text (STT) - Deepgram / Whisper
    deepgram_api_key: Optional[str] = None
    whisper_model: str = "base"  # For local Whisper

    # Language Model (LLM) - OpenAI / Ollama
    openai_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Text-to-Speech (TTS) - Cartesia / OpenAI / Silero
    cartesia_api_key: Optional[str] = None
    
    # Voice settings
    pipecat_voice_language: str = "it"  # Italian
    pipecat_voice_id: str = "alloy"  # OpenAI TTS voice
    
    # LLM settings
    pipecat_model: str = "gpt-4o-mini"
    pipecat_max_tokens: int = 150
    pipecat_temperature: float = 0.7
    
    # Audio settings
    pipecat_sample_rate: int = 16000
    pipecat_chunk_size: int = 1024
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @property
    def is_configured(self) -> bool:
        """Check if required configuration is present based on selected providers."""
        if not self.pipecat_enabled:
            return False
            
        # Validate STT
        stt_ok = False
        if self.pipecat_stt_provider == "deepgram":
            stt_ok = bool(self.deepgram_api_key and self.deepgram_api_key != "your_deepgram_api_key_here")
        elif self.pipecat_stt_provider == "whisper":
            stt_ok = True  # Local Whisper doesn't need API key
            
        # Validate LLM
        llm_ok = False
        if self.pipecat_llm_provider == "openai":
            llm_ok = bool(self.openai_api_key and self.openai_api_key != "your_openai_api_key_here")
        elif self.pipecat_llm_provider == "ollama":
            llm_ok = True  # Assuming localhost default is fine
            
        return stt_ok and llm_ok
    
    @property
    def use_cartesia_tts(self) -> bool:
        """Check if Cartesia TTS should be used instead of OpenAI TTS."""
        return bool(self.cartesia_api_key)


# Global settings instance
pipecat_settings = PipecatSettings()
