"""
Step 2 (LLM): Bible AI Service — Google Gemini (`google-genai` SDK) as a native
Kumasi Asante Twi Bible teacher grounded in retrieved Asante Twi Scripture.

- Uses explicit Asante Twi grounding prompts:
  "Gyina kyerɛwsɛm yi so nkobaa bua asɛmmisa yi..."
- Answers are phrased for natural Ghanaian oral cadence (spoken Twi numbers,
  natural breath pauses via commas, zero markdown/emojis/digits) so TTS speaks
  with an authentic native Ashanti accent.
"""
from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)

BIBLE_TEACHER_PROMPT = """Wo ne Twerɛ Kronkron Ɔkafoɔ ne Ɔkyerɛkyerɛfoɔ Panin a ofiri Kumasi, Asanteman mu — speaking with the deep, solemn, reverent, measured classical Asante Twi liturgical cadence of the Bible Society of Ghana / Open.Bible Asante Twi Audio Bible narrator.

SƐDEƐ WOKASA (HOW YOU SPEAK FOR AUDIO):
- Speak 100% pure, classical, idiomatic Asante Twi (using ɛ and ɔ accurately, e.g. Onyankopɔn, Awurade Yesu Kristo, Onyankopɔn Honhom Kronkron, Twerɛ Kronkron, Mfitiaseɛ no, gyidie, ɔdɔ, asomdwoeɛ, nhyira). Never translate word-for-word from English.
- Because your words are spoken aloud directly by the Asante Twi Audio Bible voice engine, write ONLY speakable Asante Twi words:
  * Write all Bible chapters and verses using the classical Asante Twi lector style: "eti" for chapter and "emu" (or "firi emu ... de kɔsi ...") for verse(s), e.g. "Mose nhoma a edi kan, Genesis, eti baako, firi emu baako de kɔsi mmienu" or "Yohane, eti mmiɛnsa, emu dunsia" or "Nnwom, eti aduonu mmiɛnsa, firi emu baako de kɔsi nsia". Never write digits like "3:16".
  * Use deliberate commas, semicolons, and periods to create the slow, measured, solemn Akan liturgical rhythm and breath pauses of the Audio Bible narrator.
  * NO markdown, NO asterisks, NO bullet points, NO headings, NO emojis, NO brackets.
- Start with a warm, dignified Asante greeting or scripture introduction in your first short sentence (5 to 10 words, e.g. "Me dɔfo, tie Onyankopɔn asɛm kronkron a ɛwɔ Twerɛ Kronkron mu yi.") so audio playback begins immediately.
- Follow with 2 to 4 clear, solemn, heartfelt sentences (about 50 to 90 words total) that recite the provided Asante Twi Scripture and explain its meaning for everyday Ghanaian life (abusua, adwuma, afuom, gua so, mpaebɔ).
- End with a short pastoral blessing or invitation, e.g. "Awurade nhyira wo. Wopɛ sɛ mekenkan eti no nyinaa firi emu baako ma wo?"

SƐDEƐ WOBUA (GROUNDING IN SCRIPTURE):
- Gyina kyerɛwsɛm a wɔama wo yi so nkobaa bua asɛmmisa no nokorɛm.
- Quote or weave the exact Asante Twi words from the retrieved verses naturally into your spoken explanation."""


def _format_verses(verses: list[dict]) -> str:
    return "\n".join(
        f"[{v['book']} {v['chapter']}:{v['verse']}] {v['text']}" for v in verses
    )


