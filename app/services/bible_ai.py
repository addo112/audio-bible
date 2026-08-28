"""
Bible AI Service — Uses Google Gemini to act as a knowledgeable Bible teacher.

Gemini handles EVERYTHING:
- Understanding audio in any Ghanaian language (multimodal input)
- Processing Bible questions with deep theological knowledge  
- Responding in the user's chosen language
"""
import google.generativeai as genai
from app.config import get_settings, LANGUAGES
import logging
import uuid

logger = logging.getLogger(__name__)

# Bible Teacher System Prompt — the authentic Ghanaian Bible Teacher & Pastor
BIBLE_TEACHER_PROMPT = """You are a beloved, seasoned Ghanaian pastor, elder, and Bible teacher who speaks pure, natural, deeply humanized Asante Twi (and the other Ghanaian local languages when selected).

You are speaking to listeners in Ghana (Kumasi, Accra, Cape Coast, Sunyani, Takoradi, Tamale, and all towns and villages) who may not know how to read or write. You are their personal voice Bible teacher sitting right with them under the shade of a tree in the compound.

YOUR TWO CORE MISSIONS:
1. CLEAR SCRIPTURE READING: Read the Bible passage loudly, clearly, and reverently in pure Asante Twi (*Twerɛ Kronkron* style).
2. HUMANIZED, CLEAR & UNDERSTANDABLE EXPLANATION: Break down the scripture like a loving Ghanaian elder, using everyday Ghanaian life stories (farming, market, family, sickness, faith) so that even a child or an uneducated listener understands deeply and feels comforted.

EVERY RESPONSE MUST FOLLOW THIS 4-PART FORMAT:

---
### 1. 🌟 AKWAABA NE NKRADIE (Warm Greeting)
- Welcome the listener like a loving father/brother/sister with authentic Akan warmth:
  *"Me nua dɔfo / M'awofo, Akwaaba! Ɛyɛ me anigye kɛse sɛ wo ne me abɛtena ase nnɛ de hwehwɛ Onyankopɔn Asɛm a ɛyɛ dɛ sen ɛwoɔ yi mu..."*
- Address their question or situation with gentle compassion.

### 2. 📖 TWERƐ KRONKRON NO AKENKAN (Clear Scripture Reading)
- State the Book, Chapter, and Verse clearly (e.g. *Dwom 23:1-6* or *Yohane Ti 3 Nkyekyɛm 16*).
- Read the verses word-for-word in pure, dignified Asante Twi so the listener hears God's pure Word.

### 3. 💡 ASETENA MU KYERƐKYERƐ (Deep Humanized Explanation)
- Explain verse-by-verse or theme-by-theme in simple, conversational, everyday Asante Twi.
- Use authentic Ghanaian life analogies:
  * Farming (*okuani ne n'afuo, nsuo tɔ berɛ, wira fɔmɔm, otwa berɛ*)
  * Market & Work (*dwa so asetena, adwuma mu ahokyere, aduanodi*)
  * Family & Protection (*ɔbaatan ne ne mma, guanhwɛfoɔ ne ne mmanma*)
- Use natural Akan rhetorical questions & expressions:
  *"W'ahu deɛ ɛkyerɛ?", "Tie asɛm yi yie o...", "Ɛte sɛ...", "Kae sɛ Onyankopɔn mpa wo abaw so da..."*

### 4. 🙏 ANIDASOƆ NE MMPAEƐ (Comfort & Blessing)
- Provide practical encouragement for their daily life, health, family, and peace of mind.
- Close with a short, powerful, loving prayer and blessing in Asante Twi:
  *"Awurade nhyira wo, na Ɔmma N'anim nhyerɛn wo so. Amen."*

---

LANGUAGE & TONE RULES:
- When the language is Asante Twi (`tw`), use PURE, IDIOMATIC Asante Twi—never literal word-for-word translated English!
- If the language is Fante (`fat`), use pure Mfantse.
- If Ewe (`ee`), use pure Eʋegbe.
- If GA (`gaa`), use pure Gã.
- If Hausa (`ha`), use pure Hausa.
- Avoid difficult academic jargon; use heart-language that brings peace, faith, and clarity.
"""


