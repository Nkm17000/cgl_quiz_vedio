import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
QUIZ_DIR = Path(os.getenv("QUIZ_DIR", ASSETS_DIR / "quiz_data")).expanduser()
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output")).expanduser()
OUTPUT_VIDEO = Path(os.getenv("OUTPUT_VIDEO", OUTPUT_DIR / "quiz_video.mp4")).expanduser()
QUESTION_AUDIO_DIR = Path(
    os.getenv("QUESTION_AUDIO_DIR", ASSETS_DIR / "question_audio")
).expanduser()

VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "720"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1280"))
FPS = int(os.getenv("FPS", "30"))

COUNTDOWN_SECONDS = float(os.getenv("COUNTDOWN_SECONDS", "3"))
POST_AUDIO_WAIT_SECONDS = float(os.getenv("POST_AUDIO_WAIT_SECONDS", "3"))
ANSWER_SLIDE_DURATION = float(os.getenv("ANSWER_SLIDE_DURATION", "3"))

BACKGROUND_VOLUME = float(os.getenv("BACKGROUND_VOLUME", "0.30"))
TICK_VOLUME = float(os.getenv("TICK_VOLUME", "0.80"))
CORRECT_VOLUME = float(os.getenv("CORRECT_VOLUME", "1.00"))

TTS_VOICE = os.getenv("TTS_VOICE", "en-IN-NeerjaNeural")
TTS_RATE = os.getenv("TTS_RATE", "+0%")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")

BACKGROUND_AUDIO = ASSETS_DIR / "bg_music.mp3"
TICK_AUDIO = ASSETS_DIR / "tick.mp3"
CORRECT_AUDIO = ASSETS_DIR / "correct.mp3"
LOGO_FILE = ASSETS_DIR / "logo.png"

PAGE_URL = os.getenv("PAGE_URL", "https://smartlearninglab-react.pages.dev").strip()
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v23.0").strip()
INSTAGRAM_BUSINESS_ACCOUNT_ID = (os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID") or "").strip()
INSTAGRAM_ACCESS_TOKEN = (os.getenv("INSTAGRAM_ACCESS_TOKEN") or "").strip()
MIXED_QUIZ_FILE = os.getenv(
    "MIXED_QUIZ_FILE",
    "smart_learning_lab_50000_mixed_questions.json",
).strip()

# Keep TTS generation concurrent so a 20-question quiz does not wait for
# 20 network requests one after another.
TTS_CONCURRENCY = max(1, int(os.getenv("TTS_CONCURRENCY", "6")))

# Faster/lighter H.264 encoding for GitHub Actions.
VIDEO_CRF = int(os.getenv("VIDEO_CRF", "30"))
# Kept as a named config value because video_service imports it directly.
VIDEO_PRESET = os.getenv("VIDEO_PRESET", "ultrafast").strip() or "ultrafast"
