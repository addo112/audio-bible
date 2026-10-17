"""
Local native Twi Text-to-Speech — VITS voices trained on Ghanaian speakers.

Runs fully on CPU (no API key, works offline). Default voice is chosen in config
(LOCAL_TTS_MODEL). Candidates:
  - danieldzikunuofmarvel/mms-tts-asante-twi-bibletts  (fine-tuned on BibleTTS Asante Twi)
  - ghananlpcommunity/tekyerema-tts-twi                (GhanaNLP fine-tune)
  - facebook/mms-tts-aka                               (Meta MMS Akan base)
All are CC BY-NC 4.0 (non-commercial use).
"""
from __future__ import annotations

import io
import logging
import re
import threading
import time
import wave

from app.config import get_settings
from app.services.bible_books import twi_number

logger = logging.getLogger(__name__)

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def prepare_for_speech(text: str) -> str:
    """Make text speakable by a character-based Twi voice: no markdown, numbers as Twi words."""
    t = _EMOJI.sub("", text)
    t = re.sub(r"[#*_>`\[\]]", "", t)
    t = t.replace("—", ", ").replace("–", " kɔsi ").replace("“", "").replace("”", "").replace('"', "")
    t = re.sub(r"(\d+)\s*:\s*(\d+)", lambda m: f"ti {twi_number(int(m.group(1)))}, nkyekyɛm {twi_number(int(m.group(2)))}", t)
    t = re.sub(r"(\d+)\s*-\s*(\d+)", lambda m: f"{m.group(1)} kɔsi {m.group(2)}", t)
    t = re.sub(r"\d+", lambda m: twi_number(int(m.group(0))), t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str, max_len: int = 220) -> list[str]:
    """Split into speakable chunks at sentence punctuation, then at commas if still long."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?;:])\s+|\n+", text) if p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            cut = cut if cut > max_len // 3 else p.rfind(" ", 0, max_len)
            if cut <= 0:
                break
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


class LocalTTS:
    def __init__(self):
        self.model_id = get_settings().LOCAL_TTS_MODEL
        self._model = None
        self._tok = None
        self._torch = None
        self.sampling_rate = 16000
        self._lock = threading.Lock()
        self.available = True
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
                import torch
                from transformers import AutoTokenizer, VitsModel
                torch.set_num_threads(max(1, get_settings().TORCH_THREADS))
                self._tok = AutoTokenizer.from_pretrained(self.model_id)
                self._model = VitsModel.from_pretrained(self.model_id).eval()
                self._model.speaking_rate = get_settings().LOCAL_TTS_SPEAKING_RATE
                self._torch = torch
                self.sampling_rate = self._model.config.sampling_rate
                logger.info(f"Local Twi TTS loaded ({self.model_id}) in {time.time() - t0:.1f}s")
                return True
            except Exception as e:  # missing deps or download failure → fall back to other TTS
                self.available = False
                self.error = str(e)
                logger.warning(f"Local TTS unavailable: {e}")
                return False

    def synthesize_pcm(self, text: str) -> bytes | None:
        """Synthesize one sentence → raw 16-bit PCM bytes (mono)."""
        if not self.load():
            return None
        clean = prepare_for_speech(text)
        if not re.search(r"[A-Za-zɛɔƐƆ]", clean):
            return None
        import numpy as np
        with self._lock:
            inputs = self._tok(clean, return_tensors="pt")
            if inputs["input_ids"].shape[-1] < 2:
                return None
            with self._torch.inference_mode():
                wav = self._model(**inputs).waveform[0].numpy()
        return (np.clip(wav, -1, 1) * 32767).astype(np.int16).tobytes()

    def synthesize(self, text: str, pause_s: float = 0.25) -> tuple[bytes | None, str | None]:
        """Synthesize any length of text → WAV bytes."""
        chunks = split_sentences(prepare_for_speech(text))
        silence = b"\x00\x00" * int(self.sampling_rate * pause_s)
        pcm = b""
        for c in chunks:
            part = self.synthesize_pcm(c)
            if part:
                pcm += part + silence
        if not pcm:
            return None, None
        return self.to_wav(pcm), "audio/wav"

    def to_wav(self, pcm: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sampling_rate)
            w.writeframes(pcm)
        return buf.getvalue()


local_tts = LocalTTS()
