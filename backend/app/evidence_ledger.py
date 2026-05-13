from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from .daily_records import (
    active_seconds_from_sections,
    active_seconds_from_transcriptions,
    is_current_transcription,
    item_has_violin_positive_sample,
    item_matches_keys,
    sample_duration_seconds,
    sample_is_violin_positive,
    video_match_keys,
    violin_positive_sample_ids,
    window_bounds,
)
from .state import utc_now
from .study_packets import duration_seconds_label, practice_ledger_videos


EVIDENCE_CORRECTION_TYPES = {
    "note",
    "rhythm",
    "score",
    "score_note",
    "score_match",
    "match",
    "piece",
    "active_interval",
}
EVIDENCE_CORRECTION_STATUSES = {"accepted", "rejected", "needs_review"}
BENCHMARK_TYPES = {"note", "score", "score_note", "score_match", "match", "active_interval"}


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _note_pitch_class(value: Any) -> str:
    note = _clean(value).upper()
    if not note:
        return ""
    if len(note) >= 2 and note[1] in {"#", "B"}:
        return note[:2]
    return note[:1]


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha1(body.encode('utf-8')).hexdigest()[:14]}"


def _interval_from_item(item: dict[str, Any], fallback_duration: int = 0) -> tuple[int, int]:
    start, end = window_bounds(item)
    if end <= start and fallback_duration:
        start, end = 0, fallback_duration
    return max(0, start), max(0, end)


