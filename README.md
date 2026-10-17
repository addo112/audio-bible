# 📖 Asante Twi Audio Bible AI

**Voice-first Asante Twi Audio Bible & conversational Bible teacher for listeners in Ghana**

Built for people who prefer or need to hear God's Word rather than read. Speak in Asante Twi to:
- **Have whole chapters or passages read verbatim** from the Asante Twi Bible (e.g., *"Kenkan Dwom ti aduonu mmiɛnsa"*, *"Kenkan Genesis ti 1 kɔsi 3"*, or *"Toa so"* to continue to the next chapter)
- **Ask Bible questions in Twi** and receive short, warm, conversational answers grounded in retrieved Scripture

## 🏗️ Voice Loop Architecture

1. **Speech-to-Text (`app/services/stt_service.py`)**
   - Uses **Faster-Whisper** (`int8` on CPU) with GhanaNLP's fine-tuned Akan/Twi model (`ghananlpcommunity/whisper-large-v3-turbo-twi-ctranslate`), falling back to Gemini transcription if needed.
2. **Asante Twi Bible Knowledge Base (`app/services/bible_index.py`)**
   - 30,565 verses across all 66 books (`data/bible_tw.jsonl`), built from the verse-split Open.Bible Asante Twi corpus (`davidguzmanr/open-bible-resources` → `Twi (Asante)`).
   - Understands spoken Twi and English book names and Twi number words (*"Dwom ti aduonu mmiɛnsa"*, *"Yohane 3:16"*).
   - **Read mode:** streams the exact Bible verses directly without waiting for the LLM.
   - **Answer mode:** retrieves matching Twi verses via BM25 and streams a short (2–5 sentence) conversational answer from Google Gemini (`google-genai`).
3. **Native Twi Text-to-Speech (`app/services/local_tts.py`)**
   - Synthesizes each sentence as soon as it is ready using a VITS voice trained on Ghanaian Asante Twi speakers (`danieldzikunuofmarvel/mms-tts-asante-twi-bibletts` or `ghananlpcommunity/tekyerema-tts-twi`), running locally on CPU.
4. **Streaming Phone PWA (`static/js/app.js` + `POST /api/converse`)**
   - Streams NDJSON events (`transcript`, `text`, `audio`) so the phone plays the first sentence while the rest is still being generated.

## 🚀 Running Locally

```powershell
# 1. Build the Asante Twi Bible index (one-time, downloads text columns only)
C:\Users\user\.venvs\audio-bible\Scripts\python.exe scripts\build_bible_index.py

# 2. Start the server
C:\Users\user\.venvs\audio-bible\Scripts\python.exe main.py
```

Open **http://localhost:8000** in your browser (or on a phone on the same Wi-Fi).

### Choosing the Twi Voice
Generate comparison samples of the 3 local Twi voices:
```powershell
C:\Users\user\.venvs\audio-bible\Scripts\python.exe scripts\voice_samples.py
```
Listen to `samples/A_bibletts.wav`, `samples/B_tekyerema.wav`, and `samples/C_mms_base.wav`. To switch voices, set `LOCAL_TTS_MODEL` in `.env`:
- `LOCAL_TTS_MODEL=danieldzikunuofmarvel/mms-tts-asante-twi-bibletts` (default)
- `LOCAL_TTS_MODEL=ghananlpcommunity/tekyerema-tts-twi`
- `LOCAL_TTS_MODEL=facebook/mms-tts-aka`

## 📜 Credits & Licences

- **Asante Twi Bible Text:** [Biblica Open.Bible Asante Twi](https://open.bible/) via [`davidguzmanr/open-bible-resources`](https://huggingface.co/datasets/davidguzmanr/open-bible-resources) and [`coqui-ai/open-bible-scripts`](https://github.com/coqui-ai/open-bible-scripts) — licensed under **CC BY-SA 4.0**.
- **Twi Speech Recognition (Whisper):** [`ghananlpcommunity/whisper-large-v3-turbo-twi-ctranslate`](https://huggingface.co/ghananlpcommunity/whisper-large-v3-turbo-twi-ctranslate) (converted from `katrintomanek/whisper-large-v3-turbo_Akan_standardspeech_specaugment`) — licensed under **CC BY-SA 4.0**.
- **Native Twi Voices (VITS / MMS):** [`danieldzikunuofmarvel/mms-tts-asante-twi-bibletts`](https://huggingface.co/danieldzikunuofmarvel/mms-tts-asante-twi-bibletts), [`ghananlpcommunity/tekyerema-tts-twi`](https://huggingface.co/ghananlpcommunity/tekyerema-tts-twi), and [`facebook/mms-tts-aka`](https://huggingface.co/facebook/mms-tts-aka) — licensed under **CC BY-NC 4.0** (non-commercial research, educational, and ministry use).
