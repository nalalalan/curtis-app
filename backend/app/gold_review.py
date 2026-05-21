from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from .evidence_ledger import build_truth_progress, record_truth_item
from .long_phrase_truth import collapse_consecutive_duplicate_midi, note_midi_sequence, note_midi_value
from .source_copy_catalog import NOTATION_COPY_ASPECTS, requested_original_score_snippets, requested_score_copy_records
from .state import utc_now


GOLD_REVIEW_VERSION = "gold_review_v1"
GOLD_REVIEW_STATUSES = {"pending_review", "accepted_truth", "rejected_mismatch"}
GOLD_REVIEW_TYPES = {"audio_phrase", "score_phrase", "audio_score_match", "score_copy", "note_reading", "practice_window"}
MAX_REVIEW_CLIP_SECONDS = 14.75
MIN_LONG_REVIEW_NOTES = 6
MAX_LONG_REVIEW_NOTES = 16
MIN_ACTIVE_AUDIO_REVIEW_QUEUE = 6
MAX_ADAPTIVE_REVIEW_WINDOWS_PER_SERIES = 10
MAX_ADAPTIVE_REVIEW_QUEUE = 80
SCORE_COPY_TASKS = {"score_copy_exact_notes", "score_copy_exact_notation", "score_copy_pitch_skeleton"}
NOTE_READING_TASKS = {"note_letter_reading"}


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


def _clean_note_letters(value: Any) -> list[str]:
    if isinstance(value, list):
        tokens = [str(item or "") for item in value]
    else:
        text = _clean(value).replace(",", " ")
        if any(char.isspace() for char in text):
            tokens = text.split()
        else:
            tokens = list(text)
    letters: list[str] = []
    for token in tokens:
        for char in str(token).upper():
            if char in "ABCDEFG":
                letters.append(char)
                break
    return letters


def _note_letters_from_notes(value: Any) -> list[str]:
    return _clean_note_letters(_clean_note_names(value))


def _score_note_names(*values: Any) -> list[str]:
    for value in values:
        names = _clean_note_names(value)
        if names:
            return names
    return []


def _is_score_copy_task(value: Any) -> bool:
    return _clean(value).lower() in SCORE_COPY_TASKS


def _is_note_reading_task(value: Any) -> bool:
    return _clean(value).lower() in NOTE_READING_TASKS


def _is_score_copy_item(item: dict[str, Any]) -> bool:
    return (
        _is_score_copy_task(item.get("reviewTask") or item.get("trainingTask"))
        or _clean(item.get("type")).lower() == "score_copy"
        or _clean(item.get("reviewType")).lower() == "score_copy"
    )


def _is_note_reading_item(item: dict[str, Any]) -> bool:
    return (
        _is_note_reading_task(item.get("reviewTask") or item.get("trainingTask"))
        or _clean(item.get("type")).lower() == "note_reading"
        or _clean(item.get("reviewType")).lower() == "note_reading"
    )


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
    score_copy = _is_score_copy_item(candidate)
    note_reading = _is_note_reading_item(candidate)
    if isinstance(candidate.get("normalizedDetectedMidiSequence"), list):
        values = [int(value) for value in candidate["normalizedDetectedMidiSequence"] if isinstance(value, int)]
        if values:
            key = " ".join(str(value) for value in values)
            if note_reading:
                return f"note_reading:{key}"
            return f"score_copy:{key}" if score_copy else key
    key = _review_sequence_key(_clean_note_names(candidate.get("detectedNotes")))
    if note_reading and key:
        return f"note_reading:{key}"
    return f"score_copy:{key}" if score_copy and key else key


def _review_time_bucket(value: Any) -> str:
    return f"{round(_safe_float(value) * 2) / 2:.1f}"


def _review_identity_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    sample_id = _clean(item.get("sampleId"))
    start = item.get("startSeconds")
    end = item.get("endSeconds")
    if sample_id and (start is not None or end is not None):
        keys.add(f"clip:{sample_id}:{_review_time_bucket(start)}:{_review_time_bucket(end)}")

    local_start = item.get("localStartSeconds")
    local_end = item.get("localEndSeconds")
    if sample_id and (local_start is not None or local_end is not None):
        keys.add(f"local_clip:{sample_id}:{_review_time_bucket(local_start)}:{_review_time_bucket(local_end)}")

    image = _clean(
        item.get("sourceReviewImageUrl")
        or item.get("sourceImageUrl")
        or item.get("scoreImageUrl")
        or item.get("imageUrl")
    )
    score_notes = _review_sequence_key(_clean_note_names(item.get("scoreNotes")))
    score_location = _clean(item.get("scoreLocation"))
    if image:
        score_copy = _is_score_copy_item(item)
        note_reading = _is_note_reading_item(item)
        prefix = "note_reading_image" if note_reading else "score_copy_image" if score_copy else "score_image"
        keys.add(f"{prefix}:{image}")
        if score_notes or score_location:
            keys.add(f"{prefix}_claim:{image}:{score_location}:{score_notes}")
    return keys


def _review_interval(item: dict[str, Any]) -> dict[str, Any]:
    sample_id = _clean(item.get("sampleId"))
    if not sample_id:
        return {}
    if item.get("startSeconds") is None and item.get("endSeconds") is None:
        return {}
    start = _safe_float(item.get("startSeconds"))
    end = _safe_float(item.get("endSeconds"))
    if end <= start:
        end = start + 0.5
    return {
        "sampleId": sample_id,
        "startSeconds": round(start, 3),
        "endSeconds": round(end, 3),
        "key": f"clip_overlap:{sample_id}:{_review_time_bucket(start)}:{_review_time_bucket(end)}",
    }


def _review_interval_matches(
    candidate: dict[str, Any],
    intervals: list[dict[str, Any]],
    *,
    padding_seconds: float = 0.75,
    minimum_overlap_seconds: float = 0.25,
    minimum_overlap_ratio: float = 0.34,
) -> list[str]:
    target = _review_interval(candidate)
    if not target:
        return []
    target_start = float(target["startSeconds"])
    target_end = float(target["endSeconds"])
    target_duration = max(0.05, target_end - target_start)
    matches: list[str] = []
    for interval in intervals:
        if _clean(interval.get("sampleId")) != target["sampleId"]:
            continue
        rejected_start = _safe_float(interval.get("startSeconds")) - padding_seconds
        rejected_end = _safe_float(interval.get("endSeconds")) + padding_seconds
        rejected_duration = max(0.05, rejected_end - rejected_start)
        overlap = max(0.0, min(target_end, rejected_end) - max(target_start, rejected_start))
        overlap_ratio = overlap / max(0.05, min(target_duration, rejected_duration))
        if overlap >= minimum_overlap_seconds or overlap_ratio >= minimum_overlap_ratio:
            matches.append(_clean(interval.get("key")) or f"clip_overlap:{target['sampleId']}:{target_start:.1f}:{target_end:.1f}")
    return matches


