from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from .evidence_ledger import build_truth_progress, record_truth_item
from .long_phrase_truth import note_midi_sequence, note_midi_value
from .state import utc_now


GOLD_REVIEW_VERSION = "gold_review_v1"
GOLD_REVIEW_STATUSES = {"pending_review", "accepted_truth", "rejected_mismatch"}
GOLD_REVIEW_TYPES = {"audio_phrase", "score_phrase", "audio_score_match", "practice_window"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha1(body.encode('utf-8')).hexdigest()[:14]}"


def _note_name(note: Any) -> str:
    if isinstance(note, dict):
        return _clean(note.get("note"))
    return _clean(note)


def _clean_note_names(value: Any) -> list[str]:
    if isinstance(value, list):
        names = [_note_name(item) for item in value]
    else:
        names = _clean(value).replace(",", " ").split()
    return [name for name in names if name]


def _note_dicts(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        if not _clean(item.get("note")):
            continue
        out.append(item)
    return out


def _all_audio_agreed(notes: list[dict[str, Any]]) -> bool:
    if not notes:
        return False
    return all(note.get("audioAgreement") is True for note in notes)


def _pitch_class_count(notes: list[dict[str, Any]]) -> int:
    values = set()
    for note in notes:
        midi = note_midi_value(note)
        if midi is not None:
            values.add(midi % 12)
        elif note.get("pitchClass"):
            values.add(str(note.get("pitchClass")))
    return len(values)


def best_review_note_slice(notes: list[dict[str, Any]], *, min_notes: int = 5, max_notes: int = 12) -> list[dict[str, Any]]:
    clean_notes = [note for note in notes if _clean(note.get("note")) and note_midi_value(note) is not None]
    if not clean_notes:
        return []
    if len(clean_notes) <= max_notes:
        return clean_notes if len(clean_notes) >= min_notes else clean_notes
    best: tuple[float, int, int] = (-1.0, 0, min_notes)
    search_limit = min(len(clean_notes), 96)
    for start in range(0, max(1, search_limit - min_notes + 1)):
        for length in range(min_notes, min(max_notes, search_limit - start) + 1):
            window = clean_notes[start : start + length]
            distinct = _pitch_class_count(window)
            audio_agreed = sum(1 for note in window if note.get("audioAgreement") is True)
            spectral = sum(1 for note in window if "spectral_onset" in (note.get("agreementSources") or []))
            repeated_penalty = max(0, length - distinct - 3)
            if start > 0 and note_midi_value(clean_notes[start - 1]) == note_midi_value(window[0]):
                repeated_penalty += 2
            confidence = sum(float(note.get("confidence") or 0.0) for note in window) / max(1, len(window))
            score = (distinct * 8) + (audio_agreed * 2) + spectral + confidence - repeated_penalty
            if score > best[0]:
                best = (score, start, length)
    _, start, length = best
    return clean_notes[start : start + length]


def _clip_from_series(series: dict[str, Any], notes: list[dict[str, Any]]) -> dict[str, Any]:
    sample_id = _clean(series.get("sampleId"))
    source_url = _clean(series.get("sourceUrl"))
    source_title = _clean(series.get("sourceTitle"))
    series_abs = _safe_float(series.get("startSeconds"))
    series_local = _safe_float(series.get("localStartSeconds"))
    if notes:
        local_start = max(0.0, _safe_float(notes[0].get("startSeconds")) - 0.08)
        local_end = max(local_start + 0.25, _safe_float(notes[-1].get("endSeconds")) + 0.15)
    else:
        local_start = _safe_float(series.get("localStartSeconds"))
        local_end = _safe_float(series.get("localEndSeconds"))
    absolute_start = max(0.0, series_abs + local_start - series_local)
    absolute_end = max(absolute_start, series_abs + local_end - series_local)
    media_url = f"/api/curtis/media/sample/{sample_id}" if sample_id else ""
    return {
        "type": "gold_review_window",
        "label": "review",
        "url": source_url,
        "sourceUrl": source_url,
        "sourceTitle": source_title,
        "sampleId": sample_id,
        "mediaUrl": media_url,
        "audioUrl": f"{media_url}/clip?start={local_start:.3f}&end={local_end:.3f}" if media_url and local_end > local_start else "",
        "startSeconds": round(absolute_start, 3),
        "endSeconds": round(absolute_end, 3),
        "localStartSeconds": round(local_start, 3),
        "localEndSeconds": round(local_end, 3),
        "durationSeconds": round(max(0.0, absolute_end - absolute_start), 3),
    }


def _candidate_id(payload: dict[str, Any]) -> str:
    return _stable_id(
        "gold",
        {
            "practiceDay": payload.get("practiceDay"),
            "sampleId": payload.get("sampleId"),
            "startSeconds": payload.get("startSeconds"),
            "endSeconds": payload.get("endSeconds"),
            "detectedNotes": payload.get("detectedNotes"),
            "pieceTitle": payload.get("pieceTitle"),
            "reviewKind": payload.get("reviewKind"),
        },
    )


def _candidate_from_series(record: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    notes = best_review_note_slice(_note_dicts(series.get("notes")))
    note_names = _clean_note_names(notes)
    if len(note_names) < 3:
        return {}
    clip = _clip_from_series(series, notes)
    payload = {
        "reviewKind": "audio_phrase_candidate",
        "reviewType": "audio_phrase",
        "practiceDay": _clean(record.get("practiceDay")),
        "pieceTitle": _clean((record.get("pieces") or [{}])[0].get("title") if isinstance(record.get("pieces"), list) and record.get("pieces") else ""),
        "sourceTitle": _clean(series.get("sourceTitle")),
        "sourceUrl": _clean(series.get("sourceUrl")),
        "sampleId": _clean(series.get("sampleId")),
        "startSeconds": clip["startSeconds"],
        "endSeconds": clip["endSeconds"],
        "localStartSeconds": clip["localStartSeconds"],
        "localEndSeconds": clip["localEndSeconds"],
        "detectedNotes": note_names,
        "detectedMidiSequence": note_midi_sequence(notes),
        "detectedNoteCount": len(note_names),
        "sourceDetectedNoteCount": int(series.get("noteCount") or len(_note_dicts(series.get("notes")))),
        "audioAgreementCount": sum(1 for note in notes if note.get("audioAgreement") is True),
        "spectralAgreementCount": sum(1 for note in notes if "spectral_onset" in (note.get("agreementSources") or [])),
        "audioAgreed": _all_audio_agreed(notes),
        "scoreNotes": [],
        "scoreLocation": "",
        "clip": clip,
        "defaultStatus": "pending_review",
        "acceptanceRule": "Audio phrase labels become gold audio truth. They do not become score evidence unless exact score notes and score location are added.",
    }
    payload["reviewItemId"] = _candidate_id(payload)
    return payload


def _candidate_from_group(record: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    transcription = group.get("transcription") if isinstance(group.get("transcription"), dict) else {}
    notes = best_review_note_slice(_note_dicts(transcription.get("notes")))
    note_names = _clean_note_names(notes)
    if len(note_names) < 3:
        return {}
    clip = group.get("clip") if isinstance(group.get("clip"), dict) else _clip_from_series(transcription, notes)
    score = group.get("score") if isinstance(group.get("score"), dict) else {}
    score_notes = _clean_note_names(
        group.get("sourceScoreExactSequence")
        or group.get("visibleScoreExactNoteSequence")
        or score.get("visibleScoreExactNoteSequence")
        or score.get("scoreNotes")
    )
    payload = {
        "reviewKind": "score_phrase_candidate" if score_notes else "reference_phrase_candidate",
        "reviewType": "score_phrase" if score_notes else "audio_phrase",
        "practiceDay": _clean(record.get("practiceDay")),
        "pieceTitle": _clean(group.get("pieceTitle") or ((record.get("pieces") or [{}])[0].get("title") if isinstance(record.get("pieces"), list) and record.get("pieces") else "")),
        "sourceTitle": _clean(transcription.get("sourceTitle") or clip.get("sourceTitle")),
        "sourceUrl": _clean(transcription.get("sourceUrl") or clip.get("sourceUrl") or clip.get("url")),
        "sampleId": _clean(transcription.get("sampleId") or clip.get("sampleId")),
        "startSeconds": _safe_float(clip.get("startSeconds")),
        "endSeconds": _safe_float(clip.get("endSeconds")),
        "localStartSeconds": _safe_float(clip.get("localStartSeconds")),
        "localEndSeconds": _safe_float(clip.get("localEndSeconds")),
        "detectedNotes": note_names,
        "detectedMidiSequence": note_midi_sequence(notes),
        "detectedNoteCount": len(note_names),
        "matchedNoteRun": int(group.get("matchedNoteRun") or 0),
        "audioAgreementCount": sum(1 for note in notes if note.get("audioAgreement") is True),
        "spectralAgreementCount": sum(1 for note in notes if "spectral_onset" in (note.get("agreementSources") or [])),
        "audioAgreed": _all_audio_agreed(notes),
        "scoreNotes": score_notes,
        "scoreLocation": _clean(group.get("scoreLocation") or group.get("scoreSequenceLabel") or score.get("label")),
        "scoreStatus": _clean(group.get("sourceScoreCheckStatus") or group.get("scoreSnippetStatus") or score.get("status")),
        "clip": clip,
        "defaultStatus": "pending_review",
        "acceptanceRule": "Score phrase acceptance requires exact audio-note and score-note MIDI agreement plus score location.",
    }
    payload["reviewItemId"] = _candidate_id(payload)
    return payload


def _queue_candidates(daily_records: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in daily_records.get("records", []) if isinstance(daily_records.get("records"), list) else []:
        if not isinstance(record, dict):
            continue
        for group in record.get("candidateMatchGroups", []) if isinstance(record.get("candidateMatchGroups"), list) else []:
            candidate = _candidate_from_group(record, group)
            if candidate:
                candidates.append(candidate)
        transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
        for series in transcription.get("detectedSeries", []) if isinstance(transcription.get("detectedSeries"), list) else []:
            candidate = _candidate_from_series(record, series)
            if candidate:
                candidates.append(candidate)
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        unique.setdefault(str(candidate.get("reviewItemId") or ""), candidate)
    return list(unique.values())


def normalize_gold_review_item(raw: dict[str, Any]) -> dict[str, Any]:
    status = _clean(raw.get("status") or "pending_review").lower()
    if status not in GOLD_REVIEW_STATUSES:
        raise ValueError("Unsupported gold review status.")
    item_type = _clean(raw.get("type") or raw.get("reviewType") or "audio_phrase").lower()
    if item_type not in GOLD_REVIEW_TYPES:
        raise ValueError("Unsupported gold review type.")
    detected_notes = _clean_note_names(raw.get("detectedNotes"))
    accepted_notes = _clean_note_names(raw.get("acceptedNotes") or raw.get("correctedNotes"))
    score_notes = _clean_note_names(raw.get("scoreNotes") or raw.get("sourceScoreNotes"))
    if status == "accepted_truth" and not accepted_notes:
        accepted_notes = detected_notes
    if status == "accepted_truth" and not accepted_notes:
        raise ValueError("Accepted gold review items require accepted notes.")
    if item_type in {"score_phrase", "audio_score_match"} and status == "accepted_truth" and not score_notes:
        raise ValueError("Accepted score phrase labels require score notes.")
    item = {
        "reviewItemId": _clean(raw.get("reviewItemId") or raw.get("itemId")),
        "type": item_type,
        "status": status,
        "practiceDay": _clean(raw.get("practiceDay")),
        "sampleId": _clean(raw.get("sampleId")),
        "sourceVideoId": _clean(raw.get("sourceVideoId") or raw.get("videoId")),
        "sourceUrl": _clean(raw.get("sourceUrl")),
        "sourceTitle": _clean(raw.get("sourceTitle")),
        "startSeconds": round(_safe_float(raw.get("startSeconds")), 3),
        "endSeconds": round(_safe_float(raw.get("endSeconds")), 3),
        "pieceTitle": _clean(raw.get("pieceTitle")),
        "scoreSource": _clean(raw.get("scoreSource")),
        "scoreAssetId": _clean(raw.get("scoreAssetId")),
        "scoreLocation": _clean(raw.get("scoreLocation")),
        "scoreImageUrl": _clean(raw.get("scoreImageUrl")),
        "detectedNotes": detected_notes,
        "acceptedNotes": accepted_notes,
        "scoreNotes": score_notes,
        "reason": _clean(raw.get("reason") or raw.get("note")),
        "createdAt": _clean(raw.get("createdAt")) or utc_now(),
        "reviewVersion": GOLD_REVIEW_VERSION,
    }
    if not item["reviewItemId"]:
        item["reviewItemId"] = _stable_id("gold", item)
    return item


def record_gold_review_item(state: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    item = normalize_gold_review_item(raw)
    review = state.get("goldReview") if isinstance(state.get("goldReview"), dict) else {}
    items = [entry for entry in review.get("items", []) if isinstance(entry, dict)]
    items = [entry for entry in items if entry.get("reviewItemId") != item["reviewItemId"]]
    mirror: dict[str, Any] = {}
    if item["status"] in {"accepted_truth", "rejected_mismatch"}:
        mirror = record_truth_item(
            state,
            {
                "itemId": item["reviewItemId"],
                "type": item["type"],
                "status": item["status"],
                "sourceVideoId": item["sourceVideoId"],
                "sourceUrl": item["sourceUrl"],
                "sourceTitle": item["sourceTitle"],
                "practiceDay": item["practiceDay"],
                "sampleId": item["sampleId"],
                "startSeconds": item["startSeconds"],
                "endSeconds": item["endSeconds"],
                "pieceTitle": item["pieceTitle"],
                "scoreSource": item["scoreSource"],
                "scoreAssetId": item["scoreAssetId"],
                "scoreLocation": item["scoreLocation"],
                "scoreImageUrl": item["scoreImageUrl"],
                "detectedNotes": item["detectedNotes"],
                "acceptedNotes": item["acceptedNotes"],
                "scoreNotes": item["scoreNotes"],
                "reason": item["reason"],
                "createdAt": item["createdAt"],
            },
        )
    state["goldReview"] = {
        **review,
        "version": GOLD_REVIEW_VERSION,
        "items": [item, *items][:1000],
        "updatedAt": item["createdAt"],
    }
    state["lastGoldReviewItem"] = {
        "reviewItemId": item["reviewItemId"],
        "type": item["type"],
        "status": item["status"],
        "createdAt": item["createdAt"],
    }
    return {"goldReviewItem": item, "truthMirror": mirror}


def build_gold_review_loop(state: dict[str, Any], daily_records: dict[str, Any], *, limit: int = 10) -> dict[str, Any]:
    review = state.get("goldReview") if isinstance(state.get("goldReview"), dict) else {}
    items = [entry for entry in review.get("items", []) if isinstance(entry, dict)]
    by_status = Counter(_clean(item.get("status") or "unknown") for item in items)
    by_type = Counter(_clean(item.get("type") or "unknown") for item in items)
    accepted_audio = [item for item in items if item.get("status") == "accepted_truth" and item.get("type") == "audio_phrase"]
    accepted_score = [
        item
        for item in items
        if item.get("status") == "accepted_truth" and item.get("type") in {"score_phrase", "audio_score_match"}
    ]
    reviewed_ids = {_clean(item.get("reviewItemId")) for item in items if _clean(item.get("reviewItemId"))}
    candidates = [candidate for candidate in _queue_candidates(daily_records) if _clean(candidate.get("reviewItemId")) not in reviewed_ids]
    candidates.sort(
        key=lambda item: (
            0 if item.get("reviewKind") == "score_phrase_candidate" else 1,
            -int(item.get("detectedNoteCount") or 0),
            str(item.get("practiceDay") or ""),
            str(item.get("sampleId") or ""),
        )
    )
    truth_progress = build_truth_progress(state)
    return {
        "status": "ready" if candidates or items else "empty",
        "version": GOLD_REVIEW_VERSION,
        "labelCount": len(items),
        "acceptedCount": by_status.get("accepted_truth", 0),
        "rejectedCount": by_status.get("rejected_mismatch", 0),
        "pendingCount": by_status.get("pending_review", 0),
        "acceptedAudioPhraseCount": len(accepted_audio),
        "acceptedScorePhraseCount": len(accepted_score),
        "scoreReadyTruthCount": int(truth_progress.get("scoreReadyTruthCount") or 0),
        "acceptedEvidenceReadyCount": int(truth_progress.get("acceptedEvidenceReadyCount") or 0),
        "queueCount": len(candidates),
        "reviewedIds": len(reviewed_ids),
        "itemsByType": dict(by_type),
        "itemsByStatus": dict(by_status),
        "queue": candidates[: max(0, int(limit))],
        "recentItems": items[:8],
        "nextAction": (
            "Review one queued clip: confirm exact notes, mark mismatch, or add score notes and location before accepting score evidence."
            if candidates
            else "Gold review queue is empty for current analyzed evidence."
        ),
        "acceptanceRule": "Accepted score labels require exact audio-note and score-note MIDI agreement. Audio-only labels improve transcription truth but stay out of score evidence.",
    }