def _bounded_interval(item: dict[str, Any], video_seconds: int) -> tuple[int, int]:
    start, end = _interval_from_item(item, sample_duration_seconds(item))
    if video_seconds:
        start = min(start, video_seconds)
        end = min(end, video_seconds)
    if end <= start:
        return 0, 0
    return start, end


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    valid = sorted((start, end) for start, end in intervals if end > start)
    if not valid:
        return []
    merged: list[tuple[int, int]] = [valid[0]]
    for start, end in valid[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def interval_seconds(intervals: list[tuple[int, int]]) -> int:
    return sum(end - start for start, end in merge_intervals(intervals))


def _coverage_status(checked: int, candidate: int, active: int, uploaded: int) -> str:
    if not uploaded:
        return "duration_missing"
    if not checked:
        return "pending_media"
    if active:
        return "active_measured"
    if candidate:
        return "violin_candidate_unmeasured"
    return "checked_no_violin"


def _coverage_percent(checked: int, uploaded: int) -> float:
    if not uploaded:
        return 0.0
    return round(min(1.0, checked / uploaded), 4)


def build_active_practice_coverage(
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    active_practice_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = practice_ledger_videos(inventory)
    scan = active_practice_scan or {}
    scan_intervals = [
        item
        for item in scan.get("intervals", [])
        if isinstance(item, dict) and item.get("status") == "active_violin"
    ]
    scan_results = [item for item in scan.get("sampleResults", []) if isinstance(item, dict)]
    pending_windows = [item for item in scan.get("pendingWindows", []) if isinstance(item, dict)]
    by_day: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "practiceDay": "",
            "videoCount": 0,
            "uploadedVideoSeconds": 0,
            "checkedVideoSeconds": 0,
            "activePracticeSeconds": 0,
            "activeCandidateSeconds": 0,
            "activeScanSeconds": 0,
            "activeScanIntervalCount": 0,
            "unmeasuredVideoSeconds": 0,
            "videos": [],
        }
    )
    video_rows: list[dict[str, Any]] = []
    for video in ledger:
        keys = video_match_keys(video)
        video_seconds = _safe_int(video.get("durationSeconds"))
        samples = [sample for sample in media_samples if item_matches_keys(sample, keys)]
        positive_samples = [sample for sample in samples if sample_is_violin_positive(sample)]
        positive_sample_ids = violin_positive_sample_ids(positive_samples)
        active_scan_items = [item for item in scan_intervals if item_matches_keys(item, keys)]
        active_scan_intervals = [_bounded_interval(item, video_seconds) for item in active_scan_items]
        checked_intervals = [
            *[_bounded_interval(sample, video_seconds) for sample in samples],
            *active_scan_intervals,
        ]
        candidate_intervals = [_bounded_interval(sample, video_seconds) for sample in positive_samples]
        checked_seconds = min(video_seconds, interval_seconds(checked_intervals)) if video_seconds else interval_seconds(checked_intervals)
        scan_active_seconds = min(video_seconds, interval_seconds(active_scan_intervals)) if video_seconds else interval_seconds(active_scan_intervals)
        candidate_seconds = min(video_seconds, interval_seconds([*candidate_intervals, *active_scan_intervals])) if video_seconds else interval_seconds([*candidate_intervals, *active_scan_intervals])
        video_transcriptions = [
            item
            for item in transcriptions
            if item_matches_keys(item, keys)
            and is_current_transcription(item)
            and (
                item_has_violin_positive_sample(item, positive_sample_ids)
                or not positive_sample_ids
            )
        ]
        video_sections = [
            section
            for section in sections
            if item_matches_keys(section, keys)
            or item_has_violin_positive_sample(section, positive_sample_ids)
        ]
        note_active = active_seconds_from_transcriptions(video_transcriptions)
        section_active = active_seconds_from_sections(video_sections)
        active_seconds = min(video_seconds, max(note_active, section_active, scan_active_seconds)) if video_seconds else max(note_active, section_active, scan_active_seconds)
        unmeasured_seconds = max(0, video_seconds - checked_seconds)
        status = _coverage_status(checked_seconds, candidate_seconds, active_seconds, video_seconds)
        row = {
            "videoId": _clean(video.get("id")),
            "sourceKey": _clean(video.get("sourceKey")),
            "title": _clean(video.get("title")) or "Practice video",
            "url": _clean(video.get("url")),
            "practiceDay": _clean(video.get("practiceDay") or video.get("uploadedDate")),
            "uploadedAt": _clean(video.get("publishedAt")),
            "uploadedVideoSeconds": video_seconds,
            "uploadedVideoLabel": duration_seconds_label(video_seconds),
            "checkedVideoSeconds": checked_seconds,
            "checkedVideoLabel": duration_seconds_label(checked_seconds) if checked_seconds else "",
            "activePracticeSeconds": active_seconds,
            "activePracticeLabel": duration_seconds_label(active_seconds) if active_seconds else "",
            "activeCandidateSeconds": candidate_seconds,
            "activeCandidateLabel": duration_seconds_label(candidate_seconds) if candidate_seconds else "",
            "activeScanSeconds": scan_active_seconds,
            "activeScanLabel": duration_seconds_label(scan_active_seconds) if scan_active_seconds else "",
            "activeScanIntervalCount": len(active_scan_items),
            "unmeasuredVideoSeconds": unmeasured_seconds,
            "unmeasuredVideoLabel": duration_seconds_label(unmeasured_seconds) if unmeasured_seconds else "",
            "checkedPercent": _coverage_percent(checked_seconds, video_seconds),
            "sampleCount": len(samples),
            "violinPositiveSampleCount": len(positive_samples),
            "transcriptionWindowCount": len(video_transcriptions),
            "sectionCount": len(video_sections),
            "status": status,
            "method": "checked windows are sampled source media; active practice time is measured from playing evidence only",
        }
        video_rows.append(row)
        day_key = row["practiceDay"]
        if day_key:
            day = by_day[day_key]
            day["practiceDay"] = day_key
            day["videoCount"] += 1
            day["uploadedVideoSeconds"] += video_seconds
            day["checkedVideoSeconds"] += checked_seconds
            day["activePracticeSeconds"] += active_seconds
            day["activeCandidateSeconds"] += candidate_seconds
            day["activeScanSeconds"] += scan_active_seconds
            day["activeScanIntervalCount"] += len(active_scan_items)
            day["unmeasuredVideoSeconds"] += unmeasured_seconds
            day["videos"].append(row)

    day_rows = sorted(by_day.values(), key=lambda item: item["practiceDay"])
    for day in day_rows:
        uploaded = _safe_int(day.get("uploadedVideoSeconds"))
        checked = _safe_int(day.get("checkedVideoSeconds"))
        active = _safe_int(day.get("activePracticeSeconds"))
        candidate = _safe_int(day.get("activeCandidateSeconds"))
        active_scan = _safe_int(day.get("activeScanSeconds"))
        unmeasured = _safe_int(day.get("unmeasuredVideoSeconds"))
        day["uploadedVideoLabel"] = duration_seconds_label(uploaded)
        day["checkedVideoLabel"] = duration_seconds_label(checked) if checked else ""
        day["activePracticeLabel"] = duration_seconds_label(active) if active else ""
        day["activeCandidateLabel"] = duration_seconds_label(candidate) if candidate else ""
        day["activeScanLabel"] = duration_seconds_label(active_scan) if active_scan else ""
        day["unmeasuredVideoLabel"] = duration_seconds_label(unmeasured) if unmeasured else ""
        day["checkedPercent"] = _coverage_percent(checked, uploaded)
        day["status"] = _coverage_status(checked, candidate, active, uploaded)

    total_uploaded = sum(_safe_int(video.get("uploadedVideoSeconds")) for video in video_rows)
    total_checked = sum(_safe_int(video.get("checkedVideoSeconds")) for video in video_rows)
    total_active = sum(_safe_int(video.get("activePracticeSeconds")) for video in video_rows)
    total_candidate = sum(_safe_int(video.get("activeCandidateSeconds")) for video in video_rows)
    unmeasured = max(0, total_uploaded - total_checked)
    active_ratio = (total_active / total_checked) if total_checked else 0.0
    estimated_total = (
        int(round(total_active + (unmeasured * active_ratio)))
        if total_checked and unmeasured
        else total_active
    )
    status_counts = Counter(str(video.get("status") or "pending") for video in video_rows)
    return {
        "status": "ready" if video_rows else "pending",
        "ledgerVideoCount": len(video_rows),
        "practiceDayCount": len(day_rows),
        "uploadedVideoSeconds": total_uploaded,
        "uploadedVideoLabel": duration_seconds_label(total_uploaded),
        "checkedVideoSeconds": total_checked,
        "checkedVideoLabel": duration_seconds_label(total_checked) if total_checked else "",
        "activePracticeSeconds": total_active,
        "activePracticeLabel": duration_seconds_label(total_active) if total_active else "",
        "activeCandidateSeconds": total_candidate,
        "activeCandidateLabel": duration_seconds_label(total_candidate) if total_candidate else "",
        "unmeasuredVideoSeconds": unmeasured,
        "unmeasuredVideoLabel": duration_seconds_label(unmeasured) if unmeasured else "",
        "coveragePercent": _coverage_percent(total_checked, total_uploaded),
        "estimatedTotalPracticeSeconds": estimated_total,
        "estimatedTotalPracticeLabel": duration_seconds_label(estimated_total) if estimated_total else "",
        "estimatedPracticeRatio": round(active_ratio, 4) if active_ratio else 0.0,
        "measurementStatus": "complete" if total_uploaded and not unmeasured else "partial" if total_uploaded else "pending",
        "estimateStatus": "estimated_from_checked_windows" if total_checked and unmeasured else "measured" if total_uploaded else "pending",
        "statusCounts": dict(status_counts),
        "activePracticeScan": {
            "status": "ready" if scan_intervals or scan_results or pending_windows else "pending",
            "version": scan.get("version") or "",
            "activeIntervalCount": len(scan_intervals),
            "sampleResultCount": len(scan_results),
            "pendingWindowCount": len(pending_windows),
            "lastRun": scan.get("lastRun") if isinstance(scan.get("lastRun"), dict) else None,
        },
        "days": day_rows,
        "videos": video_rows,
        "method": "practice time is measured from violin-playing intervals; checked video includes every sampled window, including non-playing windows",
        "limit": "This layer is a coverage ledger. It does not make a transcription or score match accepted.",
    }


