from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from .analyzer import parse_window_start
from .corrections import accepted_source_corrections, compact_text, source_key_from_item, youtube_video_id
from .reference_corpus import calibration_anchor_for_item
from .study_packets import (
    duration_seconds_label,
    practice_ledger_videos,
    source_matches,
)
from .transcription import TRANSCRIPTION_PIPELINE_VERSION


MAX_NOTATION_EVENTS = 192
MAX_NOTATION_SYSTEMS = 4
MAX_NOTATION_SYSTEM_EVENTS = 36
MAX_RECORDS = 120
MAX_CLIPS_PER_DAY = 5
MATCH_GROUP_MIN_NOTE_RUN = 1
MATCH_GROUP_MIN_DISTINCT_PITCH_CLASSES = 2
MAX_DETECTED_NOTE_SERIES_API = 16
MAX_DETECTED_NOTE_SERIES_NOTES = 96
NOTE_SERIES_MAX_GAP_SECONDS = 1.5
WEAK_TRANSCRIPTION_MIN_SECONDS = 8
DRAFT_TRANSCRIPTION_MIN_SECONDS = 30
WEAK_TRANSCRIPTION_MIN_NOTES = 12
DRAFT_TRANSCRIPTION_MIN_NOTES = 48
MICRO_TRANSCRIPTION_MIN_NOTES = 6
MICRO_TRANSCRIPTION_MAX_NOTES = 18
MICRO_TRANSCRIPTION_MIN_CONFIDENCE = 0.78
MICRO_TRANSCRIPTION_MIN_MEDIAN_CONFIDENCE = 0.84
MICRO_TRANSCRIPTION_MAX_DOMINANT_RATIO = 0.50
MICRO_TRANSCRIPTION_MAX_SAME_NOTE_RUN = 3
MICRO_TRANSCRIPTION_MIN_PITCH_CLASSES = 4
MICRO_TRANSCRIPTION_MAX_NOTE_GAP_SECONDS = 0.75
# Listening review showed the current micro extractor can still produce notation
# that does not audibly match the paired clip.
MICRO_TRANSCRIPTION_DISPLAY_ENABLED = False
MICRO_TRANSCRIPTION_DISPLAY_LIMIT = (
    "Candidate note/rhythm extraction is withheld because current clip "
    "review did not match reliably enough to display as transcription."
)
MATCHED_FRAGMENT_DISPLAY_LIMIT = (
    "Audio-checked note fragments are displayed. Score matches require pitch-class sequence agreement "
    "with a score or symbolic reference."
)
ACCEPTED_AUDIO_MATCHED_FRAGMENTS: tuple[dict[str, Any], ...] = (
    {
        "sourceVideoId": "Njh8_zq9_DM",
        "sourceTitle": "5-3-26",
        "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
        "sourceWindow": "*10545-10635",
        "sampleId": "Njh8_zq9_DM-10545",
        "note": "D4",
        "midi": 62,
        "startSeconds": 3.866,
        "endSeconds": 4.458,
        "durationSeconds": 0.592,
        "confidence": 0.961,
        "pitchStdCents": 7.0,
        "medianPitchOffsetCents": 0.0,
        "voicedFrameCount": 48,
        "detectors": ["pyin", "yin"],
        "verification": "human_accepted_audio_matched_fragment",
    },
    {
        "sourceVideoId": "Njh8_zq9_DM",
        "sourceTitle": "5-3-26",
        "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
        "sourceWindow": "*10815-10905",
        "sampleId": "Njh8_zq9_DM-10815",
        "note": "A4",
        "midi": 69,
        "startSeconds": 0.060,
        "endSeconds": 1.126,
        "durationSeconds": 1.067,
        "confidence": 0.983,
        "pitchStdCents": 1.79,
        "medianPitchOffsetCents": 0.0,
        "voicedFrameCount": 184,
        "detectors": ["pyin", "yin"],
        "verification": "strict_pyin_yin_audio_matched_fragment",
    },
)
VIOLIN_POSITIVE_VALUES = {
    "violin",
    "violin_playing",
    "violin_positive",
    "violin_confirmed",
    "confirmed_violin",
    "verified_violin",
    "verified_violin_playing",
    "human_verified_violin",
    "usable_violin",
}
NOTE_CLASS_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NOTE_CLASS_VALUES = {name: index for index, name in enumerate(NOTE_CLASS_NAMES)}
NOTE_CLASS_VALUES.update({"DB": 1, "EB": 3, "GB": 6, "AB": 8, "BB": 10})


def is_current_transcription(item: dict[str, Any]) -> bool:
    version = str(item.get("pipelineVersion") or "").strip()
    return not version or version == TRANSCRIPTION_PIPELINE_VERSION


def sample_is_violin_positive(sample: dict[str, Any]) -> bool:
    if not isinstance(sample, dict):
        return False
    if sample.get("containsViolin") is True or sample.get("violinDetected") is True:
        return True
    values = {
        str(sample.get(field) or "").strip().lower()
        for field in (
            "instrument",
            "instrumentDetected",
            "violinPresence",
            "violinStatus",
            "practiceEvidenceStatus",
            "audioEvidenceStatus",
            "evidenceQuality",
        )
    }
    return bool(values & VIOLIN_POSITIVE_VALUES)


def violin_positive_sample_ids(samples: list[dict[str, Any]]) -> set[str]:
    return {
        str(sample.get("id") or "").strip()
        for sample in samples
        if sample_is_violin_positive(sample) and str(sample.get("id") or "").strip()
    }


def item_has_violin_positive_sample(item: dict[str, Any], sample_ids: set[str]) -> bool:
    sample_id = str(item.get("sampleId") or item.get("id") or "").strip()
    return bool(sample_id and sample_id in sample_ids)


def video_match_keys(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("sourceKey") or source_key_from_item(item) or "").strip(),
        str(item.get("url") or item.get("sourceUrl") or "").strip(),
        compact_text(item.get("title") or item.get("sourceTitle")),
    }
    video_id = youtube_video_id(item.get("url") or item.get("sourceUrl") or item.get("id"))
    if video_id:
        values.add(video_id.lower())
        values.add(f"youtube:{video_id}")
    return {value for value in values if value}


def item_matches_keys(item: dict[str, Any], keys: set[str]) -> bool:
    if not item or not keys:
        return False
    item_keys = video_match_keys(item)
    signal = " ".join(
        str(item.get(field) or "")
        for field in ("id", "sampleId", "sourceKey", "sourceUrl", "url", "sourceTitle", "title")
    ).lower()
    return bool(item_keys & keys or any(key and key in signal for key in keys))


def sample_duration_seconds(sample: dict[str, Any]) -> int:
    start, end = window_bounds(sample)
    if end > start:
        return end - start
    try:
        return max(0, int(float(sample.get("durationSeconds") or 0)))
    except (TypeError, ValueError):
        return 0


def window_bounds(item: dict[str, Any]) -> tuple[int, int]:
    raw = str(item.get("window") or item.get("sourceWindow") or "")
    start, end = 0, 0
    if "*" in raw:
        try:
            parts = raw.split("*", 1)[1].split("-", 1)
            start = int(float(parts[0]))
            end = int(float(parts[1]))
        except (IndexError, TypeError, ValueError):
            start, end = 0, 0
    if not start:
        try:
            start = int(float(item.get("startSeconds") or item.get("sourceStartSeconds") or 0))
        except (TypeError, ValueError):
            start = 0
    if not end:
        try:
            end = int(float(item.get("endSeconds") or item.get("sourceEndSeconds") or 0))
        except (TypeError, ValueError):
            end = 0
    if end < start:
        end = 0
    return start, end


def source_window_label(start: int, end: int) -> str:
    return f"{start}-{end}" if end > start else ""


