from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from .evidence_ledger import build_truth_progress, record_truth_item
from .long_phrase_truth import collapse_consecutive_duplicate_midi, note_midi_sequence, note_midi_value
from .state import utc_now


GOLD_REVIEW_VERSION = "gold_review_v1"
GOLD_REVIEW_STATUSES = {"pending_review", "accepted_truth", "rejected_mismatch"}
GOLD_REVIEW_TYPES = {"audio_phrase", "score_phrase", "audio_score_match", "practice_window"}
MAX_REVIEW_CLIP_SECONDS = 14.75
MIN_LONG_REVIEW_NOTES = 6
MAX_LONG_REVIEW_NOTES = 16
MAX_ADAPTIVE_REVIEW_WINDOWS_PER_SERIES = 10
MAX_ADAPTIVE_REVIEW_QUEUE = 80


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


def _score_note_names(*values: Any) -> list[str]:
    for value in values:
        names = _clean_note_names(value)
        if names:
            return names
    return []


def _notes_from_names(names: list[str]) -> list[dict[str, Any]]:
    return [{"note": name} for name in names]


def _normalized_review_midi_sequence(names: list[str]) -> list[int]:
    return collapse_consecutive_duplicate_midi(note_midi_sequence(_notes_from_names(names)))


def _normalized_review_note_agreement(left: list[str], right: list[str]) -> bool:
    left_midi = _normalized_review_midi_sequence(left)
    right_midi = _normalized_review_midi_sequence(right)
    return bool(left_midi and right_midi and left_midi == right_midi)


def _review_sequence_key(names: list[str]) -> str:
    sequence = _normalized_review_midi_sequence(names)
    return " ".join(str(value) for value in sequence)


def _candidate_sequence_key(candidate: dict[str, Any]) -> str:
    if isinstance(candidate.get("normalizedDetectedMidiSequence"), list):
        values = [int(value) for value in candidate["normalizedDetectedMidiSequence"] if isinstance(value, int)]
        if values:
            return " ".join(str(value) for value in values)
    return _review_sequence_key(_clean_note_names(candidate.get("detectedNotes")))


def _review_task(raw: dict[str, Any], item_type: str, score_notes: list[str]) -> str:
    explicit = _clean(raw.get("reviewTask") or raw.get("trainingTask")).lower()
    if explicit:
        return explicit
    if item_type in {"score_phrase", "audio_score_match"} or score_notes:
        return "audio_score_exact_match"
    detected_count = len(_clean_note_names(raw.get("detectedNotes")))
    if detected_count >= MIN_LONG_REVIEW_NOTES:
        return "audio_long_phrase_exact_notes"
    return "audio_exact_notes"


def _training_example_from_item(item: dict[str, Any]) -> dict[str, Any]:
    accepted_midi = item.get("normalizedAcceptedMidiSequence") if isinstance(item.get("normalizedAcceptedMidiSequence"), list) else []
    detected_midi = item.get("normalizedDetectedMidiSequence") if isinstance(item.get("normalizedDetectedMidiSequence"), list) else []
    score_midi = item.get("normalizedScoreMidiSequence") if isinstance(item.get("normalizedScoreMidiSequence"), list) else []
    target_midi = accepted_midi or detected_midi
    if item.get("type") in {"score_phrase", "audio_score_match"} and score_midi:
        target_midi = score_midi
    label = "positive" if item.get("status") == "accepted_truth" else "negative" if item.get("status") == "rejected_mismatch" else "pending"
    return {
        "trainingExampleId": item.get("reviewItemId"),
        "task": item.get("reviewTask") or "audio_exact_notes",
        "label": label,
        "labelSource": "human_review",
        "labelNoiseModel": "noisy_human_visual_audio_review",
        "humanSignalWeight": 0.82 if label == "positive" else 0.74 if label == "negative" else 0.0,
        "hardEvidence": bool(item.get("type") in {"score_phrase", "audio_score_match"} and item.get("status") == "accepted_truth" and item.get("scoreNotes")),
        "type": item.get("type"),
        "practiceDay": item.get("practiceDay"),
        "sampleId": item.get("sampleId"),
        "startSeconds": item.get("startSeconds"),
        "endSeconds": item.get("endSeconds"),
        "pieceTitle": item.get("pieceTitle"),
        "detectedNotes": item.get("detectedNotes") or [],
        "acceptedNotes": item.get("acceptedNotes") or [],
        "scoreNotes": item.get("scoreNotes") or [],
        "normalizedTargetMidiSequence": target_midi,
        "normalizedDetectedMidiSequence": detected_midi,
        "normalizedScoreMidiSequence": score_midi,
        "scoreAgreement": bool(score_midi and detected_midi and score_midi == detected_midi),
        "noteCount": len(target_midi or detected_midi),
        "duplicateTolerance": item.get("duplicateTolerance"),
        "reason": item.get("reason"),
        "createdAt": item.get("createdAt"),
        "labelRevision": item.get("labelRevision") or 1,
        "correctedLabel": bool(item.get("correctedLabel")),
    }


