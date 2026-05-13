from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analyzer import (
    active_ranges,
    extract_wav,
    parse_window_start,
    rms_windows,
    sample_is_violin_positive,
)
from .daily_records import item_matches_keys, video_match_keys, window_bounds
from .settings import MEDIA_SAMPLE_SECONDS
from .state import load_state, save_state, utc_now
from .study_packets import practice_ledger_videos


ACTIVE_PRACTICE_SCAN_VERSION = "active_practice_scan_v1"
ACTIVE_INTERVAL_STATUS = "active_violin"
CHECKED_NO_VIOLIN_STATUS = "checked_no_violin"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha1(body.encode('utf-8')).hexdigest()[:14]}"


def _round_seconds(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0.0)), 3)
    except (TypeError, ValueError):
        return 0.0


def sample_video_id(sample: dict[str, Any]) -> str:
    sample_id = _clean(sample.get("id") or sample.get("sampleId"))
    start = parse_window_start(_clean(sample.get("window") or sample.get("sourceWindow") or ""))
    if start >= 0 and sample_id.endswith(f"-{start}"):
        return sample_id[: -(len(str(start)) + 1)]
    return _clean(sample.get("sourceVideoId") or sample.get("videoId") or sample_id)


def sample_bounds(sample: dict[str, Any]) -> tuple[float, float]:
    start, end = window_bounds(sample)
    if end <= start:
        start = parse_window_start(_clean(sample.get("window") or sample.get("sourceWindow") or ""))
        if start < 0:
            start = 0
        duration = _round_seconds(sample.get("durationSeconds")) or MEDIA_SAMPLE_SECONDS
        end = start + int(duration)
    return float(max(0, start)), float(max(start, end))


