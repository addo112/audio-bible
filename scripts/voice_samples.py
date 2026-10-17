"""
Generate voice samples from candidate native Twi TTS models so a Twi speaker can choose.

Usage:
    python scripts/voice_samples.py
Writes WAV files to samples/ and prints synthesis speed for each voice.
"""
import os
import sys
import time
import wave

import numpy as np
import torch
from transformers import AutoTokenizer, VitsModel

CANDIDATES = {
    "A_bibletts": "danieldzikunuofmarvel/mms-tts-asante-twi-bibletts",
    "B_tekyerema": "ghananlpcommunity/tekyerema-tts-twi",
    "C_mms_base": "facebook/mms-tts-aka",
}

TEXT = (
    "Me nua dɔfo, akwaaba. Awurade ne me hwɛfoɔ, biribiara renhia me. "
    "Ɔma me da adidibea frɔmfrɔm, na ɔdi me anim kɔ nsuo a ɛho dwo ho."
)

OUT = os.path.join(os.path.dirname(__file__), "..", "samples")
torch.set_num_threads(4)


def write_wav(path, audio, sr):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    os.makedirs(OUT, exist_ok=True)
    for label, repo in CANDIDATES.items():
        try:
            t0 = time.time()
            tok = AutoTokenizer.from_pretrained(repo)
            model = VitsModel.from_pretrained(repo).eval()
            load = time.time() - t0
            inputs = tok(TEXT, return_tensors="pt")
            torch.manual_seed(0)
            t1 = time.time()
            with torch.inference_mode():
                wav = model(**inputs).waveform[0].numpy()
            synth = time.time() - t1
            sr = model.config.sampling_rate
            dur = len(wav) / sr
            path = os.path.join(OUT, f"{label}.wav")
            write_wav(path, wav, sr)
            print(f"{label:14s} load={load:5.1f}s synth={synth:4.2f}s audio={dur:4.1f}s RTF={synth / dur:.2f} -> {os.path.abspath(path)}")
        except Exception as e:
            print(f"{label:14s} FAILED: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
