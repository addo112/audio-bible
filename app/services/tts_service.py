"""
Text-to-Speech Service — Converts AI responses to audio.

Fallback chain:
1. Khaya AI TTS (best quality for Ghanaian languages, 100 free calls/month)
2. gTTS (Google Translate TTS, free, supports Hausa)
3. Returns None → frontend uses browser SpeechSynthesis as last resort
"""
import httpx
from gtts import gTTS
import io
import logging
from app.config import get_settings, LANGUAGES

logger = logging.getLogger(__name__)


class TTSService:
    """Text-to-Speech with intelligent fallback chain."""
    
    def __init__(self):
        self._khaya_call_count = 0
    
    async def synthesize(self, text: str, language_code: str) -> tuple[bytes | None, str | None]:
        """
        Convert text to speech audio.
        
        Returns: (audio_bytes, mime_type) or (None, None) if all TTS fails.
        When None is returned, the frontend should use browser SpeechSynthesis.
        """
        settings = get_settings()
        lang = LANGUAGES.get(language_code)
        if not lang:
            return None, None
        
        # Strategy 1: Khaya AI TTS (best quality for Ghanaian languages)
        if settings.KHAYA_API_KEY:
            try:
                audio = await self._khaya_tts(text, language_code, settings)
                if audio:
                    logger.info(f"TTS via Khaya for {language_code} ({len(audio)} bytes)")
                    return audio, "audio/mp3"
            except Exception as e:
                logger.warning(f"Khaya TTS failed for {language_code}: {e}")
        
        # Strategy 2: gTTS (free, works for Hausa and potentially others)
        if lang.get("gtts_code"):
            try:
                audio = self._gtts(text, lang["gtts_code"])
                if audio:
                    logger.info(f"TTS via gTTS for {language_code} ({len(audio)} bytes)")
                    return audio, "audio/mp3"
            except Exception as e:
                logger.warning(f"gTTS failed for {language_code}: {e}")
        
        # Strategy 3: Try gTTS with related language codes as fallback
        fallback_codes = {
            "tw": ["ak"],      # Akan
            "fat": ["ak"],     # Akan (Fante is a dialect)
            "ee": [],          # No close fallback
            "gaa": [],         # No close fallback  
            "ha": ["ha"],      # Already tried above
        }
        for code in fallback_codes.get(language_code, []):
            try:
                audio = self._gtts(text, code)
                if audio:
                    logger.info(f"TTS via gTTS fallback ({code}) for {language_code}")
                    return audio, "audio/mp3"
            except Exception:
                continue
        
        # All strategies failed — frontend will use browser SpeechSynthesis
        logger.info(f"No server-side TTS available for {language_code}, using browser fallback")
        return None, None
    
    async def _khaya_tts(self, text: str, language_code: str, settings) -> bytes | None:
        """Call Khaya AI TTS API."""
        lang = LANGUAGES[language_code]
        
        # Split long text into chunks (Khaya may have text length limits)
        max_chunk_length = 500
        if len(text) > max_chunk_length:
            # For long responses, just send the first chunk to save API calls
            text = text[:max_chunk_length]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.KHAYA_BASE_URL}/tts/v1/tts",
                headers={
                    "Ocp-Apim-Subscription-Key": settings.KHAYA_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "language": lang["khaya_tts_code"],
                },
            )
            
            if response.status_code == 200:
                self._khaya_call_count += 1
                content_type = response.headers.get("content-type", "")
                
                if "audio" in content_type:
                    return response.content
                else:
                    # Some APIs return base64-encoded audio in JSON
                    try:
                        import base64
                        data = response.json()
                        if "audio" in data:
                            return base64.b64decode(data["audio"])
                    except Exception:
                        pass
                    return response.content
            else:
                logger.warning(f"Khaya TTS returned {response.status_code}: {response.text[:200]}")
                return None
    
    def _gtts(self, text: str, lang_code: str) -> bytes | None:
        """Generate TTS using Google Translate's free TTS engine."""
        try:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            buffer = io.BytesIO()
            tts.write_to_fp(buffer)
            buffer.seek(0)
            audio_bytes = buffer.read()
            return audio_bytes if len(audio_bytes) > 0 else None
        except Exception as e:
            logger.warning(f"gTTS error for lang={lang_code}: {e}")
            return None
    
    @property
    def khaya_calls_used(self) -> int:
        """Track how many Khaya API calls have been used (for quota awareness)."""
        return self._khaya_call_count


# Singleton instance
tts_service = TTSService()
