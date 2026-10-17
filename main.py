"""
Audio Bible AI — Main Application Entry Point

A voice-first AI Bible teaching & Scripture reading assistant in Asante Twi.
Preloads the 30,565-verse Asante Twi Bible index, native Ghanaian VITS voice,
and Twi Whisper STT on startup for fast conversational latency.
"""
import asyncio
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.services.conversation import conversation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up Bible index, local Twi TTS, and Twi Whisper STT in a background thread
    warmup_task = asyncio.create_task(asyncio.to_thread(conversation.warmup))
    yield
    if not warmup_task.done():
        warmup_task.cancel()


app = FastAPI(
    title="Asante Twi Audio Bible",
    description="Voice-first AI Bible teaching & Scripture reading assistant in Asante Twi",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path)


@app.get("/favicon.ico")
async def favicon():
    """Serve favicon."""
    favicon_path = os.path.join(static_dir, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return FileResponse(
        os.path.join(static_dir, "icons", "icon-192.png"), media_type="image/png"
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
