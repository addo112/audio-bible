"""
Step 3: Local Native Asante Twi Text-to-Speech (`BibleTTS VITS` / `Kasanoma` / `Nano-Twi` / `EveryVoice`).

Supports multiple offline neural Asante Twi TTS backends on CPU:
1. `bibletts` (`danieldzikunuofmarvel/mms-tts-asante-twi-bibletts`) — VITS model fine-tuned
   directly on the single-speaker Open.Bible / BibleTTS Asante Twi studio narrator
   (deep baritone Ghanaian lector heard in the official Asante Twi Audio Bible).
   Uses `VitsTokenizer.from_pretrained(..., normalize=False)` + `VOCAB = set(tok.encoder)`
   with NFC normalization, lowercase mapping, and Twi number expansion so every Akan
   character (`ɛ`, `ɔ`, punctuation, apostrophes) is preserved accurately.
2. `nano-twi` (`ghananlpcommunity/nano-twi` by `michsethowusu`) — Matcha-TTS + Vocos 22.05 kHz
   ONNX model served via `sherpa-onnx` with `espeak-ng` `lfn` IPA phonemization.
3. `kasanoma` (`michsethowusu/kasanoma`) — Piper VITS 16 kHz ONNX model served via `sherpa-onnx`.
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
import unicodedata
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
BIBLETTS_REPO = "danieldzikunuofmarvel/mms-tts-asante-twi-bibletts"

_CHAR_MAP = {
    "\u201c": "",
    "\u201d": "",
    '"': "",
    "\u2013": " ",
    "\u2014": ", ",
    "-": " ",
    "\u00a0": " ",
    "\u2026": ".",
    "ↄ": "ɔ",
    "Ↄ": "Ɔ",
}

# Spoken Asante Twi equivalents for English/Biblical names and loanwords
_TWI_WORD_PHONETICS: dict[str, str] = {
    "genesis": "gyenesis",
    "exodus": "eksodos",
    "leviticus": "lewitikos",
    "numbers": "numeri",
    "deuteronomy": "deuteronomium",
    "joshua": "yosua",
    "judges": "atemmufoɔ",
    "ruth": "rut",
    "chronicles": "berɛsosɛm",
    "ezra": "esra",
    "nehemiah": "nehemia",
    "esther": "ester",
    "job": "hiob",
    "psalms": "nnwom",
    "psalm": "dwom",
    "proverbs": "mmebusɛm",
    "ecclesiastes": "ɔsɛnkafoɔ",
    "isaiah": "yesaia",
    "jeremiah": "yeremia",
    "lamentations": "kwadwom",
    "ezekiel": "hesekiel",
    "obadiah": "obadia",
    "jonah": "yona",
    "micah": "mika",
    "habakkuk": "habakuk",
    "zephaniah": "sefania",
    "haggai": "hagai",
    "zechariah": "sakaria",
    "malachi": "malaki",
    "matthew": "mateo",
    "mark": "marko",
    "luke": "luka",
    "john": "yohane",
    "acts": "asomafoɔ nnwuma",
    "romans": "romafoɔ",
    "corinthians": "korintofoɔ",
    "corinth": "korinto",
    "galatians": "galatifoɔ",
    "ephesians": "efesofoɔ",
    "ephesus": "efeso",
    "philippians": "filipifoɔ",
    "philippi": "filipi",
    "colossians": "kolosefoɔ",
    "thessalonians": "tesalonikafoɔ",
    "timothy": "timoteo",
    "titus": "tito",
    "philemon": "filemon",
    "hebrews": "hebrifoɔ",
    "hebrew": "hebri",
    "james": "yakobo",
    "peter": "petro",
    "jude": "yuda",
    "judah": "yuda",
    "judas": "yuda",
    "revelation": "adiyisɛm",
    "revelations": "adiyisɛm",
    "jesus": "yesu",
    "christ": "kristo",
    "jehovah": "yehowa",
    "yahweh": "yehowa",
    "david": "dawid",
    "moses": "mose",
    "jacob": "yakob",
    "joseph": "yosef",
    "isaac": "isak",
    "solomon": "salomo",
    "elijah": "eliya",
    "elisha": "elisa",
    "jerusalem": "yerusalem",
    "zion": "sion",
    "egypt": "misraim",
    "babylon": "babilonia",
    "galilee": "galilea",
    "nazareth": "nasaret",
    "bethlehem": "betlehem",
    "jordan": "yordan",
    "pharaoh": "farao",
    "paul": "paulo",
    "barnabas": "barnaba",
    "stephen": "stefano",
    "mary": "maria",
    "martha": "marta",
    "lazarus": "lasaro",
    "bible": "twerɛ kronkron",
    "chapter": "eti",
    "verse": "emu",
    "pastor": "ɔsɔfoɔ",
}

_WORD_PHONETICS_RE = re.compile(
    r"\b(" + "|".join(sorted(_TWI_WORD_PHONETICS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _strip_combining_keep_akan(text: str) -> str:
    """
    Strip combining diacritics (turning ã -> a, õ -> o, á -> a, ɛ́ -> ɛ, ɔ́ -> ɔ)
    so nasalized or tone-marked Twi vowels are never dropped or routed to untrained tokens,
    while preserving Akan open vowels (ɛ, ɔ) and elision apostrophe (ʼ).
    """
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def normalize_twi_phonetics(text: str) -> str:
    """
    Map English/Biblical names and any non-Akan Latin consonants (c, j, q, v, x, z)
    into pure Asante Twi orthographic phonetics so every syllable is pronounced with
    authentic Ghanaian phonology.
    """
    t = _WORD_PHONETICS_RE.sub(
        lambda m: _TWI_WORD_PHONETICS[m.group(0).lower()], text
    )
    # Map non-Akan consonant digraphs & letters to Akan phonetic equivalents
    t = re.sub(r"ch", "ky", t, flags=re.IGNORECASE)
    t = re.sub(r"sh", "hy", t, flags=re.IGNORECASE)
    t = re.sub(r"ph", "f", t, flags=re.IGNORECASE)
    t = re.sub(r"th", "t", t, flags=re.IGNORECASE)
    t = re.sub(r"qu", "kw", t, flags=re.IGNORECASE)
    t = re.sub(r"c(?=[eiyɛEIYƐ])", "s", t)
    t = re.sub(r"[cC]", "k", t)
    t = re.sub(r"[jJ]", "gy", t)
    t = re.sub(r"[vV]", "w", t)
    t = re.sub(r"[xX]", "ks", t)
    t = re.sub(r"[zZ]", "s", t)
    t = re.sub(r"[qQ]", "k", t)
    return t


def prepare_for_speech(text: str) -> str:
    """
    Normalize Asante Twi text for natural Ghanaian liturgical pronunciation:
    - Strip USFM cross-references, inline footnotes, markdown, brackets, and emojis
    - Strip duplicate parenthetical numerals like '(228)' after spoken Twi numbers
    - Preserve intra-word Asante Twi elisions (nʼasɛm, wʼakoma, mʼagya) with U+02BC 'ʼ'
    - Convert Bible verse citations (e.g. 3:16 -> eti mmiɛnsa, emu dunsia)
    - Convert verse ranges (e.g. 1-31 -> firi emu baako de kɔsi aduasa baako)
    - Convert digits to spoken Asante Twi number words
    - Normalize nasalized/toned vowels (ã -> a, õ -> o, á -> a) and non-Akan consonants
    """
    t = _EMOJI.sub("", text)
    # Strip USFM cross-reference tags (\+xt ... \+xt*) and inline USFM footnotes (+ ch.v Note.)
    t = re.sub(r"\(\\\+xt\s+[^)]*\\\+xt\*\)", "", t)
    t = re.sub(r"\\\+[a-z]+\*?", "", t)
    t = re.sub(r"\s*\+\s*\d+\.\d+\s+[^.]+\.(?:\u201d|\")?", "", t)
    # Strip parenthetical duplicate numerals e.g. "ahanu aduonu nwɔtwe (228)"
    t = re.sub(r"\(\s*\d[\d,.\s]*\)", "", t)
    t = re.sub(r"[#*_>`\[\]()~]", "", t)
    t = (
        t.replace("—", ", ")
        .replace("–", "-")
        .replace("“", "")
        .replace("”", "")
        .replace('"', "")
        .replace("ↄ", "ɔ")
        .replace("Ↄ", "Ɔ")
    )
    # Preserve intra-word Asante Twi elisions (e.g. n'asɛm, w’akoma, m'agya -> nʼasɛm)
    # using U+02BC 'ʼ' (token ID 1 in BibleTTS VITS, trained on 8,479 elisions)
    t = re.sub(r"(?<=[A-Za-zɛɔƐƆ])['’‘ʼ](?=[A-Za-zɛɔƐƆ])", "ʼ", t)
    # Remove any remaining standalone single quotes so untrained ASCII "'" token is never used
    t = re.sub(r"['’‘]", "", t)

    # Chapter:Verse-Verse (e.g. 1:1-31 -> eti baako, firi emu baako de kɔsi aduasa baako)
    t = re.sub(
        r"(\d+)\s*:\s*(\d+)\s*-\s*(\d+)",
        lambda m: (
            f"eti {twi_number(int(m.group(1)))}, "
            f"firi emu {twi_number(int(m.group(2)))} de kɔsi {twi_number(int(m.group(3)))}"
        ),
        t,
    )
    # Chapter:Verse (e.g. 3:16 -> eti mmiɛnsa, emu dunsia)
    t = re.sub(
        r"(\d+)\s*:\s*(\d+)",
        lambda m: f"eti {twi_number(int(m.group(1)))}, emu {twi_number(int(m.group(2)))}",
        t,
    )
    t = re.sub(
        r"(\d+)\s*-\s*(\d+)",
        lambda m: f"firi {twi_number(int(m.group(1)))} de kɔsi {twi_number(int(m.group(2)))}",
        t,
    )
    t = re.sub(r"\d+", lambda m: twi_number(int(m.group(0))), t)
    t = _strip_combining_keep_akan(t)
    t = normalize_twi_phonetics(t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str, max_len: int = 200) -> list[str]:
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


def split_clauses(text: str, max_clause_len: int = 165) -> list[tuple[str, float]]:
    """
    Split prepared Asante Twi text into complete sentence breath-groups so VITS
    preserves natural Akan tonal downdrift (terracing) across each sentence:
    - Sentence/verse endings (. ! ? ;) -> 0.26s liturgical pause
    - Colon introductions (:) -> 0.16s pause
    - Long sentences (> max_clause_len) split at the nearest comma (,) -> 0.12s pause
    """
    raw_parts = [
        p.strip()
        for p in re.split(r"(?<=[.!?;:])\s+|\n+", text)
        if p.strip()
    ]
    clauses: list[tuple[str, float]] = []
    for part in raw_parts:
        end_pause = 0.16 if part.endswith(":") else 0.26
        while len(part) > max_clause_len:
            cut = part.rfind(",", 0, max_clause_len)
            if cut > max_clause_len // 3:
                clauses.append((part[: cut + 1].strip(), 0.12))
                part = part[cut + 1 :].strip()
            else:
                cut = part.rfind(" ", 0, max_clause_len)
                if cut <= 0:
                    break
                clauses.append((part[:cut].strip(), 0.10))
                part = part[cut + 1 :].strip()
        if part:
            clauses.append((part, end_pause))
    return clauses


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
    """
    Offline neural Asante Twi TTS powered by:
    - `bibletts` (`danieldzikunuofmarvel/mms-tts-asante-twi-bibletts` — exact Open.Bible studio narrator)
    - `sherpa-onnx` (`kasanoma` Piper VITS / `nano-twi` Matcha+Vocos) fallback.
    """

    def __init__(self):
        s = get_settings()
        self.model_id = s.LOCAL_TTS_MODEL or "bibletts"
        self.speed = s.LOCAL_TTS_SPEAKING_RATE or 0.94
        self.threads = max(1, s.TORCH_THREADS)
        self._sherpa_tts = None
        self._vits_model = None
        self._vits_tok = None
        self._vits_vocab: set[str] = set()
        self._torch = None
        self.sampling_rate = 16000
        self._lock = threading.Lock()
        self.available = True
        self.error: str | None = None

    def _ensure_nano_twi_files(self) -> str:
        """Ensure nano-twi sherpa-onnx bundle is present on disk and return its directory."""
        bundle_dir = os.path.join(MODELS_DIR, "nano-twi", "nano-twi")
        acoustic = os.path.join(bundle_dir, "twi_ep045_steps4.onnx")
        vocoder = os.path.join(bundle_dir, "vocos-22khz-univ.onnx")
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
            steps2 = os.path.join(bundle_dir, "twi_ep045_steps2.onnx")
            if os.path.exists(steps2):
                os.remove(steps2)
        except OSError:
            pass
        return bundle_dir

    def _ensure_kasanoma_files(self) -> tuple[str, str]:
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

    def _clean_for_vits(self, text: str) -> str:
        """
        Clean and normalize Asante Twi text for `mms-tts-asante-twi-bibletts`:
        1. Expand numbers, references, nasal/toned vowels & loanwords (`prepare_for_speech`)
        2. NFC normalize + map punctuation + lowercase
        3. Filter characters to trained VITS tokens (excluding untrained outlier embeddings
           like '-', ASCII "'", '2', '3', 'á' while preserving trained 'ʼ' U+02BC!)
        """
        t = prepare_for_speech(text)
        t = unicodedata.normalize("NFC", t)
        t = "".join(_CHAR_MAP.get(c, c) for c in t).lower()
        if self._vits_vocab:
            t = "".join(c if c in self._vits_vocab else " " for c in t)
        return re.sub(r"\s+", " ", t).strip()

    def load(self) -> bool:
        """Load the configured local Asante Twi neural TTS model."""
        if self._vits_model is not None or self._sherpa_tts is not None:
            return True
        if not self.available:
            return False

        with self._lock:
            if self._vits_model is not None or self._sherpa_tts is not None:
                return True

            # Strategy A: Open.Bible / BibleTTS VITS narrator (`danieldzikunuofmarvel/mms-tts-asante-twi-bibletts`)
            if self.model_id in ("bibletts", "vits") or "/" in self.model_id:
                try:
                    t0 = time.time()
                    import torch
                    from transformers import VitsModel, VitsTokenizer

                    hf_id = (
                        self.model_id
                        if "/" in self.model_id
                        else BIBLETTS_REPO
                    )
                    torch.set_num_threads(self.threads)
                    self._vits_tok = VitsTokenizer.from_pretrained(hf_id, normalize=False)
                    # Exclude the 5 untrained outlier token embeddings (-, ', 2, 3, á)
                    # while keeping all 31 trained Akan letters, punctuation, and 'ʼ' (U+02BC)
                    self._vits_vocab = set(self._vits_tok.encoder) - {"-", "'", "2", "3", "á"}
                    self._vits_model = VitsModel.from_pretrained(hf_id).eval()
                    self._vits_model.speaking_rate = self.speed
                    # Stabilize Akan tonal vowel length & vocal fold periodicity
                    self._vits_model.noise_scale = 0.42
                    self._vits_model.noise_scale_duration = 0.50
                    self._torch = torch
                    self.sampling_rate = self._vits_model.config.sampling_rate
                    logger.info(
                        f"Asante Twi BibleTTS narrator loaded ({hf_id}, {self.sampling_rate}Hz, "
                        f"speaking_rate={self.speed}, noise_scale=0.42, duration_noise=0.50) in {time.time() - t0:.1f}s"
                    )
                    return True
                except Exception as e:
                    logger.warning(f"BibleTTS VITS load failed ({e}), falling back to sherpa-onnx...")

            # Strategy B: sherpa-onnx (Kasanoma Piper VITS or Nano-Twi Matcha+Vocos)
            try:
                t0 = time.time()
                import sherpa_onnx

                nano_dir = self._ensure_nano_twi_files()
                espeak_dir = os.path.join(nano_dir, "espeak-ng-data")

                if self.model_id in ("kasanoma", "piper"):
                    onnx_path, tokens_path = self._ensure_kasanoma_files()
                    self._sherpa_tts = sherpa_onnx.OfflineTts(
                        sherpa_onnx.OfflineTtsConfig(
                            model=sherpa_onnx.OfflineTtsModelConfig(
                                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                                    model=onnx_path,
                                    lexicon="",
                                    tokens=tokens_path,
                                    data_dir=espeak_dir,
                                    noise_scale=0.50,
                                    noise_scale_w=0.60,
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
                                    noise_scale=0.55,
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
                self.available = False
                self.error = str(e)
                logger.warning(f"Local TTS unavailable: {e}")
                return False

    def synthesize_pcm(self, text: str) -> bytes | None:
        """Synthesize one clause/sentence -> raw 16-bit PCM bytes (mono) with smooth cosine envelope."""
        if not self.load():
            return None

        with self._lock:
            if self._vits_model is not None:
                import numpy as np

                clean = self._clean_for_vits(text)
                if not re.search(r"[a-zɛɔ]", clean):
                    return None
                inputs = self._vits_tok(clean, return_tensors="pt")
                if inputs["input_ids"].shape[-1] < 2:
                    return None
                self._torch.manual_seed(42)
                with self._torch.inference_mode():
                    wav = self._vits_model(**inputs).waveform[0].detach().numpy()

                # Trim leading/trailing near-silence so inter-clause breath pauses are exact
                non_silent = np.flatnonzero(np.abs(wav) > 0.004)
                if len(non_silent) > 0:
                    pad_head = min(int(self.sampling_rate * 0.015), int(non_silent[0]))
                    pad_tail = min(
                        int(self.sampling_rate * 0.025),
                        len(wav) - 1 - int(non_silent[-1]),
                    )
                    wav = wav[
                        int(non_silent[0]) - pad_head : int(non_silent[-1]) + 1 + pad_tail
                    ]

                # Gentle peak normalization for consistent warm narrator presence
                peak = float(np.max(np.abs(wav))) if len(wav) > 0 else 0.0
                if peak > 0.02:
                    wav = wav * (0.90 / max(peak, 0.25))

                # 8ms fade-in and 12ms fade-out raised-cosine window to prevent boundary clicks
                fade_in = min(int(self.sampling_rate * 0.008), len(wav) // 4)
                fade_out = min(int(self.sampling_rate * 0.012), len(wav) // 4)
                if fade_in > 1:
                    wav[:fade_in] *= 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fade_in)))
                if fade_out > 1:
                    wav[-fade_out:] *= 0.5 * (
                        1.0 + np.cos(np.linspace(0.0, np.pi, fade_out))
                    )

                return (np.clip(wav, -1, 1) * 32767).astype(np.int16).tobytes()

            if self._sherpa_tts is not None:
                clean = prepare_for_speech(text)
                if not re.search(r"[A-Za-zɛɔƐƆ]", clean):
                    return None
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

        return None

    def synthesize(self, text: str, pause_s: float = 0.26) -> tuple[bytes | None, str | None]:
        """Synthesize any length of Asante Twi text -> WAV bytes with natural clause & sentence pauses."""
        clauses = split_clauses(prepare_for_speech(text))
        if not clauses:
            return None, None
        scale = pause_s / 0.26 if pause_s > 0 else 1.0
        pcm = b""
        for idx, (clause_text, base_pause) in enumerate(clauses):
            part = self.synthesize_pcm(clause_text)
            if part:
                actual_pause = base_pause * scale if idx < len(clauses) - 1 else 0.08
                silence = b"\x00\x00" * int(self.sampling_rate * actual_pause)
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