def build_gold_training_set(items: list[dict[str, Any]]) -> dict[str, Any]:
    examples = [_training_example_from_item(item) for item in items if item.get("status") in {"accepted_truth", "rejected_mismatch"}]
    positives = [item for item in examples if item.get("label") == "positive"]
    negatives = [item for item in examples if item.get("label") == "negative"]
    audio_examples = [item for item in examples if item.get("task") in {"audio_exact_notes", "audio_long_phrase_exact_notes"}]
    score_examples = [item for item in examples if item.get("task") == "audio_score_exact_match"]
    positive_score_examples = [item for item in score_examples if item.get("label") == "positive"]
    negative_score_examples = [item for item in score_examples if item.get("label") == "negative"]
    long_phrase_examples = [item for item in examples if int(item.get("noteCount") or 0) >= MIN_LONG_REVIEW_NOTES]
    return {
        "version": f"{GOLD_REVIEW_VERSION}_training_v1",
        "exampleCount": len(examples),
        "positiveCount": len(positives),
        "negativeCount": len(negatives),
        "audioExampleCount": len(audio_examples),
        "scoreExampleCount": len(score_examples),
        "positiveScoreExampleCount": len(positive_score_examples),
        "negativeScoreExampleCount": len(negative_score_examples),
        "longPhraseExampleCount": len(long_phrase_examples),
        "positiveLongPhraseCount": len([item for item in long_phrase_examples if item.get("label") == "positive"]),
        "negativeLongPhraseCount": len([item for item in long_phrase_examples if item.get("label") == "negative"]),
        "tasks": dict(Counter(_clean(item.get("task")) for item in examples)),
        "recentExamples": examples[:8],
    }


def _item_learning_key(item: dict[str, Any]) -> str:
    for field in ("normalizedAcceptedMidiSequence", "normalizedDetectedMidiSequence", "normalizedScoreMidiSequence"):
        values = item.get(field)
        if isinstance(values, list):
            cleaned = [int(value) for value in values if isinstance(value, int)]
            if cleaned:
                return " ".join(str(value) for value in cleaned)
    for field in ("acceptedNotes", "detectedNotes", "scoreNotes"):
        key = _review_sequence_key(_clean_note_names(item.get(field)))
        if key:
            return key
    return ""


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


def _note_span_seconds(notes: list[dict[str, Any]]) -> float:
    if not notes:
        return 0.0
    start = _safe_float(notes[0].get("startSeconds"))
    end = max(start, _safe_float(notes[-1].get("endSeconds") or notes[-1].get("startSeconds")))
    return max(0.0, end - start)


def _midi_values(notes: list[dict[str, Any]]) -> list[int]:
    values: list[int] = []
    for note in notes:
        midi = note_midi_value(note)
        if midi is not None:
            values.append(int(midi))
    return values


def _adjacent_duplicate_count(values: list[int]) -> int:
    return sum(1 for left, right in zip(values, values[1:]) if left == right)


def _max_consecutive_duplicate(values: list[int]) -> int:
    longest = 0
    current = 0
    previous: int | None = None
    for value in values:
        if value == previous:
            current += 1
        else:
            current = 1
            previous = value
        longest = max(longest, current)
    return longest


