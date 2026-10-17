"""
Speech-to-Text for Asante Twi.

Primary: faster-whisper with the GhanaNLP Akan/Twi fine-tune of Whisper large-v3-turbo
         (ghananlpcommunity/whisper-large-v3-turbo-twi-ctranslate, CC BY-SA 4.0), on CPU int8.
Fallback: Gemini audio transcription (needs internet + API key).
"""
from __future__ import annotations

import io
import logging
import threading
import time

from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


class STTService:
    def __init__(self):
        s = get_settings()
        self.engine = s.STT_ENGINE
        self.model_id = s.WHISPER_MODEL
        self._model = None
        self._lock = threading.Lock()
        self.available = self.engine == "whisper"
        self.error: str | None = None

    def load(self) -> bool:
        if self._model is not None:
            return True
        if not self.available:
            return False
        with self._lock:
            if self._model is not None:
                return True
            try:
                t0 = time.time()
                from faster_whisper import WhisperModel
                s = get_settings()
                self._model = WhisperModel(self.model_id, device="cpu", compute_type=s.WHISPER_COMPUTE_TYPE,
                                           cpu_threads=s.TORCH_THREADS)
                logger.info(f"Whisper Twi STT loaded ({self.model_id}) in {time.time() - t0:.1f}s")
                return True
            except Exception as e:
                self.available = False
                self.error = str(e)
                logger.warning(f"Whisper STT unavailable, using Gemini transcription: {e}")
                return False

    def _whisper(self, audio_bytes: bytes) -> str:
        with self._lock:
            segments, _info = self._model.transcribe(
                io.BytesIO(audio_bytes),
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe(self, audio_bytes: bytes, mime_type: str, gemini_client=None, gemini_model: str = "") -> tuple[str, str]:
        """Return (transcript, engine_used). Blocking — call from a worker thread."""
        if self.load():
            try:
                text = self._whisper(audio_bytes)
                if text:
                    return text, "whisper-twi"
            except Exception as e:
                logger.warning(f"Whisper transcription failed: {e}")
        if gemini_client is None:
            return "", "none"
        resp = gemini_client.models.generate_content(
            model=gemini_model,
            contents=[
                "Transcribe this Asante Twi speech exactly as spoken, in Twi orthography (use ɛ and ɔ). "
                "Output only the transcript, nothing else.",
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=300),
        )
        return (resp.text or "").strip(), "gemini"


stt_service = STTService()