def normalize_evidence_correction(raw: dict[str, Any]) -> dict[str, Any]:
    correction_type = _clean(raw.get("type") or raw.get("category") or "match").lower()
    if correction_type not in EVIDENCE_CORRECTION_TYPES:
        raise ValueError("Unsupported correction type.")
    status = _clean(raw.get("status") or "rejected").lower()
    if status not in EVIDENCE_CORRECTION_STATUSES:
        raise ValueError("Unsupported correction status.")
    observed_note = _clean(raw.get("observedNote") or raw.get("transcribedNote"))
    displayed_score_note = _clean(raw.get("displayedScoreNote") or raw.get("scoreNote"))
    corrected_score_note = _clean(raw.get("correctedScoreNote") or raw.get("acceptedScoreNote"))
    if status == "accepted" and correction_type in {"score", "score_note", "score_match", "match"}:
        accepted_score = corrected_score_note or displayed_score_note
        if observed_note and accepted_score and _note_pitch_class(observed_note) != _note_pitch_class(accepted_score):
            raise ValueError("Accepted score evidence cannot mismatch the observed note.")
    start_seconds = _safe_float(raw.get("startSeconds") or raw.get("sourceStartSeconds"))
    end_seconds = _safe_float(raw.get("endSeconds") or raw.get("sourceEndSeconds"))
    correction = {
        "type": correction_type,
        "status": status,
        "sourceVideoId": _clean(raw.get("sourceVideoId") or raw.get("videoId")),
        "sourceUrl": _clean(raw.get("sourceUrl") or raw.get("url")),
        "sourceTitle": _clean(raw.get("sourceTitle") or raw.get("title")),
        "practiceDay": _clean(raw.get("practiceDay")),
        "sampleId": _clean(raw.get("sampleId")),
        "startSeconds": round(start_seconds, 3),
        "endSeconds": round(end_seconds, 3),
        "observedNote": observed_note,
        "displayedScoreNote": displayed_score_note,
        "correctedScoreNote": corrected_score_note,
        "pieceTitle": _clean(raw.get("pieceTitle")),
        "scoreSource": _clean(raw.get("scoreSource")),
        "scoreLocation": _clean(raw.get("scoreLocation")),
        "reason": _clean(raw.get("reason") or raw.get("note")),
        "benchmark": bool(raw.get("benchmark")),
        "createdAt": _clean(raw.get("createdAt")) or utc_now(),
    }
    correction["correctionId"] = _clean(raw.get("correctionId")) or _stable_id("correction", correction)
    return correction