def _review_note_metrics(notes: list[dict[str, Any]]) -> dict[str, Any]:
    values = _midi_values(notes)
    length = len(values)
    distinct_midi = len(set(values))
    distinct_pitch_class = _pitch_class_count(notes)
    adjacent_duplicates = _adjacent_duplicate_count(values)
    max_duplicate_run = _max_consecutive_duplicate(values)
    duplicate_ratio = adjacent_duplicates / max(1, length - 1)
    audio_agreed = sum(1 for note in notes if note.get("audioAgreement") is True)
    spectral = sum(1 for note in notes if "spectral_onset" in (note.get("agreementSources") or []))
    confidence = sum(float(note.get("confidence") or 0.0) for note in notes) / max(1, len(notes))
    repetition_penalty = (adjacent_duplicates * 8.0) + (max(0, max_duplicate_run - 2) * 12.0) + (duplicate_ratio * 18.0)
    phrase_shape_bonus = min(length, 10) * 2.0
    quality = (
        (distinct_midi * 12.0)
        + (distinct_pitch_class * 4.0)
        + phrase_shape_bonus
        + (audio_agreed * 1.5)
        + spectral
        + (confidence * 2.0)
        - repetition_penalty
    )
    return {
        "detectedMidiDistinctCount": distinct_midi,
        "distinctPitchClassCount": distinct_pitch_class,
        "adjacentDuplicateCount": adjacent_duplicates,
        "maxConsecutiveDuplicateMidi": max_duplicate_run,
        "duplicateRatio": round(duplicate_ratio, 3),
        "repetitionPenalty": round(repetition_penalty, 3),
        "adaptiveQualityScore": round(quality, 3),
        "audioAgreementCount": audio_agreed,
        "spectralAgreementCount": spectral,
        "averageConfidence": round(confidence, 3),
    }


def _adaptive_window_is_useful(notes: list[dict[str, Any]]) -> bool:
    metrics = _review_note_metrics(notes)
    length = len(_midi_values(notes))
    if length < 3:
        return False
    if length >= 6 and int(metrics["detectedMidiDistinctCount"]) <= 2:
        return False
    if int(metrics["maxConsecutiveDuplicateMidi"]) > 4:
        return False
    if float(metrics["duplicateRatio"]) > 0.58:
        return False
    return True


def best_review_note_slice(
    notes: list[dict[str, Any]],
    *,
    min_notes: int = 5,
    max_notes: int = 12,
    max_seconds: float = MAX_REVIEW_CLIP_SECONDS - 0.25,
) -> list[dict[str, Any]]:
    clean_notes = [note for note in notes if _clean(note.get("note")) and note_midi_value(note) is not None]
    if not clean_notes:
        return []
    if len(clean_notes) <= max_notes and _note_span_seconds(clean_notes) <= max_seconds:
        return clean_notes if len(clean_notes) >= min_notes else clean_notes
    best: tuple[float, int, int] | None = None
    search_limit = min(len(clean_notes), 96)
    for start in range(0, max(1, search_limit - min_notes + 1)):
        for length in range(min_notes, min(max_notes, search_limit - start) + 1):
            window = clean_notes[start : start + length]
            if _note_span_seconds(window) > max_seconds:
                continue
            distinct = _pitch_class_count(window)
            audio_agreed = sum(1 for note in window if note.get("audioAgreement") is True)
            spectral = sum(1 for note in window if "spectral_onset" in (note.get("agreementSources") or []))
            repeated_penalty = max(0, length - distinct - 3)
            if start > 0 and note_midi_value(clean_notes[start - 1]) == note_midi_value(window[0]):
                repeated_penalty += 2
            confidence = sum(float(note.get("confidence") or 0.0) for note in window) / max(1, len(window))
            score = (distinct * 8) + (audio_agreed * 2) + spectral + confidence - repeated_penalty
            if best is None or score > best[0]:
                best = (score, start, length)
    if best is None:
        return []
    _, start, length = best
    return clean_notes[start : start + length]


