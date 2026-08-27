"""
API Routes — REST endpoints for the Audio Bible app.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import base64
import logging
from app.services.bible_ai import bible_ai
from app.services.tts_service import tts_service
from app.config import LANGUAGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/process-voice")
async def process_voice(
    audio: UploadFile = File(..., description="Audio recording from user's microphone"),
    language: str = Form(..., description="Language code: tw, fat, ee, gaa, ha"),
    session_id: str = Form(None, description="Session ID for conversation continuity"),
):
    """
    Main voice processing endpoint.
    
    Flow: Audio → Gemini (understand + Bible response) → TTS → Audio response
    
    The audio is sent directly to Gemini which:
    1. Understands the spoken language (Twi, Fante, Ewe, GA, Hausa)
    2. Processes the Bible question
    3. Responds in the same language
    """
    # Validate language
    if language not in LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {language}. Supported: {list(LANGUAGES.keys())}"
        )
    
    # Read audio data
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio too short. Please speak longer.")
    
    # Determine mime type
    mime_type = audio.content_type or "audio/webm"
    # Normalize common mime types
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
    
    logger.info(f"Processing voice: lang={language}, mime={mime_type}, size={len(audio_bytes)} bytes")
    
    # Step 1: Gemini processes audio → Bible response in target language
    response_text, sid = await bible_ai.process_audio(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        language_code=language,
        session_id=session_id,
    )
    
    # Step 2: Convert response to speech
    audio_data, audio_mime = await tts_service.synthesize(response_text, language)
    
    # Build response
    result = {
        "text": response_text,
        "language": language,
        "session_id": sid,
        "has_audio": audio_data is not None,
    }
    
    if audio_data:
        result["audio"] = base64.b64encode(audio_data).decode("utf-8")
        result["audio_mime"] = audio_mime
    
    return JSONResponse(content=result)


@router.post("/process-text")
async def process_text(
    text: str = Form(..., description="User's text message"),
    language: str = Form(..., description="Language code: tw, fat, ee, gaa, ha"),
    session_id: str = Form(None, description="Session ID for conversation continuity"),
):
    """
    Text processing endpoint — used when browser Web Speech API handles STT.
    
    Flow: Text → Gemini (Bible response) → TTS → Audio response
    """
    if language not in LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {language}. Supported: {list(LANGUAGES.keys())}"
        )
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    
    logger.info(f"Processing text: lang={language}, text_length={len(text)}")
    
    # Step 1: Gemini processes text → Bible response
    response_text, sid = await bible_ai.process_text(
        text=text,
        language_code=language,
        session_id=session_id,
    )
    
    # Step 2: Convert response to speech
    audio_data, audio_mime = await tts_service.synthesize(response_text, language)
    
    result = {
        "text": response_text,
        "language": language,
        "session_id": sid,
        "has_audio": audio_data is not None,
    }
    
    if audio_data:
        result["audio"] = base64.b64encode(audio_data).decode("utf-8")
        result["audio_mime"] = audio_mime
    
    return JSONResponse(content=result)


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
    """Health check endpoint for deployment monitoring."""
    return {
        "status": "healthy",
        "service": "Audio Bible AI",
        "version": "1.0.0",
        "tts_khaya_calls": tts_service.khaya_calls_used,
    }
