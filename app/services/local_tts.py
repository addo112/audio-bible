"""
Step 3: Local Native Asante Twi Text-to-Speech (`Kasanoma` / `Piper TTS` / `Nano-Twi` / `EveryVoice`).

Supports multiple offline neural Asante Twi TTS backends on CPU:
1. `nano-twi` (`ghananlpcommunity/nano-twi` by `michsethowusu`) — Matcha-TTS + Vocos 22.05 kHz
   ONNX model served via `sherpa-onnx` with `espeak-ng` `lfn` IPA phonemization (~4x realtime on CPU, no PyTorch).
2. `kasanoma` (`michsethowusu/kasanoma`) — Piper VITS 16 kHz ONNX model served via `sherpa-onnx`
   with `espeak-ng` `lfn` IPA phonemization (~8x realtime on CPU, no PyTorch).
3. `everyvoice` (`multilingual-tts/EveryVoice-OpenBible-Twi-Asante`) — FastSpeech2 + HiFi-GAN
   trained on 26,165 Open.Bible Asante Twi utterances.
4. `vits` (`danieldzikunuofmarvel/mms-tts-asante-twi-bibletts`) — Hugging Face VITS model.
"""
from __future__ import annotations

import array
import io
import json
import logging
import os
import re
import threading
import time
import urllib.request
import wave
import zipfile

from app.config import get_settings
from app.services.bible_books import twi_number

logger = logging.getLogger(__name__)

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")

MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "tts_models")
)
NANO_TWI_URL = "https://github.com/michsethowusu/nano-twi/releases/download/v1.0/nano-twi-sherpa-onnx.zip"
KASANOMA_URL = "https://github.com/michsethowusu/kasanoma/releases/download/v1/kasanoma_model-twi.zip"


