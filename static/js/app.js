/**
 * Audio Bible AI — Frontend Application v2.0
 * 
 * Voice-first interface for Bible teaching in Ghanaian languages.
 * Two-phase architecture: text appears instantly, audio loads in background.
 */

// ============================================================
// STATE
// ============================================================
const state = {
    currentLanguage: null,
    sessionId: null,
    isRecording: false,
    isProcessing: false,
    mediaRecorder: null,
    audioChunks: [],
    currentAudio: null,
    stream: null,
};

// ============================================================
// DOM ELEMENTS
// ============================================================
const dom = {
    screenLanguage: document.getElementById('screen-language'),
    screenVoice: document.getElementById('screen-voice'),
    languageGrid: document.getElementById('language-grid'),
    voiceTopbar: document.getElementById('voice-topbar'),
    btnBack: document.getElementById('btn-back'),
    langFlag: document.getElementById('lang-flag'),
    langName: document.getElementById('lang-name'),
    statusArea: document.getElementById('status-area'),
    statusIcon: document.getElementById('status-icon'),
    statusText: document.getElementById('status-text'),
    conversationArea: document.getElementById('conversation-area'),
    welcomeMessage: document.getElementById('welcome-message'),
    messages: document.getElementById('messages'),
    audioPlayer: document.getElementById('audio-player'),
    btnPlayResponse: document.getElementById('btn-play-response'),
    btnStopResponse: document.getElementById('btn-stop-response'),
    audioProgress: document.getElementById('audio-progress'),
    audioProgressBar: document.getElementById('audio-progress-bar'),
    btnMic: document.getElementById('btn-mic'),
    micIcon: document.getElementById('mic-icon'),
    micSpinner: document.getElementById('mic-spinner'),
    micRipple: document.getElementById('mic-ripple'),
    micLabel: document.getElementById('mic-label'),
    responseAudio: document.getElementById('response-audio'),
    offlineBanner: document.getElementById('offline-banner'),
};

// ============================================================
// LANGUAGE DATA
// ============================================================
const LANGUAGES = [
    { code: 'tw', name: 'Asante Twi', native_name: 'Asante Twi', color: '#D4A017', color_light: '#FFF3D0', icon: '🇬🇭', symbol: '🟡' },
    { code: 'fat', name: 'Fante', native_name: 'Mfantse', color: '#006B3F', color_light: '#D0F5E0', icon: '🇬🇭', symbol: '🟢' },
    { code: 'ee', name: 'Ewe', native_name: 'Eʋegbe', color: '#CE1126', color_light: '#FFD6DC', icon: '🇬🇭', symbol: '🔴' },
    { code: 'gaa', name: 'GA', native_name: 'Gã', color: '#003F87', color_light: '#D0E3FF', icon: '🇬🇭', symbol: '🔵' },
    { code: 'ha', name: 'Hausa', native_name: 'Hausa', color: '#FF8C00', color_light: '#FFF0D0', icon: '🇳🇬', symbol: '🟠' },
];

// Status messages in Twi
const TWI_STATUS = {
    listening: 'Meredie wo asɛm...',
    thinking: '✨ Onyame Asɛm resiesie...',
    audio_loading: '🔊 Audio reba...',
    ready: 'Asante Twi Audio Bible',
    error: 'Kafra, bɔ mmɔden bio',
};

// ============================================================
// AUDIO UTILITIES
// ============================================================
function playBeep(frequency = 800, duration = 150, type = 'sine') {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        oscillator.frequency.value = frequency;
        oscillator.type = type;
        gainNode.gain.value = 0.1;
        gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration / 1000);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + duration / 1000);
    } catch (e) {}
}

function playStartBeep() { playBeep(600, 100); setTimeout(() => playBeep(900, 150), 120); }
function playStopBeep() { playBeep(900, 100); setTimeout(() => playBeep(600, 150), 120); }
function playSuccessChime() { playBeep(523, 100); setTimeout(() => playBeep(659, 100), 100); setTimeout(() => playBeep(784, 200), 200); }
function playErrorSound() { playBeep(300, 200, 'square'); }

// ============================================================
// INITIALIZE
// ============================================================
function init() {
    renderLanguageGrid();
    setupEventListeners();
    checkOnlineStatus();
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(() => {});
    }
}

