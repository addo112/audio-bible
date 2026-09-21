"""
Gemini TTS Service — Native voice generation using Gemini's built-in TTS.

Generates spoken audio directly from Gemini in Ghanaian languages
with authentic native tone, accent, and pastoral warmth.
"""
from google import genai
from google.genai import types
import wave
import io
import logging
import re
from app.config import get_settings, LANGUAGES

logger = logging.getLogger(__name__)

# Maximum text length per TTS request
MAX_TTS_TEXT_LENGTH = 500


class GeminiTTS:
    """Text-to-Speech using Gemini's native audio generation."""
    
    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.tts_model = settings.GEMINI_TTS_MODEL
        self.default_voice = settings.GEMINI_TTS_VOICE
    
    def _clean_text_for_speech(self, text: str) -> str:
        """Remove Markdown formatting for natural speech."""
        clean = text
        clean = re.sub(r'#{1,6}\s+', '', clean)
        clean = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', clean)
        clean = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', clean)
        clean = re.sub(r'^>\s*', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'^---+$', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\[.*?\]', '', clean)
        # Remove emoji
        clean = re.sub(r'[🌟📖💡🙏✝️🔊🎤🇬🇭🇳🇬]', '', clean)
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        return clean.strip()
    
    def _truncate_for_tts(self, text: str, max_length: int = None) -> str:
        """Truncate text at sentence boundary within limit."""
        limit = max_length or MAX_TTS_TEXT_LENGTH
        if len(text) <= limit:
            return text
        
        truncated = text[:limit]
        last_break = max(
            truncated.rfind('. '),
            truncated.rfind('! '),
            truncated.rfind('? '),
            truncated.rfind('.\n'),
            truncated.rfind('!\n'),
            truncated.rfind('?\n'),
        )
        
        if last_break > limit // 2:
            return truncated[:last_break + 1]
        return truncated
    
    async def synthesize(self, text: str, language_code: str) -> tuple[bytes | None, str | None]:
        """Convert text to speech using Gemini TTS with retry on failure."""
        lang = LANGUAGES.get(language_code)
        if not lang:
            return None, None
        
        clean_text = self._clean_text_for_speech(text)
        clean_text = self._truncate_for_tts(clean_text)
        
        if not clean_text or len(clean_text) < 10:
            return None, None
        
        voice_prompt = lang.get("tts_voice_prompt", "Read aloud clearly: ")
        tts_content = f"{voice_prompt}\n\n{clean_text}"
        
        # Try full text first, then shorter on failure
        for attempt in range(2):
            try:
                if attempt == 1:
                    # Retry with shorter text
                    clean_text = self._truncate_for_tts(clean_text, max_length=400)
                    tts_content = f"{voice_prompt}\n\n{clean_text}"
                    logger.info("Retrying TTS with shorter text...")
                
                response = self.client.models.generate_content(
                    model=self.tts_model,
                    contents=tts_content,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=self.default_voice,
                                )
                            )
                        ),
                    ),
                )
                
                if (response.candidates 
                        and response.candidates[0].content 
                        and response.candidates[0].content.parts):
                    
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            pcm_data = part.inline_data.data
                            wav_data = self._pcm_to_wav(pcm_data)
                            logger.info(
                                f"Gemini TTS: {len(wav_data)} bytes "
                                f"for {language_code} (attempt {attempt+1})"
                            )
                            return wav_data, "audio/wav"
                
                logger.warning(f"Gemini TTS: no audio in response (attempt {attempt+1})")
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    logger.warning(f"Gemini TTS rate limited (attempt {attempt+1}): {e}")
                    break  # Don't retry on rate limit
                logger.error(f"Gemini TTS error (attempt {attempt+1}): {e}")
        
        return None, None
    
    @staticmethod
    def _pcm_to_wav(
        pcm_data: bytes,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        """Wrap raw PCM audio data in a WAV header."""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        buffer.seek(0)
        return buffer.read()


# Singleton instance
gemini_tts = GeminiTTS()