def sample_by_id(media_samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    samples: dict[str, dict[str, Any]] = {}
    for sample in media_samples:
        sample_id = str(sample.get("id") or "").strip()
        if sample_id and sample_id not in samples:
            samples[sample_id] = sample
    return samples


def clip_media_fields(item: dict[str, Any], samples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sample_id = str(item.get("sampleId") or item.get("id") or "").strip()
    sample = samples.get(sample_id, {})
    if not sample:
        return {"sampleId": sample_id}
    sample_start, _ = window_bounds(sample)
    start, end = window_bounds(item)
    local_start = max(0, start - sample_start) if start else 0
    local_end = max(local_start, end - sample_start) if end else 0
    return {
        "sampleId": sample_id,
        "mediaUrl": f"/api/curtis/media/sample/{sample_id}",
        "localStartSeconds": local_start,
        "localEndSeconds": local_end,
    }


def note_duration_kind(seconds: float, tempo_bpm: float) -> str:
    beat_seconds = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5
    beats = max(0.125, seconds / beat_seconds)
    if beats <= 0.38:
        return "sixteenth"
    if beats <= 0.75:
        return "eighth"
    if beats <= 1.45:
        return "quarter"
    if beats <= 2.6:
        return "half"
    return "whole"


def notation_events(transcriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for transcription in transcriptions:
        notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
        tempo = float(transcription.get("tempoBpm") or 0.0)
        source_start = parse_window_start(str(transcription.get("sourceWindow") or ""))
        sample_id = str(transcription.get("sampleId") or "").strip()
        media_url = f"/api/curtis/media/sample/{sample_id}" if sample_id else ""
        source_title = str(transcription.get("sourceTitle") or "").strip()
        previous_end = 0.0
        for note in notes:
            if not isinstance(note, dict):
                continue
            start = float(note.get("startSeconds") or 0.0)
            end = float(note.get("endSeconds") or start)
            duration = max(0.0, float(note.get("durationSeconds") or (end - start)))
            if start - previous_end > 0.35 and not note.get("strictAudioWindow"):
                rest_seconds = start - previous_end
                events.append(
                    {
                        "kind": "rest",
                        "durationSeconds": round(rest_seconds, 3),
                        "durationKind": note_duration_kind(rest_seconds, tempo),
                        "uncertain": False,
                        "sampleId": sample_id,
                        "mediaUrl": media_url,
                        "sourceTitle": source_title,
                        "sourceStartSeconds": round(source_start + previous_end, 3),
                        "sourceEndSeconds": round(source_start + start, 3),
                        "localStartSeconds": round(previous_end, 3),
                        "localEndSeconds": round(start, 3),
                    }
                )
            note_name = str(note.get("note") or "").strip()
            if not note_name:
                continue
            confidence = float(note.get("confidence") or 0.0)
            events.append(
                {
                    "kind": "note",
                    "note": note_name,
                    "midi": note.get("midi"),
                    "rawNote": note.get("rawNote") if note.get("rawNote") else "",
                    "rawMidi": note.get("rawMidi") if note.get("rawMidi") else "",
                    "sourceStartSeconds": round(source_start + start, 3),
                    "sourceEndSeconds": round(source_start + end, 3),
                    "localStartSeconds": round(start, 3),
                    "localEndSeconds": round(end, 3),
                    "sampleId": sample_id,
                    "mediaUrl": media_url,
                    "sourceTitle": source_title,
                    "durationSeconds": round(duration, 3),
                    "durationKind": str(note.get("durationKind") or note_duration_kind(duration, tempo)),
                    "confidence": round(confidence, 3),
                    "uncertain": bool(note.get("uncertain")) or confidence < 0.62,
                    "uncertaintyReasons": note.get("uncertaintyReasons") if isinstance(note.get("uncertaintyReasons"), list) else [],
                    "audioMatchedFragment": bool(note.get("audioMatchedFragment")),
                    "strictAudioWindow": bool(note.get("strictAudioWindow")),
                }
            )
            previous_end = max(previous_end, end)
            if len(events) >= MAX_NOTATION_EVENTS:
                return events
    return events


def notation_system_payload(events: list[dict[str, Any]], index: int) -> dict[str, Any]:
    notes = [event for event in events if event.get("kind") == "note"]
    starts = [
        float(event.get("sourceStartSeconds"))
        for event in notes
        if event.get("sourceStartSeconds") is not None
    ]
    ends = [
        float(event.get("sourceEndSeconds"))
        for event in notes
        if event.get("sourceEndSeconds") is not None
    ]
    start = min(starts) if starts else 0.0
    end = max(ends) if ends else 0.0
    uncertain = sum(1 for event in notes if event.get("uncertain"))
    playable_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("mediaUrl") and event.get("sampleId")
    ]
    clip: dict[str, Any] = {}
    if playable_events:
        first = playable_events[0]
        sample_id = str(first.get("sampleId") or "")
        media_url = str(first.get("mediaUrl") or "")
        source_title = str(first.get("sourceTitle") or "")
        local_starts = [
            float(event.get("localStartSeconds"))
            for event in playable_events
            if event.get("sampleId") == sample_id and event.get("localStartSeconds") is not None
        ]
        local_ends = [
            float(event.get("localEndSeconds"))
            for event in playable_events
            if event.get("sampleId") == sample_id and event.get("localEndSeconds") is not None
        ]
        source_starts = [
            float(event.get("sourceStartSeconds"))
            for event in playable_events
            if event.get("sampleId") == sample_id and event.get("sourceStartSeconds") is not None
        ]
        source_ends = [
            float(event.get("sourceEndSeconds"))
            for event in playable_events
            if event.get("sampleId") == sample_id and event.get("sourceEndSeconds") is not None
        ]
        if local_starts and local_ends:
            strict_window = any(bool(event.get("strictAudioWindow")) for event in playable_events)
            padding = 0.0 if strict_window else 0.35
            minimum_clip_seconds = 0.0 if strict_window else 0.75
            local_start = max(0.0, min(local_starts) - padding)
            local_end = max(local_start + minimum_clip_seconds, max(local_ends) + padding)
            source_clip_start = min(source_starts) if source_starts else 0.0
            source_clip_end = max(source_ends) if source_ends else 0.0
            clip = {
                "type": "audio_evidence_window",
                "sampleId": sample_id,
                "mediaUrl": media_url,
                "audioUrl": f"{media_url}/clip?start={local_start:.3f}&end={local_end:.3f}" if strict_window else "",
                "sourceTitle": source_title,
                "localStartSeconds": round(local_start, 3),
                "localEndSeconds": round(local_end, 3),
                "sourceStartSeconds": round(source_clip_start, 3) if source_clip_start else 0,
                "sourceEndSeconds": round(source_clip_end, 3) if source_clip_end else 0,
                "startSeconds": round(source_clip_start, 3) if source_clip_start else 0,
                "endSeconds": round(source_clip_end, 3) if source_clip_end else 0,
                "durationSeconds": round(max(0.0, local_end - local_start), 3),
                "label": f"Audio for line {index}",
            }
    return {
        "id": f"system-{index}",
        "label": f"Line {index}",
        "eventCount": len(events),
        "noteCount": len(notes),
        "uncertainNoteCount": uncertain,
        "startSeconds": round(start, 3) if start else 0,
        "endSeconds": round(end, 3) if end else 0,
        "sourceWindow": source_window_label(int(start), int(end)) if end > start else "",
        "clip": clip,
        "events": events,
        "limit": "Audio evidence from the same sample. This line renders only after a short note/rhythm run passes strict audio-agreement checks.",
    }


def notation_systems(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    systems: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_notes = 0
    current_sample_id = ""

    def flush() -> None:
        nonlocal current, current_notes, current_sample_id
        if not current or len(systems) >= MAX_NOTATION_SYSTEMS:
            current = []
            current_notes = 0
            current_sample_id = ""
            return
        systems.append(notation_system_payload(current, len(systems) + 1))
        current = []
        current_notes = 0
        current_sample_id = ""

    for event in events:
        if len(systems) >= MAX_NOTATION_SYSTEMS:
            break
        if not isinstance(event, dict):
            continue
        sample_id = str(event.get("sampleId") or "")
        if current and sample_id and current_sample_id and sample_id != current_sample_id:
            flush()
        if not current_sample_id and sample_id:
            current_sample_id = sample_id
        current.append(event)
        if event.get("kind") == "note":
            current_notes += 1
        is_restart_rest = (
            event.get("kind") == "rest"
            and float(event.get("durationSeconds") or 0.0) >= 0.65
            and current_notes >= 6
        )
        if is_restart_rest or (len(current) >= MAX_NOTATION_SYSTEM_EVENTS and current_notes >= 4):
            flush()
    flush()
    return systems


def notation_display_state(
    notation: list[dict[str, Any]],
    systems: list[dict[str, Any]],
    detected_note_count: int,
) -> dict[str, Any]:
    note_events = sum(1 for event in notation if event.get("kind") == "note")
    rendered_events = sum(int(system.get("eventCount") or 0) for system in systems)
    rendered_notes = sum(int(system.get("noteCount") or 0) for system in systems)
    api_omitted_notes = max(0, detected_note_count - note_events)
    display_omitted_events = max(0, len(notation) - rendered_events)
    return {
        "eventCount": len(notation),
        "notationEventCount": len(notation),
        "renderedEventCount": rendered_events,
        "renderedNoteCount": rendered_notes,
        "detectedPitchEventCount": note_events,
        "hiddenPitchEventCount": 0,
        "rejectedMachinePitchEventCount": note_events,
        "remainingEventCount": display_omitted_events,
        "omittedDetectedNoteCount": api_omitted_notes,
        "notationSystems": systems,
        "displayNotation": False,
        "transcriptionReady": False,
        "displayLimit": (
            f"{rendered_notes} detected pitch events are kept out of notation until verified"
            + (f"; {api_omitted_notes} detected pitch events are outside the API event slice" if api_omitted_notes else "")
            + "."
        ),
    }


NOTE_CLASS_BY_NAME = {
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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def note_midi_value(note: dict[str, Any]) -> int | None:
    try:
        midi = int(note.get("midi"))
        return midi if 0 <= midi <= 127 else None
    except (TypeError, ValueError):
        pass
    raw = str(note.get("note") or "").strip().upper().replace("♭", "B").replace("♯", "#")
    if len(raw) < 2:
        return None
    octave_raw = raw[-1]
    if not octave_raw.isdigit():
        return None
    pitch = raw[:-1]
    pitch_class = NOTE_CLASS_BY_NAME.get(pitch)
    if pitch_class is None:
        return None
    octave = int(octave_raw)
    return (octave + 1) * 12 + pitch_class


def note_pitch_class(note: dict[str, Any] | str) -> str:
    if isinstance(note, dict):
        midi = note_midi_value(note)
        if midi is not None:
            return NOTE_CLASS_NAMES[midi % 12]
        raw_value = str(note.get("note") or "").strip()
    elif isinstance(note, int):
        return NOTE_CLASS_NAMES[note % 12] if 0 <= note <= 127 else ""
    else:
        raw_value = str(note or "").strip()
    raw = raw_value.upper().replace("♭", "B").replace("♯", "#").replace("FLAT", "B").replace("SHARP", "#")
    match = re.match(r"^([A-G](?:#|B)?)", raw)
    if not match:
        return ""
    pitch = match.group(1)
    value = NOTE_CLASS_VALUES.get(pitch)
    return NOTE_CLASS_NAMES[value] if value is not None else ""


def note_event_for_series(note: dict[str, Any]) -> dict[str, Any]:
    start = safe_float(note.get("startSeconds"))
    end = safe_float(note.get("endSeconds"), start)
    return {
        "note": str(note.get("note") or "").strip(),
        "pitchClass": note_pitch_class(note),
        "midi": note_midi_value(note),
        "startSeconds": round(start, 3),
        "endSeconds": round(max(start, end), 3),
        "durationSeconds": round(max(0.0, safe_float(note.get("durationSeconds"), end - start)), 3),
        "confidence": round(safe_float(note.get("confidence")), 3),
        "uncertain": bool(note.get("uncertain")) or safe_float(note.get("confidence")) < 0.62,
    }


def compact_adjacent_pitch_classes(values: list[str]) -> list[str]:
    compact: list[str] = []
    for value in values:
        if value and (not compact or compact[-1] != value):
            compact.append(value)
    return compact


def detected_note_series(
    transcriptions: list[dict[str, Any]],
    max_series: int | None = MAX_DETECTED_NOTE_SERIES_API,
    max_notes_per_series: int | None = MAX_DETECTED_NOTE_SERIES_NOTES,
) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for transcription in transcriptions:
        notes = [
            note_event_for_series(note)
            for note in (transcription.get("notes") if isinstance(transcription.get("notes"), list) else [])
            if isinstance(note, dict) and str(note.get("note") or "").strip()
        ]
        notes = [note for note in notes if note.get("pitchClass")]
        if not notes:
            continue
        notes.sort(key=lambda note: (safe_float(note.get("startSeconds")), safe_float(note.get("endSeconds"))))
        source_start = parse_window_start(str(transcription.get("sourceWindow") or ""))
        sample_id = str(transcription.get("sampleId") or "").strip()
        source_title = str(transcription.get("sourceTitle") or "").strip()
        source_url = str(transcription.get("sourceUrl") or "").strip()
        source_window = str(transcription.get("sourceWindow") or "").strip()
        current: list[dict[str, Any]] = []
        previous_end = 0.0

        def flush() -> None:
            nonlocal current
            if not current:
                return
            run = current if max_notes_per_series is None else current[:max_notes_per_series]
            pitch_classes = [str(note.get("pitchClass") or "") for note in run if note.get("pitchClass")]
            collapsed = compact_adjacent_pitch_classes(pitch_classes)
            start = safe_float(run[0].get("startSeconds"))
            end = safe_float(run[-1].get("endSeconds"), start)
            detected_count = len(current)
            series.append(
                {
                    "id": f"{sample_id or source_title}:{source_window}:{len(series) + 1}",
                    "sourceTitle": source_title,
                    "sourceUrl": source_url,
                    "sourceWindow": source_window,
                    "sampleId": sample_id,
                    "startSeconds": round(source_start + start, 3),
                    "endSeconds": round(source_start + end, 3),
                    "localStartSeconds": round(start, 3),
                    "localEndSeconds": round(end, 3),
                    "durationSeconds": round(max(0.0, end - start), 3),
                    "noteCount": detected_count,
                    "displayedNoteCount": len(run),
                    "omittedNoteCount": max(0, detected_count - len(run)),
                    "uncertainNoteCount": sum(1 for note in current if note.get("uncertain")),
                    "notes": run,
                    "noteSeries": [str(note.get("note") or "") for note in run],
                    "pitchClasses": pitch_classes,
                    "collapsedPitchClasses": collapsed,
                    "noteSeriesLabel": " ".join(str(note.get("note") or "") for note in run),
                    "pitchClassSeriesLabel": " ".join(pitch_classes),
                    "collapsedPitchClassSeriesLabel": " ".join(collapsed),
                    "status": str(transcription.get("status") or ""),
                    "pipelineVersion": str(transcription.get("pipelineVersion") or ""),
                }
            )
            current = []

        for note in notes:
            start = safe_float(note.get("startSeconds"))
            if current and start - previous_end > NOTE_SERIES_MAX_GAP_SECONDS:
                flush()
            current.append(note)
            previous_end = max(previous_end, safe_float(note.get("endSeconds"), start))
        flush()
        if max_series is not None and len(series) >= max_series:
            return series[:max_series]
    return series if max_series is None else series[:max_series]


def reference_pitch_class_sequences(target: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    for key in ("pitchClassSequence", "scorePitchClassSequence", "firstNotes"):
        value = target.get(key)
        if isinstance(value, list):
            candidates.append({"label": key, "values": value})
    for key in ("pitchClassSequences", "scorePitchClassSequences"):
        value = target.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    sequences: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        if isinstance(candidate, dict):
            values = candidate.get("values") or candidate.get("notes") or candidate.get("pitchClasses") or candidate.get("sequence")
            label = str(candidate.get("label") or candidate.get("section") or f"reference sequence {index}")
        else:
            values = candidate
            label = f"reference sequence {index}"
        if not isinstance(values, list):
            continue
        pitch_classes = [note_pitch_class(value) for value in values]
        pitch_classes = [value for value in pitch_classes if value]
        if pitch_classes:
            sequences.append({"label": label, "pitchClasses": pitch_classes})
    return sequences


def longest_common_contiguous_run(query: list[str], reference: list[str]) -> dict[str, int]:
    best = {"length": 0, "queryStart": 0, "referenceStart": 0}
    if not query or not reference:
        return best
    previous = [0] * (len(reference) + 1)
    for query_index, query_value in enumerate(query, start=1):
        current = [0] * (len(reference) + 1)
        for reference_index, reference_value in enumerate(reference, start=1):
            if query_value != reference_value:
                continue
            length = previous[reference_index - 1] + 1
            current[reference_index] = length
            if length > best["length"]:
                best = {
                    "length": length,
                    "queryStart": query_index - length,
                    "referenceStart": reference_index - length,
                }
        previous = current
    return best


def compact_pitch_class_sequence(values: list[str]) -> list[str]:
    compact: list[str] = []
    previous = ""
    for value in values:
        current = str(value or "").strip()
        if not current or current == previous:
            continue
        compact.append(current)
        previous = current
    return compact


def score_sequence_matches_for_series(
    series: list[dict[str, Any]],
    pieces: list[dict[str, Any]],
    max_matches: int = 12,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for run in series:
        raw_query = [str(value) for value in run.get("pitchClasses", []) if value]
        collapsed_query = [str(value) for value in run.get("collapsedPitchClasses", []) if value]
        queries = [raw_query]
        if collapsed_query != raw_query:
            queries.append(collapsed_query)
        for piece in pieces:
            target = piece.get("score") if isinstance(piece.get("score"), dict) else {}
            for reference in reference_pitch_class_sequences(target):
                reference_values = reference.get("pitchClasses") if isinstance(reference.get("pitchClasses"), list) else []
                best_for_reference: dict[str, Any] = {}
                for query in queries:
                    candidate = longest_common_contiguous_run(query, reference_values)
                    if candidate["length"] < MATCH_GROUP_MIN_NOTE_RUN:
                        continue
                    if candidate["length"] <= int(best_for_reference.get("matchedNoteRun") or 0):
                        continue
                    q0 = int(candidate["queryStart"])
                    q1 = q0 + int(candidate["length"])
                    r0 = int(candidate["referenceStart"])
                    r1 = r0 + int(candidate["length"])
                    detected_sequence = query[q0:q1]
                    score_sequence = reference_values[r0:r1]
                    if len(set(detected_sequence)) < MATCH_GROUP_MIN_DISTINCT_PITCH_CLASSES:
                        continue
                    best_for_reference = {
                        "status": "score_sequence_match",
                        "pieceTitle": piece.get("title") or "",
                        "matchCriterion": "pitch_class_sequence",
                        "minimumMatchedNoteRun": MATCH_GROUP_MIN_NOTE_RUN,
                        "minimumDistinctPitchClasses": MATCH_GROUP_MIN_DISTINCT_PITCH_CLASSES,
                        "matchedNoteRun": int(candidate["length"]),
                        "rhythmRequired": False,
                        "detectedSeries": run,
                        "detectedPitchClassSequence": " ".join(detected_sequence),
                        "scorePitchClassSequence": " ".join(score_sequence),
                        "detectedPitchClassSequenceCompact": " ".join(compact_pitch_class_sequence(detected_sequence)),
                        "scorePitchClassSequenceCompact": " ".join(compact_pitch_class_sequence(score_sequence)),
                        "scoreSequenceLabel": reference.get("label") or "",
                        "scoreSnippetStatus": "sequence_match_score_location_pending",
                        "score": {
                            "assetId": target.get("scoreAssetId") or "",
                            "page": target.get("scorePage") or 0,
                            "source": target.get("scoreSource") or "",
                            "sourceUrl": target.get("scoreUrl") or "",
                            "pdfUrl": target.get("scorePdfUrl") or "",
                        },
                    }
                if best_for_reference:
                    matches.append(best_for_reference)
                    if len(matches) >= max_matches:
                        return matches
    return matches


def score_reference_status(pieces: list[dict[str, Any]]) -> str:
    if not pieces:
        return "awaiting_piece_name"
    if any(reference_pitch_class_sequences(piece.get("score") if isinstance(piece.get("score"), dict) else {}) for piece in pieces):
        return "symbolic_score_sequence_ready"
    if any((piece.get("score") if isinstance(piece.get("score"), dict) else {}).get("scoreAssetId") for piece in pieces):
        return "symbolic_score_sequence_missing"
    return "score_reference_missing"


def detected_series_clip(series: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(series.get("sampleId") or "").strip()
    local_start = safe_float(series.get("localStartSeconds"))
    local_end = max(local_start, safe_float(series.get("localEndSeconds"), local_start))
    media_url = f"/api/curtis/media/sample/{sample_id}" if sample_id else ""
    return {
        "type": "detected_note_series",
        "label": "detected note series",
        "url": series.get("sourceUrl") or "",
        "sourceTitle": series.get("sourceTitle") or "",
        "startSeconds": series.get("startSeconds") or 0,
        "endSeconds": series.get("endSeconds") or 0,
        "durationSeconds": series.get("durationSeconds") or 0,
        "activeTranscribedSeconds": series.get("durationSeconds") or 0,
        "noteCount": series.get("noteCount") or 0,
        "transcriptionStatus": "detected_note_series",
        "transcriptionId": series.get("id") or "",
        "pipelineVersion": series.get("pipelineVersion") or "",
        "reason": "Detected notes from the violin-playing window.",
        "sampleId": sample_id,
        "mediaUrl": media_url,
        "audioUrl": f"{media_url}/clip?start={local_start:.3f}&end={local_end:.3f}" if media_url and local_end > local_start else "",
        "localStartSeconds": round(local_start, 3),
        "localEndSeconds": round(local_end, 3),
    }


def longest_note_run(values: list[int]) -> int:
    longest = 0
    current = 0
    previous: int | None = None
    for value in values:
        if previous is None or previous != value:
            current = 1
            previous = value
        else:
            current += 1
        longest = max(longest, current)
    return longest


def has_spectral_audio_agreement(note: dict[str, Any]) -> bool:
    sources = note.get("agreementSources") if isinstance(note.get("agreementSources"), list) else []
    detector = str(note.get("detectorSource") or "")
    return detector.startswith("spectral_onset") or "spectral_onset" in sources


def note_passes_micro_gate(note: dict[str, Any]) -> bool:
    if not isinstance(note, dict) or not str(note.get("note") or "").strip():
        return False
    if note.get("uncertain"):
        return False
    if safe_float(note.get("confidence")) < MICRO_TRANSCRIPTION_MIN_CONFIDENCE:
        return False
    if not note.get("audioAgreement") or not has_spectral_audio_agreement(note):
        return False
    return note_midi_value(note) is not None


def micro_window_quality(notes: list[dict[str, Any]]) -> dict[str, Any]:
    midi_values = [note_midi_value(note) for note in notes]
    midi_values = [midi for midi in midi_values if midi is not None]
    if len(midi_values) != len(notes):
        return {"ready": False}
    confidences = sorted(safe_float(note.get("confidence")) for note in notes)
    median_confidence = confidences[len(confidences) // 2] if confidences else 0.0
    counts = Counter(midi_values)
    dominant_ratio = counts.most_common(1)[0][1] / max(1, len(midi_values)) if counts else 1.0
    pitch_classes = {midi % 12 for midi in midi_values}
    gaps = [
        max(0.0, safe_float(notes[index + 1].get("startSeconds")) - safe_float(notes[index].get("endSeconds")))
        for index in range(len(notes) - 1)
    ]
    start = safe_float(notes[0].get("startSeconds")) if notes else 0.0
    end = safe_float(notes[-1].get("endSeconds")) if notes else 0.0
    ready = (
        len(notes) >= MICRO_TRANSCRIPTION_MIN_NOTES
        and len(pitch_classes) >= MICRO_TRANSCRIPTION_MIN_PITCH_CLASSES
        and dominant_ratio <= MICRO_TRANSCRIPTION_MAX_DOMINANT_RATIO
        and longest_note_run(midi_values) <= MICRO_TRANSCRIPTION_MAX_SAME_NOTE_RUN
        and median_confidence >= MICRO_TRANSCRIPTION_MIN_MEDIAN_CONFIDENCE
        and (not gaps or max(gaps) <= MICRO_TRANSCRIPTION_MAX_NOTE_GAP_SECONDS)
        and end > start
    )
    return {
        "ready": ready,
        "noteCount": len(notes),
        "uniquePitchClasses": len(pitch_classes),
        "dominantRatio": round(dominant_ratio, 3),
        "longestRun": longest_note_run(midi_values),
        "medianConfidence": round(median_confidence, 3),
        "durationSeconds": round(max(0.0, end - start), 3),
        "score": round((len(notes) * 1.5) + (len(pitch_classes) * 2.0) + (median_confidence * 4.0) - (dominant_ratio * 3.0), 3),
    }


def best_micro_transcription(transcriptions: list[dict[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] = {}
    full_note_count = transcription_note_count(transcriptions)
    for transcription in transcriptions:
        if transcription.get("status") != "transcribed":
            continue
        quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
        if quality.get("failed") or quality.get("failureMode") or quality.get("pitchCollapseDetected"):
            continue
        source_notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
        notes = [note for note in source_notes if isinstance(note, dict) and str(note.get("note") or "").strip()]
        if len(notes) < MICRO_TRANSCRIPTION_MIN_NOTES:
            continue
        max_size = min(MICRO_TRANSCRIPTION_MAX_NOTES, len(notes))
        for size in range(max_size, MICRO_TRANSCRIPTION_MIN_NOTES - 1, -1):
            found_for_size = False
            for start_index in range(0, len(notes) - size + 1):
                window = notes[start_index : start_index + size]
                if not all(note_passes_micro_gate(note) for note in window):
                    continue
                quality_state = micro_window_quality(window)
                if not quality_state.get("ready"):
                    continue
                found_for_size = True
                if not best or float(quality_state["score"]) > float(best.get("quality", {}).get("score") or 0.0):
                    selected = []
                    for note in window:
                        selected.append(
                            {
                                **note,
                                "microVerified": True,
                                "verification": "spectral_pitch_audio_agreement",
                                "uncertain": False,
                            }
                        )
                    best = {
                        "transcription": {
                            **transcription,
                            "notes": selected,
                            "noteCount": len(selected),
                        },
                        "quality": quality_state,
                            "fullDetectedNoteCount": full_note_count,
                        }
            if found_for_size:
                break
    return best


def matched_fragment_note(fragment: dict[str, Any]) -> dict[str, Any]:
    start = safe_float(fragment.get("startSeconds"))
    end = safe_float(fragment.get("endSeconds"))
    duration = max(0.0, safe_float(fragment.get("durationSeconds")) or (end - start))
    return {
        "note": str(fragment.get("note") or "").strip(),
        "midi": fragment.get("midi"),
        "startSeconds": round(start, 3),
        "endSeconds": round(end, 3),
        "durationSeconds": round(duration, 3),
        "durationKind": "quarter" if duration <= 0.85 else "half" if duration <= 1.35 else "whole",
        "confidence": safe_float(fragment.get("confidence")),
        "audioAgreement": True,
        "agreementSources": fragment.get("detectors") if isinstance(fragment.get("detectors"), list) else ["pyin", "yin"],
        "detectorSource": "pyin_yin_stable_pitch",
        "audioMatchedFragment": True,
        "strictAudioWindow": True,
        "microVerified": True,
        "verification": fragment.get("verification") or "stable_single_note_audio_match",
        "uncertain": False,
    }


def fragment_passes_display_gate(fragment: dict[str, Any]) -> bool:
    if not isinstance(fragment, dict) or fragment.get("status") != "audio_matched":
        return False
    if str(fragment.get("kind") or "") != "stable_single_note":
        return False
    if not str(fragment.get("note") or "").strip():
        return False
    if note_midi_value(fragment) is None:
        return False
    duration = safe_float(fragment.get("durationSeconds"))
    if duration < 0.5 or duration > 1.5:
        return False
    if safe_float(fragment.get("confidence")) < 0.88:
        return False
    if safe_float(fragment.get("pitchStdCents"), 999.0) > 18.0:
        return False
    if abs(safe_float(fragment.get("medianPitchOffsetCents"))) > 25.0:
        return False
    detectors = fragment.get("detectors") if isinstance(fragment.get("detectors"), list) else []
    return "pyin" in detectors and "yin" in detectors


def transcription_matches_accepted_fragment_source(transcription: dict[str, Any], accepted: dict[str, Any]) -> bool:
    source_id = str(accepted.get("sourceVideoId") or "").strip()
    sample_id = str(accepted.get("sampleId") or "").strip()
    if sample_id and str(transcription.get("sampleId") or "").strip() == sample_id:
        return True
    haystack = " ".join(
        str(transcription.get(field) or "")
        for field in ("sourceUrl", "sourceTitle", "transcriptionId", "sampleId")
    )
    if source_id and source_id in haystack:
        return True
    return False


def fragment_matches_accepted(fragment: dict[str, Any], transcription: dict[str, Any], accepted: dict[str, Any]) -> bool:
    if not transcription_matches_accepted_fragment_source(transcription, accepted):
        return False
    if str(transcription.get("sampleId") or "").strip() != str(accepted.get("sampleId") or "").strip():
        return False
    if str(fragment.get("note") or "").strip() != str(accepted.get("note") or "").strip():
        return False
    if note_midi_value(fragment) != int(accepted.get("midi") or -1):
        return False
    return abs(safe_float(fragment.get("startSeconds")) - safe_float(accepted.get("startSeconds"))) < 0.01


def accepted_fragment_fallback(transcriptions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    for accepted in ACCEPTED_AUDIO_MATCHED_FRAGMENTS:
        for transcription in transcriptions:
            if transcription_matches_accepted_fragment_source(transcription, accepted):
                source = {
                    **transcription,
                    "transcriptionId": f"{transcription.get('transcriptionId') or accepted.get('sampleId') or ''}#human-accepted-audio-matched-fragment",
                    "sampleId": accepted.get("sampleId") or transcription.get("sampleId") or "",
                    "sourceUrl": accepted.get("sourceUrl") or transcription.get("sourceUrl") or "",
                    "sourceTitle": accepted.get("sourceTitle") or transcription.get("sourceTitle") or "",
                    "sourceWindow": accepted.get("sourceWindow") or transcription.get("sourceWindow") or "",
                    "pipelineVersion": transcription.get("pipelineVersion") or TRANSCRIPTION_PIPELINE_VERSION,
                }
                return source, dict(accepted)
    return None, None


def accepted_fragment_source(
    transcriptions: list[dict[str, Any]],
    accepted: dict[str, Any],
) -> dict[str, Any]:
    for transcription in transcriptions:
        if transcription_matches_accepted_fragment_source(transcription, accepted):
            return {
                **transcription,
                "transcriptionId": f"{transcription.get('transcriptionId') or accepted.get('sampleId') or ''}#accepted-audio-matched-fragment",
                "sampleId": accepted.get("sampleId") or transcription.get("sampleId") or "",
                "sourceUrl": accepted.get("sourceUrl") or transcription.get("sourceUrl") or "",
                "sourceTitle": accepted.get("sourceTitle") or transcription.get("sourceTitle") or "",
                "sourceWindow": accepted.get("sourceWindow") or transcription.get("sourceWindow") or "",
                "pipelineVersion": transcription.get("pipelineVersion") or TRANSCRIPTION_PIPELINE_VERSION,
            }
    return {}


def matched_fragment_candidate(
    transcription: dict[str, Any],
    fragment: dict[str, Any],
    full_note_count: int,
    fragment_count: int = 1,
) -> dict[str, Any]:
    note = matched_fragment_note(fragment)
    duration = safe_float(note.get("durationSeconds"))
    confidence = safe_float(fragment.get("confidence"))
    pitch_std = safe_float(fragment.get("pitchStdCents"), 999.0)
    quality = {
        "score": round((confidence * 10.0) + duration - (pitch_std / 20.0), 3),
        "noteCount": 1,
        "durationSeconds": round(duration, 3),
        "medianConfidence": round(confidence, 3),
        "pitchStdCents": round(pitch_std, 2),
        "medianPitchOffsetCents": fragment.get("medianPitchOffsetCents") or 0,
        "voicedFrameCount": fragment.get("voicedFrameCount") or 0,
        "detectors": fragment.get("detectors") if isinstance(fragment.get("detectors"), list) else ["pyin", "yin"],
    }
    return {
        "transcription": {
            **transcription,
            "transcriptionId": f"{transcription.get('transcriptionId') or ''}#audio-matched-fragment",
            "status": "audio_matched_fragment",
            "notes": [note],
            "noteCount": 1,
            "durationSeconds": round(duration, 3),
            "tempoBpm": round(60.0 / duration, 1) if duration > 0 else transcription.get("tempoBpm") or 0,
            "matchedFragment": fragment,
            "quality": {
                **(transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}),
                "audioMatchedFragmentDisplayed": True,
                "audioMatchedFragmentCount": fragment_count,
            },
        },
        "quality": quality,
        "fullDetectedNoteCount": full_note_count,
    }


def matched_fragment_transcriptions(
    transcriptions: list[dict[str, Any]],
    available_sample_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    full_note_count = transcription_note_count(transcriptions)
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for accepted in ACCEPTED_AUDIO_MATCHED_FRAGMENTS:
        accepted_sample = str(accepted.get("sampleId") or "").strip()
        if available_sample_ids is not None and accepted_sample and accepted_sample not in available_sample_ids:
            continue
        accepted_key = "|".join(
            [
                accepted_sample,
                str(accepted.get("startSeconds") or ""),
                str(accepted.get("endSeconds") or ""),
                str(accepted.get("note") or ""),
            ]
        )
        best: dict[str, Any] = {}
        for transcription in transcriptions:
            if not transcription_matches_accepted_fragment_source(transcription, accepted):
                continue
            fragments = transcription.get("matchedFragments") if isinstance(transcription.get("matchedFragments"), list) else []
            for fragment in fragments:
                if not fragment_passes_display_gate(fragment):
                    continue
                if not fragment_matches_accepted(fragment, transcription, accepted):
                    continue
                source = {
                    **transcription,
                    "sampleId": accepted_sample or transcription.get("sampleId") or "",
                    "sourceUrl": accepted.get("sourceUrl") or transcription.get("sourceUrl") or "",
                    "sourceTitle": accepted.get("sourceTitle") or transcription.get("sourceTitle") or "",
                    "sourceWindow": accepted.get("sourceWindow") or transcription.get("sourceWindow") or "",
                }
                candidate = matched_fragment_candidate(source, fragment, full_note_count, len(fragments))
                if best and safe_float(candidate.get("quality", {}).get("score")) <= safe_float(best.get("quality", {}).get("score")):
                    continue
                best = candidate
        if not best:
            source = accepted_fragment_source(transcriptions, accepted)
            if source:
                best = matched_fragment_candidate(source, dict(accepted), full_note_count, 1)
        if best and accepted_key not in seen:
            seen.add(accepted_key)
            matches.append(best)
    return matches


def best_matched_fragment_transcription(transcriptions: list[dict[str, Any]]) -> dict[str, Any]:
    matches = matched_fragment_transcriptions(transcriptions)
    if matches:
        return matches[0]
    best: dict[str, Any] = {}
    full_note_count = transcription_note_count(transcriptions)
    for transcription in transcriptions:
        fragments = transcription.get("matchedFragments") if isinstance(transcription.get("matchedFragments"), list) else []
        for fragment in fragments:
            if not fragment_passes_display_gate(fragment):
                continue
            accepted = next(
                (
                    item
                    for item in ACCEPTED_AUDIO_MATCHED_FRAGMENTS
                    if fragment_matches_accepted(fragment, transcription, item)
                ),
                None,
            )
            if not accepted:
                continue
            candidate = matched_fragment_candidate(transcription, fragment, full_note_count, len(fragments))
            score = safe_float(candidate.get("quality", {}).get("score"))
            if best and score <= safe_float(best.get("quality", {}).get("score")):
                continue
            best = candidate
    if not best:
        accepted_source, accepted_fragment = accepted_fragment_fallback(transcriptions)
        if accepted_source and accepted_fragment:
            best = matched_fragment_candidate(accepted_source, accepted_fragment, full_note_count, 1)
    return best


def matched_fragment_clip(match: dict[str, Any]) -> dict[str, Any]:
    transcription = match.get("transcription") if isinstance(match.get("transcription"), dict) else {}
    notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
    note = notes[0] if notes and isinstance(notes[0], dict) else {}
    sample_id = str(transcription.get("sampleId") or "").strip()
    source_start = parse_window_start(str(transcription.get("sourceWindow") or ""))
    local_start = safe_float(note.get("startSeconds"))
    local_end = safe_float(note.get("endSeconds"))
    start = source_start + local_start
    end = source_start + local_end
    return {
        "type": "audio_matched_fragment",
        "label": "detected note",
        "url": transcription.get("sourceUrl") or "",
        "sourceTitle": transcription.get("sourceTitle") or "",
        "startSeconds": round(start, 3),
        "endSeconds": round(end, 3),
        "durationSeconds": round(max(0.0, local_end - local_start), 3),
        "activeTranscribedSeconds": round(max(0.0, local_end - local_start), 3),
        "noteCount": 1,
        "transcriptionStatus": "audio_matched_fragment",
        "transcriptionId": transcription.get("transcriptionId") or "",
        "pipelineVersion": transcription.get("pipelineVersion") or "",
        "reason": "Displayed notation is limited to this exact stable note window.",
        "sampleId": sample_id,
        "mediaUrl": f"/api/curtis/media/sample/{sample_id}" if sample_id else "",
        "audioUrl": (
            f"/api/curtis/media/sample/{sample_id}/clip?start={local_start:.3f}&end={local_end:.3f}"
            if sample_id
            else ""
        ),
        "localStartSeconds": round(local_start, 3),
        "localEndSeconds": round(local_end, 3),
    }


def active_seconds_from_transcriptions(transcriptions: list[dict[str, Any]]) -> int:
    total = 0.0
    seen: set[tuple[str, int, int]] = set()
    for transcription in transcriptions:
        start, end = window_bounds(transcription)
        key = (
            str(transcription.get("sampleId") or transcription.get("id") or transcription.get("sourceUrl") or ""),
            start,
            end,
        )
        if key in seen:
            continue
        seen.add(key)
        quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
        if quality.get("windowMode") == "detected_active_sections":
            try:
                active_duration = float(transcription.get("durationSeconds") or 0.0)
            except (TypeError, ValueError):
                active_duration = 0.0
            if active_duration > 0:
                total += active_duration
                continue
        notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
        for note in notes:
            if isinstance(note, dict):
                total += max(0.0, float(note.get("durationSeconds") or 0.0))
    return int(round(total))


def has_stable_notation(transcription: dict[str, Any]) -> bool:
    if transcription.get("status") != "transcribed":
        return False
    notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
    return any(isinstance(note, dict) and str(note.get("note") or "").strip() for note in notes)


def transcription_window_seconds(transcriptions: list[dict[str, Any]]) -> int:
    total = 0.0
    seen: set[tuple[str, int, int]] = set()
    for transcription in transcriptions:
        if not has_stable_notation(transcription):
            continue
        start, end = window_bounds(transcription)
        if end <= start:
            continue
        key = (
            str(transcription.get("sampleId") or transcription.get("id") or transcription.get("sourceUrl") or ""),
            start,
            end,
        )
        if key in seen:
            continue
        seen.add(key)
        quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
        try:
            active_duration = float(transcription.get("durationSeconds") or 0.0)
        except (TypeError, ValueError):
            active_duration = 0.0
        if quality.get("windowMode") == "detected_active_sections" and active_duration > 0:
            total += active_duration
        else:
            total += end - start
    return int(round(total))


def transcription_coverage(
    transcribed_seconds: int,
    uploaded_seconds: int,
    segment_count: int,
    active_section_mode: bool = False,
) -> dict[str, Any]:
    if transcribed_seconds <= 0:
        return {
            "windowSeconds": 0,
            "windowLabel": "",
            "coveragePercent": 0,
            "coverageLabel": "No audio-checked transcription window yet.",
            "coverageLimit": "No playable score-linked transcription window is available for this day yet.",
            "coverageStatus": "pending_transcription",
        }
    percent = round((transcribed_seconds / max(1, uploaded_seconds)) * 100, 2) if uploaded_seconds else 0
    return {
        "windowSeconds": transcribed_seconds,
        "windowLabel": duration_seconds_label(transcribed_seconds),
        "coveragePercent": percent,
        "coverageLabel": (
            f"{duration_seconds_label(transcribed_seconds)} sampled audio evidence"
            + (f" from {duration_seconds_label(uploaded_seconds)} uploaded" if uploaded_seconds else "")
        ),
        "coverageLimit": (
            "Sampled active-audio evidence only: this does not cover the full practice day as transcription."
            if active_section_mode
            else "Sampled audio evidence only: this is not full-session transcription."
            if segment_count <= 1
            else "Sampled audio evidence only: these windows are not full-session transcription."
        ),
        "coverageStatus": "active_sections_only" if active_section_mode else "sample_window_only",
    }


def transcription_session_limit(transcribed_seconds: int, uploaded_seconds: int) -> str:
    if transcribed_seconds <= 0:
        return "Full-session transcription has not started for this practice day."
    uploaded = duration_seconds_label(uploaded_seconds) if uploaded_seconds else ""
    transcribed = duration_seconds_label(transcribed_seconds)
    if uploaded:
        return f"Not a full-session transcription: {transcribed} has unverified pitch events from {uploaded} uploaded."
    return f"Not a full-session transcription: {transcribed} has unverified pitch events."


def transcription_note_count(transcriptions: list[dict[str, Any]]) -> int:
    count = 0
    for transcription in transcriptions:
        if not has_stable_notation(transcription):
            continue
        notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
        count += sum(1 for note in notes if isinstance(note, dict) and note.get("note"))
    return count


def transcription_quality_metrics(transcriptions: list[dict[str, Any]]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for transcription in transcriptions:
        quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
        for key in (
            "rawSelectedEventCount",
            "selectedEventCount",
            "audioAgreementEventCount",
            "spectralAgreedEventCount",
            "sanityGlitchDroppedCount",
            "sanityOctaveAdjustedCount",
            "sanityLargeLeapCount",
            "sanityLowConfidenceNoteCount",
            "omittedSparseWindowCount",
            "pitchCollapseEventCount",
            "pitchCollapseDetectedOnsetCount",
            "pitchCollapseWindowCount",
        ):
            totals[key] += int(quality.get(key) or 0)
    return {key: int(value) for key, value in totals.items() if value}


def transcription_failure_summary(transcriptions: list[dict[str, Any]]) -> dict[str, Any]:
    modes: Counter[str] = Counter()
    notes: Counter[str] = Counter()
    limits: list[str] = []
    event_count = 0
    onset_count = 0
    for transcription in transcriptions:
        quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
        mode = str(quality.get("failureMode") or "")
        status = str(transcription.get("status") or "")
        if not mode and status.startswith("failed_"):
            mode = status
        if not mode:
            continue
        modes[mode] += 1
        note = str(quality.get("pitchCollapseDominantNote") or "").strip()
        if note:
            notes[note] += 1
        limit = str(quality.get("failureLimit") or "").strip()
        if limit:
            limits.append(limit)
        event_count += int(quality.get("pitchCollapseEventCount") or 0)
        onset_count += int(quality.get("pitchCollapseDetectedOnsetCount") or 0)
    if not modes:
        return {}
    mode = modes.most_common(1)[0][0]
    dominant_note = notes.most_common(1)[0][0] if notes else ""
    if mode == "repeated_pitch_collapse":
        limit = (
            "The detected pitch trace did not match the audio closely enough to become notation. "
            "Only audio-checked note evidence renders as sheet music."
        )
    else:
        limit = "Only audio-checked note evidence renders as sheet music."
    return {
        "qualityStatus": "score_audio_only",
        "qualityLabel": "matching",
        "qualityLimit": limit,
        "failureMode": mode,
        "failureWindowCount": int(sum(modes.values())),
        "failureDominantNote": dominant_note,
        "failurePitchEventCount": event_count,
        "failureDetectedOnsetCount": onset_count,
    }


def transcription_quality(
    note_count: int,
    active_seconds: int,
    segment_count: int,
    metrics: dict[str, int] | None = None,
) -> dict[str, Any]:
    metrics = metrics or {}
    if note_count <= 0:
        return {
            "qualityStatus": "pending",
            "qualityLabel": "notation pending",
            "qualityLimit": "No score-linked transcription has been extracted yet.",
        }
    if active_seconds < WEAK_TRANSCRIPTION_MIN_SECONDS or note_count < WEAK_TRANSCRIPTION_MIN_NOTES:
        return {
            "qualityStatus": "weak_fragment",
            "qualityLabel": "weak fragment",
            "qualityLimit": (
                f"Only {duration_seconds_label(active_seconds) or '0s'} and {note_count} pitch events were detected; "
                "this is not enough to call it a daily transcription."
            ),
            "segmentCount": segment_count,
        }
    adjusted = int(metrics.get("sanityOctaveAdjustedCount") or 0)
    low_confidence = int(metrics.get("sanityLowConfidenceNoteCount") or 0)
    sparse = int(metrics.get("omittedSparseWindowCount") or 0)
    sparse_note = (
        f" {sparse} sparse active-window hit{' was' if sparse == 1 else 's were'} excluded from the staff."
        if sparse
        else ""
    )
    if adjusted or low_confidence >= max(8, int(note_count * 0.18)):
        parts = []
        if adjusted:
            parts.append(f"{adjusted} octave-flip correction{'s' if adjusted != 1 else ''}")
        if low_confidence:
            parts.append(f"{low_confidence} low-confidence note{'s' if low_confidence != 1 else ''}")
        return {
            "qualityStatus": "sanity_corrected_draft",
            "qualityLabel": "matching",
            "qualityLimit": (
                f"The machine pitch events contain {', '.join(parts)} and stay out of the music view. "
                f"Only audio-checked note evidence renders as sheet music.{sparse_note}"
            ),
            "qualityMetrics": metrics,
            "segmentCount": segment_count,
        }
    if active_seconds < DRAFT_TRANSCRIPTION_MIN_SECONDS or note_count < DRAFT_TRANSCRIPTION_MIN_NOTES:
        return {
            "qualityStatus": "draft_fragment",
            "qualityLabel": "matching",
            "qualityLimit": (
                f"{duration_seconds_label(active_seconds)} and {note_count} pitch events were detected; "
                f"the clip is kept for verification before notation renders.{sparse_note}"
            ),
            "qualityMetrics": metrics,
            "segmentCount": segment_count,
        }
    return {
        "qualityStatus": "usable_fragment",
        "qualityLabel": "matching",
        "qualityLimit": f"Machine pitch events exist, but only audio-checked transcription renders as notation.{sparse_note}",
        "qualityMetrics": metrics,
        "segmentCount": segment_count,
    }


def active_seconds_from_sections(sections: list[dict[str, Any]]) -> int:
    total = 0
    seen: set[tuple[str, int, int]] = set()
    for section in sections:
        start, end = window_bounds(section)
        key = (str(section.get("sampleId") or section.get("id") or ""), start, end)
        if end > start and key not in seen:
            total += end - start
            seen.add(key)
    return total


def transcription_fragments(transcriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    durations: dict[str, float] = defaultdict(float)
    examples: dict[str, list[str]] = {}
    for transcription in transcriptions:
        notes = [
            str(note.get("note") or "").strip()
            for note in (transcription.get("notes") if isinstance(transcription.get("notes"), list) else [])
            if isinstance(note, dict) and str(note.get("note") or "").strip()
        ]
        if len(notes) < 4:
            continue
        note_durations = [
            float(note.get("durationSeconds") or 0.0)
            for note in (transcription.get("notes") if isinstance(transcription.get("notes"), list) else [])
            if isinstance(note, dict) and str(note.get("note") or "").strip()
        ]
        for index in range(len(notes) - 3):
            fragment_notes = notes[index : index + 4]
            label = " ".join(fragment_notes)
            counter[label] += 1
            durations[label] += sum(note_durations[index : index + 4])
            examples[label] = fragment_notes
    if not counter:
        return []
    max_count = max(counter.values())
    fragments = []
    for label, count in counter.most_common(8):
        fragments.append(
            {
                "label": label,
                "count": count,
                "seconds": round(durations[label], 1),
                "intensity": round(count / max(1, max_count), 3),
                "notes": examples.get(label, []),
            }
        )
    return fragments


def repeat_groups(
    heat_fragments: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    slow_window_count = sum(
        1
        for transcription in transcriptions
        if float(transcription.get("tempoBpm") or 0.0) and float(transcription.get("tempoBpm") or 0.0) < 84.0
    )
    groups: list[dict[str, Any]] = []
    for fragment in heat_fragments:
        count = int(fragment.get("count") or 0)
        if count < 2:
            continue
        pattern = "repeated loop from machine note/rhythm fragments"
        if slow_window_count:
            pattern = f"repeated loop; {slow_window_count} slow-practice window{'s' if slow_window_count != 1 else ''} in this day"
        groups.append(
            {
                "label": fragment.get("label") or "repeated fragment",
                "repeatCount": count,
                "notationLabel": f"{fragment.get('label') or 'fragment'} x{count}",
                "practicePattern": pattern,
                "confidence": "machine_grouped_fragment",
                "limit": "Repeat count is based on repeated four-note transcription fragments, not full score measures yet.",
            }
        )
    return groups[:6]


def problem_observations(
    notation: list[dict[str, Any]],
    heat_fragments: list[dict[str, Any]],
    clips: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    active_status: str,
) -> list[dict[str, Any]]:
    primary_clip = clips[0] if clips else {}
    observations: list[dict[str, Any]] = []
    uncertain_notes = Counter(
        str(event.get("note") or "")
        for event in notation
        if event.get("kind") == "note" and event.get("uncertain") and event.get("note")
    )
    if uncertain_notes:
        note, count = uncertain_notes.most_common(1)[0]
        observations.append(
            {
                "passage": heat_fragments[0].get("label") if heat_fragments else "generated transcription",
                "category": "pitch/rhythm confidence",
                "frequency": f"{count} marked events",
                "trend": "not enough attempts to trend",
                "problem": f"The generated notation marks {note} as uncertain {count} times.",
                "evidence": primary_clip,
                "transcriptionSnippet": notation[:24],
                "confidence": "machine_observed_uncertain_pitch",
                "curtisReadinessIssue": "A repeated uncertain pitch/rhythm location is not stable enough to treat as audition-ready evidence.",
            }
        )

    restart_count = sum(
        1
        for event in notation
        if event.get("kind") == "rest" and float(event.get("durationSeconds") or 0.0) >= 0.65
    )
    if restart_count:
        observations.append(
            {
                "passage": heat_fragments[0].get("label") if heat_fragments else "generated transcription",
                "category": "consistency",
                "frequency": f"{restart_count} marked pauses",
                "trend": "not enough attempts to trend",
                "problem": f"The transcription contains {restart_count} longer pause or restart markers inside the playing window.",
                "evidence": primary_clip,
                "transcriptionSnippet": notation[:24],
                "confidence": "machine_observed_pause_pattern",
                "curtisReadinessIssue": "Repeated stopping inside a passage means the passage is not yet secure under continuity pressure.",
            }
        )

    if heat_fragments:
        fragment = heat_fragments[0]
        count = int(fragment.get("count") or 0)
        if count >= 2:
            observations.append(
                {
                    "passage": fragment.get("label") or "repeated fragment",
                    "category": "repetition density",
                    "frequency": f"{count} repeats",
                    "trend": "not enough attempts to trend",
                    "problem": f"The fragment {fragment.get('label')} is the densest repeated material in this record.",
                    "evidence": primary_clip,
                    "transcriptionSnippet": notation[:24],
                    "confidence": "machine_observed_repetition",
                    "curtisReadinessIssue": "The day concentrated on this fragment; its stability should be judged from the paired clips before calling it ready.",
                }
            )

    slow_windows = [
        transcription
        for transcription in transcriptions
        if float(transcription.get("tempoBpm") or 0.0) and float(transcription.get("tempoBpm") or 0.0) < 84.0
    ]
    if slow_windows:
        observations.append(
            {
                "passage": heat_fragments[0].get("label") if heat_fragments else "slow transcription window",
                "category": "tempo",
                "frequency": f"{len(slow_windows)} slow windows",
                "trend": "not enough attempts to trend",
                "problem": "At least one transcribed window is marked as slow practice by the tempo estimate.",
                "evidence": primary_clip,
                "transcriptionSnippet": notation[:24],
                "confidence": "machine_observed_tempo",
                "curtisReadinessIssue": "Slow-window evidence is useful, but the passage still needs clean continuity evidence at target tempo.",
            }
        )

    if observations:
        return observations[:4]
    if active_status == "pending_media":
        return [
            {
                "passage": "practice day",
                "category": "media",
                "frequency": "not measured",
                "trend": "pending",
                "problem": "Audio/video has not produced active-playing evidence yet.",
                "evidence": primary_clip,
                "transcriptionSnippet": [],
                "confidence": "pending_media",
                "curtisReadinessIssue": "Curtis cannot make a playing-quality claim until violin-playing audio is processed.",
            }
        ]
    if not notation:
        return [
            {
                "passage": "active playing window",
                "category": "transcription",
                "frequency": "not measured",
                "trend": "pending",
                "problem": "Active audio exists, but pitch/rhythm notation has not been generated yet.",
                "evidence": primary_clip,
                "transcriptionSnippet": [],
                "confidence": "pending_transcription",
                "curtisReadinessIssue": "Curtis-level observations require notation tied to the exact clip.",
            }
        ]
    return [
        {
            "passage": "generated transcription",
            "category": "observed pattern",
            "frequency": "no repeated failure extracted",
            "trend": "not enough attempts to trend",
            "problem": "No specific repeated pitch, rhythm, pause, or repetition problem was extracted from this notation window.",
            "evidence": primary_clip,
            "transcriptionSnippet": notation[:24],
            "confidence": "machine_observed_no_repeated_problem",
            "curtisReadinessIssue": "This is not a readiness score; it only means the current extraction did not isolate a repeated blocker.",
        }
    ]


def transcription_quality_observations(
    quality: dict[str, Any],
    notation: list[dict[str, Any]],
    clips: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    status = str(quality.get("qualityStatus") or "")
    if status not in {"weak_fragment", "sanity_corrected_draft", "machine_pitch_hidden", "transcription_failed", "score_audio_only"}:
        return []
    primary_clip = clips[0] if clips else {}
    return [
        {
            "passage": "machine transcription",
            "category": "transcription quality",
            "frequency": quality.get("qualityLabel") or status,
            "trend": "requires more aligned active audio",
            "problem": quality.get("qualityLimit") or "Only score-matched notation should be treated as transcription.",
            "evidence": primary_clip,
            "transcriptionSnippet": notation[:24],
            "confidence": "machine_quality_gate",
            "curtisReadinessIssue": (
                "This evidence can guide review, but it is not strong enough to judge Curtis readiness "
                "until the clip and score location agree."
            ),
        }
    ]


def main_curtis_blocker(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "Main Curtis-level blocker pending evidence."
    problem = str(observations[0].get("problem") or "").strip()
    issue = str(observations[0].get("curtisReadinessIssue") or "").strip()
    return " ".join(part for part in (problem, issue) if part)


def heat_map_layers(heat_fragments: list[dict[str, Any]], notation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uncertain_count = sum(1 for event in notation if event.get("kind") == "note" and event.get("uncertain"))
    restart_count = sum(
        1
        for event in notation
        if event.get("kind") == "rest" and float(event.get("durationSeconds") or 0.0) >= 0.65
    )
    problem_items = []
    if uncertain_count:
        problem_items.append({"label": "uncertain notes", "count": uncertain_count, "intensity": min(1.0, uncertain_count / 8)})
    if restart_count:
        problem_items.append({"label": "pause/restart markers", "count": restart_count, "intensity": min(1.0, restart_count / 6)})
    return [
        {
            "label": "Practice density",
            "status": "ready" if heat_fragments else "pending_transcription",
            "items": heat_fragments,
        },
        {
            "label": "Repetition density",
            "status": "ready" if heat_fragments else "pending_transcription",
            "items": heat_fragments,
        },
        {
            "label": "Problem density",
            "status": "ready" if uncertain_count or restart_count else "pending_more_attempts",
            "items": problem_items,
        },
        {
            "label": "Improvement",
            "status": "pending_multiple_aligned_attempts",
            "items": [],
        },
    ]


def clips_for_day(
    videos: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    media_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    samples = sample_by_id(media_samples)
    transcription_sort = sorted(
        transcriptions,
        key=lambda item: (int(item.get("noteCount") or 0), sample_duration_seconds(item)),
        reverse=True,
    )
    for transcription in transcription_sort:
        start, end = window_bounds(transcription)
        if end <= start:
            continue
        note_count = int(transcription.get("noteCount") or 0)
        try:
            active_duration = float(transcription.get("durationSeconds") or 0.0)
        except (TypeError, ValueError):
            active_duration = 0.0
        reason = f"{note_count} detected pitch events kept for verification before notation renders."
        quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
        if note_count <= 0:
            reason = (
                f"{duration_seconds_label(active_duration)} of active audio scanned; no reliable score-linked transcription extracted."
                if active_duration > 0
                else "Audio scanned; no reliable score-linked transcription extracted."
            )
        elif quality.get("windowMode") == "detected_active_sections" and active_duration > 0:
            reason = f"{note_count} detected pitch events from {duration_seconds_label(active_duration)} of active audio; notation renders only after note-for-note verification."
        if str(transcription.get("status") or "").startswith("failed_") or quality.get("failed"):
            reason = "Clip kept for verification. Only audio-checked note evidence renders as notation."
        clips.append(
            {
                "type": "transcribed_window",
                "label": "audio evidence window",
                "url": transcription.get("sourceUrl") or "",
                "sourceTitle": transcription.get("sourceTitle") or "",
                "startSeconds": start,
                "endSeconds": end,
                "durationSeconds": end - start,
                "activeTranscribedSeconds": round(active_duration, 1) if active_duration else 0,
                "noteCount": note_count,
                "transcriptionStatus": transcription.get("status") or "",
                "transcriptionId": transcription.get("transcriptionId") or "",
                "pipelineVersion": transcription.get("pipelineVersion") or "",
                "reason": reason,
                **clip_media_fields(transcription, samples),
            }
        )
    for section in sorted(sections, key=lambda item: float(item.get("meanRms") or 0.0), reverse=True):
        start, end = window_bounds(section)
        if end <= start:
            continue
        clips.append(
            {
                "type": "active_section",
                "label": "audio-active section",
                "url": section.get("url") or "",
                "sourceTitle": section.get("title") or "",
                "startSeconds": start,
                "endSeconds": end,
                "durationSeconds": end - start,
                "reason": section.get("note") or "Audio-active practice section.",
                **clip_media_fields(section, samples),
            }
        )
    if not clips:
        for video in videos[:2]:
            clips.append(
                {
                    "type": "source_video",
                    "label": "source video",
                    "url": video.get("url") or "",
                    "sourceTitle": video.get("title") or "",
                    "startSeconds": 0,
                    "endSeconds": 0,
                    "durationSeconds": 0,
                    "reason": "Video indexed. Main practice clips pending active-playing detection.",
                }
            )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()
    for clip in clips:
        key = (
            str(clip.get("url") or ""),
            int(clip.get("startSeconds") or 0),
            int(clip.get("endSeconds") or 0),
            str(clip.get("type") or ""),
        )
        if key not in seen:
            unique.append(clip)
            seen.add(key)
    return unique[:MAX_CLIPS_PER_DAY]


def confirmed_pieces_for_day(
    state: dict[str, Any],
    videos: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    for correction in accepted_source_corrections(state):
        title = str(correction.get("acceptedTitle") or "").strip()
        if not title:
            continue
        matched_video = next((video for video in videos if source_matches(correction, video)), None)
        matched_transcription = next((item for item in transcriptions if source_matches(correction, item)), None)
        if not matched_video and not matched_transcription:
            continue
        source = matched_video or matched_transcription or {}
        pieces.append(
            {
                "title": title,
                "status": "confirmed",
                "confidence": "human_confirmed_source",
                "reason": correction.get("sourceHint") or correction.get("reason") or "Confirmed source label.",
                "sourceTitle": source.get("title") or source.get("sourceTitle") or correction.get("sourceTitle") or "",
                "sourceUrl": source.get("url") or source.get("sourceUrl") or correction.get("sourceUrl") or "",
                "score": correction.get("referenceTarget") if isinstance(correction.get("referenceTarget"), dict) else {},
            }
        )
    return pieces


def key_signature_from_pieces(pieces: list[dict[str, Any]]) -> dict[str, Any]:
    for piece in pieces:
        score = piece.get("score") if isinstance(piece.get("score"), dict) else {}
        signature = score.get("keySignature") if isinstance(score.get("keySignature"), dict) else {}
        if signature:
            return signature
    return {
        "tonic": "",
        "mode": "",
        "accidentalType": "none",
        "accidentals": [],
        "label": "key pending",
    }


def key_signature_from_transcriptions(transcriptions: list[dict[str, Any]]) -> dict[str, Any]:
    for transcription in transcriptions:
        target = transcription.get("referenceTarget") if isinstance(transcription.get("referenceTarget"), dict) else {}
        signature = target.get("keySignature") if isinstance(target.get("keySignature"), dict) else {}
        if signature:
            return signature
        calibration = transcription.get("calibrationAnchor") if isinstance(transcription.get("calibrationAnchor"), dict) else {}
        if not calibration:
            calibration = calibration_anchor_for_item(transcription)
        target = calibration.get("referenceTarget") if isinstance(calibration.get("referenceTarget"), dict) else {}
        signature = target.get("keySignature") if isinstance(target.get("keySignature"), dict) else {}
        if signature:
            return signature
    return {}


def score_target_label(target: dict[str, Any]) -> str:
    parts = [
        str(target.get("composer") or "").strip(),
        str(target.get("work") or "").strip(),
        str(target.get("movement") or "").strip(),
        str(target.get("part") or "").strip(),
    ]
    return " / ".join(part for part in parts if part)


def note_events_for_read(notation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in notation if isinstance(event, dict) and event.get("kind") == "note"]


def note_sequence_label(notes: list[dict[str, Any]], limit: int = 18) -> str:
    values = [str(note.get("note") or "").strip() for note in notes if str(note.get("note") or "").strip()]
    return " ".join(values[:limit])


def phrase_pattern_label(notes: list[dict[str, Any]], repeat_groups: list[dict[str, Any]]) -> str:
    if repeat_groups:
        first = repeat_groups[0]
        label = str(first.get("notationLabel") or first.get("label") or "repeated fragment").strip()
        return f"{label}; grouped repeat evidence"
    midi_values = [note_midi_value(note) for note in notes]
    midi_values = [value for value in midi_values if value is not None]
    if len(midi_values) < 3:
        return "short pitch evidence"
    intervals = [midi_values[index + 1] - midi_values[index] for index in range(len(midi_values) - 1)]
    up = sum(1 for value in intervals if value > 1)
    down = sum(1 for value in intervals if value < -1)
    same = sum(1 for value in intervals if abs(value) <= 1)
    leaps = sum(1 for value in intervals if abs(value) >= 5)
    largest_drop = min(intervals) if intervals else 0
    if same >= max(up + down, 1):
        return "repeated-note figure with pitch changes"
    if up >= down * 2 and largest_drop <= -7:
        return "rising figure with restart/drop"
    if up >= down * 2:
        return "rising scalar or sequence figure"
    if down >= up * 2:
        return "falling scalar or sequence figure"
    if leaps >= 2:
        return "leap-and-step pattern"
    return "mixed stepwise phrase contour"


def phrase_contour_label(notes: list[dict[str, Any]]) -> str:
    midi_values = [note_midi_value(note) for note in notes]
    midi_values = [value for value in midi_values if value is not None]
    if len(midi_values) < 2:
        return "contour pending"
    intervals = [midi_values[index + 1] - midi_values[index] for index in range(len(midi_values) - 1)]
    up = sum(1 for value in intervals if value > 1)
    down = sum(1 for value in intervals if value < -1)
    same = sum(1 for value in intervals if abs(value) <= 1)
    leaps = sum(1 for value in intervals if abs(value) >= 5)
    return f"{up} up / {same} same / {down} down / {leaps} leaps"


def top_reference_match(transcriptions: list[dict[str, Any]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for transcription in transcriptions:
        source_matches = transcription.get("referenceMatches") if isinstance(transcription.get("referenceMatches"), list) else []
        for match in source_matches:
            if isinstance(match, dict):
                matches.append(match)
    if not matches:
        return {}
    return max(matches, key=lambda item: safe_float(item.get("score")))


def musician_read(
    confirmed: list[dict[str, Any]],
    uncertain: list[dict[str, Any]],
    display_transcriptions: list[dict[str, Any]],
    notation: list[dict[str, Any]],
    repeat_groups: list[dict[str, Any]],
    material_status: str,
) -> dict[str, Any]:
    notes = note_events_for_read(notation)
    transcription = display_transcriptions[0] if display_transcriptions else {}
    calibration = transcription.get("calibrationAnchor") if isinstance(transcription.get("calibrationAnchor"), dict) else {}
    if not calibration:
        calibration = calibration_anchor_for_item(transcription)
    reference_target = transcription.get("referenceTarget") if isinstance(transcription.get("referenceTarget"), dict) else {}
    source = "piece or exercise pending"
    title = ""
    material_type = str(transcription.get("materialType") or "").strip()
    score_mode = "piece_or_exercise_pending"
    target_label = ""
    confidence = "audio evidence pending"
    if confirmed:
        piece = confirmed[0]
        source = "Alan-confirmed source label"
        title = str(piece.get("title") or "").strip()
        material_type = "repertoire"
        score_mode = "source_confirmed_score_target"
        reference_target = piece.get("score") if isinstance(piece.get("score"), dict) else reference_target
        target_label = score_target_label(reference_target)
        confidence = "audio-checked transcription plus source label" if notes else "source label"
    elif calibration:
        source = "explicit title label"
        title = str(calibration.get("title") or "").strip()
        material_type = str(calibration.get("materialType") or material_type or "calibration").strip()
        score_mode = str(calibration.get("referenceKind") or "title_labeled_calibration").strip()
        target_label = score_target_label(reference_target)
        confidence = "audio-checked transcription plus title label" if notes else "title label"
    elif uncertain:
        source = "fingerprint candidate"
        title = str(uncertain[0].get("title") or "").strip()
        score_mode = "uncertain_reference_match"
        confidence = "uncertain pitch/rhythm fingerprint"
    elif material_status == "piece_or_exercise_pending":
        source = "score-free or unidentified material"
        material_type = material_type or "unknown_or_exercise"
        confidence = "audio-checked transcription only" if notes else "audio evidence only"

    match = top_reference_match(display_transcriptions)
    match_title = str(match.get("title") or "").strip()
    limit = (
        "measure alignment pending"
        if title and notes
        else "calibration audio needed"
        if score_mode == "title_labeled_calibration"
        else "piece or pattern alignment pending"
    )
    return {
        "status": "ready" if notes else "pending",
        "source": source,
        "pieceTitle": title,
        "materialType": material_type,
        "scoreMode": score_mode,
        "scoreTarget": target_label,
        "pattern": phrase_pattern_label(notes, repeat_groups) if notes else "notation pending",
        "contour": phrase_contour_label(notes) if notes else "contour pending",
        "notes": note_sequence_label(notes),
        "confidence": confidence,
        "nearestReference": match_title,
        "nearestReferenceScore": match.get("score") or 0,
        "limit": limit,
    }


def uncertain_pieces_for_day(transcriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uncertain: list[dict[str, Any]] = []
    for transcription in transcriptions:
        matches = transcription.get("referenceMatches") if isinstance(transcription.get("referenceMatches"), list) else []
        for match in matches[:2]:
            title = str(match.get("title") or "").strip()
            if not title:
                continue
            uncertain.append(
                {
                    "title": title,
                    "status": "uncertain",
                    "confidence": match.get("score") or 0,
                    "reason": "Pitch/rhythm fingerprint resembles a learned source; score confirmation pending.",
                    "sourceTitle": transcription.get("sourceTitle") or "",
                    "sourceUrl": transcription.get("sourceUrl") or "",
                }
            )
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for item in uncertain:
        key = compact_text(item.get("title"))
        if key and key not in seen:
            clean.append(item)
            seen.add(key)
    return clean


def day_next_step(active_status: str, pieces: list[dict[str, Any]], transcribed: bool) -> str:
    if active_status == "pending_media":
        return "Media processing must finish before active playing, notation, and playing-quality observations can be measured."
    if not transcribed:
        return "Run transcription on the active windows before adding repertoire claims."
    if not pieces:
        return "Keep the transcription as uncertain evidence until it aligns to a piece, score-free exercise, or repeated technique pattern."
    return "Use the repeated fragments and clips to choose one small passage for the next take."


def day_summary(active_status: str, pieces: list[dict[str, Any]], uncertain: list[dict[str, Any]]) -> str:
    if pieces:
        return "Confirmed repertoire evidence recorded for this practice day."
    if uncertain:
        return "Possible repertoire evidence exists, but it is not confirmed."
    if active_status == "pending_media":
        return "Video metadata is indexed; audio/video processing has not produced active-playing evidence yet."
    return "Practice evidence processed; piece confirmation pending."


def verified_transcription_rank(record: dict[str, Any]) -> tuple[int, int, float, int, str]:
    transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
    if not transcription.get("transcriptionReady") or transcription.get("displayNotation") is False:
        return (0, 0, 0.0, 0, "")
    try:
        note_count = int(
            transcription.get("microVerifiedNoteCount")
            or transcription.get("matchedFragmentNoteCount")
            or transcription.get("renderedNoteCount")
            or transcription.get("noteCount")
            or 0
        )
    except (TypeError, ValueError):
        note_count = 0
    try:
        confidence = float(transcription.get("microMedianConfidence") or transcription.get("matchedFragmentConfidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        active_seconds = int(record.get("activeViolinSeconds") or 0)
    except (TypeError, ValueError):
        active_seconds = 0
    confirmed_piece = 1 if record.get("pieces") else 0
    return (confirmed_piece, note_count, confidence, active_seconds, str(record.get("practiceDay") or ""))


def lead_verified_transcription_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        record
        for record in records
        if isinstance(record, dict) and verified_transcription_rank(record)[1] > 0
    ]
    if not candidates:
        return {}
    return max(candidates, key=verified_transcription_rank)


def build_daily_records(
    state: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    ledger = practice_ledger_videos(inventory)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for video in ledger:
        day = str(video.get("practiceDay") or video.get("uploadedDate") or "")
        if day:
            grouped[day].append(video)

    records: list[dict[str, Any]] = []
    all_violin_sample_ids = violin_positive_sample_ids(media_samples)
    withheld_sample_count = sum(
        1
        for sample in media_samples
        if isinstance(sample, dict) and sample.get("id") and not sample_is_violin_positive(sample)
    )
    for day, videos in grouped.items():
        keys = set().union(*(video_match_keys(video) for video in videos))
        raw_day_samples = [sample for sample in media_samples if item_matches_keys(sample, keys)]
        day_samples = [sample for sample in raw_day_samples if sample_is_violin_positive(sample)]
        day_sample_ids = violin_positive_sample_ids(day_samples)
        day_transcriptions = sorted(
            [
                item
                for item in transcriptions
                if item_matches_keys(item, keys)
                and is_current_transcription(item)
                and item_has_violin_positive_sample(item, day_sample_ids or all_violin_sample_ids)
            ],
            key=lambda item: (
                str(item.get("sourceTitle") or ""),
                window_bounds(item)[0],
                str(item.get("transcriptionId") or ""),
            ),
        )
        day_sections = [
            section
            for section in sections
            if (
                item_has_violin_positive_sample(section, day_sample_ids or all_violin_sample_ids)
                and (
                    item_matches_keys(section, keys)
                    or any(str(section.get("sampleId") or "") == str(sample.get("id") or "") for sample in day_samples)
                )
            )
        ]
        raw_notation = notation_events(day_transcriptions)
        note_active = active_seconds_from_transcriptions(day_transcriptions)
        section_active = active_seconds_from_sections(day_sections)
        active_seconds = note_active or section_active
        active_status = (
            "measured_from_pitch"
            if note_active
            else "estimated_from_audio_energy"
            if section_active
            else "pending_media"
        )
        confirmed = confirmed_pieces_for_day(state, videos, day_transcriptions)
        uncertain = uncertain_pieces_for_day(day_transcriptions)
        all_detected_series = detected_note_series(day_transcriptions, max_series=None)
        api_detected_series = all_detected_series[:MAX_DETECTED_NOTE_SERIES_API]
        score_reference_state = score_reference_status(confirmed)
        score_sequence_matches = score_sequence_matches_for_series(all_detected_series, confirmed)
        heat_fragments: list[dict[str, Any]] = []
        day_repeat_groups: list[dict[str, Any]] = []
        full_note_count = transcription_note_count(day_transcriptions)
        notation_segments = [item for item in day_transcriptions if has_stable_notation(item)]
        quality_metrics = transcription_quality_metrics(day_transcriptions)
        quality = transcription_quality(full_note_count, active_seconds, len(notation_segments), quality_metrics)
        failure_summary = transcription_failure_summary(day_transcriptions)
        micro = best_micro_transcription(day_transcriptions)
        available_sample_ids = day_sample_ids or all_violin_sample_ids or set()
        matched_fragments = matched_fragment_transcriptions(day_transcriptions, available_sample_ids)
        matched_fragment = matched_fragments[0] if matched_fragments else {}
        has_verified_transcription = bool(matched_fragments)
        display_transcriptions = [item["transcription"] for item in matched_fragments] if has_verified_transcription else []
        read_transcriptions = display_transcriptions if has_verified_transcription else day_transcriptions
        notation = notation_events(display_transcriptions)
        day_notation_systems = notation_systems(notation)
        visible_quality = matched_fragment.get("quality", {}) if matched_fragment else micro.get("quality", {})
        note_count = int(visible_quality.get("noteCount") or full_note_count)
        if matched_fragments:
            note_count = sum(int(item.get("quality", {}).get("noteCount") or 0) for item in matched_fragments)
        public_note_count = note_count if has_verified_transcription else full_note_count
        display_state = notation_display_state(notation, day_notation_systems, note_count)
        has_machine_pitch_events = bool(raw_notation)
        if matched_fragments:
            fragment_qualities = [item.get("quality", {}) for item in matched_fragments]
            full_detected = int(max([item.get("fullDetectedNoteCount") or 0 for item in matched_fragments] + [full_note_count, note_count]))
            rejected_count = max(0, full_detected - note_count)
            matched_seconds = sum(float(item.get("durationSeconds") or 0.0) for item in fragment_qualities)
            matched_confidences = [float(item.get("medianConfidence") or 0.0) for item in fragment_qualities if item.get("medianConfidence")]
            matched_pitch_std = max([float(item.get("pitchStdCents") or 0.0) for item in fragment_qualities] + [0.0])
            matched_detectors = sorted(
                {
                    str(detector)
                    for item in fragment_qualities
                    for detector in (item.get("detectors") if isinstance(item.get("detectors"), list) else [])
                    if detector
                }
            )
            quality = {
                **quality,
                "qualityStatus": "audio_matched_fragment",
                "qualityLabel": "detected note",
                "qualityLimit": MATCHED_FRAGMENT_DISPLAY_LIMIT,
                "matchedFragmentCount": len(matched_fragments),
                "matchedFragmentNoteCount": note_count,
                "matchedFragmentSeconds": round(matched_seconds, 3),
                "matchedFragmentConfidence": round(sum(matched_confidences) / len(matched_confidences), 3) if matched_confidences else 0,
                "matchedFragmentPitchStdCents": round(matched_pitch_std, 2),
                "matchedFragmentDetectors": matched_detectors,
                "rejectedMachinePitchEventCount": rejected_count,
            }
            display_state = {
                **display_state,
                "displayNotation": True,
                "transcriptionReady": True,
                "hiddenPitchEventCount": rejected_count,
                "rejectedMachinePitchEventCount": rejected_count,
                "detectedPitchEventCount": full_detected,
                "displayLimit": (
                    f"{note_count} audio-checked notes are displayed across {len(matched_fragments)} exact clips; "
                    f"{rejected_count} machine pitch events remain hidden."
                ),
            }
            heat_fragments = [
                {
                    "label": "audio-checked detected notes",
                    "count": len(matched_fragments),
                    "seconds": round(matched_seconds, 3),
                    "density": 1,
                    "status": "audio_matched",
                }
            ]
            day_repeat_groups = []
        elif micro:
            micro_quality = micro.get("quality", {})
            full_detected = int(micro.get("fullDetectedNoteCount") or full_note_count or note_count)
            rejected_count = max(0, full_detected - note_count)
            quality = {
                **quality,
                "qualityStatus": "candidate_micro_transcription",
                "qualityLabel": "candidate withheld",
                "qualityLimit": MICRO_TRANSCRIPTION_DISPLAY_LIMIT,
                "candidateMicroNoteCount": note_count,
                "candidateMicroSeconds": micro_quality.get("durationSeconds") or 0,
                "candidateMicroMedianConfidence": micro_quality.get("medianConfidence") or 0,
                "candidateMicroUniquePitchClasses": micro_quality.get("uniquePitchClasses") or 0,
                "rejectedMachinePitchEventCount": full_detected,
            }
            display_state = {
                **display_state,
                "displayNotation": False,
                "transcriptionReady": False,
                "hiddenPitchEventCount": full_detected,
                "rejectedMachinePitchEventCount": full_detected,
                "detectedPitchEventCount": full_detected,
                "displayLimit": (
                    f"{note_count} candidate notes are withheld after audio-match review; "
                    f"{rejected_count} additional machine pitch events remain hidden."
                ),
            }
            heat_fragments = []
            day_repeat_groups = []
        elif failure_summary:
            quality = {
                **quality,
                **failure_summary,
            }
        elif has_machine_pitch_events:
            quality = {
                **quality,
                "qualityStatus": "score_audio_only",
                "qualityLabel": "matching",
                "qualityLimit": (
                    "Machine pitch events exist for sampled audio, but only verified note/rhythm notation renders. "
                    "The clip is kept for matching before it becomes transcription."
                ),
                "failureMode": "unverified_machine_pitch",
                "failureWindowCount": len(day_transcriptions),
                "failurePitchEventCount": full_note_count,
            }
            display_state = {
                **display_state,
                "detectedPitchEventCount": full_note_count,
                "hiddenPitchEventCount": full_note_count,
                "rejectedMachinePitchEventCount": full_note_count,
                "displayLimit": (
                    f"{full_note_count} machine pitch events are hidden from notation until a short "
                    "note/rhythm run passes audio-agreement checks."
                ),
            }
        uploaded_seconds = sum(int(video.get("durationSeconds") or 0) for video in videos)
        processed_seconds = sum(sample_duration_seconds(sample) for sample in day_samples)
        transcribed_seconds = transcription_window_seconds(day_transcriptions)
        active_section_mode = any(
            isinstance(item.get("quality"), dict) and item["quality"].get("windowMode") == "detected_active_sections"
            for item in notation_segments
        )
        coverage = transcription_coverage(
            transcribed_seconds,
            uploaded_seconds,
            len(notation_segments),
            active_section_mode=active_section_mode,
        )
        key_signature = key_signature_from_pieces(confirmed)
        if key_signature.get("label") == "key pending":
            key_signature = key_signature_from_transcriptions(read_transcriptions) or key_signature
        clips = clips_for_day(videos, day_sections, day_transcriptions, day_samples)
        if matched_fragments:
            fragment_clips = [matched_fragment_clip(item) for item in matched_fragments]
            clips = [*fragment_clips, *clips[: max(0, MAX_CLIPS_PER_DAY - len(fragment_clips))]]
        material_status = (
            "confirmed_piece"
            if confirmed
            else "uncertain_piece"
            if uncertain
            else "piece_or_exercise_pending"
            if active_seconds
            else "pending_media"
        )
        material_label = {
            "confirmed_piece": "piece confirmed",
            "uncertain_piece": "piece uncertain",
            "piece_or_exercise_pending": "piece or exercise pending",
            "pending_media": "media pending",
        }[material_status]
        score_alignment_status = (
            "pending_score_alignment"
            if confirmed
            else "pending_piece_or_exercise_alignment"
            if active_seconds
            else "pending_media"
        )
        pending_transcription_limit = (
            "Clip ready for piece or score-free technique exercise matching."
            if active_seconds and not confirmed
            else "Matched notation pending."
        )
        score_or_pattern_limit = (
            "Heat map waits for score alignment when this is repertoire; score-free exercises should map repeated audio and transcription patterns instead."
            if active_seconds and not confirmed
            else "Heat map waits for practice locations to align to actual score sections."
        )
        observations = (
            problem_observations(notation, heat_fragments, clips, day_transcriptions, active_status)[:6]
            if has_verified_transcription
            else transcription_quality_observations(quality, [], clips)[:2]
        )
        blocker = main_curtis_blocker(observations)
        match_groups = [
            {
                **match,
                "clip": detected_series_clip(match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}),
                "transcription": {
                    "status": "score_sequence_match",
                    "notes": (match.get("detectedSeries") or {}).get("notes", []),
                    "noteCount": (match.get("detectedSeries") or {}).get("noteCount", 0),
                    "sourceTitle": (match.get("detectedSeries") or {}).get("sourceTitle", ""),
                    "sourceUrl": (match.get("detectedSeries") or {}).get("sourceUrl", ""),
                    "sourceWindow": (match.get("detectedSeries") or {}).get("sourceWindow", ""),
                    "sampleId": (match.get("detectedSeries") or {}).get("sampleId", ""),
                },
            }
            for match in score_sequence_matches
        ]
        if match_groups:
            score_alignment_status = "pitch_sequence_match"
            score_or_pattern_limit = "Pitch sequence matched to the piece reference; exact measure/rhythm alignment remains pending."
        matching_workflow = {
            "status": (
                "score_sequence_matches_ready"
                if match_groups
                else "searching_score_match"
                if confirmed
                else "awaiting_piece_name"
            ),
            "matchCriterion": "pitch_class_sequence",
            "minimumMatchedNoteRun": MATCH_GROUP_MIN_NOTE_RUN,
            "minimumDistinctPitchClasses": MATCH_GROUP_MIN_DISTINCT_PITCH_CLASSES,
            "rhythmRequired": False,
            "displayMode": "groups_only",
            "rawTranscriptionDisplay": "hidden",
            "detectedSeriesCount": len(all_detected_series),
            "scoreSequenceMatchCount": len(score_sequence_matches),
            "scoreReferenceStatus": score_reference_state,
            "transcriptionRunPdfUrl": f"/api/curtis/daily-records/{day}/transcription.pdf",
        }
        records.append(
            {
                "practiceDay": day,
                "status": "active_time_measured" if active_seconds else "pending_media",
                "videos": videos,
                "videoCount": len(videos),
                "uploadedVideoSeconds": uploaded_seconds,
                "uploadedVideoLabel": duration_seconds_label(uploaded_seconds),
                "processedSampleSeconds": processed_seconds,
                "processedSampleLabel": duration_seconds_label(processed_seconds) if processed_seconds else "",
                "activeViolinSeconds": active_seconds,
                "activeViolinLabel": duration_seconds_label(active_seconds) if active_seconds else "",
                "activeTimeStatus": active_status,
                "pieces": confirmed,
                "uncertainPieces": uncertain,
                "materialStatus": material_status,
                "materialLabel": material_label,
                "matchingWorkflow": matching_workflow,
                "matchGroups": match_groups,
                "transcription": {
                    "status": (
                        "audio_matched_fragment"
                        if has_verified_transcription
                        else "score_audio_only"
                        if failure_summary or has_machine_pitch_events
                        else "pending"
                    ),
                    "displayTitle": (
                        "Detected note"
                        if has_verified_transcription
                        else "Audio evidence"
                    ),
                    "kind": (
                        "audio_matched_fragment_transcription"
                        if has_verified_transcription
                        else "score_audio_evidence"
                        if has_machine_pitch_events
                        else "pending"
                    ),
                    "scoreLinked": bool(match_groups),
                    "scoreAlignmentStatus": score_alignment_status,
                    "fullSessionStatus": "incomplete",
                    "reliability": (
                        "audio_matched_fragment"
                        if has_verified_transcription
                        else "score_audio_only"
                        if failure_summary or has_machine_pitch_events
                        else "pending"
                    ),
                    "reliabilityLimit": (
                        quality.get("qualityLimit")
                        if has_verified_transcription or failure_summary or has_machine_pitch_events
                        else pending_transcription_limit
                    ),
                    "noteCount": public_note_count,
                    "segmentCount": len(notation_segments),
                    "detectedSeriesCount": len(all_detected_series),
                    "detectedSeries": api_detected_series,
                    "scoreSequenceMatchCount": len(score_sequence_matches),
                    "scoreReferenceStatus": score_reference_state,
                    "scoreSequenceMatches": score_sequence_matches[:6],
                    **coverage,
                    **quality,
                    **display_state,
                    "clef": "treble",
                    "keySignature": key_signature,
                    "fullSessionLimit": transcription_session_limit(transcribed_seconds, uploaded_seconds),
                    "events": notation,
                    "repeatGroups": day_repeat_groups,
                    "limit": (
                        "Only notation that matches the clip renders as transcription; score-free technique exercises do not require score alignment."
                        if active_seconds and not confirmed
                        else "Only notation that matches the clip renders as transcription."
                    ),
                    "musicianRead": musician_read(
                        confirmed,
                        uncertain,
                        read_transcriptions,
                        notation,
                        day_repeat_groups,
                        material_status,
                    ),
                    "pdfUrl": matching_workflow["transcriptionRunPdfUrl"],
                },
                "clips": clips,
                "heatMap": {
                    "status": score_alignment_status,
                    "fragments": heat_fragments,
                    "layers": heat_map_layers(heat_fragments, []),
                    "limit": score_or_pattern_limit,
                },
                "observations": observations,
                "mainCurtisBlocker": blocker,
                "repertoireUpdates": [
                    {
                        "pieceTitle": item["title"],
                        "action": "add_or_update",
                        "status": "confirmed",
                        "reason": item.get("reason") or "Confirmed source evidence.",
                    }
                    for item in confirmed
                ],
                "evidenceStatus": material_status,
                "summary": day_summary(active_status, confirmed, uncertain),
                "nextStep": day_next_step(active_status, confirmed, has_verified_transcription),
            }
        )

    records.sort(key=lambda item: str(item.get("practiceDay") or ""))
    lead_transcription = lead_verified_transcription_record(records)
    total_uploaded = sum(int(record.get("uploadedVideoSeconds") or 0) for record in records)
    total_processed = sum(int(record.get("processedSampleSeconds") or 0) for record in records)
    total_active = sum(int(record.get("activeViolinSeconds") or 0) for record in records)
    unmeasured_uploaded = max(0, total_uploaded - total_processed)
    return {
        "status": "ready" if records else "pending",
        "recordCount": len(records),
        "totalUploadedVideoSeconds": total_uploaded,
        "totalUploadedVideoLabel": duration_seconds_label(total_uploaded),
        "totalAnalyzedVideoSeconds": total_processed,
        "totalAnalyzedVideoLabel": duration_seconds_label(total_processed) if total_processed else "",
        "totalProcessedSampleSeconds": total_processed,
        "totalProcessedSampleLabel": duration_seconds_label(total_processed) if total_processed else "",
        "totalPracticeTimeSeconds": total_active,
        "totalPracticeTimeLabel": duration_seconds_label(total_active) if total_active else "",
        "totalActiveViolinSeconds": total_active,
        "totalActiveViolinLabel": duration_seconds_label(total_active) if total_active else "",
        "unmeasuredUploadedVideoSeconds": unmeasured_uploaded,
        "unmeasuredUploadedVideoLabel": duration_seconds_label(unmeasured_uploaded) if unmeasured_uploaded else "",
        "activeMeasurementStatus": "partial" if unmeasured_uploaded else "complete" if total_uploaded else "pending",
        "mediaSampleCount": len(media_samples),
        "violinPositiveSampleCount": len(all_violin_sample_ids),
        "withheldNonViolinSampleCount": withheld_sample_count,
        "transcribedRecordCount": sum(1 for record in records if record.get("transcription", {}).get("transcriptionReady")),
        "audioEvidenceRecordCount": sum(1 for record in records if record.get("transcription", {}).get("kind") in {"audio_evidence_only", "score_audio_evidence", "audio_verified_micro_transcription", "audio_matched_fragment_transcription"}),
        "scoreAudioOnlyRecordCount": sum(1 for record in records if record.get("transcription", {}).get("reliability") == "score_audio_only"),
        "hiddenPitchTraceRecordCount": sum(1 for record in records if record.get("transcription", {}).get("reliability") == "machine_pitch_hidden"),
        "failedTranscriptionRecordCount": sum(1 for record in records if record.get("transcription", {}).get("reliability") == "transcription_failed"),
        "leadTranscriptionPracticeDay": lead_transcription.get("practiceDay") if lead_transcription else "",
        "records": records[:MAX_RECORDS],
        "method": "Groups title-confirmed practice videos by practice day, then attaches uploaded duration, detected violin-playing time, playable audio/video windows, score targets, and repertoire evidence.",
        "limit": (
            "Total practice time means detected violin-playing footage and is independent from transcription. "
            "Uploaded archive duration is visible separately. Exact practice time for the full archive requires "
            "checking every practice video for violin-playing windows."
        ),
    }


def repertoire_heat_map(fragments: list[dict[str, Any]], observations: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    seconds: dict[str, float] = defaultdict(float)
    examples: dict[str, dict[str, Any]] = {}
    days: dict[str, set[str]] = defaultdict(set)
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        label = str(fragment.get("label") or "").strip()
        if not label:
            continue
        count = int(fragment.get("count") or 0)
        counter[label] += max(1, count)
        try:
            seconds[label] += max(0.0, float(fragment.get("seconds") or 0.0))
        except (TypeError, ValueError):
            seconds[label] += 0.0
        examples[label] = fragment
        day = str(fragment.get("practiceDay") or "").strip()
        if day:
            days[label].add(day)

    max_count = max(counter.values()) if counter else 0
    heat_fragments = []
    for label, count in counter.most_common(8):
        base = examples.get(label, {})
        heat_fragments.append(
            {
                "label": label,
                "count": count,
                "seconds": round(seconds[label], 1),
                "intensity": round(count / max(1, max_count), 3),
                "notes": base.get("notes") or [],
                "practiceDays": sorted(days[label], reverse=True)[:6],
            }
        )

    problem_items = [
        {
            "label": str(item.get("passage") or item.get("category") or "observed problem"),
            "count": 1,
            "category": item.get("category"),
            "problem": item.get("problem"),
            "practiceDay": item.get("practiceDay"),
        }
        for item in observations[:8]
        if isinstance(item, dict)
    ]
    return {
        "status": "ready" if heat_fragments else "pending_transcription",
        "fragments": heat_fragments,
        "layers": [
            {
                "label": "Practice density",
                "status": "ready" if heat_fragments else "pending_transcription",
                "items": heat_fragments,
            },
            {
                "label": "Repetition density",
                "status": "ready" if heat_fragments else "pending_transcription",
                "items": heat_fragments,
            },
            {
                "label": "Problem density",
                "status": "ready" if problem_items else "pending_more_aligned_attempts",
                "items": problem_items,
            },
            {
                "label": "Improvement",
                "status": "pending_multiple_aligned_attempts",
                "items": [],
            },
        ],
        "limit": "Piece heat map is aggregated from confirmed daily-record transcription fragments and observations only.",
    }


def build_repertoire_evidence(daily_records: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    for record in daily_records.get("records", []):
        if not isinstance(record, dict):
            continue
        for piece in record.get("pieces", []):
            if not isinstance(piece, dict):
                continue
            title = str(piece.get("title") or "").strip()
            key = compact_text(title)
            if not key:
                continue
            entry = entries.setdefault(
                key,
                {
                    "title": title,
                    "status": "confirmed",
                    "reason": piece.get("reason") or "Confirmed source evidence.",
                    "totalActiveViolinSeconds": 0,
                    "totalUploadedVideoSeconds": 0,
                    "recentPracticeDays": [],
                    "evidence": [],
                    "observations": [],
                    "heatFragments": [],
                },
            )
            entry["totalActiveViolinSeconds"] += int(record.get("activeViolinSeconds") or 0)
            entry["totalUploadedVideoSeconds"] += int(record.get("uploadedVideoSeconds") or 0)
            entry["recentPracticeDays"].append(record.get("practiceDay"))
            clip = (record.get("clips") or [{}])[0] if isinstance(record.get("clips"), list) else {}
            notation_events_for_record = record.get("transcription", {}).get("events", [])
            entry["evidence"].append(
                {
                    "practiceDay": record.get("practiceDay"),
                    "clip": clip,
                    "transcriptionSnippet": notation_events_for_record[:24] if isinstance(notation_events_for_record, list) else [],
                    "score": piece.get("score") or {},
                    "reason": piece.get("reason") or "Confirmed source evidence.",
                    "confidence": piece.get("confidence") or "confirmed",
                }
            )
            for fragment in record.get("heatMap", {}).get("fragments", []):
                if isinstance(fragment, dict):
                    entry["heatFragments"].append({**fragment, "practiceDay": record.get("practiceDay")})
            for observation in record.get("observations", [])[:2]:
                if isinstance(observation, dict):
                    entry["observations"].append(
                        {
                            "practiceDay": record.get("practiceDay"),
                            "passage": observation.get("passage"),
                            "category": observation.get("category"),
                            "problem": observation.get("problem"),
                            "frequency": observation.get("frequency"),
                            "trend": observation.get("trend"),
                            "curtisReadinessIssue": observation.get("curtisReadinessIssue"),
                            "confidence": observation.get("confidence"),
                        }
                    )
    output = []
    for entry in entries.values():
        days = [str(day) for day in entry["recentPracticeDays"] if day]
        entry["recentPracticeDays"] = list(dict.fromkeys(days))[:8]
        entry["totalActiveViolinLabel"] = duration_seconds_label(entry["totalActiveViolinSeconds"]) if entry["totalActiveViolinSeconds"] else ""
        entry["totalUploadedVideoLabel"] = duration_seconds_label(entry["totalUploadedVideoSeconds"])
        entry["progressStatus"] = "not_scored"
        entry["currentProgressLabel"] = "not scored"
        entry["heatMap"] = repertoire_heat_map(entry.pop("heatFragments", []), entry["observations"])
        entry["mainCurtisBlocker"] = (
            str(entry["observations"][0].get("curtisReadinessIssue") or entry["observations"][0].get("problem") or "")
            if entry["observations"]
            else "Specific blocker pending aligned transcription evidence."
        )
        entry["nextStep"] = "Progress percentage stays unassigned until clips, notation, and score alignment support it."
        output.append(entry)
    output.sort(key=lambda item: (len(item.get("recentPracticeDays", [])), item.get("title", "")), reverse=True)
    return {
        "status": "ready" if output else "pending",
        "entryCount": len(output),
        "entries": output,
        "method": "Only confirmed daily-record evidence promotes repertoire entries.",
        "limit": "Uncertain piece matches remain daily evidence and do not become repertoire entries.",
    }