// ============================================================
// LANGUAGE SELECTION
// ============================================================
function renderLanguageGrid() {
    dom.languageGrid.innerHTML = '';
    LANGUAGES.forEach((lang) => {
        const btn = document.createElement('button');
        btn.className = 'lang-btn';
        btn.style.background = lang.color;
        btn.style.borderColor = lang.color;
        btn.innerHTML = `
            <div class="lang-btn-icon">${lang.icon}</div>
            <div class="lang-btn-info">
                <span class="lang-btn-name">${lang.name}</span>
                <span class="lang-btn-native">${lang.native_name}</span>
            </div>
            <div class="lang-btn-arrow">▶</div>
        `;
        btn.addEventListener('click', () => selectLanguage(lang));
        dom.languageGrid.appendChild(btn);
    });
}

function selectLanguage(lang) {
    state.currentLanguage = lang;
    state.sessionId = null;
    dom.voiceTopbar.style.background = lang.color;
    dom.langFlag.textContent = lang.icon;
    dom.langName.textContent = lang.name;
    dom.btnMic.style.background = lang.color;
    dom.btnMic.style.boxShadow = `0 4px 20px ${lang.color}66`;
    dom.welcomeMessage.innerHTML = `<div style="font-size: 50px; margin-bottom: 12px;">📖✝️</div>`;
    dom.messages.innerHTML = '';
    dom.audioPlayer.style.display = 'none';
    setStatus('🎤', '');
    showScreen('voice');
    playBeep(700, 100);
}

// ============================================================
// SCREEN NAVIGATION
// ============================================================
function showScreen(screenName) {
    dom.screenLanguage.classList.remove('active');
    dom.screenVoice.classList.remove('active');
    if (screenName === 'language') dom.screenLanguage.classList.add('active');
    else if (screenName === 'voice') dom.screenVoice.classList.add('active');
}

// ============================================================
// VOICE RECORDING
// ============================================================
async function startRecording() {
    if (state.isProcessing) return;
    try {
        state.stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
        });
        const mimeType = getSupportedMimeType();
        state.mediaRecorder = new MediaRecorder(state.stream, { mimeType });
        state.audioChunks = [];
        state.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) state.audioChunks.push(event.data);
        };
        state.mediaRecorder.onstop = () => {
            const audioBlob = new Blob(state.audioChunks, { type: mimeType });
            stopMicStream();
            processAudio(audioBlob, mimeType);
        };
        state.mediaRecorder.start();
        state.isRecording = true;
        dom.btnMic.classList.add('recording');
        dom.micRipple.classList.add('active');
        dom.micRipple.style.background = state.currentLanguage.color;
        setStatus('🔴', isTwi() ? TWI_STATUS.listening : 'Listening...');
        playStartBeep();
        setTimeout(() => { if (state.isRecording) stopRecording(); }, 60000);
    } catch (err) {
        console.error('Microphone error:', err);
        playErrorSound();
        setStatus('🎤❌', '');
        addMessage('error', '🎤 ❌ — Please allow microphone access');
    }
}

function stopRecording() {
    if (!state.isRecording || !state.mediaRecorder) return;
    state.isRecording = false;
    state.mediaRecorder.stop();
    dom.btnMic.classList.remove('recording');
    dom.micRipple.classList.remove('active');
    playStopBeep();
}

function stopMicStream() {
    if (state.stream) {
        state.stream.getTracks().forEach(track => track.stop());
        state.stream = null;
    }
}

function getSupportedMimeType() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/mp4', 'audio/wav'];
    for (const type of types) {
        if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return 'audio/webm';
}

function toggleRecording() {
    if (state.isRecording) stopRecording();
    else startRecording();
}

function isTwi() {
    return state.currentLanguage && state.currentLanguage.code === 'tw';
}

// ============================================================
// TWO-PHASE API COMMUNICATION
// ============================================================

/**
 * Phase 1: Send audio to backend, get text response FAST.
 * Phase 2: Request audio generation in background.
 */
