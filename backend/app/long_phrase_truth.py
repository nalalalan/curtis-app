from __future__ import annotations

import re
from typing import Any


NOTE_CLASS_VALUES = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}

PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
DEFAULT_MAX_PHRASE_GAP_SECONDS = 3.0


def note_midi_value(note: dict[str, Any] | str) -> int | None:
    if isinstance(note, dict):
        raw_midi = note.get("midi")
        if raw_midi not in (None, ""):
            try:
                return int(float(raw_midi))
            except (TypeError, ValueError):
                return None
        value = str(note.get("note") or "").strip()
    else:
        value = str(note or "").strip()
    match = re.match(r"^([A-Ga-g])([#b]?)(-?\d+)$", value)
    if not match:
        return None
    step = match.group(1).upper()
    accidental = match.group(2).replace("b", "B").upper()
    octave = int(match.group(3))
    pitch_value = NOTE_CLASS_VALUES.get(step + accidental)
    if pitch_value is None:
        return None
    return (octave + 1) * 12 + pitch_value


def midi_pitch_class(value: int | None) -> str:
    if value is None:
        return ""
    return PITCH_CLASS_NAMES[int(value) % 12]


def note_exact_sequence(notes: list[dict[str, Any]]) -> list[str]:
    return [str(note.get("note") or "").strip() for note in notes if str(note.get("note") or "").strip()]


def note_midi_sequence(notes: list[dict[str, Any]]) -> list[int]:
    sequence: list[int] = []
    for note in notes:
        value = note_midi_value(note)
        if value is not None:
            sequence.append(value)
    return sequence


def collapse_consecutive_duplicate_midi(sequence: list[int]) -> list[int]:
    collapsed: list[int] = []
    for value in sequence:
        if collapsed and collapsed[-1] == value:
            continue
        collapsed.append(value)
    return collapsed


def note_pitch_class_sequence(notes: list[dict[str, Any]]) -> list[str]:
    return [midi_pitch_class(value) for value in note_midi_sequence(notes)]


def note_window_continuity(
    notes: list[dict[str, Any]],
    *,
    max_gap_seconds: float = DEFAULT_MAX_PHRASE_GAP_SECONDS,
) -> dict[str, Any]:
    timed_notes: list[dict[str, float]] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        try:
            start = float(note.get("startSeconds"))
        except (TypeError, ValueError):
            continue
        try:
            end = float(note.get("endSeconds"))
        except (TypeError, ValueError):
            end = start
        if end < start:
            end = start
        timed_notes.append({"start": start, "end": end})
    timed_notes = sorted(timed_notes, key=lambda item: (item["start"], item["end"]))
    if len(timed_notes) < 2:
        return {
            "continuous": True,
            "noteCount": len(timed_notes),
            "maxInterNoteGapSeconds": 0.0,
            "maxAllowedInterNoteGapSeconds": round(float(max_gap_seconds), 3),
            "largestGapAfterIndex": -1,
            "spanSeconds": 0.0,
            "soundedSeconds": 0.0,
            "limit": "",
        }

    max_gap = 0.0
    largest_gap_after = -1
    sounded = 0.0
    for index, note in enumerate(timed_notes):
        sounded += max(0.0, note["end"] - note["start"])
        if index == 0:
            continue
        previous = timed_notes[index - 1]
        gap = max(0.0, note["start"] - previous["end"])
        if gap > max_gap:
            max_gap = gap
            largest_gap_after = index - 1
    span = max(0.0, timed_notes[-1]["end"] - timed_notes[0]["start"])
    continuous = max_gap <= float(max_gap_seconds)
    return {
        "continuous": continuous,
        "noteCount": len(timed_notes),
        "maxInterNoteGapSeconds": round(max_gap, 3),
        "maxAllowedInterNoteGapSeconds": round(float(max_gap_seconds), 3),
        "largestGapAfterIndex": largest_gap_after,
        "spanSeconds": round(span, 3),
        "soundedSeconds": round(sounded, 3),
        "limit": ""
        if continuous
        else f"Exact MIDI is not accepted as one phrase because the largest internal gap is {max_gap:.3f}s.",
    }


def longest_common_contiguous_midi_run(query: list[int], reference: list[int]) -> dict[str, Any]:
    best = {"length": 0, "queryStart": 0, "referenceStart": 0}
    if not query or not reference:
        return best
    for query_index in range(len(query)):
        for reference_index in range(len(reference)):
            length = 0
            while (
                query_index + length < len(query)
                and reference_index + length < len(reference)
                and query[query_index + length] == reference[reference_index + length]
            ):
                length += 1
            if length > int(best["length"]):
                best = {"length": length, "queryStart": query_index, "referenceStart": reference_index}
    return best


