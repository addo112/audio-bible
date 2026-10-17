"""
API Routes — Streaming conversational endpoint (/api/converse) plus legacy REST endpoints.

Primary flow:
  POST /api/converse → streams NDJSON events (transcript, text sentences, native audio WAV chunks)
  so the phone starts speaking the first sentence while the rest is still being generated.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import LANGUAGES
from app.services.bible_ai import bible_ai
from app.services.bible_index import bible_index
from app.services.conversation import conversation
from app.services.local_tts import local_tts
from app.services.stt_service import stt_service
from app.services.tts_service import tts_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_audio_cache: dict[str, tuple[bytes, str]] = {}
MAX_CACHE_SIZE = 50


def _cache_key(text: str, language: str) -> str:
    return hashlib.md5(f"{language}:{text[:200]}".encode()).hexdigest()


def _normalize_mime(content_type: str | None) -> str:
    mime_type = content_type or "audio/webm"
    if "webm" in mime_type:
        return "audio/webm"
    if "wav" in mime_type:
        return "audio/wav"
    if "mp4" in mime_type or "m4a" in mime_type:
        return "audio/mp4"
    if "ogg" in mime_type:
        return "audio/ogg"
    if "mpeg" in mime_type or "mp3" in mime_type:
        return "audio/mp3"
    return "audio/webm"


@router.post("/converse")
async def converse(
    audio: UploadFile | None = File(None, description="Recorded voice input"),
    text: str | None = Form(None, description="Optional text input instead of audio"),
    language: str = Form("tw", description="Language code"),
    session_id: str | None = Form(None, description="Session ID for conversation continuity"),
):
    """
    Streamed conversational voice loop (NDJSON).
    Each line is a JSON object:
      - {"type": "session", "session_id": "..."}
      - {"type": "transcript", "text": "...", "engine": "whisper-twi"|"gemini"|"text"}
      - {"type": "mode", "mode": "read"|"answer", "title": "..."}
      - {"type": "text", "seq": 1, "text": "..."}
      - {"type": "audio", "seq": 1, "audio": "<base64 wav>", "mime": "audio/wav"}
      - {"type": "timing", ...}
      - {"type": "done"}
    """
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")

    audio_bytes: bytes | None = None
    mime_type = "audio/webm"
    if audio is not None:
        audio_bytes = await audio.read()
        if len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Audio too short.")
        mime_type = _normalize_mime(audio.content_type)
    elif not text or not text.strip():
        raise HTTPException(status_code=400, detail="Provide either audio or text.")

    async def event_stream():
        try:
            async for event in conversation.run(
                session_id=session_id,
                audio=audio_bytes,
                mime=mime_type,
                text=text,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except asyncio.CancelledError:
            logger.info("Client disconnected from /api/converse stream")
            raise
        except Exception as e:
            logger.exception(f"Error in /api/converse stream: {e}")
            err_ev = {
                "type": "error",
                "message": "Kafra, nsɛm bi ankɔ yie. Bɔ mmɔden bio.",
            }
            yield json.dumps(err_ev, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/process-voice")
async def process_voice(
    audio: UploadFile = File(..., description="Audio recording from user's microphone"),
    language: str = Form("tw", description="Language code"),
    session_id: str | None = Form(None, description="Session ID for conversation continuity"),
):
    """Legacy Phase 1 endpoint: Audio → STT + Bible Index / Gemini → Text response."""
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")

    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio too short.")

    mime_type = _normalize_mime(audio.content_type)
    sid, _ = bible_ai.get_session(session_id)

    transcript, engine = await asyncio.to_thread(
        stt_service.transcribe, audio_bytes, mime_type, bible_ai.client, bible_ai.primary_model
    )
    if not transcript:
        return JSONResponse(content={
            "text": "Kafra, mante wo asɛm no yie. Yɛ sɛ wobɛka bio.",
            "transcript": "",
            "language": language,
            "session_id": sid,
        })

    if not bible_index.ready:
        await asyncio.to_thread(bible_index.load)

    req = bible_index.parse_request(transcript)
    if req.mode == "read" and req.passage:
        verses = bible_index.get_passage(req.passage)
        if verses:
            lines = [f"📖 {req.passage.label}"] + [f"{v['verse']}. {v['text']}" for v in verses]
            return JSONResponse(content={
                "text": "\n".join(lines),
                "transcript": transcript,
                "language": language,
                "session_id": sid,
            })

    verses = bible_index.search(transcript, k=6)
    response_text = await bible_ai.answer(sid, transcript, verses)
    return JSONResponse(content={
        "text": response_text,
        "transcript": transcript,
        "language": language,
        "session_id": sid,
    })


@router.post("/process-text")
async def process_text(
    text: str = Form(..., description="User's text message"),
    language: str = Form("tw", description="Language code"),
    session_id: str | None = Form(None, description="Session ID for conversation continuity"),
):
    """Legacy Phase 1 endpoint: Text → Bible Index / Gemini → Text response."""
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    sid, _ = bible_ai.get_session(session_id)
    if not bible_index.ready:
        await asyncio.to_thread(bible_index.load)

    req = bible_index.parse_request(text)
    if req.mode == "read" and req.passage:
        verses = bible_index.get_passage(req.passage)
        if verses:
            lines = [f"📖 {req.passage.label}"] + [f"{v['verse']}. {v['text']}" for v in verses]
            return JSONResponse(content={
                "text": "\n".join(lines),
                "language": language,
                "session_id": sid,
            })

    verses = bible_index.search(text, k=6)
    response_text = await bible_ai.answer(sid, text, verses)
    return JSONResponse(content={
        "text": response_text,
        "language": language,
        "session_id": sid,
    })


@router.post("/generate-audio")
async def generate_audio(
    text: str = Form(..., description="Text to convert to speech"),
    language: str = Form("tw", description="Language code"),
):
    """Synthesize speech audio using native Twi TTS (with cache)."""
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")

    key = _cache_key(text, language)
    if key in _audio_cache:
        audio_data, audio_mime = _audio_cache[key]
        return JSONResponse(content={
            "has_audio": True,
            "audio": base64.b64encode(audio_data).decode("utf-8"),
            "audio_mime": audio_mime,
        })

    audio_data, audio_mime = await tts_service.synthesize(text, language)
    if audio_data:
        if len(_audio_cache) >= MAX_CACHE_SIZE:
            del _audio_cache[next(iter(_audio_cache))]
        _audio_cache[key] = (audio_data, audio_mime)
        return JSONResponse(content={
            "has_audio": True,
            "audio": base64.b64encode(audio_data).decode("utf-8"),
            "audio_mime": audio_mime,
        })

    return JSONResponse(content={"has_audio": False})


@router.get("/languages")
async def get_languages():
    return [
        {
            "code": code,
            "name": lang["name"],
            "native_name": lang["native_name"],
            "color": lang["color"],
            "color_light": lang["color_light"],
            "icon": lang["icon"],
        }
        for code, lang in LANGUAGES.items()
    ]


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Asante Twi Audio Bible",
        "version": "3.0.0",
        "bible_verses_indexed": len(bible_index.verses),
        "stt_model": stt_service.model_id if stt_service.available else "gemini-fallback",
        "tts_model": local_tts.model_id if local_tts.available else "cloud-fallback",
        "tts_khaya_calls": tts_service.khaya_calls_used,
    }