async function processAudio(audioBlob, mimeType) {
    if (state.isProcessing) return;
    state.isProcessing = true;

    // Show processing UI
    dom.btnMic.classList.add('processing');
    dom.micIcon.style.display = 'none';
    dom.micSpinner.style.display = 'flex';
    setStatus('⏳', isTwi() ? TWI_STATUS.thinking : 'Processing...');

    // Add user message
    addMessage('user', isTwi() ? '🎤 Wo nne regye aso...' : '🎤 ...');

    // Show typing indicator
    const typingId = showTypingIndicator();

    try {
        // Prepare form data
        const formData = new FormData();
        let extension = 'webm';
        if (mimeType.includes('ogg')) extension = 'ogg';
        else if (mimeType.includes('mp4')) extension = 'mp4';
        else if (mimeType.includes('wav')) extension = 'wav';
        formData.append('audio', audioBlob, `recording.${extension}`);
        formData.append('language', state.currentLanguage.code);
        if (state.sessionId) formData.append('session_id', state.sessionId);

        // PHASE 1: Get text response (fast — no TTS wait!)
        const response = await fetch('/api/process-voice', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) throw new Error(`Server error: ${response.status}`);
        const data = await response.json();

        // Remove typing indicator
        removeTypingIndicator(typingId);

        // Update session
        state.sessionId = data.session_id;

        // Show text immediately — user sees response NOW
        const msgElement = addMessage('ai', data.text);
        playSuccessChime();
        setStatus('📖', isTwi() ? TWI_STATUS.ready : '');

        // PHASE 2: Fetch audio in background (non-blocking!)
        fetchAndPlayAudio(data.text, data.language, msgElement);

    } catch (err) {
        console.error('Processing error:', err);
        removeTypingIndicator(typingId);
        playErrorSound();
        setStatus('❌', isTwi() ? TWI_STATUS.error : '');
        addMessage('error', '⚠️ ' + (navigator.onLine ? 'Kafra, bɔ mmɔden bio 🔄' : '📵 No Internet') + ' — 🔄');
    } finally {
        state.isProcessing = false;
        dom.btnMic.classList.remove('processing');
        dom.micIcon.style.display = 'block';
        dom.micSpinner.style.display = 'none';
    }
}

/**
 * Phase 2: Fetch TTS audio in background and auto-play.
 * This runs AFTER the text is already shown to the user.
 */
async function fetchAndPlayAudio(text, language, msgElement) {
    // Show audio loading indicator on the message
    const audioBtn = msgElement ? msgElement.querySelector('.play-message-btn') : null;
    if (audioBtn) {
        audioBtn.innerHTML = '⏳ Audio reba...';
        audioBtn.disabled = true;
    }

    setStatus('🔊', isTwi() ? TWI_STATUS.audio_loading : 'Loading audio...');

    try {
        const formData = new FormData();
        formData.append('text', text);
        formData.append('language', language);

        const response = await fetch('/api/generate-audio', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) throw new Error(`Audio error: ${response.status}`);
        const data = await response.json();

        if (data.has_audio && data.audio) {
            // Store audio data on the message element for replay
            if (msgElement) {
                msgElement.dataset.audio = data.audio;
                msgElement.dataset.audioMime = data.audio_mime;
            }

            // Update the replay button
            if (audioBtn) {
                audioBtn.innerHTML = '🔊 Tie bio (Replay)';
                audioBtn.disabled = false;
                audioBtn.onclick = () => playResponseAudio(data.audio, data.audio_mime);
            }

            // Auto-play the audio (audio-first experience!)
            playResponseAudio(data.audio, data.audio_mime);
            setStatus('📖', isTwi() ? TWI_STATUS.ready : '');
        } else {
            // No server audio — use browser TTS fallback
            if (audioBtn) {
                audioBtn.innerHTML = '🔊 Tie bio (Replay)';
                audioBtn.disabled = false;
                audioBtn.onclick = () => speakWithBrowserTTS(text);
            }
            speakWithBrowserTTS(text);
            setStatus('📖', isTwi() ? TWI_STATUS.ready : '');
        }
    } catch (err) {
        console.error('Audio fetch error:', err);
        // Fallback to browser TTS
        if (audioBtn) {
            audioBtn.innerHTML = '🔊 Tie bio (Replay)';
            audioBtn.disabled = false;
            audioBtn.onclick = () => speakWithBrowserTTS(text);
        }
        speakWithBrowserTTS(text);
        setStatus('📖', isTwi() ? TWI_STATUS.ready : '');
    }
}

// ============================================================
// TYPING INDICATOR
// ============================================================
let typingCounter = 0;

