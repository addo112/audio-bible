# 📖 Audio Bible AI

**Voice-first AI Bible teaching assistant for Ghanaian languages**

Listen to God's Word explained in your language — Asante Twi, Fante, Ewe, GA, and Hausa. Designed for people who cannot read or write.

## 🎯 Features

- 🎤 **Voice Input** — Speak your question in your language
- 🧠 **AI Bible Teacher** — Expert explanations with verse references  
- 🔊 **Audio Responses** — Hear answers in your language
- 📱 **Mobile PWA** — Install on your phone like a native app
- 🌍 **5 Languages** — Asante Twi, Fante, Ewe, GA, Hausa
- ♿ **Accessibility** — No reading required, icon-driven interface

## 🚀 Quick Start

### 1. Get a Free Gemini API Key
Visit [aistudio.google.com](https://aistudio.google.com/) and create a free API key.

### 2. Setup
```bash
# Clone the repository
git clone <your-repo-url>
cd audio-bible

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 3. Run Locally
```bash
python main.py
# Or: uvicorn main:app --reload --port 8000
```

Open http://localhost:8000 on your phone or browser.

### 4. Deploy to Render (Free)

1. Push code to a GitHub repository
2. Go to [render.com](https://render.com/) and sign up
3. Click **New → Web Service**
4. Connect your GitHub repo
5. Settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables:
   - `GEMINI_API_KEY` = your Gemini key
   - `KHAYA_API_KEY` = (optional) your Khaya key
7. Click **Deploy**

Your app will be live at `https://your-app-name.onrender.com`

## 🏗️ Architecture

```
User speaks (Twi/Fante/Ewe/GA/Hausa)
    → Browser records audio
    → FastAPI backend
    → Google Gemini AI (understands audio + responds as Bible teacher)
    → Text-to-Speech (Khaya AI / gTTS / Browser TTS)
    → User hears Bible teaching in their language
```

## 📁 Project Structure

```
audio-bible/
├── main.py                    # FastAPI entry point
├── app/
│   ├── config.py              # Language & API configuration
│   ├── services/
│   │   ├── bible_ai.py        # Gemini Bible teacher AI
│   │   └── tts_service.py     # Text-to-Speech (multi-fallback)
│   └── routes/
│       └── api.py             # REST API endpoints
├── static/
│   ├── index.html             # Main UI (voice-first SPA)
│   ├── manifest.json          # PWA manifest
│   ├── sw.js                  # Service worker
│   ├── css/style.css          # Mobile-first styles
│   ├── js/app.js              # Frontend logic
│   └── icons/                 # App icons
├── requirements.txt
├── Dockerfile
├── render.yaml
└── .env.example
```

## 🔑 API Keys

| Service | Purpose | Cost | Required? |
|---------|---------|------|-----------|
| Google Gemini | AI Bible teacher + audio understanding | Free tier | ✅ Yes |
| Khaya AI | High-quality Ghanaian TTS | 100 free calls/month | ❌ Optional |

## 📜 License

Built with ❤️ for the people of Ghana and West Africa.
