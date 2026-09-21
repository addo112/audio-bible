"""
API Routes — Two-phase REST endpoints for the Audio Bible app.

Phase 1: /api/process-voice or /api/process-text → returns AI text instantly (no TTS wait)
Phase 2: /api/generate-audio → generates TTS audio on demand (called by frontend after showing text)
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import base64
import logging
import hashlib
from app.services.bible_ai import bible_ai
from app.services.tts_service import tts_service
from app.config import LANGUAGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Simple in-memory audio cache (hash of text → audio data)
_audio_cache: dict[str, tuple[bytes, str]] = {}
MAX_CACHE_SIZE = 50


def _cache_key(text: str, language: str) -> str:
    """Generate cache key from text + language."""
    return hashlib.md5(f"{language}:{text[:200]}".encode()).hexdigest()


@router.post("/process-voice")
async def process_voice(
    audio: UploadFile = File(..., description="Audio recording from user's microphone"),
    language: str = Form(..., description="Language code: tw, fat, ee, gaa, ha"),
    session_id: str = Form(None, description="Session ID for conversation continuity"),
):
    """
    Phase 1: Audio → Gemini → Text response (NO TTS — returns fast).
    Frontend will call /api/generate-audio separately for speech.
    """
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio too short.")
    
    mime_type = audio.content_type or "audio/webm"
    if "webm" in mime_type:
        mime_type = "audio/webm"
    elif "wav" in mime_type:
        mime_type = "audio/wav"
    elif "mp4" in mime_type or "m4a" in mime_type:
        mime_type = "audio/mp4"
    elif "ogg" in mime_type:
        mime_type = "audio/ogg"
    elif "mpeg" in mime_type or "mp3" in mime_type:
        mime_type = "audio/mp3"
    
    logger.info(f"Voice: lang={language}, mime={mime_type}, size={len(audio_bytes)}")
    
    # Get AI response (text only — fast!)
    response_text, sid = await bible_ai.process_audio(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        language_code=language,
        session_id=session_id,
    )
    
    return JSONResponse(content={
        "text": response_text,
        "language": language,
        "session_id": sid,
    })


@router.post("/process-text")
async def process_text(
    text: str = Form(..., description="User's text message"),
    language: str = Form(..., description="Language code: tw, fat, ee, gaa, ha"),
    session_id: str = Form(None, description="Session ID for conversation continuity"),
):
    """
    Phase 1: Text → Gemini → Text response (NO TTS — returns fast).
    Frontend will call /api/generate-audio separately for speech.
    """
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    
    logger.info(f"Text: lang={language}, length={len(text)}")
    
    response_text, sid = await bible_ai.process_text(
        text=text,
        language_code=language,
        session_id=session_id,
    )
    
    return JSONResponse(content={
        "text": response_text,
        "language": language,
        "session_id": sid,
    })


@router.post("/generate-audio")
async def generate_audio(
    text: str = Form(..., description="Text to convert to speech"),
    language: str = Form(..., description="Language code"),
):
    """
    Phase 2: Text → TTS → Audio.
    Called by frontend AFTER showing the text response to the user.
    Returns base64-encoded audio data.
    """
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    
    # Check cache first
    key = _cache_key(text, language)
    if key in _audio_cache:
        audio_data, audio_mime = _audio_cache[key]
        logger.info(f"Audio cache hit for {language}")
        return JSONResponse(content={
            "has_audio": True,
            "audio": base64.b64encode(audio_data).decode("utf-8"),
            "audio_mime": audio_mime,
        })
    
    # Generate TTS
    audio_data, audio_mime = await tts_service.synthesize(text, language)
    
    if audio_data:
        # Cache the result
        if len(_audio_cache) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(_audio_cache))
            del _audio_cache[oldest_key]
        _audio_cache[key] = (audio_data, audio_mime)
        
        return JSONResponse(content={
            "has_audio": True,
            "audio": base64.b64encode(audio_data).decode("utf-8"),
            "audio_mime": audio_mime,
        })
    
    return JSONResponse(content={"has_audio": False})


@router.get("/languages")
async def get_languages():
    """Return list of supported languages with metadata for UI rendering."""
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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Audio Bible AI",
        "version": "2.0.0",
        "tts_khaya_calls": tts_service.khaya_calls_used,
    }
