/**
 * Audio Bible AI — Frontend Application
 * 
 * Voice-first interface for Bible teaching in Ghanaian languages.
 * Handles: audio recording, API communication, TTS playback, UI state.
 */

// ============================================================
// STATE
// ============================================================
const state = {
    currentLanguage: null,    // Selected language object
    sessionId: null,          // Conversation session ID
    isRecording: false,       // Currently recording audio
    isProcessing: false,      // Waiting for AI response
    mediaRecorder: null,      // MediaRecorder instance
    audioChunks: [],          // Recorded audio chunks
    currentAudio: null,       // Currently playing audio element
    stream: null,             // Microphone MediaStream
};

// ============================================================
// DOM ELEMENTS
// ============================================================
const dom = {
    // Screens
    screenLanguage: document.getElementById('screen-language'),
    screenVoice: document.getElementById('screen-voice'),
    
    // Language screen
    languageGrid: document.getElementById('language-grid'),
    
    // Voice screen
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
    
    // Audio player
    audioPlayer: document.getElementById('audio-player'),
    btnPlayResponse: document.getElementById('btn-play-response'),
    btnStopResponse: document.getElementById('btn-stop-response'),
    audioProgress: document.getElementById('audio-progress'),
    audioProgressBar: document.getElementById('audio-progress-bar'),
    
    // Microphone
    btnMic: document.getElementById('btn-mic'),
    micIcon: document.getElementById('mic-icon'),
    micSpinner: document.getElementById('mic-spinner'),
    micRipple: document.getElementById('mic-ripple'),
    micLabel: document.getElementById('mic-label'),
    
    // Audio element
    responseAudio: document.getElementById('response-audio'),
    
    // Offline
    offlineBanner: document.getElementById('offline-banner'),
};

// ============================================================
// LANGUAGE DATA
// ============================================================
const LANGUAGES = [
    {
        code: 'tw',
        name: 'Asante Twi',
        native_name: 'Asante Twi',
        color: '#D4A017',
        color_light: '#FFF3D0',
        icon: '🇬🇭',
        symbol: '🟡',
    },
    {
        code: 'fat',
        name: 'Fante',
        native_name: 'Mfantse',
        color: '#006B3F',
        color_light: '#D0F5E0',
        icon: '🇬🇭',
        symbol: '🟢',
    },
    {
        code: 'ee',
        name: 'Ewe',
        native_name: 'Eʋegbe',
        color: '#CE1126',
        color_light: '#FFD6DC',
        icon: '🇬🇭',
        symbol: '🔴',
    },
    {
        code: 'gaa',
        name: 'GA',
        native_name: 'Gã',
        color: '#003F87',
        color_light: '#D0E3FF',
        icon: '🇬🇭',
        symbol: '🔵',
    },
    {
        code: 'ha',
        name: 'Hausa',
        native_name: 'Hausa',
        color: '#FF8C00',
        color_light: '#FFF0D0',
        icon: '🇳🇬',
        symbol: '🟠',
    },
];

// ============================================================
// AUDIO UTILITIES
// ============================================================

/**
 * Generate a simple beep sound using Web Audio API.
 * Used for audio feedback (no external sound files needed).
 */
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
        
        // Fade out
        gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration / 1000);
        
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + duration / 1000);
    } catch (e) {
        // Audio feedback is non-critical
    }
}

function playStartBeep() {
    playBeep(600, 100);
    setTimeout(() => playBeep(900, 150), 120);
}

function playStopBeep() {
    playBeep(900, 100);
    setTimeout(() => playBeep(600, 150), 120);
}

function playSuccessChime() {
    playBeep(523, 100); // C5
    setTimeout(() => playBeep(659, 100), 100); // E5
    setTimeout(() => playBeep(784, 200), 200); // G5
}

function playErrorSound() {
    playBeep(300, 200, 'square');
}

// ============================================================
// INITIALIZE
// ============================================================
function init() {
    renderLanguageGrid();
    setupEventListeners();
    checkOnlineStatus();
    
    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(() => {});
    }
}

// ============================================================
// LANGUAGE SELECTION SCREEN
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
    state.sessionId = null; // New session for new language
    
    // Update voice screen colors
    dom.voiceTopbar.style.background = lang.color;
    dom.langFlag.textContent = lang.icon;
    dom.langName.textContent = lang.name;
    dom.btnMic.style.background = lang.color;
    dom.btnMic.style.boxShadow = `0 4px 20px ${lang.color}66`;
    
    // Set welcome message
    dom.welcomeMessage.innerHTML = `
        <div style="font-size: 50px; margin-bottom: 12px;">📖✝️</div>
    `;
    
    // Clear previous messages
    dom.messages.innerHTML = '';
    dom.audioPlayer.style.display = 'none';
    
    // Update status
    setStatus('🎤', '');
    
    // Switch screens
    showScreen('voice');
    
    // Play selection feedback
    playBeep(700, 100);
}