def _activity_ranges_for_media(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "media_sample_missing"
    cleanup = False
    wav_path = path
    if path.suffix.lower() != ".wav":
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            wav_path = Path(temp.name)
        cleanup = True
        ok, output = extract_wav(path, wav_path)
        if not ok:
            wav_path.unlink(missing_ok=True)
            return [], f"audio_extract_failed:{output[-180:]}"
    try:
        return active_ranges(rms_windows(wav_path)), ""
    finally:
        if cleanup:
            wav_path.unlink(missing_ok=True)


def active_intervals_from_sample(sample: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sample_id = _clean(sample.get("id") or sample.get("sampleId"))
    source_video_id = sample_video_id(sample)
    sample_start, sample_end = sample_bounds(sample)
    source_url = _clean(sample.get("url") or sample.get("sourceUrl"))
    source_title = _clean(sample.get("title") or sample.get("sourceTitle"))
    base_payload = {
        "sampleId": sample_id,
        "sourceVideoId": source_video_id,
        "sourceUrl": source_url,
        "sourceTitle": source_title,
        "sourceWindow": _clean(sample.get("window") or sample.get("sourceWindow")),
        "sampleStartSeconds": sample_start,
        "sampleEndSeconds": sample_end,
        "detectorVersion": ACTIVE_PRACTICE_SCAN_VERSION,
    }
    if not sample_id:
        return [], {**base_payload, "status": "blocked", "blocker": "sample_id_missing"}
    if not sample_is_violin_positive(sample):
        return [], {
            **base_payload,
            "status": CHECKED_NO_VIOLIN_STATUS,
            "activeIntervalCount": 0,
            "activeSeconds": 0,
            "createdAt": utc_now(),
        }

    path = Path(_clean(sample.get("path")))
    ranges, blocker = _activity_ranges_for_media(path)
    if blocker:
        return [], {
            **base_payload,
            "status": "blocked",
            "blocker": blocker[:220],
            "activeIntervalCount": 0,
            "activeSeconds": 0,
            "createdAt": utc_now(),
        }

    intervals: list[dict[str, Any]] = []
    for index, item in enumerate(ranges, start=1):
        local_start = _round_seconds(item.get("start"))
        local_end = _round_seconds(item.get("end"))
        source_start = max(sample_start, sample_start + local_start)
        source_end = min(sample_end, sample_start + local_end)
        if source_end <= source_start:
            continue
        interval_payload = {
            **base_payload,
            "status": ACTIVE_INTERVAL_STATUS,
            "localStartSeconds": local_start,
            "localEndSeconds": local_end,
            "startSeconds": _round_seconds(source_start),
            "endSeconds": _round_seconds(source_end),
            "durationSeconds": _round_seconds(source_end - source_start),
            "peakDbfs": round(float(item.get("peakDbfs") or 0.0), 1),
            "meanRms": round(float(item.get("meanRms") or 0.0), 1),
            "method": "positive_sample_audio_activity",
            "confidence": "violin_positive_sample_active_audio",
            "intervalIndex": index,
            "id": source_video_id,
            "sourceKey": f"youtube:{source_video_id}" if source_video_id else "",
            "createdAt": utc_now(),
        }
        interval_payload["intervalId"] = _stable_id(
            "active",
            {
                "sampleId": sample_id,
                "startSeconds": interval_payload["startSeconds"],
                "endSeconds": interval_payload["endSeconds"],
                "version": ACTIVE_PRACTICE_SCAN_VERSION,
            },
        )
        intervals.append(interval_payload)

    result = {
        **base_payload,
        "status": ACTIVE_INTERVAL_STATUS if intervals else "no_active_audio_detected",
        "activeIntervalCount": len(intervals),
        "activeSeconds": round(sum(float(item.get("durationSeconds") or 0.0) for item in intervals), 3),
        "createdAt": utc_now(),
    }
    return intervals, result


def _sample_result_key(result: dict[str, Any]) -> str:
    return "|".join(
        [
            _clean(result.get("sampleId")),
            _clean(result.get("sourceWindow")),
            _clean(result.get("detectorVersion")),
        ]
    )


def _pending_windows(
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
    max_queue: int,
) -> list[dict[str, Any]]:
    sampled: set[tuple[str, int]] = set()
    for sample in media_samples:
        if not isinstance(sample, dict):
            continue
        start, _ = window_bounds(sample)
        url = _clean(sample.get("url") or sample.get("sourceUrl"))
        video_id = sample_video_id(sample)
        if url or video_id:
            sampled.add((url or video_id, start))

    queued: list[dict[str, Any]] = []
    for video in practice_ledger_videos(inventory):
        if len(queued) >= max_queue:
            break
        try:
            duration = max(0, int(float(video.get("durationSeconds") or 0)))
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0:
            continue
        url = _clean(video.get("url") or video.get("sourceUrl"))
        video_id = _clean(video.get("id") or video.get("sourceVideoId"))
        key = url or video_id
        latest = max(0, duration - MEDIA_SAMPLE_SECONDS)
        for start in range(0, latest + 1, MEDIA_SAMPLE_SECONDS):
            if len(queued) >= max_queue:
                break
            if (key, start) in sampled:
                continue
            queued.append(
                {
                    "sourceVideoId": video_id,
                    "sourceUrl": url,
                    "sourceTitle": _clean(video.get("title")),
                    "practiceDay": _clean(video.get("practiceDay") or video.get("uploadedDate")),
                    "startSeconds": start,
                    "endSeconds": min(duration, start + MEDIA_SAMPLE_SECONDS),
                    "sampleId": f"{video_id}-{start}" if video_id else "",
                    "status": "pending_media",
                    "method": "low_cost_active_practice_queue",
                }
            )
    return queued


def run_active_practice_scan(max_samples: int = 80, max_queue: int = 250) -> dict[str, Any]:
    state = load_state()
    scan = state.setdefault(
        "activePracticeScan",
        {
            "version": ACTIVE_PRACTICE_SCAN_VERSION,
            "intervals": [],
            "sampleResults": [],
            "pendingWindows": [],
            "runs": [],
        },
    )
    scan["version"] = ACTIVE_PRACTICE_SCAN_VERSION

    media_samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    previous_results = [
        result
        for result in scan.get("sampleResults", [])
        if isinstance(result, dict) and result.get("sampleId")
    ]
    previous_keys = {_sample_result_key(result) for result in previous_results}
    selected = [
        sample
        for sample in media_samples
        if _sample_result_key(
            {
                "sampleId": sample.get("id") or sample.get("sampleId"),
                "sourceWindow": sample.get("window") or sample.get("sourceWindow"),
                "detectorVersion": ACTIVE_PRACTICE_SCAN_VERSION,
            }
        )
        not in previous_keys
    ][: max(0, int(max_samples))]

    new_results: list[dict[str, Any]] = []
    new_intervals: list[dict[str, Any]] = []
    for sample in selected:
        intervals, result = active_intervals_from_sample(sample)
        new_intervals.extend(intervals)
        new_results.append(result)

    replaced_sample_ids = {_clean(result.get("sampleId")) for result in new_results if result.get("sampleId")}
    existing_intervals = [
        item
        for item in scan.get("intervals", [])
        if isinstance(item, dict)
        and _clean(item.get("sampleId")) not in replaced_sample_ids
    ]
    scan["intervals"] = [*new_intervals, *existing_intervals][:10000]

    result_by_key = {_sample_result_key(result): result for result in previous_results}
    for result in new_results:
        result_by_key[_sample_result_key(result)] = result
    scan["sampleResults"] = list(result_by_key.values())[-10000:]
    pending = _pending_windows(
        state.get("inventory", {}) if isinstance(state.get("inventory"), dict) else {},
        media_samples,
        max(0, int(max_queue)),
    )
    scan["pendingWindows"] = pending

    active_seconds = round(sum(float(item.get("durationSeconds") or 0.0) for item in scan["intervals"]), 3)
    run = {
        "startedAt": utc_now(),
        "status": (
            "active_intervals_recorded"
            if new_intervals
            else "samples_checked"
            if new_results
            else "queued"
            if pending
            else "complete"
        ),
        "detectorVersion": ACTIVE_PRACTICE_SCAN_VERSION,
        "selectedSampleCount": len(selected),
        "sampleResultCount": len(scan["sampleResults"]),
        "newActiveIntervalCount": len(new_intervals),
        "activeIntervalCount": len(scan["intervals"]),
        "activePracticeSeconds": active_seconds,
        "checkedNoViolinSampleCount": sum(1 for item in new_results if item.get("status") == CHECKED_NO_VIOLIN_STATUS),
        "blockedSampleCount": sum(1 for item in new_results if item.get("status") == "blocked"),
        "pendingWindowCount": len(pending),
        "pendingWindows": pending[:12],
        "method": (
            "Scans stored local media samples for audio-active intervals only after the sample is violin-positive; "
            "queues remaining strict-ledger windows for later owner media capture."
        ),
    }
    scan["lastRun"] = run
    scan["runs"] = [run, *[item for item in scan.get("runs", []) if isinstance(item, dict)]][:20]
    state["activePracticeScan"] = scan
    save_state(state)
    return run


def active_scan_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    scan = state.get("activePracticeScan") if isinstance(state.get("activePracticeScan"), dict) else {}
    intervals = [item for item in scan.get("intervals", []) if isinstance(item, dict)]
    results = [item for item in scan.get("sampleResults", []) if isinstance(item, dict)]
    pending = [item for item in scan.get("pendingWindows", []) if isinstance(item, dict)]
    status_counts = Counter(str(item.get("status") or "unknown") for item in results)
    return {
        "status": "ready" if intervals or results or pending else "pending",
        "version": scan.get("version") or ACTIVE_PRACTICE_SCAN_VERSION,
        "activeIntervalCount": len(intervals),
        "sampleResultCount": len(results),
        "sampleStatusCounts": dict(status_counts),
        "activeViolinSampleCount": status_counts.get(ACTIVE_INTERVAL_STATUS, 0),
        "checkedNoViolinSampleCount": status_counts.get(CHECKED_NO_VIOLIN_STATUS, 0),
        "blockedSampleCount": status_counts.get("blocked", 0),
        "pendingWindowCount": len(pending),
        "activePracticeSeconds": round(sum(float(item.get("durationSeconds") or 0.0) for item in intervals), 3),
        "lastRun": scan.get("lastRun") if isinstance(scan.get("lastRun"), dict) else None,
    }
