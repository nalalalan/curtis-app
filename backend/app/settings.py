from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = Path(os.getenv("CURTIS_RUNTIME_DIR", ROOT_DIR / ".runtime"))
STATE_PATH = Path(os.getenv("CURTIS_STATE_PATH", RUNTIME_DIR / "curtis_state.json"))
MEDIA_DIR = Path(os.getenv("CURTIS_MEDIA_DIR", RUNTIME_DIR / "media"))

SERVICE_NAME = "curtis-media-worker"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")
OPENAI_AUDIO_MODEL = os.getenv("OPENAI_AUDIO_MODEL", "gpt-audio-mini")
OPENAI_PIECE_VERIFY_MODEL = os.getenv("OPENAI_PIECE_VERIFY_MODEL", "gpt-audio-mini")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
YOUTUBE_MAX_RESULTS = int(os.getenv("YOUTUBE_MAX_RESULTS", "1000"))
INSTAGRAM_MAX_RESULTS = int(os.getenv("INSTAGRAM_MAX_RESULTS", "12"))
INSTAGRAM_GRAPH_VERSION = os.getenv("INSTAGRAM_GRAPH_VERSION", "v20.0")
PUBLIC_REFERENCE_MAX_RESULTS = int(os.getenv("CURTIS_PUBLIC_REFERENCE_MAX_RESULTS", "3"))
PUBLIC_REFERENCE_REFRESH_SECONDS = int(
    os.getenv("CURTIS_PUBLIC_REFERENCE_REFRESH_SECONDS", str(7 * 24 * 60 * 60))
)
SCAN_INTERVAL_SECONDS = int(os.getenv("CURTIS_SCAN_INTERVAL_SECONDS", str(60 * 60 * 24)))
MEDIA_SAMPLE_SECONDS = int(os.getenv("CURTIS_MEDIA_SAMPLE_SECONDS", "90"))
MEDIA_SAMPLE_START_SECONDS = int(os.getenv("CURTIS_MEDIA_SAMPLE_START_SECONDS", str(10 * 60)))
MEDIA_PROBE_LIMIT = int(os.getenv("CURTIS_MEDIA_PROBE_LIMIT", "4"))
MEDIA_SAMPLE_WINDOWS_PER_VIDEO = int(os.getenv("CURTIS_MEDIA_SAMPLE_WINDOWS_PER_VIDEO", "4"))
MEDIA_SAMPLE_RETENTION_LIMIT = int(os.getenv("CURTIS_MEDIA_SAMPLE_RETENTION_LIMIT", "10000"))
MODEL_REVIEW_SAMPLE_SECONDS = int(os.getenv("CURTIS_MODEL_REVIEW_SAMPLE_SECONDS", "14"))
MODEL_REVIEW_FRAME_COUNT = int(os.getenv("CURTIS_MODEL_REVIEW_FRAME_COUNT", "4"))
UPLOAD_TOKEN = os.getenv("CURTIS_UPLOAD_TOKEN", "")
REQUIRE_SOURCE_CONFIRMED_PIECE_TITLES = os.getenv(
    "CURTIS_REQUIRE_SOURCE_CONFIRMED_PIECE_TITLES",
    "1",
).strip().lower() not in {"0", "false", "no", "off"}


def env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def token_matches(value: str) -> bool:
    return bool(UPLOAD_TOKEN) and secrets.compare_digest(value, UPLOAD_TOKEN)


def allowed_origins() -> list[str]:
    raw = os.getenv("CURTIS_ALLOWED_ORIGINS", "")
    configured = [item.strip() for item in raw.split(",") if item.strip()]
    defaults = [
        "https://curtis.aolabs.io",
        "https://nalalalan.github.io",
        "https://curtis-app-production.up.railway.app",
        "http://127.0.0.1:4177",
        "http://127.0.0.1:8000",
        "http://localhost:4177",
        "http://localhost:8000",
    ]
    return list(dict.fromkeys(configured + defaults))
