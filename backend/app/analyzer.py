from __future__ import annotations

import math
import re
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from .state import load_state, save_state, utc_now


WINDOW_RE = re.compile(r"\*(\d+)-(\d+)")


def run_process(args: list[str], timeout: int = 120) -> tuple[int, str]:
    completed = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout


def parse_window_start(value: str) -> int:
    match = WINDOW_RE.search(value or "")
    if not match:
        return 0
    return int(match.group(1))


def extract_wav(source: Path, target: Path) -> tuple[bool, str]:
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(target),
        ],
        timeout=180,
    )
    return code == 0 and target.exists() and target.stat().st_size > 44, output


def rms_windows(wav_path: Path, window_seconds: float = 1.0) -> list[dict[str, float]]:
    windows: list[dict[str, float]] = []
    with wave.open(str(wav_path), "rb") as handle:
        frame_rate = handle.getframerate()
        sample_width = handle.getsampwidth()
        if sample_width != 2:
            return windows
        frames_per_window = max(1, int(frame_rate * window_seconds))
        index = 0
        while True:
            frames = handle.readframes(frames_per_window)
            if not frames:
                break
            sample_count = len(frames) // sample_width
            if not sample_count:
                break
            samples = struct.unpack(f"<{sample_count}h", frames)
            mean_square = sum(float(sample) * float(sample) for sample in samples) / sample_count
            rms = math.sqrt(mean_square)
            dbfs = 20 * math.log10(max(rms, 1.0) / 32768.0)
            windows.append({"start": index * window_seconds, "end": (index + 1) * window_seconds, "rms": rms, "dbfs": dbfs})
            index += 1
    return windows


def active_ranges(windows: list[dict[str, float]]) -> list[dict[str, Any]]:
    if not windows:
        return []
    rms_values = sorted(window["rms"] for window in windows)
    midpoint = rms_values[len(rms_values) // 2]
    upper = rms_values[max(0, int(len(rms_values) * 0.75) - 1)]
    threshold = max(280.0, min(midpoint * 0.8, upper * 0.6))
    ranges: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for window in windows:
        is_active = window["rms"] >= threshold
        if is_active and current is None:
            current = {
                "start": window["start"],
                "end": window["end"],
                "peakDbfs": window["dbfs"],
                "meanRms": window["rms"],
                "windows": 1,
            }
        elif is_active and current is not None:
            current["end"] = window["end"]
            current["peakDbfs"] = max(current["peakDbfs"], window["dbfs"])
            current["meanRms"] += window["rms"]
            current["windows"] += 1
        elif current is not None:
            current["meanRms"] = current["meanRms"] / max(1, current["windows"])
            if current["end"] - current["start"] >= 2:
                ranges.append(current)
            current = None

    if current is not None:
        current["meanRms"] = current["meanRms"] / max(1, current["windows"])
        if current["end"] - current["start"] >= 2:
            ranges.append(current)
    return ranges[:8]


def section_key(section: dict[str, Any]) -> str:
    return "|".join(
        [
            str(section.get("sampleId", "")),
            str(section.get("startSeconds", "")),
            str(section.get("endSeconds", "")),
            str(section.get("method", "")),
        ]
    )


def analyze_sample(sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(sample.get("path") or ""))
    if not path.exists():
        return {"status": "blocked", "blocker": "media_sample_missing", "sampleId": sample.get("id")}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        wav_path = Path(temp.name)
    try:
        ok, output = extract_wav(path, wav_path)
        if not ok:
            return {"status": "blocked", "blocker": "audio_extract_failed", "sampleId": sample.get("id"), "detail": output[-500:]}
        windows = rms_windows(wav_path)
        ranges = active_ranges(windows)
    finally:
        wav_path.unlink(missing_ok=True)

    base_start = parse_window_start(str(sample.get("window") or ""))
    sections = []
    for index, item in enumerate(ranges, start=1):
        start = base_start + int(item["start"])
        end = base_start + int(item["end"])
        sections.append(
            {
                "id": f"{sample.get('id', 'sample')}-{start}-{end}",
                "sampleId": sample.get("id"),
                "url": sample.get("url"),
                "title": sample.get("title"),
                "dimension": "media",
                "judgment": "Unjudged",
                "status": "candidate_playing_section",
                "method": "audio_energy",
                "startSeconds": start,
                "endSeconds": end,
                "peakDbfs": round(float(item["peakDbfs"]), 1),
                "meanRms": round(float(item["meanRms"]), 1),
                "note": f"Audio-active section {index}. Musicianship judgment pending.",
                "createdAt": utc_now(),
            }
        )
    return {"status": "sections_scanned", "sampleId": sample.get("id"), "sections": sections}


def analyze_media_samples(limit: int = 3) -> dict[str, Any]:
    state = load_state()
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    analyzed_ids = {
        section.get("sampleId")
        for section in state.get("review", {}).get("notableSections", [])
        if isinstance(section, dict) and section.get("sampleId")
    }
    selected = [sample for sample in samples if sample.get("id") not in analyzed_ids][:limit]
    results = [analyze_sample(sample) for sample in selected]
    new_sections = [
        section
        for result in results
        for section in result.get("sections", [])
        if isinstance(section, dict)
    ]

    review = state.setdefault("review", {})
    existing_sections = [section for section in review.get("notableSections", []) if isinstance(section, dict)]
    by_key = {section_key(section): section for section in existing_sections}
    for section in new_sections:
        by_key[section_key(section)] = section
    sections = list(by_key.values())[:80]

    review["notableSections"] = sections
    if new_sections:
        review["currentWork"] = "Audio/video samples scanned. Musicianship judgment pending."
        review["mediaAccess"] = "sample_ready"
    review["strongestSignal"] = "Unjudged"
    review["weakestRecurringSignal"] = "Unjudged"

    blockers = [result.get("blocker") for result in results if result.get("status") == "blocked" and result.get("blocker")]
    run = {
        "startedAt": utc_now(),
        "status": "sections_scanned" if new_sections else "blocked" if blockers else "no_new_samples",
        "sampleCount": len(selected),
        "sectionCount": len(new_sections),
        "blockers": list(dict.fromkeys(blockers)),
        "results": results,
    }
    state["lastAnalysisRun"] = run
    save_state(state)
    return run
