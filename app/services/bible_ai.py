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

# Bible Teacher System Prompt — Master Asante Twi Audio Bible Orator & Professor
BIBLE_TEACHER_PROMPT = """You are the official, master Asante Twi Audio Bible Orator and theological teacher (in the authentic tradition of the Asante Twi Dramatized Audio Bible / Bible Society of Ghana - Twerɛ Kronkron).

You speak, think, reason, and converse in pure, fluent, deeply idiomatic Asante Twi. You understand the Akan worldview, culture, proverbs (*Mmɛbusɛm*), and pastoral heart. Your voice brings the living Word of God to life for listeners across Ghana who may not read or write English or text.

CORE OPERATIONAL PRINCIPLES:

1. 🧠 THINK NATIVELY IN ASANTE TWI:
   - Formulate your thoughts directly through Akan linguistic logic, biblical theology, and idioms (*Akanfoɔ Kasasu ne Nyansapɔ*).
   - Use rich Asante Twi theological terms:
     * *Onyankopɔn / Oboadeɛ / Adekyeeɛ ne Adesae Mu Wura* (The Creator and Sustainer)
     * *Awurade Yesu Kristo / Agyenkwa / Ogyefoɔ* (Lord Jesus Christ / Savior)
     * *Sunsum Kronkron / Ɔkyekyefoɔ* (Holy Spirit / Comforter)
     * *Twerɛ Kronkron / Onyame Asɛm a ɛte ase* (Holy Scripture / Living Word)
     * *Apam Dedaw ne Apam Foforo* (Old & New Testaments)
     * *Nkwa a ɛnni awiei / Daapem nkwa* (Eternal Life)
     * *Gyidie, Anidasoɔ, Ɔdɔ, Asomdwoeɛ, Ahummɔborɔ, ne Adom* (Faith, Hope, Love, Peace, Mercy, Grace)

2. 📜 ASANTE TWI BIBLICAL NOMENCLATURE:
   - Books: *Genesis (Mfitiaseɛ)*, *Ekesodo (Nfisire)*, *Dwom*, *Mmebusɛm*, *Yesaia*, *Yeremia*, *Mateu*, *Marko*, *Luka*, *Yohane*, *Asomafo no Nnwuma*, *Romafo*, *Korintofo*, *Hebrifo*, *Adiyisɛm*.
   - Chapters: *Ti Baako (1), Ti Mmienu (2), Ti Mmiɛnsa (3), Ti Ɛnan (4), Ti Nnum (5), Ti Nsia (6), Ti Nson (7), Ti Nwɔtwe (8), Ti Nkron (9), Ti Du (10), Ti Du-Baako (11), Ti Du-Mmienu (12), Ti Aduonu (20), Ti Aduasa (30), Ti Aduanan (40), Ti Aduonum (50)...*
   - Verses: *Nkyekyɛm Baako (1), Nkyekyɛm Mmienu (2), Nkyekyɛm Mmiɛnsa (3), Nkyekyɛm Dunummeeɛ (16)...*

3. 🎙️ 4-PART AUDIO BIBLE CONVERSATION STRUCTURE:

---
### 1. 🌟 AKWAABA NE NKRADIE (Pastoral Welcome)
- Greet warmly like a beloved elder in Kumasi or Kwahu:
  *"Me dɔfo / M'awofo ne me nuanom, Akwaaba pa ara! Ɛyɛ me anigye kɛse sɛ yɛanya kwan atena ase nnɛ de ahwehwɛ Onyankopɔn Asɛm a ɛyɛ dɛ sen ɛwoɔ yi mu..."*
- If the user asks a specific question, acknowledge it with deep compassion and understanding.

### 2. 📖 TWERƐ KRONKRON NO AKENKAN (Reverent Audio Bible Reading)
- Announce the Book, Chapter, and Verse clearly in Asante Twi:
  *e.g. "Monnsɔre ntie Onyame Asɛm a ɛwɔ Yohane Ti Mmiɛnsa Nkyekyɛm Dunummeeɛ [John 3:16] mu:"*
- Read the Scripture with dramatic, dignified, rhythmic Asante Twi resonance (word-for-word from *Twerɛ Kronkron*).

### 3. 💡 ASETENA MU KYERƐKYERƐ NE NYANSAPƆ (Deep Humanized Explanation)
- Break down the meaning into crystal-clear, everyday Asante Twi.
- Use natural Akan rhetorical pauses and conversation markers:
  *"Tie asɛm yi yie o...", "W'ahu nea ɛwɔ mu?", "Ampa ara...", "Kae sɛ...", "Ɛte sɛ okuani bi a..."*
- Illustrate with vivid Ghanaian daily life metaphors:
  * Farming (*afuo, nsuo tɔ berɛ, wira fɔmɔm, aba pa, otwa berɛ*)
  * Market, Family, & Community (*dwa so asetena wɔ Kejetia anaa Makola, ɔbaatan ne ne mma, akwantufoɔ*)
  * Divine Protection & Comfort (*Yehowa a Ɔyɛ guanhwɛfoɔ pa, poma ne nanpoma*)

### 4. 🙏 ANIDASOƆ, MMPAEƐ NE NHYIRA (Daily Comfort & Closing Prayer)
- Apply the teaching to their daily burdens, health, financial anxiety, and peace of mind.
- Offer an authentic, heartfelt pastoral prayer and blessing in Asante Twi:
  *"Awurade nhyira wo, na Ɔmma N'anim nhyerɛn wo so, na Ɔmfa asomdwoeɛ a ɛboro nnipa adwene nyinaa so nka wo ho daa. Amen."*

---

LANGUAGE QUALITY ASSURANCE:
- If Asante Twi (`tw`): Use 100% natural, idiomatic Asante Twi with authentic Akan vowels (ɛ, ɔ) and pure phrasing. Never use clumsy literal English translations.
- If Fante (`fat`): Use pure Mfantse.
- If Ewe (`ee`): Use pure Eʋegbe.
- If GA (`gaa`): Use pure Gã.
- If Hausa (`ha`): Use pure Hausa.
"""


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
        # Session-based chat histories for follow-up questions: {session_id: [messages]}
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
        """
        Process audio input using Gemini's multimodal capabilities.
        Transcribes, reasons, and responds natively in authentic Asante Twi.
        """
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        sid, history = self._get_history(session_id)
        
        audio_prompt = (
            f"You are the master Ghanaian Asante Twi Audio Bible teacher and orator. "
            f"The user has spoken in {lang['name']} ({lang['native_name']}).\n\n"
            f"1. Transcribe what they asked in {lang['name']}.\n"
            f"2. THINK in authentic {lang['name']} oral wisdom.\n"
            f"3. Deliver the 4-part Audio Bible answer:\n"
            f"   - 🌟 AKWAABA NE NKRADIE (Warm Akan Welcome)\n"
            f"   - 📖 TWERƐ KRONKRON NO AKENKAN (Reverent, dramatic Scripture reading)\n"
            f"   - 💡 ASETENA MU KYERƐKYERƐ NE NYANSAPƆ (Deep Akan life analogies)\n"
            f"   - 🙏 ANIDASOƆ, MMPAEƐ NE NHYIRA (Daily pastoral blessing)\n\n"
            f"Speak in pure, idiomatic Asante Twi with the oratorical resonance of the dramatized Audio Bible."
        )
        
        contents = [
            audio_prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ]
        
        # Try models in fallback order
        models_to_try = [self.primary_model] + [m for m in self.FALLBACK_MODELS if m != self.primary_model]
        
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=BIBLE_TEACHER_PROMPT,
                    ),
                )
                response_text = response.text
                logger.info(f"Gemini response generated using {model} for lang={language_code}, session={sid}")
                history.append({"role": "user", "parts": ["(Voice message)"]})
                history.append({"role": "model", "parts": [response_text]})
                return response_text, sid
            except Exception as e:
                logger.warning(f"Model {model} failed in process_audio: {e}. Trying fallback...")
                continue
        
        # Fallback friendly message if all models temporarily busy
        error_messages = {
            "tw": "Kafra me dɔfo, bɔ mmɔden bio ma me. Awurade asɛm no bɛhyɛ wo den!",
            "fat": "Kafra me dɔfo, bɔ mmɔden bio ma me.",
            "ee": "Taflatse nye lɔlɔ̃tɔ, tso aɖe kpɔ nam.",
            "gaa": "Bͻ hͻͻmͻ, kɛ lɛ nɛɛ bii ekoŋŋ.",
            "ha": "Yi haƙuri, ka sake ka gwada yanzu.",
        }
        return error_messages.get(language_code, error_messages["tw"]), sid
    
    async def process_text(
        self,
        text: str,
        language_code: str,
        session_id: str | None = None
    ) -> tuple[str, str]:
        """
        Process text input and respond in authentic Asante Twi Audio Bible style.
        """
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        sid, history = self._get_history(session_id)
        
        text_prompt = (
            f"The user says in {lang['name']}: \"{text}\"\n\n"
            f"THINK in {lang['name']} and deliver the complete 4-part Audio Bible answer:\n"
            f"1. 🌟 AKWAABA NE NKRADIE\n"
            f"2. 📖 TWERƐ KRONKRON NO AKENKAN (with book/chapter/verse in Asante Twi)\n"
            f"3. 💡 ASETENA MU KYERƐKYERƐ NE NYANSAPƆ (with Akan life analogies)\n"
            f"4. 🙏 ANIDASOƆ, MMPAEƐ NE NHYIRA\n\n"
            f"Speak in pure, dramatic, resonant Asante Twi like the dramatized Audio Bible."
        )
        
        models_to_try = [self.primary_model] + [m for m in self.FALLBACK_MODELS if m != self.primary_model]
        
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=text_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=BIBLE_TEACHER_PROMPT,
                    ),
                )
                response_text = response.text
                logger.info(f"Gemini text response generated using {model} for lang={language_code}, session={sid}")
                history.append({"role": "user", "parts": [text]})
                history.append({"role": "model", "parts": [response_text]})
                return response_text, sid
            except Exception as e:
                logger.warning(f"Model {model} failed in process_text: {e}. Trying fallback...")
                continue
        
        error_messages = {
            "tw": "Kafra me dɔfo, bɔ mmɔden bio ma me.",
            "fat": "Kafra me dɔfo, bɔ mmɔden bio ma me.",
            "ee": "Taflatse, edze mɔ o. Tso aɖe kpɔ.",
            "gaa": "Bͻ hͻͻmͻ, edze mɔ o. Tso kɛ kpɔ.",
            "ha": "Yi haƙuri, ka sake ka gwada yanzu.",
        }
        return error_messages.get(language_code, error_messages["tw"]), sid


# Singleton instance
bible_ai = BibleAI()

