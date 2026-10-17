/**
 * Audio Bible AI — Asante Twi Audio Bible
 *
 * Voice-first interface for Bible reading & teaching in Asante Twi.
 * Uses streaming (/api/converse) so the first sentence starts playing
 * in a native Ghanaian voice while the rest of the answer or chapter streams.
 */

// ============================================================
// STATE
// ============================================================
const state = {
    currentLanguage: {
        code: 'tw',
        name: 'Asante Twi',
        native_name: 'Asante Twi',
        color: '#D4A017',
        color_light: '#FFF3D0',
        icon: '🇬🇭',
    },
    sessionId: null,
    isRecording: false,
    isProcessing: false,
    mediaRecorder: null,
    audioChunks: [],
    stream: null,
    abortController: null,
    playbackQueue: [],
    isPlayingQueue: false,
    currentObjectUrl: null,
};

// ============================================================
// DOM ELEMENTS
// ============================================================
const dom = {
    screenLanguage: document.getElementById('screen-language'),
    screenVoice: document.getElementById('screen-voice'),
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

// Twi status messages
const STATUS = {
    listening: 'Meredie wo asɛm...',
    thinking: '✨ Onyame Asɛm resiesie...',
    speaking: '🔊 Tie Onyame Asɛm...',
    ready: 'Kasa kyerɛ Onyame Asɛm Ɔkyerɛkyerɛfoɔ no',
    error: 'Kafra, bɔ mmɔden bio',
};

const PAUSE_ICON = `<svg viewBox="0 0 24 24" width="40" height="40" fill="white"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>`;
const PLAY_ICON = `<svg viewBox="0 0 24 24" width="40" height="40" fill="white"><path d="M8 5v14l11-7z"/></svg>`;

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
// INITIALIZE — Auto-launch into Twi voice screen
// ============================================================
function init() {
    setupEventListeners();
    checkOnlineStatus();

    const lang = state.currentLanguage;
    dom.voiceTopbar.style.background = lang.color;
    dom.langFlag.textContent = lang.icon;
    dom.langName.textContent = 'Asante Twi Audio Bible';
    dom.btnMic.style.background = lang.color;
    dom.btnMic.style.boxShadow = `0 4px 20px ${lang.color}66`;
    dom.welcomeMessage.innerHTML = `
        <div style="font-size: 50px; margin-bottom: 12px;">📖✝️</div>
        <div style="font-size: 16px; color: var(--text-secondary); margin-top: 8px;">
            Kasa kyerɛ Onyame Asɛm Ɔkyerɛkyerɛfoɔ no
        </div>
    `;
    setStatus('🎤', STATUS.ready);

    dom.screenLanguage.classList.remove('active');
    dom.screenVoice.classList.add('active');

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(() => {});
    }
}