function showTypingIndicator() {
    const id = `typing-${++typingCounter}`;
    if (dom.welcomeMessage.style.display !== 'none') {
        dom.welcomeMessage.style.display = 'none';
    }
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message message-ai typing-indicator';
    div.innerHTML = `
        <div class="typing-dots">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
        </div>
        <span class="typing-text">${isTwi() ? 'Ɔkyerɛkyerɛfoɔ no resusuw...' : 'Thinking...'}</span>
    `;
    dom.messages.appendChild(div);
    dom.conversationArea.scrollTop = dom.conversationArea.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// ============================================================
// AUDIO PLAYBACK
// ============================================================
function playResponseAudio(base64Audio, mimeType) {
    try {
        stopCurrentAudio();
        const audioData = atob(base64Audio);
        const arrayBuffer = new ArrayBuffer(audioData.length);
        const view = new Uint8Array(arrayBuffer);
        for (let i = 0; i < audioData.length; i++) {
            view[i] = audioData.charCodeAt(i);
        }
        const blob = new Blob([arrayBuffer], { type: mimeType || 'audio/wav' });
        const audioUrl = URL.createObjectURL(blob);
        dom.responseAudio.src = audioUrl;
        dom.responseAudio.play().catch(err => {
            console.warn('Auto-play blocked:', err);
            showAudioPlayer(audioUrl);
        });
        showAudioPlayer(audioUrl);
        dom.responseAudio.ontimeupdate = () => {
            if (dom.responseAudio.duration) {
                const progress = (dom.responseAudio.currentTime / dom.responseAudio.duration) * 100;
                dom.audioProgressBar.style.width = `${progress}%`;
            }
        };
        dom.responseAudio.onended = () => {
            dom.audioProgressBar.style.width = '100%';
            setTimeout(() => {
                dom.audioPlayer.style.display = 'none';
                dom.audioProgressBar.style.width = '0%';
            }, 1000);
        };
    } catch (err) {
        console.error('Audio playback error:', err);
    }
}

function showAudioPlayer(audioUrl) {
    dom.audioPlayer.style.display = 'flex';
    dom.audioPlayer.style.background = state.currentLanguage ? state.currentLanguage.color + '33' : '';
    dom.btnPlayResponse.onclick = () => {
        if (dom.responseAudio.paused) {
            dom.responseAudio.play();
            dom.btnPlayResponse.innerHTML = `<svg viewBox="0 0 24 24" width="40" height="40" fill="white"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>`;
        } else {
            dom.responseAudio.pause();
            dom.btnPlayResponse.innerHTML = `<svg viewBox="0 0 24 24" width="40" height="40" fill="white"><path d="M8 5v14l11-7z"/></svg>`;
        }
    };
    dom.btnStopResponse.onclick = () => stopCurrentAudio();
}

function stopCurrentAudio() {
    try {
        dom.responseAudio.pause();
        dom.responseAudio.currentTime = 0;
        dom.audioPlayer.style.display = 'none';
        dom.audioProgressBar.style.width = '0%';
    } catch (e) {}
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}

// ============================================================
// BROWSER TTS FALLBACK
// ============================================================
function prepareTextForSpeech(text, langCode) {
    let clean = text
        .replace(/###\s+/g, '').replace(/##\s+/g, '').replace(/#\s+/g, '')
        .replace(/\*\*/g, '').replace(/\*/g, '')
        .replace(/__|_/g, '').replace(/>/g, '')
        .replace(/\[.*?\]/g, '').replace(/---/g, '').trim();

    if (langCode === 'tw' || langCode === 'fat') {
        clean = clean
            .replace(/ɛ/g, 'e').replace(/Ɛ/g, 'E')
            .replace(/ɔ/g, 'o').replace(/Ɔ/g, 'O')
            .replace(/\bOnyankopɔn\b/gi, 'O-nyankopon')
            .replace(/\bNyankopɔn\b/gi, 'Nyankopon')
            .replace(/\bTwerɛ\b/gi, 'Twere')
            .replace(/\bMpaebɔ\b/gi, 'Mpaebo')
            .replace(/\bMmpaeɛ\b/gi, 'Mpaee')
            .replace(/\bAsomdwoeɛ\b/gi, 'Asomdwee')
            .replace(/\bNhyira\b/gi, 'N-hyira');
    }
    return clean;
}

function speakWithBrowserTTS(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const langCode = state.currentLanguage ? state.currentLanguage.code : 'tw';
    const cleanText = prepareTextForSpeech(text, langCode);
    const chunks = cleanText.split(/(?<=[.!?:;\n])\s+/).map(c => c.trim()).filter(c => c.length > 0);
    const voices = window.speechSynthesis.getVoices();
    const langMap = {
        'tw': ['en-GH', 'en-NG', 'ak', 'tw', 'en-ZA', 'en-GB'],
        'fat': ['en-GH', 'en-NG', 'ak', 'tw', 'en-ZA', 'en-GB'],
        'ee': ['en-GH', 'en-NG', 'ee', 'en-ZA', 'en-GB'],
        'gaa': ['en-GH', 'en-NG', 'en-ZA', 'en-GB'],
        'ha': ['ha', 'ha-NG', 'ha-NE', 'en-NG', 'en-GH'],
    };
    let matchedVoice = null;
    let matchedLang = 'en-GH';
    if (state.currentLanguage) {
        const preferredLangs = langMap[state.currentLanguage.code] || ['en-GH', 'en'];
        for (const lang of preferredLangs) {
            const voice = voices.find(v => v.lang.toLowerCase().replace('_', '-').startsWith(lang.toLowerCase()));
            if (voice) { matchedVoice = voice; matchedLang = voice.lang; break; }
        }
    }
    chunks.forEach((chunk) => {
        const utterance = new SpeechSynthesisUtterance(chunk);
        if (matchedVoice) { utterance.voice = matchedVoice; utterance.lang = matchedLang; }
        utterance.rate = 0.82;
        utterance.pitch = 0.98;
        window.speechSynthesis.speak(utterance);
    });
}

// ============================================================
// UI HELPERS
// ============================================================
function setStatus(icon, text) {
    dom.statusIcon.textContent = icon;
    dom.statusText.textContent = text;
}

function addMessage(type, content, audioData = null) {
    if (dom.welcomeMessage.style.display !== 'none') {
        dom.welcomeMessage.style.display = 'none';
    }
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;

    if (type === 'ai') {
        messageDiv.innerHTML = `
            <div class="message-text">${formatMessageText(content)}</div>
            <button class="play-message-btn" disabled>
                ⏳ Audio reba...
            </button>
        `;
    } else {
        messageDiv.innerHTML = `<div class="message-text">${formatMessageText(content)}</div>`;
    }

    dom.messages.appendChild(messageDiv);
    dom.conversationArea.scrollTop = dom.conversationArea.scrollHeight;
    return messageDiv;
}

function formatMessageText(text) {
    return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/###\s+(.*?)(\n|$)/g, '<h3 class="msg-header">$1</h3>')
        .replace(/##\s+(.*?)(\n|$)/g, '<h2 class="msg-header">$1</h2>')
        .replace(/#\s+(.*?)(\n|$)/g, '<h1 class="msg-header">$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>')
        .replace(/---/g, '<hr class="msg-divider">');
}

function replayMessage(button) {
    const msgEl = button.closest('.message');
    if (msgEl && msgEl.dataset.audio) {
        playResponseAudio(msgEl.dataset.audio, msgEl.dataset.audioMime);
    } else {
        const textEl = button.closest('.message').querySelector('.message-text');
        if (textEl) speakWithBrowserTTS(textEl.textContent);
    }
}

// ============================================================
// EVENT LISTENERS
// ============================================================
function setupEventListeners() {
    dom.btnBack.addEventListener('click', () => {
        stopCurrentAudio();
        stopMicStream();
        if (state.isRecording) {
            state.isRecording = false;
            if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') state.mediaRecorder.stop();
        }
        showScreen('language');
        playBeep(500, 100);
    });

    dom.btnMic.addEventListener('click', () => toggleRecording());

    window.addEventListener('online', () => { dom.offlineBanner.style.display = 'none'; });
    window.addEventListener('offline', () => { dom.offlineBanner.style.display = 'flex'; });

    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }

    document.addEventListener('dblclick', (e) => { e.preventDefault(); }, { passive: false });
}

// ============================================================
// ONLINE STATUS
// ============================================================
function checkOnlineStatus() {
    if (!navigator.onLine) dom.offlineBanner.style.display = 'flex';
}

// ============================================================
// GLOBAL FUNCTIONS
// ============================================================
window.replayMessage = replayMessage;
window.speakWithBrowserTTS = speakWithBrowserTTS;

// ============================================================
// BOOT
// ============================================================
document.addEventListener('DOMContentLoaded', init);
