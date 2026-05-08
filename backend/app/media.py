from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

from .settings import MEDIA_DIR, MEDIA_PROBE_LIMIT, MEDIA_SAMPLE_SECONDS, MEDIA_SAMPLE_START_SECONDS
from .state import load_state, save_state, utc_now
from .study_packets import practice_ledger_videos


def practice_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = state.get("inventory", {})
    ledger = practice_ledger_videos(inventory if isinstance(inventory, dict) else [])
    if ledger:
        return [
            item
            for item in ledger
            if isinstance(item, dict) and item.get("id") and item.get("url")
        ]
    youtube = inventory.get("youtube", []) if isinstance(inventory, dict) else []
    if not isinstance(youtube, list):
        return []
    return [
        item
        for item in youtube
        if isinstance(item, dict) and item.get("practiceCandidate") and item.get("id") and item.get("url")
    ]


def sample_window(item: dict[str, Any]) -> str:
    duration = item.get("durationSeconds")
    start = MEDIA_SAMPLE_START_SECONDS
    if isinstance(duration, int) and duration > MEDIA_SAMPLE_SECONDS + 60:
        start = min(start, max(0, duration - MEDIA_SAMPLE_SECONDS - 30))
    else:
        start = 0
    return f"*{start}-{start + MEDIA_SAMPLE_SECONDS}"


def classify_media_error(output: str) -> str:
    lowered = output.lower()
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return "youtube_media_fetch_requires_owner_browser_or_export"
    if "cookies" in lowered:
        return "youtube_media_fetch_needs_cookies"
    if "ffmpeg" in lowered:
        return "ffmpeg_unavailable"
    return "youtube_media_fetch_failed"


async def run_command(args: list[str], timeout: int = 240) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        stdout, _ = await process.communicate()
        return 124, stdout.decode("utf-8", errors="replace")
    return process.returncode or 0, stdout.decode("utf-8", errors="replace")


async def probe_youtube_media(limit: int = MEDIA_PROBE_LIMIT) -> dict[str, Any]:
    state = load_state()
    candidates = practice_candidates(state)
    if not candidates:
        run = {
            "startedAt": utc_now(),
            "status": "blocked",
            "blockers": ["no_practice_candidate_inventory"],
            "samples": [],
        }
        state["lastMediaRun"] = run
        save_state(state)
        return run

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    existing_ids = {
        sample.get("id")
        for sample in state.get("mediaSamples", [])
        if isinstance(sample, dict) and sample.get("id")
    }
    selected = [item for item in candidates if item.get("id") not in existing_ids][:limit] or candidates[:limit]
    samples: list[dict[str, Any]] = []
    blockers: list[str] = []

    for item in selected:
        video_id = str(item["id"])
        output_template = str(MEDIA_DIR / f"{video_id}.%(ext)s")
        args = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--download-sections",
            sample_window(item),
            "--force-keyframes-at-cuts",
            "-f",
            "bv*[height<=360]+ba/b[height<=360]/worst",
            "-o",
            output_template,
            str(item["url"]),
        ]
        code, output = await run_command(args)
        files = sorted(MEDIA_DIR.glob(f"{video_id}.*"), key=lambda path: path.stat().st_mtime, reverse=True)
        if code == 0 and files:
            media_file = files[0]
            sample = {
                "id": video_id,
                "url": item["url"],
                "title": item.get("title"),
                "createdAt": utc_now(),
                "status": "media_sample_ready",
                "path": str(media_file),
                "sizeBytes": media_file.stat().st_size,
                "window": sample_window(item),
            }
            samples.append(sample)
            continue
        blockers.append(classify_media_error(output))

    media_samples = [*samples, *state.get("mediaSamples", [])]
    state["mediaSamples"] = media_samples[:20]
    state.setdefault("review", {})["mediaAccess"] = "sample_ready" if samples else "blocked"
    run = {
        "startedAt": utc_now(),
        "status": "media_sample_ready" if samples else "blocked",
        "blockers": list(dict.fromkeys(blockers)),
        "samples": samples,
        "attempted": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "url": item.get("url"),
                "window": sample_window(item),
            }
            for item in selected
        ],
    }
    state["lastMediaRun"] = run
    save_state(state)
    return run


def record_uploaded_sample(
    source_path: Path,
    *,
    video_id: str,
    title: str = "",
    url: str = "",
    window: str = "",
) -> dict[str, Any]:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(char for char in video_id if char.isalnum() or char in {"_", "-"})[:80] or "uploaded"
    suffix = source_path.suffix if source_path.suffix else ".media"
    target = MEDIA_DIR / f"{safe_id}-{utc_now().replace(':', '').replace('+', 'Z')}{suffix}"
    shutil.move(str(source_path), target)

    state = load_state()
    sample = {
        "id": safe_id,
        "url": url,
        "title": title or safe_id,
        "createdAt": utc_now(),
        "status": "media_sample_ready",
        "path": str(target),
        "sizeBytes": target.stat().st_size,
        "window": window,
        "source": "owner_upload",
    }
    state["mediaSamples"] = [sample, *state.get("mediaSamples", [])][:20]
    state.setdefault("review", {})["mediaAccess"] = "sample_ready"
    state["lastMediaRun"] = {
        "startedAt": utc_now(),
        "status": "media_sample_ready",
        "blockers": [],
        "samples": [sample],
        "attempted": [],
    }
    save_state(state)
    return sample
