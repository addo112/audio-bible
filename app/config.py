"""
Application configuration and Asante Twi voice/knowledge settings.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Required: Google Gemini API key (free at https://aistudio.google.com/)
    GEMINI_API_KEY: str = ""

    # Optional: Khaya AI API key for GhanaNLP cloud TTS/ASR
    KHAYA_API_KEY: Optional[str] = None
    KHAYA_BASE_URL: str = "https://translation.ghananlp.org"

    # Gemini model for Asante Twi Bible teaching (multi-model fallback in bible_ai.py)
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Gemini TTS models for expressive native Ghanaian Asante Twi speech
    GEMINI_TTS_MODEL: str = "gemini-3.8-flash-lite-tts"
    GEMINI_TTS_VOICE: str = "Charon"

    # --- Step 1: Speech-to-Text (Voice Input — Akan/Twi Whisper + Gemini fallback) ---
    STT_ENGINE: str = "whisper"
    WHISPER_MODEL: str = "ghananlpcommunity/whisper-large-v3-turbo-twi-ctranslate"
    WHISPER_HF_MODEL: str = "ghananlpcommunity/whisper-small-twi"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # --- Step 3: Text-to-Speech (Native Ghanaian Asante Twi Voice Output) ---
    # "local" (primary: offline BibleTTS VITS narrator + Gemini/Kasanoma fallback),
    # "hybrid" (Gemini Native Twi first + Offline BibleTTS fallback), or "gemini"
    TTS_ENGINE: str = "local"
    # Local TTS backend: "bibletts" (danieldzikunuofmarvel/mms-tts-asante-twi-bibletts — exact Open.Bible narrator),
    # "nano-twi" (michsethowusu Matcha+Vocos 22kHz sherpa-onnx), or "kasanoma" (michsethowusu Piper VITS ONNX)
    LOCAL_TTS_MODEL: str = "bibletts"
    LOCAL_TTS_SPEAKING_RATE: float = 0.94

    # CPU threads for local ONNX / PyTorch inference
    TORCH_THREADS: int = 4

    # Max tokens for conversational Asante Twi answers
    ANSWER_MAX_TOKENS: int = 450

    class Config:
        env_file = ".env"
        extra = "ignore"


# Supported language — Asante Twi only
LANGUAGES = {
    "tw": {
        "name": "Asante Twi",
        "native_name": "Asante Twi",
        "color": "#D4A017",
        "color_light": "#FFF3D0",
        "icon": "🇬🇭",
        "pattern": "kente",
        "gtts_code": None,
        "khaya_tts_code": "tw",
        "khaya_asr_code": "tw",
        "translate_pair": "en-tw",
        "greeting_audio": "Ɛte sɛn! Akwaaba!",
        # Single Twi-only speaker cue so Gemini TTS never reads an English preamble aloud
        "tts_voice_prompt": "",
        "sample_questions": [
            "Kenkan Genesis eti baako, firi emu baako de kɔsi nnum ma me",
            "Kenkan Nnwom eti aduonu mmiɛnsa ma me",
            "Kyerɛ me Yohane eti mmiɛnsa, emu dunsia ase",
        ],
    },
}


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