class BibleAI:
    """Gemini-powered Bible teaching assistant."""
    
    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=BIBLE_TEACHER_PROMPT,
        )
        # Session-based chat histories for follow-up questions
        self._sessions: dict[str, genai.ChatSession] = {}
    
    def _get_or_create_session(self, session_id: str | None) -> tuple[str, genai.ChatSession]:
        """Get existing chat session or create a new one."""
        if session_id and session_id in self._sessions:
            return session_id, self._sessions[session_id]
        
        new_id = session_id or str(uuid.uuid4())
        chat = self.model.start_chat(history=[])
        self._sessions[new_id] = chat
        
        # Limit stored sessions to prevent memory issues
        if len(self._sessions) > 1000:
            oldest = list(self._sessions.keys())[0]
            del self._sessions[oldest]
        
        return new_id, chat
    
    async def process_audio(
        self, 
        audio_bytes: bytes, 
        mime_type: str, 
        language_code: str,
        session_id: str | None = None
    ) -> tuple[str, str]:
        """
        Process audio input using Gemini's multimodal capabilities.
        
        Gemini listens to the audio, understands the language, and responds
        as a Bible teacher in the same language.
        
        Returns: (response_text, session_id)
        """
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        sid, chat = self._get_or_create_session(session_id)
        
        # Build the prompt that guides Gemini to understand and respond correctly
        audio_prompt = (
            f"The user is speaking to you in {lang['name']} ({lang['native_name']}). "
            f"Listen carefully to their audio message. They are asking a question about the Bible "
            f"or requesting you to read/explain a Bible passage.\n\n"
            f"IMPORTANT: You MUST respond ENTIRELY in {lang['name']} language. "
            f"Only Bible verse references (like 'Genesis 1:1' or 'John 3:16') should remain in English/numbers.\n\n"
            f"If you cannot clearly understand the audio, respond politely in {lang['name']} "
            f"asking them to please speak again more clearly."
        )
        
        try:
            # Send audio + prompt to Gemini (multimodal)
            response = chat.send_message([
                audio_prompt,
                {
                    "mime_type": mime_type,
                    "data": audio_bytes,
                }
            ])
            
            response_text = response.text
            logger.info(f"Gemini response generated for language={language_code}, session={sid}")
            return response_text, sid
            
        except Exception as e:
            logger.error(f"Gemini audio processing error: {e}")
            # Return a polite error message in the user's language
            error_messages = {
                "tw": "Kafra, mete sɛ wo ka bio. Me ntee aseɛ yie. Yɛ sɛ woka no bio.",
                "fat": "Kafra, me ntee aseɛ yie. Ka no bio ma me.",
                "ee": "Taflatse, gblɔe again. Nyemesee gɔme o.",
                "gaa": "Bͻ hͻͻmͻ, kɛ lɛ nɛɛ bii. Minnyɛ ji o.",
                "ha": "Yi haƙuri, ban ji ba. Ka sake ka faɗa mini.",
            }
            return error_messages.get(language_code, error_messages["tw"]), sid
    
    async def process_text(
        self,
        text: str,
        language_code: str,
        session_id: str | None = None
    ) -> tuple[str, str]:
        """
        Process text input and respond as a Bible teacher.
        
        Used when browser's Web Speech API handles speech-to-text on the client side.
        
        Returns: (response_text, session_id)
        """
        lang = LANGUAGES.get(language_code, LANGUAGES["tw"])
        sid, chat = self._get_or_create_session(session_id)
        
        text_prompt = (
            f"The user says this in {lang['name']}: \"{text}\"\n\n"
            f"Respond as a Bible teacher ENTIRELY in {lang['name']} language. "
            f"Only Bible verse references should remain in English/numbers."
        )
        
        try:
            response = chat.send_message(text_prompt)
            response_text = response.text
            logger.info(f"Gemini text response for language={language_code}, session={sid}")
            return response_text, sid
            
        except Exception as e:
            logger.error(f"Gemini text processing error: {e}")
            error_messages = {
                "tw": "Kafra, ɛnyɛ yie. Bɔ mmɔden bio.",
                "fat": "Kafra, ɛnyɛ yie. Bɔ mmɔden bio.",
                "ee": "Taflatse, edze mɔ o. Tso aɖe kpɔ.",
                "gaa": "Bͻ hͻͻmͻ, edze mɔ o. Tso kɛ kpɔ.",
                "ha": "Yi haƙuri, ba yi ba. Ka sake ka gwada.",
            }
            return error_messages.get(language_code, error_messages["tw"]), sid


# Singleton instance
bible_ai = BibleAI()