// ============================================================
// SCREEN NAVIGATION
// ============================================================
function showScreen(screenName) {
    dom.screenLanguage.classList.remove('active');
    dom.screenVoice.classList.remove('active');
    
    if (screenName === 'language') {
        dom.screenLanguage.classList.add('active');
    } else if (screenName === 'voice') {
        dom.screenVoice.classList.add('active');
    }
}

// ============================================================
// VOICE RECORDING
// ============================================================

async function startRecording() {
    if (state.isProcessing) return;
    
    try {
        // Request microphone access
        state.stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
            } 
        });
        
        // Determine best supported MIME type
        const mimeType = getSupportedMimeType();
        
        state.mediaRecorder = new MediaRecorder(state.stream, { 
            mimeType: mimeType,
        });
        state.audioChunks = [];
        
        state.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                state.audioChunks.push(event.data);
            }
        };
        
        state.mediaRecorder.onstop = () => {
            const audioBlob = new Blob(state.audioChunks, { type: mimeType });
            stopMicStream();
            processAudio(audioBlob, mimeType);
        };
        
        state.mediaRecorder.start();
        state.isRecording = true;
        
        // Update UI
        dom.btnMic.classList.add('recording');
        dom.micRipple.classList.add('active');
        dom.micRipple.style.background = state.currentLanguage.color;
        setStatus('🔴', '');
        
        // Audio feedback
        playStartBeep();
        
        // Auto-stop after 60 seconds
        setTimeout(() => {
            if (state.isRecording) {
                stopRecording();
            }
        }, 60000);
        
    } catch (err) {
        console.error('Microphone error:', err);
        playErrorSound();
        setStatus('🎤❌', '');
        
        // Show error message
        addMessage('error', '🎤 ❌ — Please allow microphone access');
    }
}

function stopRecording() {
    if (!state.isRecording || !state.mediaRecorder) return;
    
    state.isRecording = false;
    state.mediaRecorder.stop();
    
    // Update UI
    dom.btnMic.classList.remove('recording');
    dom.micRipple.classList.remove('active');
    
    // Audio feedback
    playStopBeep();
}

function stopMicStream() {
    if (state.stream) {
        state.stream.getTracks().forEach(track => track.stop());
        state.stream = null;
    }
}

function getSupportedMimeType() {
    const types = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        'audio/mp4',
        'audio/wav',
    ];
    
    for (const type of types) {
        if (MediaRecorder.isTypeSupported(type)) {
            return type;
        }
    }
    return 'audio/webm'; // Default fallback
}

