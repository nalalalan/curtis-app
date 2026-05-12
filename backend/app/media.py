from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

from .analyzer import classify_violin_presence
from .settings import (
    MEDIA_DIR,
    MEDIA_PROBE_LIMIT,
    MEDIA_SAMPLE_SECONDS,
    MEDIA_SAMPLE_START_SECONDS,
    MEDIA_SAMPLE_RETENTION_LIMIT,
    MEDIA_SAMPLE_WINDOWS_PER_VIDEO,
)
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
    return sample_windows(item, max_windows=1)[0]


def sample_windows(item: dict[str, Any], max_windows: int = MEDIA_SAMPLE_WINDOWS_PER_VIDEO) -> list[str]:
    duration = item.get("durationSeconds")
    if not isinstance(duration, int) or duration <= MEDIA_SAMPLE_SECONDS + 60:
        return [f"*0-{MEDIA_SAMPLE_SECONDS}"]
    latest_start = max(0, duration - MEDIA_SAMPLE_SECONDS - 30)
    if max_windows > 8:
        starts = list(range(0, latest_start + 1, MEDIA_SAMPLE_SECONDS))
        if not starts or starts[-1] != latest_start:
            starts.append(latest_start)
        return [f"*{start}-{start + MEDIA_SAMPLE_SECONDS}" for start in starts[:max_windows]]
    anchors = [MEDIA_SAMPLE_START_SECONDS]
    anchors.extend([int(duration * fraction) for fraction in (0.25, 0.5, 0.625, 0.75)])
    anchors.append(latest_start)
    if max_windows >= 6:
        anchors.extend([5 * 60, 15 * 60, int(duration * 0.125)])
    starts: list[int] = []
    for raw_start in anchors:
        start = max(0, min(int(raw_start), latest_start))
        if all(abs(start - existing) >= MEDIA_SAMPLE_SECONDS for existing in starts):
            starts.append(start)
        if len(starts) >= max(1, max_windows):
            break
    if not starts:
        starts = [latest_start]
    return [f"*{start}-{start + MEDIA_SAMPLE_SECONDS}" for start in starts]


def sample_id(video_id: str, window: str) -> str:
    start = "0"
    if "*" in window:
        try:
            start = str(int(float(window.split("*", 1)[1].split("-", 1)[0])))
        except (IndexError, TypeError, ValueError):
            start = "0"
    return f"{video_id}-{start}"


def classify_media_error(output: str) -> str:
    lowered = output.lower()
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return "youtube_media_fetch_requires_owner_browser_or_export"
    if "cookies" in lowered:
        return "youtube_media_fetch_needs_cookies"
    if "ffmpeg" in lowered:
        return "ffmpeg_unavailable"
    return "youtube_media_fetch_failed"


def violin_presence_metadata(path: Path) -> dict[str, Any]:
    try:
        return classify_violin_presence(path)
    except Exception as exc:  # pragma: no cover - defensive media boundary
        return {
            "containsViolin": False,
            "violinPresence": "unverified",
            "practiceEvidenceStatus": "needs_violin_verification",
            "violinSamplerVersion": "violin_presence_v1",
            "violinSamplerScore": 0,
            "violinSamplerBlocker": "violin_presence_scan_failed",
            "violinSamplerDetail": str(exc)[:180],
        }


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
    selected = candidates[:limit]
    samples: list[dict[str, Any]] = []
    blockers: list[str] = []
    attempted: list[dict[str, Any]] = []

    for item in selected:
        video_id = str(item["id"])
        for window in sample_windows(item):
            current_id = sample_id(video_id, window)
            attempted.append(
                {
                    "id": current_id,
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "window": window,
                }
            )
            if current_id in existing_ids:
                continue
            output_template = str(MEDIA_DIR / f"{current_id}.%(ext)s")
            args = [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-playlist",
                "--download-sections",
                window,
                "--force-keyframes-at-cuts",
                "-f",
                "bv*[height<=360]+ba/b[height<=360]/worst",
                "-o",
                output_template,
                str(item["url"]),
            ]
            code, output = await run_command(args)
            files = sorted(MEDIA_DIR.glob(f"{current_id}.*"), key=lambda path: path.stat().st_mtime, reverse=True)
            if code == 0 and files:
                media_file = files[0]
                presence = violin_presence_metadata(media_file)
                sample = {
                    "id": current_id,
                    "url": item["url"],
                    "title": item.get("title"),
                    "createdAt": utc_now(),
                    "status": "media_sample_ready",
                    **presence,
                    "path": str(media_file),
                    "sizeBytes": media_file.stat().st_size,
                    "window": window,
                }
                samples.append(sample)
                continue
            blockers.append(classify_media_error(output))

    media_samples = [*samples, *state.get("mediaSamples", [])]
    state["mediaSamples"] = media_samples[:MEDIA_SAMPLE_RETENTION_LIMIT]
    state.setdefault("review", {})["mediaAccess"] = "sample_ready" if samples else "blocked"
    run = {
        "startedAt": utc_now(),
        "status": "media_sample_ready" if samples else "blocked",
        "blockers": list(dict.fromkeys(blockers)),
        "samples": samples,
        "attempted": attempted,
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
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(char for char in video_id if char.isalnum() or char in {"_", "-"})[:80] or "uploaded"
    suffix = source_path.suffix if source_path.suffix else ".media"
    target = MEDIA_DIR / f"{safe_id}-{utc_now().replace(':', '').replace('+', 'Z')}{suffix}"
    shutil.move(str(source_path), target)

    state = load_state()
    presence = violin_presence_metadata(target)
    incoming = metadata or {}
    if presence.get("violinSamplerBlocker") and incoming.get("violinSamplerVersion"):
        presence = {**presence, **incoming}

    sample = {
        "id": safe_id,
        "url": url,
        "title": title or safe_id,
        "createdAt": utc_now(),
        "status": "media_sample_ready",
        **presence,
        "path": str(target),
        "sizeBytes": target.stat().st_size,
        "window": window,
        "source": "owner_upload",
    }
    state["mediaSamples"] = [sample, *state.get("mediaSamples", [])][:MEDIA_SAMPLE_RETENTION_LIMIT]
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
