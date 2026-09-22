"""
Application configuration and language settings.
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Required: Google Gemini API key (free at https://aistudio.google.com/)
    GEMINI_API_KEY: str = ""
    
    # Optional: Khaya AI API key for high-quality Ghanaian TTS
    # Free tier: 100 calls/month at https://translation.ghananlp.org/
    KHAYA_API_KEY: Optional[str] = None
    
    # Khaya API base URL (Azure API Management)
    KHAYA_BASE_URL: str = "https://translation.ghananlp.org"
    
    # Gemini model to use for Bible teaching
    GEMINI_MODEL: str = "gemini-3.5-flash"  # CHANGED from gemini-3.6-flash
    
    # Gemini TTS model for native voice generation
    GEMINI_TTS_MODEL: str = "gemini-3.1-flash-tts-preview"
    
    # Default TTS voice name (Gemini prebuilt voice — Charon is deep and resonant like the Audio Bible narrator)
    GEMINI_TTS_VOICE: str = "Charon"
    
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
        "greeting_audio": "Ɛte sɛn! Mo abra o!",
        "tts_voice_prompt": (
            "You are the official Asante Twi Audio Bible narrator from Ghana (Faith Comes By Hearing / Bible Society of Ghana style). "
            "Speak in authentic, fluent, idiomatic Asante Twi with a deep, warm, resonant, and natural Ghanaian tone. "
            "Pronounce every Asante word with authentic Akan tonal cadences and rhythmic pauses. "
            "Deliver both the Scripture reading and the pastoral teaching with clear, soothing, lifelike clarity: "
        ),
        "sample_questions": [
            "Kenkan Genesis Ti Baako ma me",
            "Kyerɛ me Awurade mpaebɔ no (Mateu 6:9-13)",
            "Dɛn na Twerɛ Kronkron ka fa ɔdɔ ho?"
        ]
    },
}


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