// ============================================================
// VOICE RECORDING
// ============================================================
async function startRecording() {
    stopCurrentAudio();
    if (state.isProcessing && state.abortController) {
        state.abortController.abort();
    }
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
        setStatus('🔴', STATUS.listening);
        playStartBeep();
        setTimeout(() => { if (state.isRecording) stopRecording(); }, 60000);
    } catch (err) {
        console.error('Microphone error:', err);
        playErrorSound();
        setStatus('🎤❌', '');
        addMessage('error', '🎤 ❌ — Ma me kwan na menye wo nne (Allow microphone)');
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

// ============================================================
// STREAMED CONVERSATION (/api/converse)
// ============================================================
async function processAudio(audioBlob, mimeType) {
    const formData = new FormData();
    let extension = 'webm';
    if (mimeType.includes('ogg')) extension = 'ogg';
    else if (mimeType.includes('mp4')) extension = 'mp4';
    else if (mimeType.includes('wav')) extension = 'wav';
    formData.append('audio', audioBlob, `recording.${extension}`);
    formData.append('language', 'tw');
    if (state.sessionId) formData.append('session_id', state.sessionId);

    const userMsgEl = addMessage('user', '🎤 Wo nne regye aso...');
    await runConverseStream(formData, userMsgEl);
}

async function processTextPrompt(text) {
    stopCurrentAudio();
    const formData = new FormData();
    formData.append('text', text);
    formData.append('language', 'tw');
    if (state.sessionId) formData.append('session_id', state.sessionId);

    const userMsgEl = addMessage('user', `🗣️ ${text}`);
    await runConverseStream(formData, userMsgEl);
}

async function runConverseStream(formData, userMsgEl) {
    state.isProcessing = true;
    state.abortController = new AbortController();

    dom.btnMic.classList.add('processing');
    dom.micIcon.style.display = 'none';
    dom.micSpinner.style.display = 'flex';
    setStatus('⏳', STATUS.thinking);

    const typingId = showTypingIndicator();
    let aiMsgEl = null;
    let aiTextLines = [];
    let savedChunks = [];

    try {
        const response = await fetch('/api/converse', {
            method: 'POST',
            body: formData,
            signal: state.abortController.signal,
        });
        if (!response.ok || !response.body) {
            throw new Error(`Server error: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            let newlineIdx;
            while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
                const line = buffer.slice(0, newlineIdx).trim();
                buffer = buffer.slice(newlineIdx + 1);
                if (!line) continue;

                let ev;
                try {
                    ev = JSON.parse(line);
                } catch (e) {
                    continue;
                }

                if (ev.type === 'session') {
                    state.sessionId = ev.session_id;
                } else if (ev.type === 'transcript' && ev.text && userMsgEl) {
                    const textDiv = userMsgEl.querySelector('.message-text');
                    if (textDiv) textDiv.innerHTML = formatMessageText(`🎤 ${ev.text}`);
                } else if (ev.type === 'text' && ev.text) {
                    removeTypingIndicator(typingId);
                    aiTextLines.push(ev.text);
                    if (!aiMsgEl) {
                        aiMsgEl = addMessage('ai', ev.text);
                        playSuccessChime();
                    } else {
                        const textDiv = aiMsgEl.querySelector('.message-text');
                        if (textDiv) {
                            textDiv.innerHTML = formatMessageText(aiTextLines.join('\n'));
                        }
                        dom.conversationArea.scrollTop = dom.conversationArea.scrollHeight;
                    }
                } else if (ev.type === 'audio') {
                    if (ev.audio) {
                        const chunk = { audio: ev.audio, mime: ev.mime || 'audio/wav' };
                        savedChunks.push(chunk);
                        enqueueAudioChunk(chunk);
                    } else if (ev.has_audio === false && ev.text) {
                        const chunk = { browserText: ev.text };
                        savedChunks.push(chunk);
                        enqueueAudioChunk(chunk);
                    }
                } else if (ev.type === 'error') {
                    removeTypingIndicator(typingId);
                    addMessage('error', `⚠️ ${ev.message || STATUS.error}`);
                }
            }
        }

        if (aiMsgEl) {
            aiMsgEl._savedChunks = savedChunks;
            const fullText = aiTextLines.join('\n');
            const audioBtn = aiMsgEl.querySelector('.play-message-btn');
            if (audioBtn) {
                audioBtn.innerHTML = '🔊 Tie bio (Replay)';
                audioBtn.disabled = false;
                audioBtn.onclick = () => {
                    if (aiMsgEl._savedChunks && aiMsgEl._savedChunks.length > 0) {
                        stopCurrentAudio();
                        aiMsgEl._savedChunks.forEach(c => enqueueAudioChunk(c));
                    } else {
                        speakWithBrowserTTS(fullText);
                    }
                };
            }
        }
    } catch (err) {
        removeTypingIndicator(typingId);
        if (err.name !== 'AbortError') {
            console.error('Stream error:', err);
            playErrorSound();
            setStatus('❌', STATUS.error);
            addMessage('error', '⚠️ Kafra, bɔ mmɔden bio 🔄');
        }
    } finally {
        removeTypingIndicator(typingId);
        state.isProcessing = false;
        dom.btnMic.classList.remove('processing');
        dom.micIcon.style.display = 'block';
        dom.micSpinner.style.display = 'none';
        if (!state.isPlayingQueue) {
            setStatus('🎤', STATUS.ready);
        }
    }
}

// ============================================================
// SEQUENTIAL STREAMED AUDIO QUEUE
// ============================================================
function enqueueAudioChunk(chunk) {
    state.playbackQueue.push(chunk);
    if (!state.isPlayingQueue) {
        playNextInQueue();
    }
}

function playNextInQueue() {
    if (state.playbackQueue.length === 0) {
        state.isPlayingQueue = false;
        dom.audioProgressBar.style.width = '100%';
        setTimeout(() => {
            if (!state.isPlayingQueue) {
                dom.audioPlayer.style.display = 'none';
                dom.audioProgressBar.style.width = '0%';
                setStatus('🎤', STATUS.ready);
            }
        }, 600);
        return;
    }

    state.isPlayingQueue = true;
    setStatus('🔊', STATUS.speaking);
    showAudioPlayer();

    const next = state.playbackQueue.shift();
    if (next.browserText) {
        speakChunkWithBrowserTTS(next.browserText, () => playNextInQueue());
        return;
    }

    try {
        if (state.currentObjectUrl) {
            URL.revokeObjectURL(state.currentObjectUrl);
            state.currentObjectUrl = null;
        }
        const audioData = atob(next.audio);
        const arrayBuffer = new ArrayBuffer(audioData.length);
        const view = new Uint8Array(arrayBuffer);
        for (let i = 0; i < audioData.length; i++) {
            view[i] = audioData.charCodeAt(i);
        }
        const blob = new Blob([arrayBuffer], { type: next.mime || 'audio/wav' });
        state.currentObjectUrl = URL.createObjectURL(blob);
        dom.responseAudio.src = state.currentObjectUrl;
        dom.btnPlayResponse.innerHTML = PAUSE_ICON;

        dom.responseAudio.ontimeupdate = () => {
            if (dom.responseAudio.duration) {
                const progress = (dom.responseAudio.currentTime / dom.responseAudio.duration) * 100;
                dom.audioProgressBar.style.width = `${progress}%`;
            }
        };
        dom.responseAudio.onended = () => {
            playNextInQueue();
        };
        dom.responseAudio.onerror = () => {
            playNextInQueue();
        };
        dom.responseAudio.play().catch(err => {
            console.warn('Auto-play blocked:', err);
            dom.btnPlayResponse.innerHTML = PLAY_ICON;
        });
    } catch (err) {
        console.error('Chunk playback error:', err);
        playNextInQueue();
    }
}

function showAudioPlayer() {
    dom.audioPlayer.style.display = 'flex';
    dom.audioPlayer.style.background = state.currentLanguage.color + '33';
    dom.btnPlayResponse.onclick = () => {
        if (dom.responseAudio.paused) {
            dom.responseAudio.play();
            dom.btnPlayResponse.innerHTML = PAUSE_ICON;
        } else {
            dom.responseAudio.pause();
            dom.btnPlayResponse.innerHTML = PLAY_ICON;
        }
    };
    dom.btnStopResponse.onclick = () => {
        if (state.isProcessing && state.abortController) {
            state.abortController.abort();
        }
        stopCurrentAudio();
        setStatus('🎤', STATUS.ready);
    };
}

function stopCurrentAudio() {
    state.playbackQueue = [];
    state.isPlayingQueue = false;
    try {
        dom.responseAudio.onended = null;
        dom.responseAudio.pause();
        dom.responseAudio.currentTime = 0;
        dom.audioPlayer.style.display = 'none';
        dom.audioProgressBar.style.width = '0%';
        if (state.currentObjectUrl) {
            URL.revokeObjectURL(state.currentObjectUrl);
            state.currentObjectUrl = null;
        }
    } catch (e) {}
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
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
        <span class="typing-text">Ɔkyerɛkyerɛfoɔ no resusuw...</span>
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
// BROWSER TTS FALLBACK
// ============================================================
function prepareTextForSpeech(text) {
    let clean = text
        .replace(/###\s+/g, '').replace(/##\s+/g, '').replace(/#\s+/g, '')
        .replace(/\*\*/g, '').replace(/\*/g, '')
        .replace(/__|_/g, '').replace(/>/g, '')
        .replace(/\[.*?\]/g, '').replace(/---/g, '').trim();

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
    return clean;
}

function speakChunkWithBrowserTTS(text, onDone) {
    if (!('speechSynthesis' in window)) {
        if (onDone) onDone();
        return;
    }
    const cleanText = prepareTextForSpeech(text);
    const voices = window.speechSynthesis.getVoices();
    let matchedVoice = null;
    let matchedLang = 'en-GH';
    for (const lang of ['en-GH', 'en-NG', 'ak', 'tw', 'en-ZA', 'en-GB']) {
        const voice = voices.find(v => v.lang.toLowerCase().replace('_', '-').startsWith(lang.toLowerCase()));
        if (voice) { matchedVoice = voice; matchedLang = voice.lang; break; }
    }
    const utterance = new SpeechSynthesisUtterance(cleanText);
    if (matchedVoice) { utterance.voice = matchedVoice; utterance.lang = matchedLang; }
    utterance.rate = 0.85;
    utterance.pitch = 0.98;
    utterance.onend = () => { if (onDone) onDone(); };
    utterance.onerror = () => { if (onDone) onDone(); };
    window.speechSynthesis.speak(utterance);
}

function speakWithBrowserTTS(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const cleanText = prepareTextForSpeech(text);
    const chunks = cleanText.split(/(?<=[.!?:;\n])\s+/).map(c => c.trim()).filter(c => c.length > 0);
    chunks.forEach(c => enqueueAudioChunk({ browserText: c }));
}

// ============================================================
// UI HELPERS
// ============================================================
function setStatus(icon, text) {
    dom.statusIcon.textContent = icon;
    dom.statusText.textContent = text;
}

function addMessage(type, content) {
    if (dom.welcomeMessage.style.display !== 'none') {
        dom.welcomeMessage.style.display = 'none';
    }
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;

    if (type === 'ai') {
        messageDiv.innerHTML = `
            <div class="message-text">${formatMessageText(content)}</div>
            <button class="play-message-btn" disabled>⏳ Audio reba...</button>
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
    });

    dom.btnMic.addEventListener('click', () => toggleRecording());
    window.addEventListener('online', () => { dom.offlineBanner.style.display = 'none'; });
    window.addEventListener('offline', () => { dom.offlineBanner.style.display = 'flex'; });

    if ('speechSynthesis' in window) {
        window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }

    document.addEventListener('dblclick', (e) => { e.preventDefault(); }, { passive: false });
}

function checkOnlineStatus() {
    if (!navigator.onLine) dom.offlineBanner.style.display = 'flex';
}

window.speakWithBrowserTTS = speakWithBrowserTTS;
window.processTextPrompt = processTextPrompt;

document.addEventListener('DOMContentLoaded', init);
