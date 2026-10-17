"""
Step 3: Text-to-Speech Service — Converts Asante Twi Bible readings and AI explanations
to authentic native Ghanaian audio.

Hybrid Voice Architecture:
1. `hybrid` mode (default):
   - Primary for conversational explanations: Gemini Native Ghanaian Twi TTS
     (`gemini-3.8-flash-lite-tts` / `gemini-3.8-flash-tts` / `gemini-3.1-flash-tts-preview`
     with single-clause Ashanti voice direction — 10/10 native cadence).
   - Instant offline / rate-limit fallback: Local `sherpa-onnx` Neural Twi TTS
     (`Nano-Twi` Matcha+Vocos 22.05kHz & `Kasanoma` Piper VITS by `michsethowusu`, ~0.3s on CPU).
2. `local` mode:
   - Uses offline `Kasanoma` / `Nano-Twi` (`sherpa-onnx`) first, then cloud fallback.
3. Official Chapter Audio:
   - Fetches authentic dramatized Asante Twi Audio Bible chapter MP3s when reading full chapters.
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
    """Hybrid Asante Twi Text-to-Speech with Gemini Native Twi + Offline Kasanoma/Nano-Twi ONNX."""

    def __init__(self):
        self._khaya_call_count = 0
        self._sentence_cache: dict[str, tuple[bytes, str]] = {}
        self._max_cache = 128

    def warmup(self) -> None:
        """Preload local sherpa-onnx Twi TTS model (Nano-Twi / Kasanoma) on startup."""
        settings = get_settings()
        if settings.TTS_ENGINE in ("local", "hybrid"):
            local_tts.load()

    async def fetch_chapter_audio(self, url: str) -> tuple[bytes | None, str | None]:
        """Fetch official dramatized Asante Twi Audio Bible chapter MP3."""
        key = hashlib.md5(f"chapter:{url}".encode("utf-8")).hexdigest()
        if key in self._sentence_cache:
            return self._sentence_cache[key]
        try:
            async with httpx.AsyncClient(timeout=20.0, verify=False, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    val = (resp.content, "audio/mpeg")
                    self._put_cache(key, val)
                    return val
        except Exception as e:
            logger.warning(f"Chapter audio fetch failed ({url}): {e}")
        return None, None

    async def synthesize_sentence(
        self, text: str, language_code: str = "tw", prefer_local: bool = False
    ) -> tuple[bytes | None, str | None]:
        """
        Synthesize a sentence or paragraph for streaming playback.
        Never returns None if either Gemini TTS or Local Kasanoma/Nano-Twi is available.
        """
        if not text or not text.strip():
            return None, None

        key = hashlib.md5(f"{language_code}:{prefer_local}:{text.strip()}".encode("utf-8")).hexdigest()
        if key in self._sentence_cache:
            return self._sentence_cache[key]

        settings = get_settings()

        # If local-first is requested (or TTS_ENGINE == "local"), use Kasanoma / Nano-Twi sherpa-onnx first
        if prefer_local or settings.TTS_ENGINE == "local":
            try:
                audio, mime = await asyncio.to_thread(local_tts.synthesize, text, 0.16)
                if audio and mime:
                    self._put_cache(key, (audio, mime))
                    return audio, mime
            except Exception as e:
                logger.warning(f"Local sherpa-onnx TTS failed: {e}")

        # Otherwise use full synthesize chain (Hybrid: Khaya -> Gemini 3.8 Native Twi -> Local Kasanoma/Nano-Twi)
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
        Convert Asante Twi text to speech audio using the hybrid fallback chain:
        1. Local Kasanoma/Nano-Twi first if TTS_ENGINE == "local"
        2. Khaya AI TTS (if KHAYA_API_KEY configured)
        3. Gemini Native Twi TTS (`gemini-3.8-flash-lite-tts` / `3.8-flash-tts` / `3.1-flash-tts-preview`)
        4. Local Kasanoma / Nano-Twi (`sherpa-onnx` offline CPU neural TTS)
        """
        settings = get_settings()
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])

        # Strategy 1: Local-first if explicitly configured
        if settings.TTS_ENGINE == "local":
            try:
                audio, mime = await asyncio.to_thread(local_tts.synthesize, text)
                if audio:
                    logger.info(
                        f"TTS via Local sherpa-onnx ({local_tts.model_id}) ({len(audio)} bytes)"
                    )
                    return audio, mime
            except Exception as e:
                logger.warning(f"Local TTS failed: {e}")

        # Strategy 2: Khaya AI TTS (if configured)
        if settings.KHAYA_API_KEY:
            try:
                audio = await self._khaya_tts(text, language_code, settings)
                if audio:
                    logger.info(f"TTS via Khaya ({len(audio)} bytes)")
                    return audio, "audio/mp3"
            except Exception as e:
                logger.warning(f"Khaya TTS failed: {e}")

        # Strategy 3: Gemini Native Ghanaian Twi TTS (10/10 natural Ashanti accent)
        try:
            audio, mime = await gemini_tts.synthesize(text, language_code)
            if audio:
                return audio, mime
        except Exception as e:
            logger.warning(f"Gemini TTS failed: {e}")

        # Strategy 4: Offline Local Kasanoma / Nano-Twi (`sherpa-onnx`) fallback
        # Guarantees native Twi neural voice even when offline or rate-limited!
        try:
            audio, mime = await asyncio.to_thread(local_tts.synthesize, text)
            if audio:
                logger.info(
                    f"TTS via Local sherpa-onnx fallback ({local_tts.model_id}) ({len(audio)} bytes)"
                )
                return audio, mime
        except Exception as e:
            logger.warning(f"Local sherpa-onnx fallback failed: {e}")

        # Strategy 5: gTTS fallback (if configured)
        if lang.get("gtts_code"):
            try:
                audio = await asyncio.to_thread(self._gtts, text, lang["gtts_code"])
                if audio:
                    return audio, "audio/mp3"
            except Exception as e:
                logger.warning(f"gTTS failed: {e}")

        return None, None

    async def _khaya_tts(self, text: str, language_code: str, settings) -> bytes | None:
        lang = LANGUAGES[language_code]
        if len(text) > 500:
            text = text[:500]

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
            return None

    def _gtts(self, text: str, lang_code: str) -> bytes | None:
        try:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            buffer = io.BytesIO()
            tts.write_to_fp(buffer)
            buffer.seek(0)
            audio_bytes = buffer.read()
            return audio_bytes if len(audio_bytes) > 0 else None
        except Exception:
            return None

    @property
    def khaya_calls_used(self) -> int:
        return self._khaya_call_count


tts_service = TTSService()
