"""
Gemini TTS Service — Native voice generation using Gemini's built-in TTS.

Generates spoken audio directly from Gemini in Ghanaian languages
with authentic native tone, accent, and pastoral warmth.

No extra API keys needed — uses the same Gemini API key as the Bible AI.
"""
from google import genai
from google.genai import types
import wave
import io
import logging
import re
from app.config import get_settings, LANGUAGES

logger = logging.getLogger(__name__)

# Maximum text length per TTS request (keeps audio response under 2-3 seconds)
MAX_TTS_TEXT_LENGTH = 500


class GeminiTTS:
    """Text-to-Speech using Gemini's native audio generation."""
    
    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.tts_model = settings.GEMINI_TTS_MODEL
        self.default_voice = settings.GEMINI_TTS_VOICE
    
    def _clean_text_for_speech(self, text: str) -> str:
        """
        Remove Markdown formatting and clean text for natural speech.
        Keeps the actual words but strips formatting artifacts.
        """
        clean = text
        # Remove markdown headers (### , ## , # )
        clean = re.sub(r'#{1,6}\s+', '', clean)
        # Remove bold/italic markers
        clean = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', clean)
        clean = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', clean)
        # Remove blockquote markers
        clean = re.sub(r'^>\s*', '', clean, flags=re.MULTILINE)
        # Remove horizontal rules
        clean = re.sub(r'^---+$', '', clean, flags=re.MULTILINE)
        # Remove bracket content like [Note]
        clean = re.sub(r'\[.*?\]', '', clean)
        # Collapse multiple newlines into pauses
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        return clean.strip()
    
    def _truncate_for_tts(self, text: str) -> str:
        """
        Truncate text to fit TTS limits while keeping it coherent.
        Cuts at the last sentence boundary within the limit.
        """
        if len(text) <= MAX_TTS_TEXT_LENGTH:
            return text
        
        # Find the last sentence-ending punctuation within the limit
        truncated = text[:MAX_TTS_TEXT_LENGTH]
        # Look for last sentence boundary (., !, ?, or newline)
        last_break = max(
            truncated.rfind('. '),
            truncated.rfind('! '),
            truncated.rfind('? '),
            truncated.rfind('.\n'),
            truncated.rfind('!\n'),
            truncated.rfind('?\n'),
        )
        
        if last_break > MAX_TTS_TEXT_LENGTH // 2:
            return truncated[:last_break + 1]
        return truncated
    
    async def synthesize(self, text: str, language_code: str) -> tuple[bytes | None, str | None]:
        """
        Convert text to native-sounding speech using Gemini TTS.
        
        Returns: (wav_audio_bytes, mime_type) or (None, None) on failure.
        """
        lang = LANGUAGES.get(language_code)
        if not lang:
            return None, None
        
        # Clean and prepare text for speech
        clean_text = self._clean_text_for_speech(text)
        clean_text = self._truncate_for_tts(clean_text)
        
        if not clean_text or len(clean_text) < 10:
            return None, None
        
        # Build the TTS prompt with language-specific voice instructions
        voice_prompt = lang.get("tts_voice_prompt", "Read the following text aloud clearly: ")
        tts_content = f"{voice_prompt}\n\n{clean_text}"
        
        try:
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
            
            # Extract audio data from response
            if (response.candidates 
                    and response.candidates[0].content 
                    and response.candidates[0].content.parts):
                
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        pcm_data = part.inline_data.data
                        # Convert raw PCM to WAV for browser playback
                        wav_data = self._pcm_to_wav(pcm_data)
                        logger.info(
                            f"Gemini TTS: generated {len(wav_data)} bytes "
                            f"for {language_code} ({lang['name']})"
                        )
                        return wav_data, "audio/wav"
            
            logger.warning("Gemini TTS: no audio data in response")
            return None, None
            
        except Exception as e:
            logger.error(f"Gemini TTS error for {language_code}: {e}")
            return None, None
    
    @staticmethod
    def _pcm_to_wav(
        pcm_data: bytes,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        """
        Wrap raw PCM audio data in a WAV header for browser playback.
        
        Gemini TTS outputs raw PCM: 16-bit, 24kHz, mono, little-endian.
        Browsers need a proper WAV file header to play it.
        """
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