def correction_regression_key(correction: dict[str, Any]) -> str:
    parts = [
        _clean(correction.get("type")),
        _clean(correction.get("sourceVideoId") or correction.get("sourceUrl") or correction.get("sampleId")),
        _clean(correction.get("observedNote")),
        _clean(correction.get("displayedScoreNote")),
        _clean(correction.get("correctedScoreNote")),
        _clean(correction.get("scoreLocation")),
    ]
    return "|".join(part for part in parts if part)


def benchmark_fixture_for_correction(correction: dict[str, Any]) -> dict[str, Any]:
    regression_key = correction_regression_key(correction)
    fixture = {
        "fixtureId": _stable_id("benchmark", {"correctionId": correction.get("correctionId"), "regressionKey": regression_key}),
        "correctionId": correction.get("correctionId"),
        "type": correction.get("type"),
        "status": correction.get("status"),
        "sourceVideoId": correction.get("sourceVideoId"),
        "sourceUrl": correction.get("sourceUrl"),
        "sourceTitle": correction.get("sourceTitle"),
        "practiceDay": correction.get("practiceDay"),
        "sampleId": correction.get("sampleId"),
        "startSeconds": correction.get("startSeconds"),
        "endSeconds": correction.get("endSeconds"),
        "expectedObservedNote": correction.get("observedNote"),
        "forbiddenDisplayedScoreNote": correction.get("displayedScoreNote")
        if correction.get("status") == "rejected"
        else "",
        "expectedScoreNote": correction.get("correctedScoreNote") or correction.get("displayedScoreNote"),
        "scoreLocation": correction.get("scoreLocation"),
        "regressionKey": regression_key,
        "createdAt": correction.get("createdAt") or utc_now(),
        "limit": "Fixture protects accepted evidence gates; it is not a solved long-phrase transcription.",
    }
    return fixture


