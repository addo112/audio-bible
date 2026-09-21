"""
Bible AI Service — Uses Google Gemini to act as a knowledgeable Bible teacher.

Gemini handles EVERYTHING:
- Understanding audio in any Ghanaian language (multimodal input)
- Processing Bible questions with deep theological knowledge  
- Responding in the user's chosen language
"""
from google import genai
from google.genai import types
from app.config import get_settings, LANGUAGES
import logging
import uuid

logger = logging.getLogger(__name__)

# Bible Teacher System Prompt — Concise for fast audio delivery
BIBLE_TEACHER_PROMPT = """You are the master Asante Twi Audio Bible Orator (Twerɛ Kronkron Ɔkafoɔ Panin) — in the authentic tradition of the Faith Comes By Hearing / Bible Society of Ghana dramatized Audio Bible.

You speak, think, and reason in pure, fluent, deeply idiomatic Asante Twi. You understand the Akan worldview, proverbs (Mmɛbusɛm), and pastoral heart.

CRITICAL: Keep your response focused and clear — about 200-400 words. This response will be read aloud as audio, so clarity and natural flow are essential. Always complete all 4 sections fully.

USE THESE NATIVE TWI TERMS:
- Onyankopɔn / Oboadeɛ (Creator)
- Awurade Yesu Kristo / Agyenkwa (Lord Jesus / Savior)
- Sunsum Kronkron / Ɔkyekyefoɔ (Holy Spirit / Comforter)
- Twerɛ Kronkron (Holy Scripture)
- Gyidie, Anidasoɔ, Ɔdɔ, Asomdwoeɛ (Faith, Hope, Love, Peace)

TWI BIBLE BOOK NAMES: Genesis (Mfitiaseɛ), Mateu, Marko, Luka, Yohane, Dwom, Mmebusɛm, Asomafo Nnwuma, Adiyisɛm.
CHAPTERS: Ti Baako (1), Ti Mmienu (2), Ti Mmiɛnsa (3)...
VERSES: Nkyekyɛm Baako (1), Nkyekyɛm Mmienu (2)...

RESPONSE STRUCTURE (keep each section SHORT):

1. 🌟 AKWAABA — Brief warm greeting (1-2 sentences max)
2. 📖 TWERƐ KRONKRON — Read the Scripture in Twi (announce book/chapter/verse clearly)
3. 💡 KYERƐKYERƐ — Brief explanation using everyday Ghanaian life examples (farming, market, family)
4. 🙏 NHYIRA — Short closing prayer/blessing (2-3 sentences)

LANGUAGE RULES:
- tw: 100% Asante Twi. Use authentic Akan vowels (ɛ, ɔ). Never literal English translations.
- fat: Pure Mfantse
- ee: Pure Eʋegbe
- gaa: Pure Gã
- ha: Pure Hausa

Remember: You are speaking to listeners who hear, not read. Be warm, clear, and conversational like a beloved pastor."""


class BibleAI:
    """Gemini-powered Bible teaching assistant with multi-model fallback."""
    
    # Available models in order of priority
    FALLBACK_MODELS = [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-3.7-flash",
    ]
    
    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.primary_model = settings.GEMINI_MODEL or "gemini-3.5-flash"
        # Session-based chat histories for follow-up questions
        self._history: dict[str, list[dict]] = {}
    
    def _get_history(self, session_id: str | None) -> tuple[str, list[dict]]:
        """Get or initialize conversation history for a session."""
        sid = session_id or str(uuid.uuid4())
        if sid not in self._history:
            self._history[sid] = []
        if len(self._history) > 1000:
            oldest = list(self._history.keys())[0]
            del self._history[oldest]
        return sid, self._history[sid]
    
    async def process_audio(
        self, 
        audio_bytes: bytes, 
        mime_type: str, 
        language_code: str,
        session_id: str | None = None
    ) -> tuple[str, str]:
        """Process audio input using Gemini's multimodal capabilities."""
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        sid, history = self._get_history(session_id)
        
        audio_prompt = (
            f"The user spoke in {lang['name']}. "
            f"Transcribe what they asked, then deliver a complete Audio Bible answer "
            f"in pure {lang['name']} following the 4-part structure "
            f"(Akwaaba, Scripture Reading, Explanation, Blessing)."
        )
        
        contents = [
            audio_prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ]
        
        models_to_try = [self.primary_model] + [m for m in self.FALLBACK_MODELS if m != self.primary_model]
        
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=BIBLE_TEACHER_PROMPT,
                        max_output_tokens=2048,
                        temperature=0.7,
                    ),
                )
                response_text = response.text
                logger.info(f"Audio response via {model}, lang={language_code}, session={sid}")
                history.append({"role": "user", "parts": ["(Voice message)"]})
                history.append({"role": "model", "parts": [response_text]})
                return response_text, sid
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}. Trying fallback...")
                continue
        
        error_messages = {
            "tw": "Kafra me dɔfo, bɔ mmɔden bio. Awurade nhyira wo!",
            "fat": "Kafra, bɔ mmɔden bio ma me.",
            "ee": "Taflatse, tso aɖe kpɔ.",
            "gaa": "Bͻ hͻͻmͻ, tso kɛ kpɔ.",
            "ha": "Yi haƙuri, ka gwada yanzu.",
        }
        return error_messages.get(language_code, error_messages["tw"]), sid
    
    async def process_text(
        self,
        text: str,
        language_code: str,
        session_id: str | None = None
    ) -> tuple[str, str]:
        """Process text input and respond in authentic Audio Bible style."""
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        sid, history = self._get_history(session_id)
        
        text_prompt = (
            f"The user says in {lang['name']}: \"{text}\"\n\n"
            f"Deliver a complete Audio Bible answer in pure {lang['name']} "
            f"following the 4-part structure (Akwaaba, Scripture, Explanation, Blessing)."
        )
        
        models_to_try = [self.primary_model] + [m for m in self.FALLBACK_MODELS if m != self.primary_model]
        
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=text_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=BIBLE_TEACHER_PROMPT,
                        max_output_tokens=2048,
                        temperature=0.7,
                    ),
                )
                response_text = response.text
                logger.info(f"Text response via {model}, lang={language_code}, session={sid}")
                history.append({"role": "user", "parts": [text]})
                history.append({"role": "model", "parts": [response_text]})
                return response_text, sid
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}. Trying fallback...")
                continue
        
        error_messages = {
            "tw": "Kafra me dɔfo, bɔ mmɔden bio.",
            "fat": "Kafra, bɔ mmɔden bio.",
            "ee": "Taflatse, tso aɖe kpɔ.",
            "gaa": "Bͻ hͻͻmͻ, tso kɛ kpɔ.",
            "ha": "Yi haƙuri, ka gwada yanzu.",
        }
        return error_messages.get(language_code, error_messages["tw"]), sid


# Singleton instance
bible_ai = BibleAI()