def _review_task(raw: dict[str, Any], item_type: str, score_notes: list[str]) -> str:
    explicit = _clean(raw.get("reviewTask") or raw.get("trainingTask")).lower()
    if explicit:
        return explicit
    if item_type == "note_reading":
        return "note_letter_reading"
    if item_type == "score_copy":
        return "score_copy_exact_notation"
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
    if item.get("type") in {"score_phrase", "audio_score_match", "score_copy"} and score_midi:
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
        "scoreCopyOnly": bool(item.get("type") == "score_copy"),
        "noteReadingOnly": bool(item.get("type") == "note_reading"),
        "notationCopyOnly": bool(item.get("notationCopyOnly")),
        "sourcePieceTrainingOnly": bool(item.get("sourcePieceTrainingOnly")),
        "notationCopyAspects": item.get("notationCopyAspects") if isinstance(item.get("notationCopyAspects"), list) else [],
        "type": item.get("type"),
        "practiceDay": item.get("practiceDay"),
        "sampleId": item.get("sampleId"),
        "startSeconds": item.get("startSeconds"),
        "endSeconds": item.get("endSeconds"),
        "pieceTitle": item.get("pieceTitle"),
        "detectedNotes": item.get("detectedNotes") or [],
        "acceptedNotes": item.get("acceptedNotes") or [],
        "scoreNotes": item.get("scoreNotes") or [],
        "expectedNoteLetters": item.get("expectedNoteLetters") or [],
        "userNoteLetters": item.get("userNoteLetters") or [],
        "noteLetterAnswer": item.get("noteLetterAnswer") or "",
        "noteLetterCorrect": bool(item.get("noteLetterCorrect")),
        "noteReadingAnswerMode": item.get("noteReadingAnswerMode") or "",
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
    score_copy_examples = [item for item in examples if _is_score_copy_task(item.get("task"))]
    note_reading_examples = [item for item in examples if _is_note_reading_task(item.get("task"))]
    positive_score_examples = [item for item in score_examples if item.get("label") == "positive"]
    negative_score_examples = [item for item in score_examples if item.get("label") == "negative"]
    positive_score_copy_examples = [item for item in score_copy_examples if item.get("label") == "positive"]
    negative_score_copy_examples = [item for item in score_copy_examples if item.get("label") == "negative"]
    positive_note_reading_examples = [item for item in note_reading_examples if item.get("label") == "positive"]
    negative_note_reading_examples = [item for item in note_reading_examples if item.get("label") == "negative"]
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
        "scoreCopyExampleCount": len(score_copy_examples),
        "positiveScoreCopyExampleCount": len(positive_score_copy_examples),
        "negativeScoreCopyExampleCount": len(negative_score_copy_examples),
        "noteReadingExampleCount": len(note_reading_examples),
        "positiveNoteReadingExampleCount": len(positive_note_reading_examples),
        "negativeNoteReadingExampleCount": len(negative_note_reading_examples),
        "longPhraseExampleCount": len(long_phrase_examples),
        "positiveLongPhraseCount": len([item for item in long_phrase_examples if item.get("label") == "positive"]),
        "negativeLongPhraseCount": len([item for item in long_phrase_examples if item.get("label") == "negative"]),
        "tasks": dict(Counter(_clean(item.get("task")) for item in examples)),
        "recentExamples": examples[:8],
    }


def build_rejection_insights(items: list[dict[str, Any]]) -> dict[str, Any]:
    rejected = [item for item in items if item.get("status") == "rejected_mismatch"]
    long_rejected = [item for item in rejected if len(_normalized_review_midi_sequence(_clean_note_names(item.get("detectedNotes")))) >= MIN_LONG_REVIEW_NOTES]
    dense_rejected = []
    unstable_rejected = []
    for item in long_rejected:
        notes = _clean_note_names(item.get("detectedNotes"))
        midi = _normalized_review_midi_sequence(notes)
        duration = max(0.0, _safe_float(item.get("endSeconds")) - _safe_float(item.get("startSeconds")))
        notes_per_second = len(midi) / duration if duration > 0 else 0.0
        if len(midi) >= 10 or notes_per_second >= 2.0:
            dense_rejected.append(item)
        if _large_leap_count(midi) >= 3 or _midi_range(midi) >= 24:
            unstable_rejected.append(item)
    issue = ""
    if dense_rejected and unstable_rejected:
        issue = "rejected_fast_dense_unstable_windows"
    elif dense_rejected:
        issue = "rejected_fast_dense_windows"
    elif unstable_rejected:
        issue = "rejected_unstable_register_windows"
    return {
        "rejectedLongPhraseCount": len(long_rejected),
        "rejectedFastDenseCount": len(dense_rejected),
        "rejectedUnstableRegisterCount": len(unstable_rejected),
        "dominantIssue": issue,
        "nextAction": (
            "Rank shorter, steadier onset-bounded windows ahead of long fast candidates until accepted examples prove the fast-note detector."
            if issue
            else ""
        ),
    }


def _item_learning_key(item: dict[str, Any]) -> str:
    score_copy = _is_score_copy_item(item)
    note_reading = _is_note_reading_item(item)
    for field in ("normalizedAcceptedMidiSequence", "normalizedDetectedMidiSequence", "normalizedScoreMidiSequence"):
        values = item.get(field)
        if isinstance(values, list):
            cleaned = [int(value) for value in values if isinstance(value, int)]
            if cleaned:
                key = " ".join(str(value) for value in cleaned)
                if note_reading:
                    return f"note_reading:{key}"
                return f"score_copy:{key}" if score_copy else key
    for field in ("acceptedNotes", "detectedNotes", "scoreNotes"):
        key = _review_sequence_key(_clean_note_names(item.get(field)))
        if key:
            if note_reading:
                return f"note_reading:{key}"
            return f"score_copy:{key}" if score_copy else key
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


