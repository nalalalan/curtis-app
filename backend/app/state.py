from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import STATE_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_STATE: dict[str, Any] = {
    "sources": {
        "youtube": "",
        "instagram": "",
        "scanScope": "Latest public posts",
        "scanCadence": "Run now",
    },
    "inventory": {
        "youtube": [],
        "instagram": [],
    },
    "review": {
        "reviewedVideoCount": 0,
        "notableSections": [],
        "currentWork": "No processed video sections.",
        "strongestSignal": "Unjudged",
        "weakestRecurringSignal": "Unjudged",
    },
    "auth": {
        "youtube": {
            "connected": False,
            "channelTitle": "",
            "connectedAt": "",
            "scope": "",
        },
    },
    "runs": [],
    "lastScan": None,
    "evidenceCorrections": [],
    "transcriptionBenchmarks": [],
    "truthWorkbench": {
        "version": "truth_workbench_v1",
        "items": [],
    },
    "goldReview": {
        "version": "gold_review_v1",
        "items": [],
    },
    "activePracticeScan": {
        "version": "active_practice_scan_v1",
        "intervals": [],
        "sampleResults": [],
        "pendingWindows": [],
        "runs": [],
    },
}


def deep_merge(default: Any, value: Any) -> Any:
    if isinstance(default, dict) and isinstance(value, dict):
        merged = copy.deepcopy(default)
        for key, item in value.items():
            merged[key] = deep_merge(merged.get(key), item)
        return merged
    if isinstance(default, list) and not isinstance(value, list):
        return copy.deepcopy(default)
    return copy.deepcopy(value) if value is not None else copy.deepcopy(default)


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        if not path.exists():
            return copy.deepcopy(DEFAULT_STATE)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return deep_merge(DEFAULT_STATE, raw)
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_STATE)


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def append_run(state: dict[str, Any], run: dict[str, Any], keep: int = 20) -> None:
    runs = [run, *state.get("runs", [])]
    state["runs"] = runs[:keep]
    state["lastScan"] = run