def prepare_for_speech(text: str) -> str:
    """
    Normalize Asante Twi text for natural Ghanaian pronunciation:
    - Strip markdown, brackets, and emojis
    - Convert Bible verse citations (e.g. 3:16 -> ti mmiɛnsa, nkyekyɛm dunsia)
    - Convert digits to spoken Asante Twi number words
    - Normalize curly apostrophes and glottal stops (ʼ / ’ -> ')
    """
    t = _EMOJI.sub("", text)
    t = re.sub(r"[#*_>`\[\]]", "", t)
    t = (
        t.replace("—", ", ")
        .replace("–", " kɔsi ")
        .replace("“", "")
        .replace("”", "")
        .replace('"', "")
        .replace("ʼ", "'")
        .replace("’", "'")
    )
    t = re.sub(
        r"(\d+)\s*:\s*(\d+)",
        lambda m: f"ti {twi_number(int(m.group(1)))}, nkyekyɛm {twi_number(int(m.group(2)))}",
        t,
    )
    t = re.sub(r"(\d+)\s*-\s*(\d+)", lambda m: f"{m.group(1)} kɔsi {m.group(2)}", t)
    t = re.sub(r"\d+", lambda m: twi_number(int(m.group(0))), t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str, max_len: int = 240) -> list[str]:
    """Split into speakable sentences at punctuation, then at commas if still long."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?;:])\s+|\n+", text) if p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            cut = cut if cut > max_len // 3 else p.rfind(" ", 0, max_len)
            if cut <= 0:
                break
            out.append(p[: cut + 1].strip())
            p = p[cut + 1 :].strip()
        if p:
            out.append(p)
    return out


def _encode_onnx_metadata(meta: dict[str, str]) -> bytes:
    """Encode top-level ModelProto.metadata_props (field #14) in pure Python protobuf."""
    def enc_str(field_no: int, s: str) -> bytes:
        b = s.encode("utf-8")
        return bytes([(field_no << 3) | 2, len(b)]) + b

    def enc_kv(k: str, v: str) -> bytes:
        inner = enc_str(1, k) + enc_str(2, v)
        return bytes([(14 << 3) | 2, len(inner)]) + inner

    return b"".join(enc_kv(k, v) for k, v in meta.items())


class LocalTTS:
    """Offline neural Asante Twi TTS powered by sherpa-onnx (Kasanoma / Nano-Twi) or EveryVoice."""

    def __init__(self):
        s = get_settings()
        self.model_id = s.LOCAL_TTS_MODEL or "nano-twi"
        self.speed = s.LOCAL_TTS_SPEAKING_RATE or 0.96
        self.threads = max(1, s.TORCH_THREADS)
        self._sherpa_tts = None
        self._vits_model = None
        self._vits_tok = None
        self._torch = None
        self.sampling_rate = 22050
        self._lock = threading.Lock()
        self.available = True
        self.error: str | None = None

    def _ensure_nano_twi_files(self) -> str:
        """Ensure nano-twi sherpa-onnx bundle is present on disk and return its directory."""
        bundle_dir = os.path.join(MODELS_DIR, "nano-twi", "nano-twi")
        acoustic = os.path.join(bundle_dir, "twi_ep045_steps4.onnx")
        vocoder = os.path.join(bundle_dir, "vocos-22khz-univ.onnx")
        tokens = os.path.join(bundle_dir, "tokens.txt")
        espeak_dir = os.path.join(bundle_dir, "espeak-ng-data")

        if os.path.exists(acoustic) and os.path.exists(vocoder) and os.path.exists(espeak_dir):
            return bundle_dir

        os.makedirs(os.path.join(MODELS_DIR, "nano-twi"), exist_ok=True)
        zip_path = os.path.join(MODELS_DIR, "nano-twi.zip")
        logger.info(f"Downloading nano-twi ONNX bundle from {NANO_TWI_URL}...")
        urllib.request.urlretrieve(NANO_TWI_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(os.path.join(MODELS_DIR, "nano-twi"))
        try:
            os.remove(zip_path)
            # Remove steps2 model if present to save disk space
            steps2 = os.path.join(bundle_dir, "twi_ep045_steps2.onnx")
            if os.path.exists(steps2):
                os.remove(steps2)
        except OSError:
            pass
        return bundle_dir

    def _ensure_kasanoma_files(self, espeak_dir: str) -> tuple[str, str]:
        """Ensure Kasanoma Piper VITS ONNX model + tokens.txt are ready for sherpa-onnx."""
        k_dir = os.path.join(MODELS_DIR, "kasanoma")
        patched_onnx = os.path.join(k_dir, "kasanoma_sherpa.onnx")
        tokens_path = os.path.join(k_dir, "tokens.txt")
        raw_onnx = os.path.join(k_dir, "model.onnx")
        raw_json = os.path.join(k_dir, "model.onnx.json")

        if not (os.path.exists(raw_onnx) and os.path.exists(raw_json)):
            os.makedirs(k_dir, exist_ok=True)
            zip_path = os.path.join(MODELS_DIR, "kasanoma.zip")
            logger.info(f"Downloading Kasanoma Piper Twi model from {KASANOMA_URL}...")
            urllib.request.urlretrieve(KASANOMA_URL, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(k_dir)
            try:
                os.remove(zip_path)
            except OSError:
                pass

        if not os.path.exists(tokens_path):
            cfg = json.load(open(raw_json, encoding="utf-8"))
            with open(tokens_path, "w", encoding="utf-8") as f:
                for sym, ids in cfg["phoneme_id_map"].items():
                    f.write(f"{sym} {ids[0]}\n")

        if not os.path.exists(patched_onnx):
            meta = {
                "sample_rate": "16000",
                "voice": "lfn",
                "has_espeak": "1",
                "n_speakers": "1",
                "num_speakers": "1",
                "num_symbols": "256",
                "comment": "piper",
                "language": "Twi",
                "dataset": "kasanoma",
                "quality": "medium",
            }
            orig = open(raw_onnx, "rb").read()
            open(patched_onnx, "wb").write(orig + _encode_onnx_metadata(meta))

        return patched_onnx, tokens_path

    def load(self) -> bool:
        """Load the configured local Twi neural TTS model."""
        if self._sherpa_tts is not None or self._vits_model is not None:
            return True
        if not self.available:
            return False

        with self._lock:
            if self._sherpa_tts is not None or self._vits_model is not None:
                return True

            # Strategy A: sherpa-onnx (Kasanoma Piper VITS or Nano-Twi Matcha+Vocos)
            if self.model_id in ("nano-twi", "kasanoma", "piper"):
                try:
                    t0 = time.time()
                    import sherpa_onnx

                    nano_dir = self._ensure_nano_twi_files()
                    espeak_dir = os.path.join(nano_dir, "espeak-ng-data")

                    if self.model_id in ("kasanoma", "piper"):
                        onnx_path, tokens_path = self._ensure_kasanoma_files(espeak_dir)
                        self._sherpa_tts = sherpa_onnx.OfflineTts(
                            sherpa_onnx.OfflineTtsConfig(
                                model=sherpa_onnx.OfflineTtsModelConfig(
                                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                                        model=onnx_path,
                                        lexicon="",
                                        tokens=tokens_path,
                                        data_dir=espeak_dir,
                                        noise_scale=0.667,
                                        noise_scale_w=0.8,
                                        length_scale=1.02,
                                    ),
                                    num_threads=self.threads,
                                    provider="cpu",
                                ),
                                max_num_sentences=1,
                            )
                        )
                        self.sampling_rate = self._sherpa_tts.sample_rate
                        logger.info(
                            f"Kasanoma Piper Twi TTS loaded via sherpa-onnx ({self.sampling_rate}Hz) in {time.time() - t0:.1f}s"
                        )
                        return True
                    else:
                        # Default: Nano-Twi (Matcha-TTS + Vocos 22.05kHz by michsethowusu)
                        self._sherpa_tts = sherpa_onnx.OfflineTts(
                            sherpa_onnx.OfflineTtsConfig(
                                model=sherpa_onnx.OfflineTtsModelConfig(
                                    matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(
                                        acoustic_model=os.path.join(
                                            nano_dir, "twi_ep045_steps4.onnx"
                                        ),
                                        vocoder=os.path.join(
                                            nano_dir, "vocos-22khz-univ.onnx"
                                        ),
                                        lexicon="",
                                        tokens=os.path.join(nano_dir, "tokens.txt"),
                                        data_dir=espeak_dir,
                                        noise_scale=0.667,
                                        length_scale=1.0,
                                    ),
                                    num_threads=self.threads,
                                    provider="cpu",
                                ),
                                max_num_sentences=1,
                            )
                        )
                        self.sampling_rate = self._sherpa_tts.sample_rate
                        logger.info(
                            f"Nano-Twi Matcha+Vocos TTS loaded via sherpa-onnx ({self.sampling_rate}Hz) in {time.time() - t0:.1f}s"
                        )
                        return True
                except Exception as e:
                    logger.warning(f"sherpa-onnx Twi TTS load failed: {e}")

            # Strategy B: Hugging Face VITS fallback (if torch + transformers installed)
            try:
                t0 = time.time()
                import torch
                from transformers import AutoTokenizer, VitsModel

                hf_id = (
                    self.model_id
                    if "/" in self.model_id
                    else "danieldzikunuofmarvel/mms-tts-asante-twi-bibletts"
                )
                torch.set_num_threads(self.threads)
                self._vits_tok = AutoTokenizer.from_pretrained(hf_id)
                self._vits_model = VitsModel.from_pretrained(hf_id).eval()
                self._vits_model.speaking_rate = self.speed
                self._torch = torch
                self.sampling_rate = self._vits_model.config.sampling_rate
                logger.info(f"HF VITS Twi TTS loaded ({hf_id}) in {time.time() - t0:.1f}s")
                return True
            except Exception as e:
                self.available = False
                self.error = str(e)
                logger.warning(f"Local TTS unavailable: {e}")
                return False

    def synthesize_pcm(self, text: str) -> bytes | None:
        """Synthesize one sentence -> raw 16-bit PCM bytes (mono)."""
        if not self.load():
            return None
        clean = prepare_for_speech(text)
        if not re.search(r"[A-Za-zɛɔƐƆ]", clean):
            return None

        with self._lock:
            if self._sherpa_tts is not None:
                audio = self._sherpa_tts.generate(clean, sid=0, speed=self.speed)
                if not audio.samples:
                    return None
                self.sampling_rate = audio.sample_rate
                pcm = array.array(
                    "h",
                    (
                        int(max(-1.0, min(1.0, float(s))) * 32767)
                        for s in audio.samples
                    ),
                )
                return pcm.tobytes()

            if self._vits_model is not None:
                import numpy as np

                inputs = self._vits_tok(clean, return_tensors="pt")
                if inputs["input_ids"].shape[-1] < 2:
                    return None
                with self._torch.inference_mode():
                    wav = self._vits_model(**inputs).waveform[0].numpy()
                return (np.clip(wav, -1, 1) * 32767).astype(np.int16).tobytes()

        return None

    def synthesize(self, text: str, pause_s: float = 0.22) -> tuple[bytes | None, str | None]:
        """Synthesize any length of Asante Twi text -> WAV bytes."""
        chunks = split_sentences(prepare_for_speech(text))
        if not chunks:
            return None, None
        pcm = b""
        for c in chunks:
            part = self.synthesize_pcm(c)
            if part:
                silence = b"\x00\x00" * int(self.sampling_rate * pause_s)
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