def long_review_note_slice(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean_notes = [note for note in notes if _clean(note.get("note")) and note_midi_value(note) is not None]
    if not clean_notes:
        return []
    best: tuple[float, int, int] | None = None
    search_limit = min(len(clean_notes), 128)
    for start in range(0, search_limit):
        for length in range(MIN_LONG_REVIEW_NOTES, min(MAX_LONG_REVIEW_NOTES, search_limit - start) + 1):
            window = clean_notes[start : start + length]
            span = _note_span_seconds(window)
            if span > MAX_REVIEW_CLIP_SECONDS - 0.25:
                continue
            distinct = _pitch_class_count(window)
            audio_agreed = sum(1 for note in window if note.get("audioAgreement") is True)
            confidence = sum(float(note.get("confidence") or 0.0) for note in window) / max(1, len(window))
            score = (length * 5) + (distinct * 4) + (audio_agreed * 2) + confidence
            if start > 0 and note_midi_value(clean_notes[start - 1]) == note_midi_value(window[0]):
                score -= 5
            if best is None or score > best[0]:
                best = (score, start, length)
    if best is None:
        return best_review_note_slice(clean_notes, min_notes=3, max_notes=MAX_LONG_REVIEW_NOTES)
    _, start, length = best
    return clean_notes[start : start + length]


def adaptive_review_note_windows(
    notes: list[dict[str, Any]],
    *,
    max_windows: int = MAX_ADAPTIVE_REVIEW_WINDOWS_PER_SERIES,
) -> list[list[dict[str, Any]]]:
    clean_notes = [note for note in notes if _clean(note.get("note")) and note_midi_value(note) is not None]
    if not clean_notes:
        return []
    scored: list[tuple[float, int, list[dict[str, Any]]]] = []
    seen: set[str] = set()
    search_limit = min(len(clean_notes), 160)
    for start in range(0, search_limit):
        max_length = min(MAX_LONG_REVIEW_NOTES, search_limit - start)
        for length in range(3, max_length + 1):
            window = clean_notes[start : start + length]
            span = _note_span_seconds(window)
            if span > MAX_REVIEW_CLIP_SECONDS - 0.25:
                continue
            key = _review_sequence_key(_clean_note_names(window))
            if not key or key in seen:
                continue
            seen.add(key)
            if not _adaptive_window_is_useful(window):
                continue
            metrics = _review_note_metrics(window)
            score = float(metrics["adaptiveQualityScore"])
            if start > 0 and note_midi_value(clean_notes[start - 1]) == note_midi_value(window[0]):
                score -= 10.0
            scored.append((score, start, window))
    scored.sort(key=lambda item: (-item[0], item[1], -len(item[2])))
    return [window for _, _, window in scored[: max(0, int(max_windows))]]


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
    if local_end - local_start > MAX_REVIEW_CLIP_SECONDS:
        local_end = local_start + MAX_REVIEW_CLIP_SECONDS
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


def _clip_is_playable(clip: dict[str, Any]) -> bool:
    if not isinstance(clip, dict):
        return False
    if not _clean(clip.get("sampleId")):
        return False
    local_start = _safe_float(clip.get("localStartSeconds"))
    local_end = _safe_float(clip.get("localEndSeconds"))
    duration = local_end - local_start
    return 0.05 < duration <= 15.0 and bool(_clean(clip.get("mediaUrl")) and _clean(clip.get("audioUrl")))


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


def _candidate_from_series(
    record: dict[str, Any],
    series: dict[str, Any],
    *,
    notes_override: list[dict[str, Any]] | None = None,
    adaptive_index: int | None = None,
) -> dict[str, Any]:
    notes = notes_override if notes_override is not None else long_review_note_slice(_note_dicts(series.get("notes")))
    note_names = _clean_note_names(notes)
    if len(note_names) < 3:
        return {}
    clip = _clip_from_series(series, notes)
    if not _clip_is_playable(clip):
        return {}
    note_metrics = _review_note_metrics(notes)
    payload = {
        "reviewKind": "long_audio_phrase_candidate" if len(note_names) >= MIN_LONG_REVIEW_NOTES else "audio_phrase_candidate",
        "reviewType": "audio_phrase",
        "acceptanceMode": "binary_exact_claim",
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
        "normalizedDetectedMidiSequence": collapse_consecutive_duplicate_midi(note_midi_sequence(notes)),
        "detectedNoteCount": len(note_names),
        "sourceDetectedNoteCount": int(series.get("noteCount") or len(_note_dicts(series.get("notes")))),
        "audioAgreementCount": note_metrics["audioAgreementCount"],
        "spectralAgreementCount": note_metrics["spectralAgreementCount"],
        "detectedMidiDistinctCount": note_metrics["detectedMidiDistinctCount"],
        "distinctPitchClassCount": note_metrics["distinctPitchClassCount"],
        "adjacentDuplicateCount": note_metrics["adjacentDuplicateCount"],
        "maxConsecutiveDuplicateMidi": note_metrics["maxConsecutiveDuplicateMidi"],
        "duplicateRatio": note_metrics["duplicateRatio"],
        "repetitionPenalty": note_metrics["repetitionPenalty"],
        "adaptiveQualityScore": note_metrics["adaptiveQualityScore"],
        "audioAgreed": _all_audio_agreed(notes),
        "scoreNotes": [],
        "scoreLocation": "",
        "clip": clip,
        "defaultStatus": "pending_review",
        "reviewTask": "audio_long_phrase_exact_notes" if len(note_names) >= MIN_LONG_REVIEW_NOTES else "audio_exact_notes",
        "binaryReview": True,
        "binaryOnly": True,
        "adaptiveReview": adaptive_index is not None,
        "adaptiveWindowIndex": adaptive_index,
        "adaptiveQualityTier": (
            "phrase_shaped"
            if float(note_metrics["adaptiveQualityScore"]) >= 45.0
            else "usable"
            if float(note_metrics["adaptiveQualityScore"]) >= 25.0
            else "low"
        ),
        "reviewTrainingLane": "audio_notes",
        "reviewQuestion": "Do the displayed notes match the paired audio? Reject if one note is wrong.",
        "acceptanceRule": "Accept only if every displayed note matches the paired audio after adjacent duplicate detections are collapsed.",
        "rejectionRule": "Reject if any displayed note is wrong, missing, extra, out of order, or not audible in the paired clip.",
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
    if not _clip_is_playable(clip):
        return {}
    score = group.get("score") if isinstance(group.get("score"), dict) else {}
    score_notes = _score_note_names(
        group.get("sourceScoreExactSequence"),
        group.get("visibleScoreExactNoteSequence"),
        group.get("scoreExactNoteSequenceLabel"),
        group.get("scoreNoteSeriesLabel"),
        group.get("scoreMatchedNotes"),
        score.get("visibleScoreExactNoteSequence"),
        score.get("scoreExactNoteSequenceLabel"),
        score.get("scoreNoteSeriesLabel"),
        score.get("scoreMatchedNotes"),
        score.get("scoreNotes"),
    )
    detected_midi = collapse_consecutive_duplicate_midi(note_midi_sequence(notes))
    score_midi = _normalized_review_midi_sequence(score_notes)
    score_agreement = bool(score_midi and detected_midi and score_midi == detected_midi)
    payload = {
        "reviewKind": "score_phrase_candidate" if score_notes else "reference_phrase_candidate",
        "reviewType": "audio_score_match" if score_notes else "audio_phrase",
        "acceptanceMode": "binary_exact_claim",
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
        "normalizedDetectedMidiSequence": detected_midi,
        "detectedNoteCount": len(note_names),
        "matchedNoteRun": int(group.get("matchedNoteRun") or 0),
        "audioAgreementCount": sum(1 for note in notes if note.get("audioAgreement") is True),
        "spectralAgreementCount": sum(1 for note in notes if "spectral_onset" in (note.get("agreementSources") or [])),
        "audioAgreed": _all_audio_agreed(notes),
        "scoreNotes": score_notes,
        "normalizedScoreMidiSequence": score_midi,
        "scoreAgreement": score_agreement,
        "scoreAgreementStatus": "exact_midi_agreement" if score_agreement else "score_midi_mismatch" if score_notes else "no_score_context",
        "reviewTrainingLane": "score_alignment" if score_notes else "audio_notes",
        "scoreLocation": _clean(group.get("scoreLocation") or group.get("scoreSequenceLabel") or score.get("label")),
        "scoreStatus": _clean(group.get("sourceScoreCheckStatus") or group.get("scoreSnippetStatus") or score.get("status")),
        "clip": clip,
        "defaultStatus": "pending_review",
        "reviewTask": "audio_score_exact_match" if score_notes else "audio_exact_notes",
        "binaryReview": True,
        "binaryOnly": True,
        "reviewQuestion": (
            "Do the audio, displayed transcription, and score notes all match? Reject if one note is wrong."
            if score_notes
            else "Do the displayed notes match the paired audio? Reject if one note is wrong."
        ),
        "acceptanceRule": "Accept only if every displayed audio/transcription note and every score note agree after adjacent duplicate detections are collapsed.",
        "rejectionRule": "Reject if any note is wrong, missing, extra, out of order, or the score location is not the same phrase.",
    }
    payload["reviewItemId"] = _candidate_id(payload)
    return payload


def _queue_candidates(daily_records: dict[str, Any], *, adaptive: bool = False) -> list[dict[str, Any]]:
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
            if adaptive:
                for index, window in enumerate(adaptive_review_note_windows(_note_dicts(series.get("notes")))):
                    candidate = _candidate_from_series(record, series, notes_override=window, adaptive_index=index)
                    if candidate:
                        candidates.append(candidate)
            else:
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
    score_notes = _score_note_names(
        raw.get("scoreNotes"),
        raw.get("sourceScoreNotes"),
        raw.get("scoreExactNoteSequenceLabel"),
        raw.get("scoreNoteSeriesLabel"),
        raw.get("scoreMatchedNotes"),
    )
    review_task = _review_task(raw, item_type, score_notes)
    if status == "accepted_truth" and not accepted_notes:
        accepted_notes = detected_notes
    if status == "accepted_truth" and not accepted_notes:
        raise ValueError("Accepted gold review items require accepted notes.")
    if item_type in {"score_phrase", "audio_score_match"} and status == "accepted_truth" and not score_notes:
        raise ValueError("Accepted score phrase labels require score notes.")
    if item_type in {"score_phrase", "audio_score_match"} and status == "accepted_truth":
        if not _normalized_review_note_agreement(accepted_notes, score_notes):
            raise ValueError("Accepted score phrase labels require normalized audio and score MIDI agreement.")
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
        "reviewTask": review_task,
        "trainingTask": review_task,
        "trainingLabel": "positive" if status == "accepted_truth" else "negative" if status == "rejected_mismatch" else "pending",
        "normalizedDetectedMidiSequence": _normalized_review_midi_sequence(detected_notes),
        "normalizedAcceptedMidiSequence": _normalized_review_midi_sequence(accepted_notes),
        "normalizedScoreMidiSequence": _normalized_review_midi_sequence(score_notes),
        "duplicateTolerance": "consecutive_duplicate_notes_collapsed",
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
    previous = next((entry for entry in items if entry.get("reviewItemId") == item["reviewItemId"]), None)
    if previous:
        item["labelRevision"] = int(previous.get("labelRevision") or 1) + 1
        item["previousStatus"] = _clean(previous.get("status"))
        item["correctedLabel"] = item["previousStatus"] != item["status"]
        history = [entry for entry in previous.get("labelHistory", []) if isinstance(entry, dict)]
        history.append(
            {
                "status": _clean(previous.get("status")),
                "trainingLabel": _clean(previous.get("trainingLabel")),
                "acceptedNotes": previous.get("acceptedNotes") or [],
                "scoreNotes": previous.get("scoreNotes") or [],
                "createdAt": _clean(previous.get("createdAt")),
                "labelRevision": int(previous.get("labelRevision") or 1),
            }
        )
        item["labelHistory"] = history[-12:]
    else:
        item["labelRevision"] = 1
        item["previousStatus"] = ""
        item["correctedLabel"] = False
        item["labelHistory"] = []
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
                "reviewTask": item["reviewTask"],
                "trainingTask": item["trainingTask"],
                "trainingLabel": item["trainingLabel"],
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


def build_review_learning_profile(items: list[dict[str, Any]]) -> dict[str, Any]:
    accepted_keys: set[str] = set()
    rejected_keys: set[str] = set()
    accepted_counts: Counter[str] = Counter()
    rejected_counts: Counter[str] = Counter()
    for item in items:
        key = _item_learning_key(item)
        if not key:
            continue
        if item.get("status") == "accepted_truth":
            accepted_keys.add(key)
            accepted_counts[key] += 1
        elif item.get("status") == "rejected_mismatch":
            rejected_keys.add(key)
            rejected_counts[key] += 1
    rejected_only: set[str] = set()
    soft_rejected = rejected_keys - accepted_keys
    return {
        "acceptedKeys": accepted_keys,
        "rejectedKeys": rejected_keys,
        "rejectedOnlyKeys": rejected_only,
        "softRejectedKeys": soft_rejected,
        "acceptedCounts": dict(accepted_counts),
        "rejectedCounts": dict(rejected_counts),
        "acceptedPatternCount": len(accepted_keys),
        "rejectedPatternCount": len(rejected_keys),
        "softRejectedPatternCount": len(soft_rejected),
        "suppressionThreshold": None,
        "suppressionRule": "Human review labels are useful but noisy. Human labels do not hard-hide candidates by themselves; accepted patterns are prioritized, rejected-only patterns are deprioritized, and independent evidence gates decide whether a phrase is blocked from accepted display.",
    }


def apply_review_learning_to_candidates(
    candidates: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_keys = profile.get("acceptedKeys") if isinstance(profile.get("acceptedKeys"), set) else set()
    rejected_only_keys = profile.get("rejectedOnlyKeys") if isinstance(profile.get("rejectedOnlyKeys"), set) else set()
    soft_rejected_keys = profile.get("softRejectedKeys") if isinstance(profile.get("softRejectedKeys"), set) else set()
    active: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _candidate_sequence_key(candidate)
        status = (
            "accepted_pattern"
            if key in accepted_keys
            else "soft_rejected_pattern"
            if key in soft_rejected_keys
            else "new_pattern"
        )
        enriched = {
            **candidate,
            "reviewLearningKey": key,
            "reviewLearningStatus": status,
            "reviewLearningReliability": "noisy_human_signal",
        }
        if key and key in rejected_only_keys:
            suppressed.append(enriched)
        else:
            active.append(enriched)
    return active, suppressed


def _review_candidate_rank(item: dict[str, Any]) -> tuple[Any, ...]:
    learning_rank = {
        "accepted_pattern": 0,
        "new_pattern": 1,
        "soft_rejected_pattern": 2,
    }.get(str(item.get("reviewLearningStatus") or ""), 1)
    return (
        0 if item.get("reviewKind") == "score_phrase_candidate" else 1 if item.get("reviewKind") == "long_audio_phrase_candidate" else 2,
        0 if item.get("scoreAgreement") is True else 1,
        learning_rank,
        -float(item.get("adaptiveQualityScore") or 0.0),
        float(item.get("repetitionPenalty") or 0.0),
        -int(item.get("detectedMidiDistinctCount") or 0),
        -int(item.get("audioAgreementCount") or 0),
        -int(item.get("detectedNoteCount") or 0),
        str(item.get("practiceDay") or ""),
        str(item.get("sampleId") or ""),
    )


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
    learning_profile = build_review_learning_profile(items)
    raw_candidates = [candidate for candidate in _queue_candidates(daily_records) if _clean(candidate.get("reviewItemId")) not in reviewed_ids]
    candidates, suppressed_candidates = apply_review_learning_to_candidates(raw_candidates, learning_profile)
    adaptive_candidates: list[dict[str, Any]] = []
    adaptive_suppressed_candidates: list[dict[str, Any]] = []
    adaptive_candidate_pool_count = 0
    adaptive_mode = False
    if not candidates:
        raw_adaptive_candidates = [
            candidate
            for candidate in _queue_candidates(daily_records, adaptive=True)
            if _clean(candidate.get("reviewItemId")) not in reviewed_ids
        ]
        adaptive_candidates, adaptive_suppressed_candidates = apply_review_learning_to_candidates(raw_adaptive_candidates, learning_profile)
        adaptive_candidates.sort(key=_review_candidate_rank)
        adaptive_candidate_pool_count = len(adaptive_candidates)
        adaptive_candidates = adaptive_candidates[:MAX_ADAPTIVE_REVIEW_QUEUE]
        if adaptive_candidates:
            candidates = adaptive_candidates
            adaptive_mode = True
    score_candidates = [item for item in candidates if item.get("reviewTask") == "audio_score_exact_match"]
    exact_score_candidates = [item for item in score_candidates if item.get("scoreAgreement") is True]
    long_candidates = [item for item in candidates if item.get("reviewKind") == "long_audio_phrase_candidate"]
    candidates.sort(key=_review_candidate_rank)
    truth_progress = build_truth_progress(state)
    training_set = build_gold_training_set(items)
    hidden_rejected_keys = {
        str(item.get("reviewLearningKey") or "")
        for item in [*suppressed_candidates, *adaptive_suppressed_candidates]
        if str(item.get("reviewLearningKey") or "")
    }
    queue_status = (
        "adaptive_review_ready"
        if adaptive_mode
        else "review_queue_ready"
        if candidates
        else "current_batch_exhausted_by_rejections"
        if suppressed_candidates or adaptive_suppressed_candidates
        else "review_queue_empty"
    )
    return {
        "status": "ready" if candidates or items else "empty",
        "version": GOLD_REVIEW_VERSION,
        "labelCount": len(items),
        "correctedLabelCount": len([item for item in items if item.get("correctedLabel") is True]),
        "reviewRevisionCount": sum(max(0, int(item.get("labelRevision") or 1) - 1) for item in items),
        "acceptedCount": by_status.get("accepted_truth", 0),
        "rejectedCount": by_status.get("rejected_mismatch", 0),
        "pendingCount": by_status.get("pending_review", 0),
        "acceptedAudioPhraseCount": len(accepted_audio),
        "acceptedScorePhraseCount": len(accepted_score),
        "scoreReadyTruthCount": int(truth_progress.get("scoreReadyTruthCount") or 0),
        "acceptedEvidenceReadyCount": int(truth_progress.get("acceptedEvidenceReadyCount") or 0),
        "queueCount": len(candidates),
        "queueStatus": queue_status,
        "scoreQueueCount": len(score_candidates),
        "scoreExactAgreementQueueCount": len(exact_score_candidates),
        "longPhraseQueueCount": len(long_candidates),
        "rawQueueCount": len(raw_candidates),
        "adaptiveMode": adaptive_mode,
        "adaptiveCandidateCount": len(adaptive_candidates),
        "adaptiveCandidatePoolCount": adaptive_candidate_pool_count,
        "adaptiveQueueLimit": MAX_ADAPTIVE_REVIEW_QUEUE,
        "adaptiveSuppressedByLearningCount": len(adaptive_suppressed_candidates),
        "suppressedByLearningCount": len(suppressed_candidates),
        "reviewedIds": len(reviewed_ids),
        "acceptedPatternCount": int(learning_profile.get("acceptedPatternCount") or 0),
        "rejectedPatternCount": int(learning_profile.get("rejectedPatternCount") or 0),
        "softRejectedPatternCount": int(learning_profile.get("softRejectedPatternCount") or 0),
        "suppressionThreshold": learning_profile.get("suppressionThreshold"),
        "trainingSet": training_set,
        "trainingExampleCount": int(training_set.get("exampleCount") or 0),
        "trainingPositiveCount": int(training_set.get("positiveCount") or 0),
        "trainingNegativeCount": int(training_set.get("negativeCount") or 0),
        "trainingLongPhraseExampleCount": int(training_set.get("longPhraseExampleCount") or 0),
        "trainingScoreExampleCount": int(training_set.get("scoreExampleCount") or 0),
        "trainingPositiveScoreExampleCount": int(training_set.get("positiveScoreExampleCount") or 0),
        "trainingNegativeScoreExampleCount": int(training_set.get("negativeScoreExampleCount") or 0),
        "reviewLearningStatus": "reducing_review_load" if suppressed_candidates else "learning_no_suppression_yet",
        "reviewLearningRule": learning_profile.get("suppressionRule") or "",
        "rejectionDigest": {
            "status": queue_status,
            "hiddenRejectedPatternCount": len(hidden_rejected_keys),
            "hiddenRejectedCandidateCount": len(suppressed_candidates) + len(adaptive_suppressed_candidates),
            "rejectedPatternCount": int(learning_profile.get("rejectedPatternCount") or 0),
            "softRejectedPatternCount": int(learning_profile.get("softRejectedPatternCount") or 0),
            "message": (
                "Adaptive review is mining fresh windows from analyzed audio while skipping exact rejected patterns."
                if queue_status == "adaptive_review_ready"
                else
                "Current review batch is exhausted; remaining candidates repeat rejected note patterns."
                if queue_status == "current_batch_exhausted_by_rejections"
                else "Review the next queued clip."
                if queue_status == "review_queue_ready"
                else "No review candidates are available from current analyzed evidence."
            ),
        },
        "itemsByType": dict(by_type),
        "itemsByStatus": dict(by_status),
        "queue": candidates[: max(0, int(limit))],
        "suppressedQueuePreview": (suppressed_candidates + adaptive_suppressed_candidates)[:5],
        "recentItems": items[:8],
        "nextAction": (
            "Adaptive review is ready: keep accepting exact clips and rejecting any wrong note."
            if adaptive_mode
            else
            "Review one queued clip: accept only if the displayed claim is exact; reject if one note is wrong."
            if candidates
            else "Current batch complete: remaining candidates repeat rejected patterns. Generate fresh candidates from unreviewed or rescanned audio."
            if suppressed_candidates
            else "Gold review queue is empty for current analyzed evidence."
        ),
        "acceptanceRule": "Gold review is binary. Accept only exact displayed notes; reject any note, order, octave, audio, or score mismatch. Accepted score labels require exact audio-note and score-note MIDI agreement after consecutive duplicate detections are collapsed.",
    }
