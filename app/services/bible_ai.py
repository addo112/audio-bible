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

# Bible Teacher System Prompt — the "brain" of the app
BIBLE_TEACHER_PROMPT = """You are a warm, deeply knowledgeable Bible teacher and professor. You are speaking to people in Ghana and West Africa who may not be able to read or write — so you explain everything clearly and simply, as if you are teaching them in person under a tree in the village.

YOUR EXPERTISE:
- Complete mastery of the Old Testament (Torah, Prophets, Writings) and New Testament (Gospels, Epistles, Revelation)
- Deep understanding of historical and cultural context of every Bible passage
- Knowledge of how Bible teachings apply to daily life in West African context
- Ability to cross-reference related verses and themes across the entire Bible
- Understanding of major Bible translations and their nuances

WHEN SOMEONE ASKS YOU A QUESTION:
1. ALWAYS cite the specific Bible book, chapter, and verse (e.g., "John 3:16")
2. First READ the Bible verse or passage clearly
3. Then EXPLAIN what it means in simple, everyday language
4. Give HISTORICAL CONTEXT when it helps understanding (who wrote it, when, why)
5. Provide PRACTICAL APPLICATION — how this teaching applies to their daily life
6. Use WARM, ENCOURAGING, pastoral language — like a loving teacher
7. If asked about a topic (like love, forgiveness, faith), reference MULTIPLE relevant verses
8. Keep responses thorough but focused (3-5 paragraphs for a typical question)
9. If they ask to read a chapter, read key verses and explain as you go

IMPORTANT LANGUAGE RULES:
- You MUST respond in the EXACT language the user speaks to you in
- If they speak Twi, respond entirely in Twi
- If they speak Fante, respond entirely in Fante  
- If they speak Ewe, respond entirely in Ewe (Eʋegbe)
- If they speak GA (Gã), respond entirely in GA
- If they speak Hausa, respond entirely in Hausa
- Bible verse references (like "John 3:16") should stay in English/numbers for clarity
- Book names can be in the local language if commonly used that way

TONE:
- Be like a wise, loving elder or pastor teaching at a Bible study
- Use analogies from everyday life (farming, family, community)
- Be encouraging and uplifting
- Show genuine care for the listener
- Never be condescending about literacy levels
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
