"""
Text-to-Speech Service — Converts Bible readings and AI responses to native audio.

Fallback chain:
1. Local Native Twi TTS (VITS models trained on Ghanaian speakers — fast, offline, CPU)
2. Khaya AI TTS (if KHAYA_API_KEY is configured)
3. Gemini TTS (cloud fallback)
4. Browser SpeechSynthesis (client-side last resort)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging

import httpx
from gtts import gTTS

from app.config import LANGUAGES, get_settings
from app.services.gemini_tts import gemini_tts
from app.services.local_tts import local_tts

logger = logging.getLogger(__name__)


class TTSService:
    """Text-to-Speech with local Ghanaian VITS voice primary and cloud fallbacks."""

    def __init__(self):
        self._khaya_call_count = 0
        self._sentence_cache: dict[str, tuple[bytes, str]] = {}
        self._max_cache = 128

    def warmup(self) -> None:
        """Preload local TTS model on startup."""
        settings = get_settings()
        if settings.TTS_ENGINE == "local":
            local_tts.load()

    async def synthesize_sentence(
        self, text: str, language_code: str = "tw"
    ) -> tuple[bytes | None, str | None]:
        """
        Synthesize a single sentence or verse quickly for streaming playback.
        Uses local native VITS voice first, with in-memory caching.
        """
        if not text or not text.strip():
            return None, None

        key = hashlib.md5(f"{language_code}:{text.strip()}".encode("utf-8")).hexdigest()
        if key in self._sentence_cache:
            return self._sentence_cache[key]

        settings = get_settings()

        # 1. Local native Twi VITS model (offline, fast on CPU)
        if settings.TTS_ENGINE == "local" and language_code == "tw":
            try:
                audio, mime = await asyncio.to_thread(
                    local_tts.synthesize, text, 0.12
                )
                if audio and mime:
                    self._put_cache(key, (audio, mime))
                    return audio, mime
            except Exception as e:
                logger.warning(f"Local TTS sentence synthesis failed: {e}")

        # 2. Fallback to full synthesize chain
        audio, mime = await self.synthesize(text, language_code)
        if audio and mime:
            self._put_cache(key, (audio, mime))
        return audio, mime

    def _put_cache(self, key: str, val: tuple[bytes, str]) -> None:
        if len(self._sentence_cache) >= self._max_cache:
            oldest = next(iter(self._sentence_cache))
            del self._sentence_cache[oldest]
        self._sentence_cache[key] = val

    async def synthesize(
        self, text: str, language_code: str = "tw"
    ) -> tuple[bytes | None, str | None]:
        """
        Convert text to speech audio using fallback chain.
        Returns: (audio_bytes, mime_type) or (None, None) if all server TTS fails.
        """
        settings = get_settings()
        lang = LANGUAGES.get(language_code)
        if not lang:
            return None, None

        # Strategy 1: Local native Twi VITS voice
        if settings.TTS_ENGINE == "local" and language_code == "tw":
            try:
                audio, mime = await asyncio.to_thread(local_tts.synthesize, text)
                if audio:
                    logger.info(
                        f"TTS via Local VITS ({local_tts.model_id}) for {language_code} ({len(audio)} bytes)"
                    )
                    return audio, mime
            except Exception as e:
                logger.warning(f"Local TTS failed for {language_code}: {e}")

        # Strategy 2: Khaya AI TTS (if configured)
        if settings.KHAYA_API_KEY:
            try:
                audio = await self._khaya_tts(text, language_code, settings)
                if audio:
                    logger.info(f"TTS via Khaya for {language_code} ({len(audio)} bytes)")
                    return audio, "audio/mp3"
            except Exception as e:
                logger.warning(f"Khaya TTS failed for {language_code}: {e}")

        # Strategy 3: Gemini TTS
        try:
            audio, mime = await gemini_tts.synthesize(text, language_code)
            if audio:
                logger.info(f"TTS via Gemini for {language_code} ({len(audio)} bytes)")
                return audio, mime
        except Exception as e:
            logger.warning(f"Gemini TTS failed for {language_code}: {e}")

        # Strategy 4: gTTS fallback
        if lang.get("gtts_code"):
            try:
                audio = await asyncio.to_thread(self._gtts, text, lang["gtts_code"])
                if audio:
                    return audio, "audio/mp3"
            except Exception as e:
                logger.warning(f"gTTS failed for {language_code}: {e}")

        logger.info(f"No server-side TTS available for {language_code}, using browser fallback")
        return None, None

    async def _khaya_tts(self, text: str, language_code: str, settings) -> bytes | None:
        """Call Khaya AI TTS API."""
        lang = LANGUAGES[language_code]
        max_chunk_length = 500
        if len(text) > max_chunk_length:
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
                try:
                    import base64
                    data = response.json()
                    if "audio" in data:
                        return base64.b64decode(data["audio"])
                except Exception:
                    pass
                return response.content
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
        return self._khaya_call_count


tts_service = TTSService()
