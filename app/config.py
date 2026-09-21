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


# Supported languages with metadata for UI and API calls
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
    "fat": {
        "name": "Fante",
        "native_name": "Mfantse",
        "color": "#006B3F",
        "color_light": "#D0F5E0",
        "icon": "🇬🇭",
        "pattern": "adinkra",
        "gtts_code": None,
        "khaya_tts_code": "fat",
        "khaya_asr_code": "fat",
        "translate_pair": "en-fat",
        "greeting_audio": "Maakye! Mo abra!",
        "tts_voice_prompt": (
            "Read the following Mfantse (Fante) text aloud in a warm, gentle, pastoral Ghanaian tone. "
            "Speak naturally like a loving Cape Coast elder or pastor. "
            "Use authentic Fante pronunciation and intonation. Speak clearly at a calm pace: "
        ),
        "sample_questions": [
            "Kenkan Genesis chapta 1 ma me",
            "Kyerɛ me Psalm 23",
            "Dɛn na Bible ka fa asomdwee ho?"
        ]
    },
    "ee": {
        "name": "Ewe",
        "native_name": "Eʋegbe",
        "color": "#CE1126",
        "color_light": "#FFD6DC",
        "icon": "🇬🇭",
        "pattern": "ewe_cloth",
        "gtts_code": None,
        "khaya_tts_code": "ee",
        "khaya_asr_code": "ee",
        "translate_pair": "en-ee",
        "greeting_audio": "Ŋdi! Woezo!",
        "tts_voice_prompt": (
            "Read the following Ewe (Eʋegbe) text aloud in a warm, kind, pastoral tone. "
            "Speak naturally like a loving Volta Region elder or pastor. "
            "Use authentic Ewe pronunciation with proper tonal patterns. Speak clearly and gently: "
        ),
        "sample_questions": [
            "Xlẽ Genesis chapita 1 nam",
            "Fia Psalm 23 nye",
            "Nukae Biblia gblɔ tso lɔlɔ̃ ŋu?"
        ]
    },
    "gaa": {
        "name": "GA",
        "native_name": "Gã",
        "color": "#003F87",
        "color_light": "#D0E3FF",
        "icon": "🇬🇭",
        "pattern": "ga_pattern",
        "gtts_code": None,
        "khaya_tts_code": "gaa",
        "khaya_asr_code": "gaa",
        "translate_pair": "en-gaa",
        "greeting_audio": "Ojeogbɛnɔ! Miiyɛ gbɛ!",
        "tts_voice_prompt": (
            "Read the following Ga (Gã) text aloud in a warm, fatherly, pastoral tone. "
            "Speak naturally like a wise Accra elder or pastor. "
            "Use authentic Ga pronunciation and rhythm. Speak clearly and with compassion: "
        ),
        "sample_questions": [
            "Kɛ Genesis chapter 1 ni mɛi",
            "Fa Psalm 23 shiɛ mɛi",
            "Mɛni lɛ Bible kɛ shi shikpɔŋ jiemɔ?"
        ]
    },
    "ha": {
        "name": "Hausa",
        "native_name": "Hausa",
        "color": "#FF8C00",
        "color_light": "#FFF0D0",
        "icon": "🇳🇬",
        "pattern": "hausa_pattern",
        "gtts_code": "ha",
        "khaya_tts_code": "ha",
        "khaya_asr_code": "ha",
        "translate_pair": "en-ha",
        "greeting_audio": "Sannu! Barka da zuwa!",
        "tts_voice_prompt": (
            "Read the following Hausa text aloud in a warm, respectful, pastoral tone. "
            "Speak naturally like a wise Mallam or pastor in Northern Ghana or Nigeria. "
            "Use authentic Hausa pronunciation and cadence. Speak clearly at a calm, steady pace: "
        ),
        "sample_questions": [
            "Ka karanta mini Farawa sura ta 1",
            "Bayyana mini Zabura 23",
            "Menene Littafi Mai Tsarki ya ce game da ƙauna?"
        ]
    },
}


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
