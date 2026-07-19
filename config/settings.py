"""
Charlie AI Assistant - Configuration
Edit these values before running. Everything defaults to local/free options
so the system runs at $0 ongoing cost unless you deliberately enable a cloud API.
"""

USER_NAME = "Harshvardhan"

# --- Wake word ---
WAKE_WORD = "hey_jarvis"  
WAKE_WORD_SENSITIVITY = 0.55

# --- Speech-to-Text ---
STT_MODEL_SIZE = "tiny"  # tiny/base/small/medium/large - bigger = more accurate but slower
STT_DEVICE = "cpu"  # "cuda" if you have an NVIDIA GPU set up with CUDA + cuDNN

# --- Brain (LLM) ---
BRAIN_MODE = "local"  # "local" (Ollama, free, unlimited) or "cloud" (API, costs tokens)
OLLAMA_MODEL = "llama3.2:1b"  # 1B model is required because this machine doesn't have enough RAM for 3B+
CLOUD_API_KEY = ""  # only needed if BRAIN_MODE = "cloud"

# --- Text-to-Speech ---
TTS_ENGINE = "pyttsx3"  # "pyttsx3" (instant, offline, robotic) or "coqui" (better quality, slower, offline)
TTS_RATE = 175  # words per minute for pyttsx3

# --- Camera / emotion module ---
CAMERA_ENABLED = False  # OFF by default. Read camera_module.py notes before enabling.
CAMERA_INDEX = 0
EMOTION_CHECK_INTERVAL_SECONDS = 15  # how often to sample, NOT continuous frame-by-frame
EMOTION_CONFIDENCE_THRESHOLD = 0.6  # only act on emotion reads above this confidence

# --- Task list ---
TASKS_FILE = "config/tasks.json"

# --- Proactive Activity Monitor ---
ACTIVITY_ENABLED = True  # Enable Charlie noticing your active windows
ACTIVITY_CHECK_INTERVAL_SECONDS = 60  # Check every 60 seconds
ACTIVITY_PROACTIVE_CHANCE = 0.2  # 20% chance to speak up when activity changes

# --- App Launcher Paths ---
APP_PATHS = {
    "antigravity": r"C:\Users\Harshvardhan Sheikh\Downloads\Antigravity.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "web whatsapp": "https://web.whatsapp.com",
}
BROWSER_PATHS = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
}
SITE_URLS = {
    "youtube": "https://youtube.com",
    "trading": "https://trading.com",
}

ROUTINES = {
    "good morning": [
        ("open_url", {"url": "https://mail.google.com", "browser": "chrome"}),
        ("system_status", {}),
    ],
    "focus mode": [
        ("close_app", {"app_name": "chrome"}),
        ("mute_toggle", {}),
        ("set_display_mode", {"mode": "widget"}),
    ],
}
CONTACTS_FILE = "config/contacts.json"