function toggleRecording() {
    if (state.isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
}

// ============================================================
// API COMMUNICATION
// ============================================================

async function processAudio(audioBlob, mimeType) {
    if (state.isProcessing) return;
    
    state.isProcessing = true;
    
    // Update UI to processing state
    dom.btnMic.classList.add('processing');
    dom.micIcon.style.display = 'none';
    dom.micSpinner.style.display = 'flex';
    setStatus('⏳', '');
    
    // Add user message indicator
    addMessage('user', '🎤 ...');
    
    try {
        // Prepare form data
        const formData = new FormData();
        
        // Determine file extension from mime type
        let extension = 'webm';
        if (mimeType.includes('ogg')) extension = 'ogg';
        else if (mimeType.includes('mp4')) extension = 'mp4';
        else if (mimeType.includes('wav')) extension = 'wav';
        
        formData.append('audio', audioBlob, `recording.${extension}`);
        formData.append('language', state.currentLanguage.code);
        if (state.sessionId) {
            formData.append('session_id', state.sessionId);
        }
        
        // Send to backend
        const response = await fetch('/api/process-voice', {
            method: 'POST',
            body: formData,
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update session ID for conversation continuity
        state.sessionId = data.session_id;
        
        // Add AI response message
        addMessage('ai', data.text, data.has_audio ? data : null);
        
        // Play audio response
        if (data.has_audio && data.audio) {
            playResponseAudio(data.audio, data.audio_mime);
        } else {
            // Use browser TTS as fallback
            speakWithBrowserTTS(data.text);
        }
        
        // Success feedback
        playSuccessChime();
        setStatus('📖', '');
        
    } catch (err) {
        console.error('Processing error:', err);
        playErrorSound();
        setStatus('❌', '');
        addMessage('error', '⚠️ ' + (navigator.onLine ? 'Error' : 'No Internet') + ' — 🔄');
    } finally {
        // Reset UI state
        state.isProcessing = false;
        dom.btnMic.classList.remove('processing');
        dom.micIcon.style.display = 'block';
        dom.micSpinner.style.display = 'none';
    }
}

// ============================================================
// AUDIO PLAYBACK
// ============================================================

function playResponseAudio(base64Audio, mimeType) {
    try {
        // Stop any currently playing audio
        stopCurrentAudio();
        
        // Create audio from base64
        const audioData = atob(base64Audio);
        const arrayBuffer = new ArrayBuffer(audioData.length);
        const view = new Uint8Array(arrayBuffer);
        for (let i = 0; i < audioData.length; i++) {
            view[i] = audioData.charCodeAt(i);
        }
        
        const blob = new Blob([arrayBuffer], { type: mimeType || 'audio/mp3' });
        const audioUrl = URL.createObjectURL(blob);
        
        dom.responseAudio.src = audioUrl;
        dom.responseAudio.play().catch(err => {
            console.warn('Auto-play blocked, user interaction needed:', err);
            // Show play button
            showAudioPlayer(audioUrl);
        });
        
        // Show audio player
        showAudioPlayer(audioUrl);
        
        // Track progress
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
    
    // Update play button
    dom.btnPlayResponse.onclick = () => {
        if (dom.responseAudio.paused) {
            dom.responseAudio.play();
            dom.btnPlayResponse.innerHTML = `
                <svg viewBox="0 0 24 24" width="40" height="40" fill="white">
                    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
                </svg>`;
        } else {
            dom.responseAudio.pause();
            dom.btnPlayResponse.innerHTML = `
                <svg viewBox="0 0 24 24" width="40" height="40" fill="white">
                    <path d="M8 5v14l11-7z"/>
                </svg>`;
        }
    };
    
    dom.btnStopResponse.onclick = () => {
        stopCurrentAudio();
    };
}

function stopCurrentAudio() {
    try {
        dom.responseAudio.pause();
        dom.responseAudio.currentTime = 0;
        dom.audioPlayer.style.display = 'none';
        dom.audioProgressBar.style.width = '0%';
    } catch (e) {}
    
    // Also stop browser TTS
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
}

/**
 * Prepare and smooth text for realistic, humanized pronunciation by speech engines.
 * Converts special orthography (ɛ, ɔ, etc.) to clean phonetic equivalents
 * and inserts natural rhythm pauses for authentic Ghanaian cadence.
 */
function prepareTextForSpeech(text, langCode) {
    let clean = text
        .replace(/###\s+/g, '')
        .replace(/##\s+/g, '')
        .replace(/#\s+/g, '')
        .replace(/\*\*/g, '')
        .replace(/\*/g, '')
        .replace(/__|_/g, '')
        .replace(/>/g, '')
        .replace(/\[.*?\]/g, '')
        .replace(/---/g, '')
        .trim();
        
    if (langCode === 'tw' || langCode === 'fat') {
        // Phonetic smoothing for natural Akan pronunciation on standard synthesizers
        clean = clean
            .replace(/ɛ/g, 'e')
            .replace(/Ɛ/g, 'E')
            .replace(/ɔ/g, 'o')
            .replace(/Ɔ/g, 'O')
            .replace(/\bOnyankopɔn\b/gi, 'O-nyankopon')
            .replace(/\bNyankopɔn\b/gi, 'Nyankopon')
            .replace(/\bTwerɛ\b/gi, 'Twere')
            .replace(/\bMpaebɔ\b/gi, 'Mpaebo')
            .replace(/\bMmpaeɛ\b/gi, 'Mpaee')
            .replace(/\bAsomdwoeɛ\b/gi, 'Asomdwee')
            .replace(/\bNhyira\b/gi, 'N-hyira')
            .replace(/\bYehowa\b/gi, 'Yehowa')
            .replace(/\bYohane\b/gi, 'Yohane')
            .replace(/\bYesu\b/gi, 'Yesu');
    }
    return clean;
}

/**
 * Browser-based TTS with Ghanaian/West African voice prioritization,
 * sentence chunking, and natural breathing pauses.
 */
function speakWithBrowserTTS(text) {
    if (!('speechSynthesis' in window)) return;
    
    // Cancel any ongoing speech
    window.speechSynthesis.cancel();
    
    const langCode = state.currentLanguage ? state.currentLanguage.code : 'tw';
    const cleanSpeechText = prepareTextForSpeech(text, langCode);
    
    // Split into short, natural spoken clauses so speech sounds rhythmic and conversational
    const chunks = cleanSpeechText
        .split(/(?<=[.!?:;\n])\s+/)
        .map(c => c.trim())
        .filter(c => c.length > 0);
    
    const voices = window.speechSynthesis.getVoices();
    
    // Prioritize Ghanaian (en-GH), West African (en-NG), and natural African English voices
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
            if (voice) {
                matchedVoice = voice;
                matchedLang = voice.lang;
                break;
            }
        }
    }
    
    chunks.forEach((chunk) => {
        const utterance = new SpeechSynthesisUtterance(chunk);
        if (matchedVoice) {
            utterance.voice = matchedVoice;
            utterance.lang = matchedLang;
        }
        utterance.rate = 0.82; // Natural, clear, relaxed cadence for clear listening
        utterance.pitch = 0.98; // Warm, grounded pitch
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
    // Remove welcome message on first interaction
    if (dom.welcomeMessage.style.display !== 'none') {
        dom.welcomeMessage.style.display = 'none';
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;
    
    if (type === 'ai' && audioData && audioData.has_audio) {
        // AI message with replay button
        messageDiv.innerHTML = `
            <div class="message-text">${formatMessageText(content)}</div>
            <button class="play-message-btn" onclick="replayMessage(this)" 
                    data-audio="${audioData.audio}" 
                    data-mime="${audioData.audio_mime}">
                🔊 Tie bio (Replay)
            </button>
        `;
    } else if (type === 'ai') {
        messageDiv.innerHTML = `
            <div class="message-text">${formatMessageText(content)}</div>
            <button class="play-message-btn" onclick="speakWithBrowserTTS(decodeURIComponent('${encodeURIComponent(content)}'))">
                🔊 Tie bio (Replay)
            </button>
        `;
    } else {
        messageDiv.innerHTML = `<div class="message-text">${formatMessageText(content)}</div>`;
    }
    
    dom.messages.appendChild(messageDiv);
    
    // Scroll to bottom
    dom.conversationArea.scrollTop = dom.conversationArea.scrollHeight;
}

function formatMessageText(text) {
    // Convert Markdown headers, blockquotes, bold, and line breaks
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/###\s+(.*?)(\n|$)/g, '<h3 class="msg-header">$1</h3>')
        .replace(/##\s+(.*?)(\n|$)/g, '<h2 class="msg-header">$1</h2>')
        .replace(/#\s+(.*?)(\n|$)/g, '<h1 class="msg-header">$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>')
        .replace(/---/g, '<hr class="msg-divider">');
}

function replayMessage(button) {
    const audio = button.getAttribute('data-audio');
    const mime = button.getAttribute('data-mime');
    if (audio) {
        playResponseAudio(audio, mime);
    }
}

// ============================================================
// EVENT LISTENERS
// ============================================================

function setupEventListeners() {
    // Back button
    dom.btnBack.addEventListener('click', () => {
        stopCurrentAudio();
        stopMicStream();
        if (state.isRecording) {
            state.isRecording = false;
            if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
                state.mediaRecorder.stop();
            }
        }
        showScreen('language');
        playBeep(500, 100);
    });
    
    // Microphone button
    dom.btnMic.addEventListener('click', () => {
        toggleRecording();
    });
    
    // Online/offline detection
    window.addEventListener('online', () => {
        dom.offlineBanner.style.display = 'none';
    });
    
    window.addEventListener('offline', () => {
        dom.offlineBanner.style.display = 'flex';
    });
    
    // Load voices for browser TTS (needed for some browsers)
    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => {
            window.speechSynthesis.getVoices();
        };
    }
    
    // Prevent zoom on double-tap
    document.addEventListener('dblclick', (e) => {
        e.preventDefault();
    }, { passive: false });
}

// ============================================================
// ONLINE STATUS
// ============================================================

function checkOnlineStatus() {
    if (!navigator.onLine) {
        dom.offlineBanner.style.display = 'flex';
    }
}

// ============================================================
// GLOBAL FUNCTIONS (called from HTML onclick)
// ============================================================
window.replayMessage = replayMessage;

// ============================================================
// BOOT
// ============================================================
document.addEventListener('DOMContentLoaded', init);