def _large_leap_count(values: list[int]) -> int:
    return sum(1 for left, right in zip(values, values[1:]) if abs(right - left) >= 12)


def _midi_range(values: list[int]) -> int:
    return max(values) - min(values) if values else 0


def _review_note_metrics(notes: list[dict[str, Any]]) -> dict[str, Any]:
    values = _midi_values(notes)
    length = len(values)
    distinct_midi = len(set(values))
    distinct_pitch_class = _pitch_class_count(notes)
    adjacent_duplicates = _adjacent_duplicate_count(values)
    max_duplicate_run = _max_consecutive_duplicate(values)
    large_leaps = _large_leap_count(values)
    midi_range = _midi_range(values)
    duplicate_ratio = adjacent_duplicates / max(1, length - 1)
    audio_agreed = sum(1 for note in notes if note.get("audioAgreement") is True)
    spectral = sum(1 for note in notes if "spectral_onset" in (note.get("agreementSources") or []))
    confidence = sum(float(note.get("confidence") or 0.0) for note in notes) / max(1, len(notes))
    repetition_penalty = (adjacent_duplicates * 8.0) + (max(0, max_duplicate_run - 2) * 12.0) + (duplicate_ratio * 18.0)
    unstable_fast_penalty = (large_leaps * 9.0) + max(0, midi_range - 24) * 1.5
    phrase_shape_bonus = min(length, 10) * 2.0
    quality = (
        (distinct_midi * 12.0)
        + (distinct_pitch_class * 4.0)
        + phrase_shape_bonus
        + (audio_agreed * 1.5)
        + spectral
        + (confidence * 2.0)
        - repetition_penalty
        - unstable_fast_penalty
    )
    return {
        "detectedMidiDistinctCount": distinct_midi,
        "distinctPitchClassCount": distinct_pitch_class,
        "adjacentDuplicateCount": adjacent_duplicates,
        "maxConsecutiveDuplicateMidi": max_duplicate_run,
        "largeLeapCount": large_leaps,
        "detectedMidiRange": midi_range,
        "duplicateRatio": round(duplicate_ratio, 3),
        "repetitionPenalty": round(repetition_penalty, 3),
        "unstableFastPenalty": round(unstable_fast_penalty, 3),
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
    if length >= 8 and int(metrics["largeLeapCount"]) >= 4 and int(metrics["detectedMidiRange"]) >= 24:
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
            "scoreNotes": payload.get("scoreNotes"),
            "scoreLocation": payload.get("scoreLocation"),
            "sourceReviewImageUrl": payload.get("sourceReviewImageUrl") or payload.get("scoreImageUrl"),
            "pieceTitle": payload.get("pieceTitle"),
            "reviewKind": payload.get("reviewKind"),
            "reviewTask": payload.get("reviewTask"),
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
        "reviewTrainingLaneLabel": "transcription-alan",
        "reviewQuestion": "Do the displayed notes match the paired audio? Reject if one note is wrong.",
        "acceptanceRule": "Accept transcription-alan only if every displayed note matches the paired audio after adjacent duplicate detections are collapsed.",
        "rejectionRule": "Reject transcription-alan if any displayed note is wrong, missing, extra, out of order, or not audible in the paired clip.",
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
        "reviewTrainingLaneLabel": "transcription-alan",
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
        "acceptanceRule": "Accept transcription-alan only if every displayed audio/transcription note matches the paired audio after adjacent duplicate detections are collapsed.",
        "rejectionRule": "Reject transcription-alan if any note is wrong, missing, extra, out of order, or the score location is not the same phrase.",
    }
    payload["reviewItemId"] = _candidate_id(payload)
    return payload


