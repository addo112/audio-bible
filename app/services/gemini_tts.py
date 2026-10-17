"""
Gemini Native Twi TTS Service — Expressive Ghanaian Asante Twi speech generation.

Uses a rotating pool of Gemini TTS models (`gemini-3.8-flash-lite-tts`,
`gemini-3.8-flash-tts`, `gemini-3.1-flash-tts-preview`) with a single-clause
director prefix ("Speak in a warm, deep, native Ghanaian Asante Twi voice: ")
so ONLY the Asante Twi text is spoken with authentic Akan tonal cadence.
"""
from __future__ import annotations

import io
import logging
import re
import wave

from google import genai
from google.genai import types

from app.config import LANGUAGES, get_settings
from app.services.local_tts import prepare_for_speech

logger = logging.getLogger(__name__)

MAX_TTS_TEXT_LENGTH = 600


class GeminiTTS:
    """Text-to-Speech using Gemini's native audio generation with model rotation."""

    TTS_MODELS = [
        "gemini-3.8-flash-lite-tts",
        "gemini-3.8-flash-tts",
        "gemini-3.1-flash-tts-preview",
    ]

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.default_voice = settings.GEMINI_TTS_VOICE or "Charon"
        self._idx = 0

    def _next_models(self) -> list[str]:
        n = len(self.TTS_MODELS)
        start = self._idx % n
        self._idx += 1
        return [self.TTS_MODELS[(start + i) % n] for i in range(n)]

    def _clean_text_for_speech(self, text: str) -> str:
        """Normalize numbers/references into Asante Twi words and strip formatting."""
        clean = prepare_for_speech(text)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def _truncate_for_tts(self, text: str, max_length: int | None = None) -> str:
        limit = max_length or MAX_TTS_TEXT_LENGTH
        if len(text) <= limit:
            return text
        truncated = text[:limit]
        last_break = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
            truncated.rfind(", "),
        )
        if last_break > limit // 2:
            return truncated[: last_break + 1]
        return truncated

    async def synthesize(
        self, text: str, language_code: str = "tw"
    ) -> tuple[bytes | None, str | None]:
        """Convert Asante Twi text to WAV speech using rotating Gemini TTS models."""
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        clean_text = self._clean_text_for_speech(text)
        clean_text = self._truncate_for_tts(clean_text)

        if not clean_text or len(clean_text) < 2:
            return None, None

        # Single-clause style prefix before colon (NO periods before colon!)
        voice_prompt = lang.get(
            "tts_voice_prompt",
            "Speak in a warm, deep, native Ghanaian Asante Twi voice: ",
        )
        # Strip any accidental periods in custom voice_prompt so it is never read aloud
        voice_prompt = voice_prompt.replace(".", ",").rstrip()
        if not voice_prompt.endswith(":"):
            voice_prompt += ":"

        tts_content = f"{voice_prompt} {clean_text}"

        for model in self._next_models():
            try:
                response = await self.client.aio.models.generate_content(
                    model=model,
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

                if (
                    response.candidates
                    and response.candidates[0].content
                    and response.candidates[0].content.parts
                ):
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            pcm_data = part.inline_data.data
                            wav_data = self._pcm_to_wav(pcm_data)
                            logger.info(
                                f"Gemini TTS ({model}): {len(wav_data)} bytes for {language_code}"
                            )
                            return wav_data, "audio/wav"
            except Exception as e:
                logger.warning(f"Gemini TTS ({model}) failed: {e}")
                continue

        return None, None

    @staticmethod
    def _pcm_to_wav(
        pcm_data: bytes,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        buffer.seek(0)
        return buffer.read()


gemini_tts = GeminiTTS()
