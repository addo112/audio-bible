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
    # "hybrid" (Gemini Native Twi + Offline Kasanoma/Nano-Twi sherpa-onnx),
    # "local" (offline Kasanoma / Nano-Twi / EveryVoice / VITS only), or "gemini"
    TTS_ENGINE: str = "hybrid"
    # Local TTS backend: "nano-twi" (michsethowusu Matcha+Vocos 22kHz sherpa-onnx),
    # "kasanoma" (michsethowusu Piper VITS ONNX), "everyvoice" (EveryVoice OpenBible Twi-Asante),
    # or "vits" (HuggingFace MMS-TTS BibleTTS)
    LOCAL_TTS_MODEL: str = "nano-twi"
    LOCAL_TTS_SPEAKING_RATE: float = 0.96

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
        # IMPORTANT: Must be a single director clause with NO periods before the colon,
        # otherwise Gemini TTS will read the English sentences aloud as a preamble!
        "tts_voice_prompt": "Speak in a warm, deep, native Ghanaian Asante Twi voice: ",
        "sample_questions": [
            "Kenkan Nnwom ti aduonu mmiɛnsa ma me",
            "Kyerɛ me Yohane ti mmiɛnsa nkyekyɛm dunsia ase",
            "Dɛn na Twerɛ Kronkron ka fa gyidie ne ɔdɔ ho?",
        ],
    },
}


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