def _score_copy_candidate_from_snippet(
    record: dict[str, Any],
    piece: dict[str, Any],
    target: dict[str, Any],
    snippet: dict[str, Any],
) -> dict[str, Any]:
    source_image = _clean(snippet.get("sourceReviewImageUrl") or snippet.get("imageUrl") or snippet.get("scoreImageUrl"))
    source_abc = _clean(snippet.get("sourceNotationAbc") or snippet.get("scoreNotationAbc"))
    copy_abc = _clean(snippet.get("copyNotationAbc") or source_abc)
    source_events = snippet.get("sourceNotationEvents") if isinstance(snippet.get("sourceNotationEvents"), list) else []
    copy_events = snippet.get("copyNotationEvents") if isinstance(snippet.get("copyNotationEvents"), list) else source_events
    score_notes = _score_note_names(
        snippet.get("visibleScoreExactNoteSequence"),
        snippet.get("acceptedScoreSpellingSequence"),
        snippet.get("scoreExactNoteSequenceLabel"),
        snippet.get("scoreNotes"),
    )
    if not (source_image or source_abc or source_events) or not score_notes:
        return {}
    score_midi = _normalized_review_midi_sequence(score_notes)
    if not score_midi:
        return {}
    verified_source_notes = _score_note_names(
        snippet.get("verifiedSourceNoteSequence"),
        snippet.get("sourceVerifiedNoteSequence"),
        snippet.get("sourceCropVerifiedNoteSequence"),
    )
    verified_source_midi = _normalized_review_midi_sequence(verified_source_notes)
    blocked_tokens = ("rejected", "blocked", "mismatch", "failed", "wrong")
    source_status_text = " ".join(
        str(snippet.get(key) or "")
        for key in (
            "status",
            "verification",
            "sourceStatus",
            "sourceReviewKind",
            "rejectionReason",
            "verificationLimit",
        )
    ).lower()
    source_copy_review_ready = bool(
        snippet.get("sourceCopyReviewReady") is True
        and source_image
        and verified_source_midi
        and verified_source_midi == score_midi
        and not bool(snippet.get("sourceCropRejected"))
        and not bool(snippet.get("sourceImageRequiredForOriginalScore"))
        and not any(token in source_status_text for token in blocked_tokens)
    )
    source_copy_best_effort_ready = bool(
        snippet.get("sourceCopyBestEffortReviewReady") is True
        and source_image
        and score_midi
        and bool(record.get("trainingOnly") or snippet.get("sourcePieceTrainingOnly"))
        and not bool(snippet.get("sourceCropRejected"))
        and not bool(snippet.get("sourceImageRequiredForOriginalScore"))
        and not any(token in source_status_text for token in blocked_tokens)
    )
    if not (source_copy_review_ready or source_copy_best_effort_ready):
        return {}
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    score_source = _clean(
        target.get("scoreSource")
        or target.get("scoreUrl")
        or score_config.get("source")
        or score_config.get("sourcePdfLocalPath")
        or "source score"
    )
    location = _clean(snippet.get("measureLabel") or snippet.get("label") or snippet.get("scoreLocation"))
    notation_aspects = snippet.get("notationCopyAspects") if isinstance(snippet.get("notationCopyAspects"), list) else NOTATION_COPY_ASPECTS
    source_status = _clean(snippet.get("sourceStatus") or snippet.get("status") or snippet.get("verification"))
    source_review_kind = _clean(snippet.get("sourceReviewKind"))
    training_only = bool(record.get("trainingOnly") or snippet.get("sourcePieceTrainingOnly"))
    pitch_skeleton_only = bool(snippet.get("sourceCopyPitchSkeletonOnly"))
    explicit_original_score_snippet = bool(snippet.get("originalScoreSnippet") is True and source_image)
    source_text = f"{source_image} {score_source} {source_status} {source_review_kind}".lower()
    original_score_snippet = bool(
        source_image
        and not source_image.lower().startswith("data:")
        and (
            explicit_original_score_snippet
            or (
                not training_only
                and "training" not in source_text
            )
        )
        and "generated" not in source_text
        and "symbolic" not in source_text
    )
    payload = {
        "reviewKind": "score_copy_candidate",
        "reviewType": "score_copy",
        "acceptanceMode": "binary_exact_claim",
        "practiceDay": _clean(record.get("practiceDay")),
        "trainingOnly": training_only,
        "pieceTitle": _clean(piece.get("title") or target.get("work") or score_config.get("title")),
        "sourceTitle": _clean(piece.get("sourceTitle") or score_config.get("title")),
        "sourceUrl": _clean(
            snippet.get("sourceUrl")
            or piece.get("sourceUrl")
            or target.get("scoreUrl")
            or target.get("scorePdfUrl")
        ),
        "sampleId": "",
        "startSeconds": 0.0,
        "endSeconds": 0.0,
        "detectedNotes": score_notes,
        "acceptedNotes": score_notes,
        "detectedMidiSequence": score_midi,
        "normalizedDetectedMidiSequence": score_midi,
        "detectedNoteCount": len(score_notes),
        "scoreNotes": score_notes,
        "sourceScoreNotes": score_notes,
        "normalizedScoreMidiSequence": score_midi,
        "scoreAgreement": False,
        "scoreAgreementStatus": "score_copy_review",
        "reviewTrainingLane": "score_copy",
        "reviewTrainingLaneLabel": "score-transcription",
        "scoreSource": score_source,
        "scoreAssetId": _clean(target.get("scoreAssetId") or score_config.get("sourceId")),
        "scoreLocation": location,
        "scoreStatus": _clean(snippet.get("status") or snippet.get("verification")),
        "sourceStatus": source_status,
        "sourceReviewKind": source_review_kind,
        "sourceCopyReviewReady": source_copy_review_ready,
        "sourceCopyBestEffortReviewReady": source_copy_best_effort_ready,
        "bestEffortScoreTranscription": bool(snippet.get("bestEffortScoreTranscription") or source_copy_best_effort_ready),
        "evidenceLevel": "best_effort_review_only" if source_copy_best_effort_ready else "verified_source_copy_review",
        "evidenceBoundary": (
            "score-transcription training only; accept/reject feedback required before this can teach the source-copy model"
            if source_copy_best_effort_ready
            else "verified source-copy review candidate"
        ),
        "scoreImageUrl": source_image,
        "sourceReviewImageUrl": source_image,
        "sourceImageUrl": _clean(snippet.get("imageUrl")) or source_image,
        "originalScoreSnippet": original_score_snippet,
        "sourceImageRequiredForOriginalScore": not original_score_snippet,
        "sourceNotationAbc": source_abc,
        "copyNotationAbc": copy_abc,
        "sourceNotationEvents": source_events,
        "copyNotationEvents": copy_events,
        "notationCopyAspects": notation_aspects,
        "keySignature": target.get("keySignature") if isinstance(target.get("keySignature"), dict) else {},
        "clip": {},
        "defaultStatus": "pending_review",
        "reviewTask": "score_copy_pitch_skeleton" if pitch_skeleton_only else "score_copy_exact_notation",
        "trainingTask": "score_copy_pitch_skeleton" if pitch_skeleton_only else "score_copy_exact_notation",
        "binaryReview": True,
        "binaryOnly": True,
        "sourceCopyOnly": True,
        "notationCopyOnly": True,
        "sourceCopyPitchSkeletonOnly": pitch_skeleton_only,
        "sourcePieceTrainingOnly": bool(snippet.get("sourcePieceTrainingOnly")),
        "reviewQuestion": (
            "Do the score-transcription notes match the source crop? Reject if one note is wrong."
            if pitch_skeleton_only
            else "Does score-transcription match the source notation? Reject if one visible detail is wrong."
        ),
        "acceptanceRule": (
            "Accept score-transcription if the displayed pitch, octave, accidental, and note order match the source crop; ignore engraving style in this lane."
            if pitch_skeleton_only
            else "Accept score-transcription only if Curtis copied the source notation exactly: pitch, octave, accidental, rhythm value, rest, beam, tuplet, stem direction, notehead, spacing, slur/tie, and source range."
        ),
        "rejectionRule": (
            "Reject score-transcription if any copied pitch, accidental, octave, or note order is wrong."
            if pitch_skeleton_only
            else "Reject score-transcription if any copied note, accidental, octave, duration, rest, beam, tuplet, stem direction, notehead, spacing, slur/tie, order, or source range is wrong."
        ),
    }
    payload["reviewItemId"] = _candidate_id(payload)
    return payload