def should_create_benchmark(correction: dict[str, Any]) -> bool:
    if correction.get("type") not in BENCHMARK_TYPES:
        return False
    if correction.get("benchmark"):
        return True
    return correction.get("status") == "rejected" and correction.get("type") in {"score", "score_note", "score_match", "match"}


def record_evidence_correction(state: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    correction = normalize_evidence_correction(raw)
    corrections = [item for item in state.get("evidenceCorrections", []) if isinstance(item, dict)]
    corrections = [item for item in corrections if item.get("correctionId") != correction["correctionId"]]
    state["evidenceCorrections"] = [correction, *corrections][:500]
    benchmark = {}
    if should_create_benchmark(correction):
        benchmark = benchmark_fixture_for_correction(correction)
        fixtures = [item for item in state.get("transcriptionBenchmarks", []) if isinstance(item, dict)]
        existing_keys = {str(item.get("regressionKey") or "") for item in fixtures}
        if benchmark["regressionKey"] not in existing_keys:
            state["transcriptionBenchmarks"] = [benchmark, *fixtures][:500]
        else:
            state["transcriptionBenchmarks"] = fixtures
    state["lastEvidenceCorrection"] = {
        "correctionId": correction["correctionId"],
        "type": correction["type"],
        "status": correction["status"],
        "benchmarkCreated": bool(benchmark),
        "createdAt": correction["createdAt"],
    }
    return {"correction": correction, "benchmark": benchmark}


def build_evidence_progress(state: dict[str, Any]) -> dict[str, Any]:
    corrections = [item for item in state.get("evidenceCorrections", []) if isinstance(item, dict)]
    benchmarks = [item for item in state.get("transcriptionBenchmarks", []) if isinstance(item, dict)]
    by_type = Counter(str(item.get("type") or "unknown") for item in corrections)
    by_status = Counter(str(item.get("status") or "unknown") for item in corrections)
    rejected_score = [
        item
        for item in corrections
        if item.get("status") == "rejected"
        and item.get("type") in {"score", "score_note", "score_match", "match"}
    ]
    wrong_score_note = [
        item
        for item in rejected_score
        if _note_pitch_class(item.get("observedNote"))
        and _note_pitch_class(item.get("displayedScoreNote"))
        and _note_pitch_class(item.get("observedNote")) != _note_pitch_class(item.get("displayedScoreNote"))
    ]
    return {
        "status": "ready" if corrections or benchmarks else "pending",
        "correctionCount": len(corrections),
        "benchmarkCount": len(benchmarks),
        "correctionsByType": dict(by_type),
        "correctionsByStatus": dict(by_status),
        "rejectedScoreMatchCount": len(rejected_score),
        "wrongScoreNoteRegressionCount": len(wrong_score_note),
        "acceptedEvidenceCorrectionCount": by_status.get("accepted", 0),
        "needsReviewCorrectionCount": by_status.get("needs_review", 0),
        "lastCorrectionAt": corrections[0].get("createdAt") if corrections else "",
        "regressionRules": [
            "accepted score evidence cannot mismatch the observed note",
            "rejected score-note crops become benchmark fixtures",
            "coverage ledgers do not make transcription or score matches accepted",
        ],
        "recentCorrections": corrections[:10],
        "recentBenchmarks": benchmarks[:10],
    }
