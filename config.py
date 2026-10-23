"""
config.py
Central configuration and credentials management for Al Haqq Shorts & Mini-Long Video Repurposing Engine.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("al-haqq-engine")

# Working Directories
JOBS_DIR = BASE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Template
TEMPLATE_PATH = BASE_DIR / "AL HAQQQ TEMP.jpg"

# ── API Credentials ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_PRIMARY_MODEL = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-2.5-flash-lite").strip()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_API_KEY_FALLBACK = os.getenv("GROQ_API_KEY_FALLBACK", "").strip()
GROQ_WHISPER_MODEL = "whisper-large-v3"
GROQ_FALLBACK_LLM = "qwen/qwen3.8-27b"

# Security & Port
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()
PORT = int(os.getenv("PORT", "10000"))

# ── Duration & Video Standards ──────────────────────────────────────────────
SHORTS_MIN_DURATION = 35.0         # Seconds
SHORTS_MAX_DURATION = 175.0        # < 3 minutes (YouTube Shorts boundary)
MINI_LONG_MAX_DURATION = 360.0     # Strict 6 minutes cap for long complete topics

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 1280
VIDEO_BOX_WIDTH = 640
VIDEO_BOX_HEIGHT = 640
VIDEO_BOX_LEFT = 40
VIDEO_BOX_TOP = 360

# ── Cross-Platform Typography Support (Windows & Linux/Docker) ──────────────
def resolve_font_path(candidates):
    for path_str in candidates:
        if os.path.exists(path_str):
            return path_str
    return None

FONT_HOOK_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
]
FONT_HOOK = resolve_font_path(FONT_HOOK_CANDIDATES)

FONT_ARABIC_CANDIDATES = [
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf"
]
FONT_ARABIC = resolve_font_path(FONT_ARABIC_CANDIDATES)