def _score_copy_candidates(record: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    pieces = record.get("pieces") if isinstance(record.get("pieces"), list) else []
    for piece in pieces:
        if not isinstance(piece, dict):
            continue
        target = piece.get("score") if isinstance(piece.get("score"), dict) else {}
        score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
        snippets = score_config.get("sourceSnippets") if isinstance(score_config.get("sourceSnippets"), list) else []
        for snippet in snippets:
            if not isinstance(snippet, dict):
                continue
            candidate = _score_copy_candidate_from_snippet(record, piece, target, snippet)
            if candidate:
                candidates.append(candidate)
    return candidates


def _note_reading_candidate_from_score_copy(candidate: dict[str, Any]) -> dict[str, Any]:
    notes = _clean_note_names(candidate.get("sourceScoreNotes") or candidate.get("scoreNotes") or candidate.get("detectedNotes"))
    letters = _note_letters_from_notes(notes)
    if not notes or not letters:
        return {}
    payload = {
        **candidate,
        "reviewKind": "note_reading_candidate",
        "reviewType": "note_reading",
        "acceptanceMode": "typed_note_letters",
        "detectedNotes": notes,
        "acceptedNotes": notes,
        "scoreNotes": notes,
        "sourceScoreNotes": notes,
        "normalizedDetectedMidiSequence": _normalized_review_midi_sequence(notes),
        "normalizedScoreMidiSequence": _normalized_review_midi_sequence(notes),
        "detectedNoteCount": len(notes),
        "expectedNoteLetters": letters,
        "expectedNoteLetterText": " ".join(letter.lower() for letter in letters),
        "userNoteLetters": [],
        "noteLetterAnswer": "",
        "noteLetterCorrect": False,
        "noteReadingAnswerMode": "letters_only_ignore_accidentals_octaves",
        "reviewTrainingLane": "note_reading",
        "reviewTrainingLaneLabel": "note-reading",
        "reviewTask": "note_letter_reading",
        "trainingTask": "note_letter_reading",
        "sourceCopyOnly": False,
        "notationCopyOnly": False,
        "noteReadingOnly": True,
        "binaryReview": False,
        "binaryOnly": False,
        "reviewQuestion": "Write the note letters only.",
        "acceptanceRule": "Type note letters only; ignore accidentals and octave numbers.",
        "rejectionRule": "If the typed letter sequence differs from the source, Curtis stores a note-reading mismatch.",
    }
    payload.pop("reviewItemId", None)
    payload["reviewItemId"] = _candidate_id(payload)
    return payload


def _note_reading_candidates(score_copy_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for candidate in score_copy_candidates:
        note_reading = _note_reading_candidate_from_score_copy(candidate)
        if note_reading:
            candidates.append(note_reading)
    return candidates


def _queue_candidates(
    daily_records: dict[str, Any],
    *,
    adaptive: bool = False,
    include_source_copy_catalog: bool = False,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    source_records = requested_score_copy_records() if include_source_copy_catalog and not adaptive else []
    for record in source_records:
        score_copy_candidates = _score_copy_candidates(record)
        candidates.extend(score_copy_candidates)
        candidates.extend(_note_reading_candidates(score_copy_candidates))
    for record in daily_records.get("records", []) if isinstance(daily_records.get("records"), list) else []:
        if not isinstance(record, dict):
            continue
        if not adaptive:
            score_copy_candidates = _score_copy_candidates(record)
            candidates.extend(score_copy_candidates)
            candidates.extend(_note_reading_candidates(score_copy_candidates))
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
    expected_note_letters = _clean_note_letters(raw.get("expectedNoteLetters") or _note_letters_from_notes(score_notes or detected_notes))
    user_note_letters = _clean_note_letters(raw.get("userNoteLetters") or raw.get("noteLetterAnswer"))
    note_letter_correct = bool(expected_note_letters and user_note_letters and expected_note_letters == user_note_letters)
    if status == "accepted_truth" and item_type != "note_reading" and not accepted_notes:
        accepted_notes = detected_notes
    if status == "accepted_truth" and item_type != "note_reading" and not accepted_notes:
        raise ValueError("Accepted gold review items require accepted notes.")
    if item_type in {"score_phrase", "audio_score_match"} and status == "accepted_truth" and not score_notes:
        raise ValueError("Accepted score phrase labels require score notes.")
    if item_type in {"score_phrase", "audio_score_match"} and status == "accepted_truth":
        if not _normalized_review_note_agreement(accepted_notes, score_notes):
            raise ValueError("Accepted score phrase labels require normalized audio and score MIDI agreement.")
    if item_type == "score_copy" and status == "accepted_truth":
        if not score_notes:
            raise ValueError("Accepted score-transcription labels require source score notes.")
        if not _normalized_review_note_agreement(accepted_notes, score_notes):
            raise ValueError("Accepted score-transcription labels require copied notes and source notes to agree.")
    if item_type == "note_reading" and status == "accepted_truth" and not user_note_letters:
        raise ValueError("Accepted note-reading labels require typed note letters.")
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
        "sourceReviewImageUrl": _clean(raw.get("sourceReviewImageUrl")),
        "sourceImageUrl": _clean(raw.get("sourceImageUrl")),
        "originalScoreSnippet": bool(raw.get("originalScoreSnippet")),
        "sourceImageRequiredForOriginalScore": bool(raw.get("sourceImageRequiredForOriginalScore")),
        "sourceNotationAbc": _clean(raw.get("sourceNotationAbc")),
        "copyNotationAbc": _clean(raw.get("copyNotationAbc")),
        "sourceNotationEvents": raw.get("sourceNotationEvents") if isinstance(raw.get("sourceNotationEvents"), list) else [],
        "copyNotationEvents": raw.get("copyNotationEvents") if isinstance(raw.get("copyNotationEvents"), list) else [],
        "notationCopyAspects": raw.get("notationCopyAspects") if isinstance(raw.get("notationCopyAspects"), list) else [],
        "sourcePieceTrainingOnly": bool(raw.get("sourcePieceTrainingOnly")),
        "notationCopyOnly": bool(raw.get("notationCopyOnly")),
        "noteReadingOnly": bool(raw.get("noteReadingOnly") or item_type == "note_reading"),
        "detectedNotes": detected_notes,
        "acceptedNotes": accepted_notes,
        "scoreNotes": score_notes,
        "expectedNoteLetters": expected_note_letters,
        "userNoteLetters": user_note_letters,
        "noteLetterAnswer": _clean(raw.get("noteLetterAnswer")),
        "noteLetterCorrect": note_letter_correct,
        "noteReadingAnswerMode": _clean(raw.get("noteReadingAnswerMode")) or ("letters_only_ignore_accidentals_octaves" if item_type == "note_reading" else ""),
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
                "expectedNoteLetters": previous.get("expectedNoteLetters") or [],
                "userNoteLetters": previous.get("userNoteLetters") or [],
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
    if item["status"] in {"accepted_truth", "rejected_mismatch"} and item["type"] != "note_reading":
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
                "sourceReviewImageUrl": item["sourceReviewImageUrl"],
                "sourceImageUrl": item["sourceImageUrl"],
                "originalScoreSnippet": item["originalScoreSnippet"],
                "sourceImageRequiredForOriginalScore": item["sourceImageRequiredForOriginalScore"],
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
    accepted_identity_keys: set[str] = set()
    rejected_identity_keys: set[str] = set()
    accepted_intervals: list[dict[str, Any]] = []
    rejected_intervals: list[dict[str, Any]] = []
    accepted_counts: Counter[str] = Counter()
    rejected_counts: Counter[str] = Counter()
    for item in items:
        key = _item_learning_key(item)
        interval = _review_interval(item)
        if item.get("status") == "accepted_truth":
            if key:
                accepted_keys.add(key)
                accepted_counts[key] += 1
            accepted_identity_keys.update(_review_identity_keys(item))
            if interval:
                accepted_intervals.append(interval)
        elif item.get("status") == "rejected_mismatch":
            if key:
                rejected_keys.add(key)
                rejected_counts[key] += 1
            rejected_identity_keys.update(_review_identity_keys(item))
            if interval:
                rejected_intervals.append(interval)
    rejected_only = rejected_keys - accepted_keys
    rejected_identity_only = rejected_identity_keys - accepted_identity_keys
    soft_rejected: set[str] = set()
    return {
        "acceptedKeys": accepted_keys,
        "rejectedKeys": rejected_keys,
        "rejectedOnlyKeys": rejected_only,
        "softRejectedKeys": soft_rejected,
        "acceptedIdentityKeys": accepted_identity_keys,
        "rejectedIdentityKeys": rejected_identity_keys,
        "rejectedOnlyIdentityKeys": rejected_identity_only,
        "acceptedIntervals": accepted_intervals,
        "rejectedIntervals": rejected_intervals,
        "acceptedCounts": dict(accepted_counts),
        "rejectedCounts": dict(rejected_counts),
        "acceptedPatternCount": len(accepted_keys),
        "rejectedPatternCount": len(rejected_keys),
        "rejectedCandidateFingerprintCount": len(rejected_identity_keys),
        "softRejectedPatternCount": len(soft_rejected),
        "suppressionThreshold": 1,
        "suppressionRule": "Already accepted source areas are treated as covered. A rejected exact MIDI pattern, same clip/score fingerprint, or overlapping rejected clip window is removed from the active review queue unless an accepted label covers the same area.",
    }


def apply_review_learning_to_candidates(
    candidates: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_keys = profile.get("acceptedKeys") if isinstance(profile.get("acceptedKeys"), set) else set()
    rejected_only_keys = profile.get("rejectedOnlyKeys") if isinstance(profile.get("rejectedOnlyKeys"), set) else set()
    soft_rejected_keys = profile.get("softRejectedKeys") if isinstance(profile.get("softRejectedKeys"), set) else set()
    accepted_identity_keys = profile.get("acceptedIdentityKeys") if isinstance(profile.get("acceptedIdentityKeys"), set) else set()
    rejected_only_identity_keys = (
        profile.get("rejectedOnlyIdentityKeys") if isinstance(profile.get("rejectedOnlyIdentityKeys"), set) else set()
    )
    accepted_intervals = profile.get("acceptedIntervals") if isinstance(profile.get("acceptedIntervals"), list) else []
    rejected_intervals = profile.get("rejectedIntervals") if isinstance(profile.get("rejectedIntervals"), list) else []
    active: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _candidate_sequence_key(candidate)
        identity_keys = _review_identity_keys(candidate)
        rejected_identity_matches = sorted(identity_keys & rejected_only_identity_keys)
        accepted_identity_matches = sorted(identity_keys & accepted_identity_keys)
        accepted_interval_matches = _review_interval_matches(candidate, accepted_intervals, padding_seconds=0.25)
        rejected_interval_matches = (
            []
            if accepted_interval_matches
            else _review_interval_matches(candidate, rejected_intervals, padding_seconds=0.75)
        )
        accepted_area_matches = bool(accepted_identity_matches or accepted_interval_matches)
        rejected_area_matches = bool(rejected_identity_matches or rejected_interval_matches)
        status = (
            "accepted_candidate_covered"
            if accepted_area_matches
            else "rejected_candidate_hidden"
            if rejected_area_matches
            else "accepted_pattern"
            if key in accepted_keys
            else "rejected_pattern_hidden"
            if key in rejected_only_keys
            else "soft_rejected_pattern"
            if key in soft_rejected_keys
            else "new_pattern"
        )
        enriched = {
            **candidate,
            "reviewLearningKey": key,
            "reviewCandidateFingerprintKeys": sorted(identity_keys),
            "reviewCandidateAcceptedFingerprintKeys": accepted_identity_matches,
            "reviewCandidateRejectedFingerprintKeys": rejected_identity_matches,
            "reviewCandidateAcceptedOverlapKeys": accepted_interval_matches,
            "reviewCandidateRejectedOverlapKeys": rejected_interval_matches,
            "reviewLearningStatus": status,
            "reviewLearningReliability": "noisy_human_signal",
        }
        if accepted_area_matches or rejected_area_matches or (key and key in rejected_only_keys):
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
        learning_rank,
        0
        if item.get("reviewKind") == "score_copy_candidate"
        else 1
        if item.get("reviewKind") == "score_phrase_candidate"
        else 2
        if item.get("reviewKind") == "long_audio_phrase_candidate"
        else 3,
        0 if item.get("scoreAgreement") is True else 1,
        -float(item.get("adaptiveQualityScore") or 0.0),
        float(item.get("repetitionPenalty") or 0.0),
        float(item.get("unstableFastPenalty") or 0.0),
        -int(item.get("detectedMidiDistinctCount") or 0),
        -int(item.get("audioAgreementCount") or 0),
        -int(item.get("detectedNoteCount") or 0),
        str(item.get("practiceDay") or ""),
        str(item.get("sampleId") or ""),
    )


def build_gold_review_loop(
    state: dict[str, Any],
    daily_records: dict[str, Any],
    *,
    limit: int = 10,
    include_source_copy_catalog: bool = False,
) -> dict[str, Any]:
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
    accepted_score_copy = [
        item for item in items if item.get("status") == "accepted_truth" and item.get("type") == "score_copy"
    ]
    reviewed_ids = {_clean(item.get("reviewItemId")) for item in items if _clean(item.get("reviewItemId"))}
    learning_profile = build_review_learning_profile(items)
    raw_candidates = [
        candidate
        for candidate in _queue_candidates(daily_records, include_source_copy_catalog=include_source_copy_catalog)
        if _clean(candidate.get("reviewItemId")) not in reviewed_ids
    ]
    candidates, suppressed_candidates = apply_review_learning_to_candidates(raw_candidates, learning_profile)
    adaptive_candidates: list[dict[str, Any]] = []
    adaptive_suppressed_candidates: list[dict[str, Any]] = []
    adaptive_candidate_pool_count = 0
    adaptive_mode = False
    primary_audio_candidates = [item for item in candidates if not _is_score_copy_item(item) and not _is_note_reading_item(item)]
    suppressed_audio_candidates = [
        item for item in suppressed_candidates if not _is_score_copy_item(item) and not _is_note_reading_item(item)
    ]
    primary_queue_is_only_soft_rejected = len(primary_audio_candidates) >= 2 and all(
        item.get("reviewLearningStatus") == "soft_rejected_pattern" for item in primary_audio_candidates
    )
    primary_queue_suppressed_by_learning = not primary_audio_candidates and bool(suppressed_audio_candidates)
    primary_queue_low = 0 < len(primary_audio_candidates) < MIN_ACTIVE_AUDIO_REVIEW_QUEUE
    if not primary_audio_candidates or primary_queue_is_only_soft_rejected or (include_source_copy_catalog and primary_queue_low):
        raw_adaptive_candidates = [
            candidate
            for candidate in _queue_candidates(daily_records, adaptive=True, include_source_copy_catalog=False)
            if _clean(candidate.get("reviewItemId")) not in reviewed_ids
        ]
        adaptive_candidates, adaptive_suppressed_candidates = apply_review_learning_to_candidates(raw_adaptive_candidates, learning_profile)
        adaptive_candidates.sort(key=_review_candidate_rank)
        adaptive_candidate_pool_count = len(adaptive_candidates)
        adaptive_candidates = adaptive_candidates[:MAX_ADAPTIVE_REVIEW_QUEUE]
        if adaptive_candidates:
            candidates = [*adaptive_candidates, *candidates]
            adaptive_mode = True
    score_candidates = [item for item in candidates if item.get("reviewTask") == "audio_score_exact_match"]
    score_copy_candidates = [item for item in candidates if _is_score_copy_task(item.get("reviewTask"))]
    note_reading_candidates = [item for item in candidates if _is_note_reading_task(item.get("reviewTask"))]
    audio_candidates = [item for item in candidates if not _is_score_copy_item(item) and not _is_note_reading_item(item)]
    source_copy_training_candidates = [
        item for item in score_copy_candidates if item.get("sourcePieceTrainingOnly") or item.get("trainingOnly")
    ]
    source_score_snippets = requested_original_score_snippets() if include_source_copy_catalog else []
    source_score_ready_snippets = [
        item for item in source_score_snippets if item.get("originalScoreSnippet") is True and item.get("imageUrl")
    ]
    exact_score_candidates = [item for item in score_candidates if item.get("scoreAgreement") is True]
    long_candidates = [item for item in candidates if item.get("reviewKind") == "long_audio_phrase_candidate"]
    candidates.sort(key=_review_candidate_rank)
    truth_progress = build_truth_progress(state)
    training_set = build_gold_training_set(items)
    rejection_insights = build_rejection_insights(items)
    suppressed_all = [*suppressed_candidates, *adaptive_suppressed_candidates]
    hidden_reviewed_keys = {
        str(item.get("reviewLearningKey") or "")
        for item in suppressed_all
        if str(item.get("reviewLearningKey") or "")
    }
    hidden_rejected_keys = {
        str(item.get("reviewLearningKey") or "")
        for item in suppressed_all
        if str(item.get("reviewLearningStatus") or "").startswith("rejected")
        if str(item.get("reviewLearningKey") or "")
    }
    hidden_reviewed_fingerprint_keys = {
        str(key)
        for item in suppressed_all
        for key in [
            *(
                item.get("reviewCandidateAcceptedFingerprintKeys", [])
                if isinstance(item.get("reviewCandidateAcceptedFingerprintKeys"), list)
                else []
            ),
            *(
                item.get("reviewCandidateAcceptedOverlapKeys", [])
                if isinstance(item.get("reviewCandidateAcceptedOverlapKeys"), list)
                else []
            ),
            *(
                item.get("reviewCandidateRejectedFingerprintKeys", [])
                if isinstance(item.get("reviewCandidateRejectedFingerprintKeys"), list)
                else []
            ),
            *(
                item.get("reviewCandidateRejectedOverlapKeys", [])
                if isinstance(item.get("reviewCandidateRejectedOverlapKeys"), list)
                else []
            ),
        ]
        if str(key)
    }
    hidden_rejected_fingerprint_keys = {
        str(key)
        for item in suppressed_all
        if str(item.get("reviewLearningStatus") or "").startswith("rejected")
        for key in [
            *(item.get("reviewCandidateRejectedFingerprintKeys", []) if isinstance(item.get("reviewCandidateRejectedFingerprintKeys"), list) else []),
            *(item.get("reviewCandidateRejectedOverlapKeys", []) if isinstance(item.get("reviewCandidateRejectedOverlapKeys"), list) else []),
        ]
        if str(key)
    }
    suppressed_statuses = {str(item.get("reviewLearningStatus") or "") for item in suppressed_all}
    current_batch_is_covered = bool(suppressed_all) and suppressed_statuses <= {"accepted_candidate_covered"}
    queue_status = (
        "adaptive_review_ready"
        if adaptive_mode
        else "review_queue_ready"
        if candidates
        else "current_batch_covered_by_review"
        if current_batch_is_covered
        else "current_batch_exhausted_by_learning"
        if suppressed_all
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
        "acceptedScoreCopyCount": len(accepted_score_copy),
        "scoreReadyTruthCount": int(truth_progress.get("scoreReadyTruthCount") or 0),
        "acceptedEvidenceReadyCount": int(truth_progress.get("acceptedEvidenceReadyCount") or 0),
        "queueCount": len(candidates),
        "queueStatus": queue_status,
        "scoreQueueCount": len(score_candidates),
        "scoreCopyQueueCount": len(score_copy_candidates),
        "noteReadingQueueCount": len(note_reading_candidates),
        "audioQueueCount": len(audio_candidates),
        "transcriptionAlanQueueCount": len(audio_candidates),
        "scoreTranscriptionQueueCount": len(score_copy_candidates),
        "noteReadingTrainingQueueCount": len(note_reading_candidates),
        "sourceCopyTrainingQueueCount": len(source_copy_training_candidates),
        "sourceScoreSnippetCount": len(source_score_snippets),
        "sourceScoreReadySnippetCount": len(source_score_ready_snippets),
        "scoreExactAgreementQueueCount": len(exact_score_candidates),
        "longPhraseQueueCount": len(long_candidates),
        "rawQueueCount": len(raw_candidates),
        "adaptiveMode": adaptive_mode,
        "adaptiveReason": (
            "primary_queue_suppressed_by_learning"
            if primary_queue_suppressed_by_learning and adaptive_mode
            else "primary_queue_only_soft_rejected"
            if primary_queue_is_only_soft_rejected and adaptive_mode
            else "primary_queue_low"
            if primary_queue_low and adaptive_mode
            else "primary_queue_empty"
            if adaptive_mode
            else ""
        ),
        "adaptiveCandidateCount": len(adaptive_candidates),
        "adaptiveCandidatePoolCount": adaptive_candidate_pool_count,
        "adaptiveQueueLimit": MAX_ADAPTIVE_REVIEW_QUEUE,
        "adaptiveSuppressedByLearningCount": len(adaptive_suppressed_candidates),
        "suppressedByLearningCount": len(suppressed_candidates),
        "reviewedIds": len(reviewed_ids),
        "acceptedPatternCount": int(learning_profile.get("acceptedPatternCount") or 0),
        "rejectedPatternCount": int(learning_profile.get("rejectedPatternCount") or 0),
        "rejectedCandidateFingerprintCount": int(learning_profile.get("rejectedCandidateFingerprintCount") or 0),
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
        "trainingScoreCopyExampleCount": int(training_set.get("scoreCopyExampleCount") or 0),
        "trainingPositiveScoreCopyExampleCount": int(training_set.get("positiveScoreCopyExampleCount") or 0),
        "trainingNegativeScoreCopyExampleCount": int(training_set.get("negativeScoreCopyExampleCount") or 0),
        "trainingNoteReadingExampleCount": int(training_set.get("noteReadingExampleCount") or 0),
        "trainingPositiveNoteReadingExampleCount": int(training_set.get("positiveNoteReadingExampleCount") or 0),
        "trainingNegativeNoteReadingExampleCount": int(training_set.get("negativeNoteReadingExampleCount") or 0),
        "trainingLanes": [
            {
                "id": "transcription-alan",
                "label": "transcription-alan",
                "queueKey": "audioQueue",
                "queueCount": len(audio_candidates),
                "trainingTask": "audio_to_transcription_review",
            },
            {
                "id": "score-transcription",
                "label": "score-transcription",
                "queueKey": "scoreCopyQueue",
                "queueCount": len(score_copy_candidates),
                "trainingTask": "source_score_to_transcription_review",
                "gate": "verified source crop notes must match copied notes",
            },
            {
                "id": "note-reading",
                "label": "note-reading",
                "queueKey": "noteReadingQueue",
                "queueCount": len(note_reading_candidates),
                "trainingTask": "source_score_note_letter_entry",
                "gate": "type note letters only",
            },
        ],
        "rejectionInsights": rejection_insights,
        "reviewLearningStatus": "reducing_review_load" if suppressed_all else "learning_no_suppression_yet",
        "reviewLearningRule": learning_profile.get("suppressionRule") or "",
        "rejectionDigest": {
            "status": queue_status,
            "hiddenReviewedPatternCount": len(hidden_reviewed_keys),
            "hiddenRejectedPatternCount": len(hidden_rejected_keys),
            "hiddenReviewedCandidateFingerprintCount": len(hidden_reviewed_fingerprint_keys),
            "hiddenRejectedCandidateFingerprintCount": len(hidden_rejected_fingerprint_keys),
            "hiddenReviewedCandidateCount": len(suppressed_all),
            "hiddenRejectedCandidateCount": len(
                [item for item in suppressed_all if str(item.get("reviewLearningStatus") or "").startswith("rejected")]
            ),
            "rejectedPatternCount": int(learning_profile.get("rejectedPatternCount") or 0),
            "softRejectedPatternCount": int(learning_profile.get("softRejectedPatternCount") or 0),
            "message": (
                "Adaptive review is mining fresh windows from analyzed audio while skipping covered source areas and rejected patterns."
                if queue_status == "adaptive_review_ready"
                else
                "Current review batch is already covered by accepted labels."
                if queue_status == "current_batch_covered_by_review"
                else
                "Current review batch is exhausted; remaining candidates repeat covered source areas or rejected note patterns."
                if queue_status == "current_batch_exhausted_by_learning"
                else "Review the next queued clip."
                if queue_status == "review_queue_ready"
                else "No review candidates are available from current analyzed evidence."
            ),
        },
        "itemsByType": dict(by_type),
        "itemsByStatus": dict(by_status),
        "queue": candidates[: max(0, int(limit))],
        "audioQueue": audio_candidates[: max(4, min(12, int(limit)))],
        "scoreCopyQueue": score_copy_candidates[: max(4, min(12, int(limit)))],
        "noteReadingQueue": note_reading_candidates[: max(4, min(12, int(limit)))],
        "sourceScoreSnippets": source_score_snippets,
        "suppressedQueuePreview": (suppressed_candidates + adaptive_suppressed_candidates)[:5],
        "recentItems": items[:8],
        "nextAction": (
            "Adaptive review is ready: keep accepting exact clips and rejecting any wrong note."
            if adaptive_mode
            else
            "Review one queued clip: accept only if the displayed claim is exact; reject if one note is wrong."
            if candidates
            else "Current batch complete: remaining candidates repeat covered source areas or rejected patterns. Generate fresh candidates from unreviewed or rescanned audio."
            if suppressed_all
            else "Gold review queue is empty for current analyzed evidence."
        ),
        "acceptanceRule": "Gold review is binary. Accept only exact displayed notes. transcription-alan labels train audio-to-notation review. score-transcription labels train source-score-to-notation review and require the visible source crop notes to match the copied notes. Accepted score evidence still requires exact audio-note and score-note MIDI agreement after consecutive duplicate detections are collapsed.",
    }
