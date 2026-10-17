"""
Step 1: Speech-to-Text (Voice Input) for Asante Twi (Akan).

Supports:
1. Faster-Whisper with the GhanaNLP Akan/Twi fine-tuned Whisper model
   (`ghananlpcommunity/whisper-large-v3-turbo-twi-ctranslate`) on CPU int8.
2. Hugging Face `transformers` ASR pipeline (`ghananlpcommunity/whisper-small-twi`).
3. Multi-model Gemini Asante Twi audio transcription fallback (`gemini-3.5-flash`,
   `gemini-3.8-flash`, `gemini-flash-latest`) with authentic Akan orthography (`ɛ`, `ɔ`).
"""
from __future__ import annotations

import io
import logging
import tempfile
import threading
import time

from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)

GEMINI_STT_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3.6-flash",
]


class STTService:
    """Speech-to-Text for spoken Asante Twi."""

    def __init__(self):
        s = get_settings()
        self.engine = s.STT_ENGINE
        self.model_id = s.WHISPER_MODEL
        self.hf_model_id = s.WHISPER_HF_MODEL
        self._model = None
        self._hf_pipe = None
        self._lock = threading.Lock()
        self.available = self.engine == "whisper"
        self.error: str | None = None

    def load(self) -> bool:
        """Load local Akan/Twi Whisper model (Faster-Whisper primary, HF transformers secondary)."""
        if self._model is not None or self._hf_pipe is not None:
            return True
        if not self.available:
            return False
        with self._lock:
            if self._model is not None or self._hf_pipe is not None:
                return True
            s = get_settings()
            # 1) Try Faster-Whisper (CTranslate2 int8)
            try:
                t0 = time.time()
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.model_id,
                    device="cpu",
                    compute_type=s.WHISPER_COMPUTE_TYPE,
                    cpu_threads=s.TORCH_THREADS,
                )
                logger.info(
                    f"Faster-Whisper Twi STT loaded ({self.model_id}) in {time.time() - t0:.1f}s"
                )
                return True
            except Exception as e:
                logger.info(f"Faster-Whisper unavailable ({e}); checking HF transformers...")

            # 2) Try Hugging Face transformers pipeline (only if torch + transformers installed)
            try:
                t0 = time.time()
                from transformers import pipeline

                self._hf_pipe = pipeline(
                    "automatic-speech-recognition",
                    model=self.hf_model_id,
                    device=-1,
                )
                self.model_id = self.hf_model_id
                logger.info(
                    f"HF Transformers Twi Whisper loaded ({self.hf_model_id}) in {time.time() - t0:.1f}s"
                )
                return True
            except Exception as e:
                self.available = False
                self.error = str(e)
                logger.info(
                    f"Local Whisper STT not loaded ({e}); using Gemini Asante Twi ASR fallback."
                )
                return False

    def _whisper(self, audio_bytes: bytes) -> str:
        with self._lock:
            if self._model is not None:
                segments, _info = self._model.transcribe(
                    io.BytesIO(audio_bytes),
                    beam_size=1,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    without_timestamps=True,
                )
                return " ".join(seg.text.strip() for seg in segments).strip()
            if self._hf_pipe is not None:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                    tmp.write(audio_bytes)
                    tmp.flush()
                    out = self._hf_pipe(tmp.name)
                    return (out.get("text") or "").strip()
        return ""

    def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str,
        gemini_client=None,
        gemini_model: str = "",
    ) -> tuple[str, str]:
        """Return (transcript, engine_used). Blocking — call from a worker thread."""
        if self.load():
            try:
                text = self._whisper(audio_bytes)
                if text:
                    return text, "whisper-twi"
            except Exception as e:
                logger.warning(f"Local Whisper transcription failed: {e}")

        if gemini_client is None:
            return "", "none"

        models_to_try = []
        if gemini_model and gemini_model != "gemini-2.5-flash":
            models_to_try.append(gemini_model)
        for m in GEMINI_STT_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        prompt = (
            "The speaker is a Ghanaian talking to an Asante Twi Audio Bible app. "
            "Transcribe what they said accurately in Asante Twi orthography (using ɛ and ɔ properly). "
            "If they mentioned a Bible book, chapter (ti), or verse (nkyekyɛm), preserve it clearly. "
            "Output ONLY the transcribed words, nothing else."
        )

        for model in models_to_try:
            try:
                resp = gemini_client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.0, max_output_tokens=250
                    ),
                )
                text = (resp.text or "").strip().strip('"').strip("'")
                if text:
                    return text, f"gemini-asr ({model})"
            except Exception as e:
                logger.warning(f"Gemini STT failed on {model}: {e}")
                continue

        return "", "none"


stt_service = STTService()