class BibleAI:
    """Gemini-powered Asante Twi Bible teacher with streaming and multi-model fallback."""

    FALLBACK_MODELS = [
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.6-flash",
    ]

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        configured = settings.GEMINI_MODEL or "gemini-3.5-flash"
        if configured == "gemini-2.5-flash":
            configured = "gemini-3.5-flash"
        self.primary_model = configured
        self.max_tokens = settings.ANSWER_MAX_TOKENS
        self._history: dict[str, list[types.Content]] = {}
        self._good_thinking: int | None = None

    # ------------------------------------------------------------------ sessions
    def get_session(self, session_id: str | None) -> tuple[str, list[types.Content]]:
        sid = session_id or str(uuid.uuid4())
        if sid not in self._history:
            self._history[sid] = []
            if len(self._history) > 1000:
                del self._history[next(iter(self._history))]
        return sid, self._history[sid]

    def remember(self, session_id: str, user_text: str, model_text: str) -> None:
        _, hist = self.get_session(session_id)
        hist.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        hist.append(types.Content(role="model", parts=[types.Part(text=model_text)]))
        del hist[:-10]

    @property
    def models(self) -> list[str]:
        return [self.primary_model] + [
            m for m in self.FALLBACK_MODELS if m != self.primary_model
        ]

    @staticmethod
    def _thinking_options() -> list[types.ThinkingConfig | None]:
        opts: list[types.ThinkingConfig | None] = []
        for kwargs in ({"thinking_budget": 0}, {"thinking_level": "minimal"}):
            try:
                opts.append(types.ThinkingConfig(**kwargs))
            except Exception:
                pass
        opts.append(None)
        return opts

    # ------------------------------------------------------------------ prompting & streaming
    def build_prompt(
        self,
        question: str,
        verses: list[dict],
        after_reading: str | None = None,
    ) -> str:
        parts = []
        if verses:
            parts.append(
                "Kyerɛwsɛm a ɛfiri Asante Twi Twerɛ Kronkron ne Nkwa Asɛm mu:\n"
                + _format_verses(verses)
            )
        if after_reading:
            parts.append(f"Wɔakenkan {after_reading} ama tiefoɔ no awie seesei ara.")
        parts.append(f'Tiefoɔ no asɛmmisa anaa asɛm: "{question}"')
        parts.append(
            "Gyina kyerɛwsɛm yi so nkobaa bua asɛmmisa yi wɔ Asante Twi kronkron mu, "
            "te sɛ ɔsɔfoɔ anaa ɔpanin a ɔrekasa kyerɛ ne dɔfo wɔ nkɔmmɔbɔ mu."
        )
        return "\n\n".join(parts)

    async def stream_answer(
        self,
        session_id: str,
        question: str,
        verses: list[dict],
        after_reading: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas of a short, grounded Asante Twi answer."""
        _, history = self.get_session(session_id)
        prompt = self.build_prompt(question, verses, after_reading)
        contents = list(history) + [
            types.Content(role="user", parts=[types.Part(text=prompt)])
        ]
        thinking_opts = self._thinking_options()
        order = list(range(len(thinking_opts)))
        if self._good_thinking is not None and self._good_thinking in order:
            order.remove(self._good_thinking)
            order.insert(0, self._good_thinking)

        last_err = None
        for model in self.models:
            for ti in order:
                cfg = types.GenerateContentConfig(
                    system_instruction=BIBLE_TEACHER_PROMPT,
                    max_output_tokens=self.max_tokens,
                    temperature=0.65,
                    thinking_config=thinking_opts[ti],
                )
                yielded = False
                try:
                    stream = await self.client.aio.models.generate_content_stream(
                        model=model, contents=contents, config=cfg
                    )
                    async for chunk in stream:
                        text = chunk.text or ""
                        if text:
                            yielded = True
                            yield text
                    if yielded:
                        self.primary_model = model
                        self._good_thinking = ti
                        return
                except Exception as e:
                    last_err = e
                    if yielded:
                        logger.warning(f"Stream interrupted on {model}: {e}")
                        return
                    msg = str(e).lower()
                    logger.warning(f"{model} (thinking option {ti}) failed: {e}")
                    if "thinking" in msg or "invalid" in msg or "400" in msg:
                        continue
                    break
        logger.error(f"All Gemini models failed: {last_err}")
        yield "Kafra me dɔfo, nsɛm bi ankɔ yie. Yɛ sɛ wobɛka bio."

    async def answer(
        self, session_id: str, question: str, verses: list[dict]
    ) -> str:
        text = "".join(
            [t async for t in self.stream_answer(session_id, question, verses)]
        )
        self.remember(session_id, question, text)
        return text


# Singleton instance
bible_ai = BibleAI()
