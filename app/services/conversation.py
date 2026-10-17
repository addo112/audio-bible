"""
Step 4: Conversation Pipeline — Connecting the Asante Twi Voice Loop.

    audio ─► Step 1: Twi STT (Whisper Akan / Gemini ASR)
                │
                ▼
         Step 2: Core Knowledge Engine (Open.Bible + jdapaah/asante-twi-bible)
                ├─► READ (Whole Chapter): Stream authentic dramatized Asante Twi Audio Bible MP3
                │                         or cohesive native Twi TTS passages
                └─► ANSWER (Question):    Stream Gemini grounded in Twi Scripture
                                          ("Gyina kyerɛwsɛm yi so nkobaa bua asɛmmisa yi...")
                                                │
                                                ▼
                                   Step 3: Native Ghanaian Twi TTS
                                   (Gemini 3.8 Native Twi + Kasanoma/Nano-Twi sherpa-onnx)
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from typing import AsyncIterator

from app.services.bible_ai import bible_ai
from app.services.bible_books import BOOKS, twi_number
from app.services.bible_index import Passage, bible_index
from app.services.stt_service import stt_service
from app.services.tts_service import tts_service

logger = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"[.!?;]+[\"'”’)]*\s")
MIN_FIRST_CHUNK = 28
MIN_PARAGRAPH_CHUNK = 220


class Conversation:
    def __init__(self):
        self._last_passage: dict[str, Passage] = {}

    # ------------------------------------------------------------------ warmup
    @staticmethod
    def warmup() -> None:
        """Load Bible index, Kasanoma/Nano-Twi sherpa-onnx TTS, and Twi Whisper STT."""
        t0 = time.time()
        bible_index.load()
        tts_service.warmup()
        stt_service.load()
        logger.info(f"Voice loop warm in {time.time() - t0:.1f}s")

    # ------------------------------------------------------------------ main entry
    async def run(
        self,
        session_id: str | None,
        audio: bytes | None = None,
        mime: str = "audio/webm",
        text: str | None = None,
    ) -> AsyncIterator[dict]:
        t0 = time.time()
        timing: dict[str, float] = {}
        sid, _ = bible_ai.get_session(session_id)
        yield {"type": "session", "session_id": sid}

        # Step 1: Speech-to-Text
        if audio is not None:
            transcript, engine = await asyncio.to_thread(
                stt_service.transcribe,
                audio,
                mime,
                bible_ai.client,
                bible_ai.primary_model,
            )
            timing["stt"] = round(time.time() - t0, 2)
        else:
            transcript, engine = (text or "").strip(), "text"
        yield {"type": "transcript", "text": transcript, "engine": engine}

        if not transcript:
            async for ev in self._speak_items(
                [("Kafra, mante wo asɛm no yie. Yɛ sɛ wobɛka bio.", None)], timing, t0
            ):
                yield ev
            yield {"type": "done"}
            return

        if not bible_index.ready:
            await asyncio.to_thread(bible_index.load)

        # Step 2: Parse request & retrieve Asante Twi Scripture
        req = bible_index.parse_request(transcript)
        if req.mode == "continue":
            req.passage = self._next_chapter(sid)
            req.mode = "read" if req.passage else "answer"

        # 3a) Read Scripture verbatim
        if req.mode == "read" and req.passage:
            verses = bible_index.get_passage(req.passage)
            if verses:
                self._last_passage[sid] = req.passage
                yield {"type": "mode", "mode": "read", "title": req.passage.label}

                # Check if whole chapter(s) requested and official dramatized Asante Twi Audio Bible MP3 is available
                used_official_mp3 = False
                if req.passage.verse_start is None:
                    chapter_mp3s: list[tuple[int, bytes, str]] = []
                    for ch in range(req.passage.chapter_start, req.passage.chapter_end + 1):
                        url = bible_index.get_chapter_audio_url(req.passage.book, ch)
                        if url:
                            mp3_bytes, mp3_mime = await tts_service.fetch_chapter_audio(url)
                            if mp3_bytes and mp3_mime:
                                chapter_mp3s.append((ch, mp3_bytes, mp3_mime))

                    if len(chapter_mp3s) == (req.passage.chapter_end - req.passage.chapter_start + 1):
                        used_official_mp3 = True
                        # Stream all verses as readable text first
                        display_lines = [f"📖 {req.passage.label}"]
                        cur_ch = req.passage.chapter_start
                        for v in verses:
                            if v["chapter"] != cur_ch:
                                cur_ch = v["chapter"]
                                display_lines.append(f"— Ti {cur_ch} —")
                            display_lines.append(f"{v['verse']}. {v['text']}")
                        yield {"type": "text", "seq": 1, "text": "\n".join(display_lines)}

                        for idx, (_ch, mp3_bytes, mp3_mime) in enumerate(chapter_mp3s, 1):
                            if "first_audio" not in timing:
                                timing["first_audio"] = round(time.time() - t0, 2)
                            yield {
                                "type": "audio",
                                "seq": idx,
                                "audio": base64.b64encode(mp3_bytes).decode(),
                                "mime": mp3_mime,
                            }

                if not used_official_mp3:
                    items = self._reading_items(req.passage, verses)
                    if not req.wants_explanation:
                        items.append(self._closing_offer(req.passage))
                    async for ev in self._speak_items(items, timing, t0):
                        yield ev

                if req.wants_explanation:
                    async for ev in self._answer(
                        sid,
                        transcript,
                        verses[:40],
                        timing,
                        t0,
                        after=req.passage.label,
                    ):
                        yield ev
                else:
                    bible_ai.remember(
                        sid, transcript, f"(Mekenkanee {req.passage.label} maa no.)"
                    )
                timing["total"] = round(time.time() - t0, 2)
                yield {"type": "timing", **timing}
                yield {"type": "done"}
                return

        # 3b) Conversational answer grounded in retrieved Open.Bible + jdapaah/asante-twi-bible verses
        context: list[dict] = []
        if req.passage:
            context.extend(
                bible_index.get_passage(
                    Passage(
                        req.passage.book,
                        req.passage.chapter_start,
                        req.passage.chapter_start,
                        req.passage.verse_start,
                        req.passage.verse_end,
                    )
                )[:30]
            )
        seen = {(v["book"], v["chapter"], v["verse"]) for v in context}
        for v in bible_index.search(transcript, k=6):
            if (v["book"], v["chapter"], v["verse"]) not in seen:
                context.append(v)
        timing["retrieval"] = round(time.time() - t0, 2)
        yield {"type": "mode", "mode": "answer", "title": ""}
        async for ev in self._answer(sid, transcript, context, timing, t0):
            yield ev
        timing["total"] = round(time.time() - t0, 2)
        yield {"type": "timing", **timing}
        yield {"type": "done"}

    # ------------------------------------------------------------------ reading
    @staticmethod
    def _reading_items(p: Passage, verses: list[dict]) -> list[tuple[str, str | None]]:
        """
        Group verses into natural cohesive spoken passages (~250-350 chars each)
        so TTS speaks with continuous Ghanaian cadence instead of choppy 1-verse fragments.
        """
        items: list[tuple[str, str | None]] = []
        disp_buf: list[str] = [f"📖 {p.label}"]
        spoken_buf: list[str] = [p.spoken_title + "."]
        current_ch = p.chapter_start

        for v in verses:
            if v["chapter"] != current_ch:
                if disp_buf:
                    items.append(("\n".join(disp_buf), " ".join(spoken_buf)))
                    disp_buf, spoken_buf = [], []
                current_ch = v["chapter"]
                disp_buf.append(f"— Ti {current_ch} —")
                spoken_buf.append(f"Ti {twi_number(current_ch)}.")

            disp_buf.append(f"{v['verse']}. {v['text']}")
            spoken_buf.append(v["text"])

            if sum(len(s) for s in spoken_buf) >= 280:
                items.append(("\n".join(disp_buf), " ".join(spoken_buf)))
                disp_buf, spoken_buf = [], []

        if disp_buf:
            items.append(("\n".join(disp_buf), " ".join(spoken_buf)))
        return items

    def _closing_offer(self, p: Passage) -> tuple[str, str | None]:
        if p.chapter_end < BOOKS[p.book]["chapters"] and not p.verse_start:
            line = "Awurade nhyira wo. Sɛ wopɛ sɛ mekɔ so a, ka sɛ: toa so."
        else:
            line = "Awurade nhyira wo wɔ N'asɛm a woatie yi ho."
        return line, line

    def _next_chapter(self, sid: str) -> Passage | None:
        last = self._last_passage.get(sid)
        if not last:
            return None
        nxt = last.chapter_end + 1
        if nxt > BOOKS[last.book]["chapters"]:
            return None
        return Passage(last.book, nxt, nxt)

    # ------------------------------------------------------------------ answering
    async def _answer(
        self,
        sid: str,
        question: str,
        verses: list[dict],
        timing: dict,
        t0: float,
        after: str | None = None,
    ) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        full: list[str] = []

        async def produce():
            buf = ""
            first_emitted = False
            try:
                async for delta in bible_ai.stream_answer(
                    sid, question, verses, after_reading=after
                ):
                    if "first_token" not in timing:
                        timing["first_token"] = round(time.time() - t0, 2)
                    full.append(delta)
                    buf += delta
                    while True:
                        min_len = MIN_FIRST_CHUNK if not first_emitted else MIN_PARAGRAPH_CHUNK
                        m = None
                        for mm in _SENTENCE_END.finditer(buf):
                            if mm.end() >= min_len:
                                m = mm
                                if first_emitted:
                                    # Keep going to the last sentence boundary in buf for cohesive paragraph prosody
                                    continue
                                break
                        if not m:
                            break
                        await queue.put((buf[: m.end()].strip(), None))
                        first_emitted = True
                        buf = buf[m.end() :]
                if buf.strip():
                    await queue.put((buf.strip(), None))
            finally:
                await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            async for ev in self._speak_queue(queue, timing, t0):
                yield ev
        finally:
            task.cancel()
        answer = "".join(full).strip()
        if answer:
            bible_ai.remember(sid, question, answer)

    # ------------------------------------------------------------------ speaking
    async def _speak_items(self, items, timing, t0) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        for it in items:
            queue.put_nowait(it)
        queue.put_nowait(None)
        async for ev in self._speak_queue(queue, timing, t0):
            yield ev

    async def _speak_queue(
        self, queue: asyncio.Queue, timing: dict, t0: float
    ) -> AsyncIterator[dict]:
        seq = 0
        while True:
            item = await queue.get()
            if item is None:
                break
            display, spoken = item
            seq += 1
            yield {"type": "text", "seq": seq, "text": display}
            audio, mime = await tts_service.synthesize_sentence(spoken or display)
            if audio:
                if "first_audio" not in timing:
                    timing["first_audio"] = round(time.time() - t0, 2)
                yield {
                    "type": "audio",
                    "seq": seq,
                    "audio": base64.b64encode(audio).decode(),
                    "mime": mime,
                }
            else:
                yield {
                    "type": "audio",
                    "seq": seq,
                    "has_audio": False,
                    "text": spoken or display,
                }


conversation = Conversation()
