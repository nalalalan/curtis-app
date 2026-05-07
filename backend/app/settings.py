from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = Path(os.getenv("CURTIS_RUNTIME_DIR", ROOT_DIR / ".runtime"))
STATE_PATH = Path(os.getenv("CURTIS_STATE_PATH", RUNTIME_DIR / "curtis_state.json"))

SERVICE_NAME = "curtis-media-worker"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "xhigh")
YOUTUBE_MAX_RESULTS = int(os.getenv("YOUTUBE_MAX_RESULTS", "12"))
INSTAGRAM_MAX_RESULTS = int(os.getenv("INSTAGRAM_MAX_RESULTS", "12"))
INSTAGRAM_GRAPH_VERSION = os.getenv("INSTAGRAM_GRAPH_VERSION", "v20.0")
SCAN_INTERVAL_SECONDS = int(os.getenv("CURTIS_SCAN_INTERVAL_SECONDS", str(60 * 60 * 24)))


def env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


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