def best_ordered_midi_subsequence_run(query: list[int], reference: list[int]) -> dict[str, Any]:
    best = {"length": 0, "queryStart": 0, "queryEnd": 0, "referenceStart": 0, "referenceEnd": 0}
    if not query or not reference:
        return best
    for query_start in range(len(query)):
        reference_index = 0
        run_length = 0
        reference_start = -1
        reference_end = -1
        for query_index in range(query_start, len(query)):
            found_at = -1
            while reference_index < len(reference):
                if query[query_index] == reference[reference_index]:
                    found_at = reference_index
                    break
                reference_index += 1
            if found_at < 0:
                break
            if reference_start < 0:
                reference_start = found_at
            reference_end = found_at + 1
            run_length += 1
            reference_index = found_at + 1
        if run_length > int(best["length"]):
            best = {
                "length": run_length,
                "queryStart": query_start,
                "queryEnd": query_start + run_length,
                "referenceStart": max(0, reference_start),
                "referenceEnd": max(0, reference_end),
            }
    return best


def exact_midi_phrase_gate(
    detected_notes: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    *,
    audio_agreed: bool,
    min_exact_notes: int = 5,
    require_full_query: bool = True,
    collapse_repeated_detections: bool = False,
) -> dict[str, Any]:
    query_midi = note_midi_sequence(detected_notes)
    source_midi = note_midi_sequence(source_notes)
    comparable_query_midi = collapse_consecutive_duplicate_midi(query_midi) if collapse_repeated_detections else query_midi
    comparable_source_midi = collapse_consecutive_duplicate_midi(source_midi) if collapse_repeated_detections else source_midi
    query_exact = note_exact_sequence(detected_notes)
    source_exact = note_exact_sequence(source_notes)
    query_pitch = [midi_pitch_class(value) for value in comparable_query_midi]
    source_pitch = [midi_pitch_class(value) for value in comparable_source_midi]
    if not detected_notes or not query_midi:
        status = "source_score_exact_midi_missing"
    elif len(query_midi) != len(detected_notes):
        status = "source_score_exact_midi_missing"
    elif not source_midi:
        status = "source_score_map_missing"
    else:
        status = ""
    if status:
        return {
            "accepted": False,
            "status": status,
            "bestOverlap": 0,
            "queryLength": len(query_midi),
            "referenceLength": len(source_midi),
            "comparableQueryLength": len(comparable_query_midi),
            "comparableReferenceLength": len(comparable_source_midi),
            "exactMidiChecked": False,
            "audioAgreed": bool(audio_agreed),
            "queryExactSequence": query_exact,
            "queryPitchClassSequence": query_pitch,
            "queryMidiSequence": query_midi,
            "referenceExactSequence": source_exact,
            "referencePitchClassSequence": source_pitch,
            "referenceMidiSequence": source_midi,
            "comparableQueryMidiSequence": comparable_query_midi,
            "comparableReferenceMidiSequence": comparable_source_midi,
            "bestOverlapExactSequence": [],
            "bestOverlapMidiSequence": [],
            "orderedOverlap": 0,
            "collapseRepeatedDetections": bool(collapse_repeated_detections),
        }

    contiguous = longest_common_contiguous_midi_run(comparable_query_midi, comparable_source_midi)
    ordered = best_ordered_midi_subsequence_run(comparable_query_midi, comparable_source_midi)
    overlap = int(contiguous.get("length") or 0)
    query_start = int(contiguous.get("queryStart") or 0)
    reference_start = int(contiguous.get("referenceStart") or 0)
    reference_end = reference_start + overlap
    required_overlap = (
        len(comparable_query_midi)
        if require_full_query
        else min(int(min_exact_notes), len(comparable_query_midi))
    )
    accepted = bool(audio_agreed) and len(comparable_query_midi) >= int(min_exact_notes) and overlap >= required_overlap
    status = (
        "source_score_exact_midi_sequence_verified"
        if accepted
        else "source_audio_agreement_missing"
        if not audio_agreed
        else "source_score_exact_midi_phrase_too_short"
        if len(comparable_query_midi) < int(min_exact_notes)
        else "source_score_exact_midi_sequence_not_found"
    )
    return {
        "accepted": accepted,
        "status": status,
        "bestOverlap": overlap,
        "queryStart": query_start,
        "referenceStart": reference_start,
        "referenceEnd": reference_end,
        "queryLength": len(query_midi),
        "referenceLength": len(source_midi),
        "comparableQueryLength": len(comparable_query_midi),
        "comparableReferenceLength": len(comparable_source_midi),
        "exactMidiChecked": True,
        "audioAgreed": bool(audio_agreed),
        "queryExactSequence": query_exact,
        "queryPitchClassSequence": query_pitch,
        "queryMidiSequence": query_midi,
        "referenceExactSequence": source_exact,
        "referencePitchClassSequence": source_pitch,
        "referenceMidiSequence": source_midi,
        "comparableQueryMidiSequence": comparable_query_midi,
        "comparableReferenceMidiSequence": comparable_source_midi,
        "bestOverlapExactSequence": source_exact[reference_start:reference_end],
        "bestOverlapMidiSequence": comparable_source_midi[reference_start:reference_end],
        "orderedOverlap": int(ordered.get("length") or 0),
        "orderedReferenceStart": int(ordered.get("referenceStart") or 0),
        "orderedReferenceEnd": int(ordered.get("referenceEnd") or 0),
        "minimumExactNotes": int(min_exact_notes),
        "requireFullQuery": bool(require_full_query),
        "collapseRepeatedDetections": bool(collapse_repeated_detections),
    }
