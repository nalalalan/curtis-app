from __future__ import annotations

import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .analyzer import parse_window_start, run_process, sample_is_violin_positive
from .corrections import correction_for_item, source_key_from_item
from .reference_corpus import calibration_anchor_for_item, symbolic_reference_items
from .state import load_state, save_state, utc_now


MAX_TRANSCRIPTION_SECONDS = int(os.getenv("CURTIS_TRANSCRIPTION_MAX_SECONDS", "180"))
TRANSCRIPTION_SAMPLE_LIMIT = int(os.getenv("CURTIS_TRANSCRIPTION_SAMPLE_LIMIT", "8"))
TRANSCRIPTION_PIPELINE_VERSION = "violin_audio_matched_fragment_v13"
MIN_NOTE_SECONDS = float(os.getenv("CURTIS_MIN_NOTE_SECONDS", "0.055"))
MIN_ONSET_NOTE_SECONDS = float(os.getenv("CURTIS_MIN_ONSET_NOTE_SECONDS", "0.04"))
MAX_STORED_NOTES = int(os.getenv("CURTIS_MAX_STORED_NOTES", "240"))
PITCH_MATCH_THRESHOLD = float(os.getenv("CURTIS_PITCH_MATCH_THRESHOLD", "0.58"))
VIOLIN_MIN_MIDI = int(os.getenv("CURTIS_VIOLIN_MIN_MIDI", "55"))
VIOLIN_MAX_MIDI = int(os.getenv("CURTIS_VIOLIN_MAX_MIDI", "108"))
MIN_VOICED_PROBABILITY = float(os.getenv("CURTIS_MIN_VOICED_PROBABILITY", "0.50"))
NOTE_CHANGE_CONFIRM_FRAMES = int(os.getenv("CURTIS_NOTE_CHANGE_CONFIRM_FRAMES", "2"))
VIBRATO_SEMITONE_RANGE = int(os.getenv("CURTIS_VIBRATO_SEMITONE_RANGE", "1"))
VIBRATO_CHANGE_CONFIRM_FRAMES = int(os.getenv("CURTIS_VIBRATO_CHANGE_CONFIRM_FRAMES", "4"))
NOTE_MERGE_GAP_SECONDS = float(os.getenv("CURTIS_NOTE_MERGE_GAP_SECONDS", "0.07"))
ONSET_EVENT_MULTIPLIER = float(os.getenv("CURTIS_ONSET_EVENT_MULTIPLIER", "1.12"))
ONSET_MIN_VOICED_FRAMES = int(os.getenv("CURTIS_ONSET_MIN_VOICED_FRAMES", "1"))
HARMONIC_MARGIN = float(os.getenv("CURTIS_HARMONIC_MARGIN", "8.0"))
PITCH_FRAME_LENGTH = int(os.getenv("CURTIS_PITCH_FRAME_LENGTH", "1024"))
PITCH_HOP_LENGTH = int(os.getenv("CURTIS_PITCH_HOP_LENGTH", "256"))
LOW_CONFIDENCE_GLITCH_SECONDS = float(os.getenv("CURTIS_LOW_CONFIDENCE_GLITCH_SECONDS", "0.07"))
LOW_CONFIDENCE_GLITCH_THRESHOLD = float(os.getenv("CURTIS_LOW_CONFIDENCE_GLITCH_THRESHOLD", "0.68"))
OCTAVE_FLIP_MIN_SEMITONES = int(os.getenv("CURTIS_OCTAVE_FLIP_MIN_SEMITONES", "10"))
NEIGHBOR_AGREEMENT_SEMITONES = int(os.getenv("CURTIS_NEIGHBOR_AGREEMENT_SEMITONES", "3"))
OCTAVE_ADJUSTMENT_MIN_GAIN = int(os.getenv("CURTIS_OCTAVE_ADJUSTMENT_MIN_GAIN", "8"))
LARGE_LEAP_SEMITONES = int(os.getenv("CURTIS_LARGE_LEAP_SEMITONES", "17"))
MIN_ACTIVE_WINDOW_NOTES = int(os.getenv("CURTIS_MIN_ACTIVE_WINDOW_NOTES", "4"))
ACTIVE_SECTION_PADDING_SECONDS = float(os.getenv("CURTIS_ACTIVE_SECTION_PADDING_SECONDS", "0.35"))
ACTIVE_SECTION_MERGE_GAP_SECONDS = float(os.getenv("CURTIS_ACTIVE_SECTION_MERGE_GAP_SECONDS", "0.55"))
MAX_ACTIVE_TRANSCRIPTION_SECTIONS = int(os.getenv("CURTIS_MAX_ACTIVE_TRANSCRIPTION_SECTIONS", "12"))
PITCH_COLLAPSE_MIN_EVENTS = int(os.getenv("CURTIS_PITCH_COLLAPSE_MIN_EVENTS", "14"))
PITCH_COLLAPSE_MIN_RUN = int(os.getenv("CURTIS_PITCH_COLLAPSE_MIN_RUN", "10"))
PITCH_COLLAPSE_DOMINANT_RATIO = float(os.getenv("CURTIS_PITCH_COLLAPSE_DOMINANT_RATIO", "0.82"))
PITCH_COLLAPSE_MAX_PITCH_CLASSES = int(os.getenv("CURTIS_PITCH_COLLAPSE_MAX_PITCH_CLASSES", "2"))
SPECTRAL_MIN_CONFIDENCE = float(os.getenv("CURTIS_SPECTRAL_MIN_CONFIDENCE", "0.18"))
SPECTRAL_MIN_SEGMENT_SECONDS = float(os.getenv("CURTIS_SPECTRAL_MIN_SEGMENT_SECONDS", "0.035"))
SPECTRAL_HARMONIC_COUNT = int(os.getenv("CURTIS_SPECTRAL_HARMONIC_COUNT", "5"))
FAST_ONSET_DELTA = float(os.getenv("CURTIS_FAST_ONSET_DELTA", "0.05"))
FAST_ONSET_WAIT_FRAMES = int(os.getenv("CURTIS_FAST_ONSET_WAIT_FRAMES", "1"))
FAST_ONSET_MIN_FRAME_GAP = int(os.getenv("CURTIS_FAST_ONSET_MIN_FRAME_GAP", "2"))
SPECTRAL_OCTAVE_RESCUE_RATIO = float(os.getenv("CURTIS_SPECTRAL_OCTAVE_RESCUE_RATIO", "0.70"))
SPECTRAL_OCTAVE_RESCUE_MIN_MIDI = int(os.getenv("CURTIS_SPECTRAL_OCTAVE_RESCUE_MIN_MIDI", "81"))
SPECTRAL_FAST_MIN_EVENTS = int(os.getenv("CURTIS_SPECTRAL_FAST_MIN_EVENTS", "6"))
SPECTRAL_MICRO_WINDOW_SECONDS = float(os.getenv("CURTIS_SPECTRAL_MICRO_WINDOW_SECONDS", "0.034"))
SPECTRAL_MICRO_HOP_SECONDS = float(os.getenv("CURTIS_SPECTRAL_MICRO_HOP_SECONDS", "0.016"))
SPECTRAL_MICRO_MIN_RMS_RATIO = float(os.getenv("CURTIS_SPECTRAL_MICRO_MIN_RMS_RATIO", "0.28"))
SPECTRAL_MICRO_MIN_MIDI = int(os.getenv("CURTIS_SPECTRAL_MICRO_MIN_MIDI", "81"))
SPECTRAL_MICRO_MIN_EVENTS = int(os.getenv("CURTIS_SPECTRAL_MICRO_MIN_EVENTS", "6"))
YIN_TRANSITION_RMS_RATIO = float(os.getenv("CURTIS_YIN_TRANSITION_RMS_RATIO", "0.18"))
YIN_TRANSITION_MIN_SECONDS = float(os.getenv("CURTIS_YIN_TRANSITION_MIN_SECONDS", "0.018"))
AUDIO_AGREEMENT_SECONDS = float(os.getenv("CURTIS_AUDIO_AGREEMENT_SECONDS", "0.11"))
AUDIO_AGREEMENT_MIDI_TOLERANCE = int(os.getenv("CURTIS_AUDIO_AGREEMENT_MIDI_TOLERANCE", "1"))
MATCHED_FRAGMENT_MIN_SECONDS = float(os.getenv("CURTIS_MATCHED_FRAGMENT_MIN_SECONDS", "0.52"))
MATCHED_FRAGMENT_MAX_SECONDS = float(os.getenv("CURTIS_MATCHED_FRAGMENT_MAX_SECONDS", "1.35"))
MATCHED_FRAGMENT_MIN_PROBABILITY = float(os.getenv("CURTIS_MATCHED_FRAGMENT_MIN_PROBABILITY", "0.88"))
MATCHED_FRAGMENT_MAX_PITCH_STD_CENTS = float(os.getenv("CURTIS_MATCHED_FRAGMENT_MAX_PITCH_STD_CENTS", "18.0"))
MATCHED_FRAGMENT_MAX_MEDIAN_ABS_CENTS = float(os.getenv("CURTIS_MATCHED_FRAGMENT_MAX_MEDIAN_ABS_CENTS", "25.0"))
MATCHED_FRAGMENT_FRAME_LENGTH = int(os.getenv("CURTIS_MATCHED_FRAGMENT_FRAME_LENGTH", "2048"))
MATCHED_FRAGMENT_HOP_LENGTH = int(os.getenv("CURTIS_MATCHED_FRAGMENT_HOP_LENGTH", "256"))
MATCHED_FRAGMENT_LIMIT = int(os.getenv("CURTIS_MATCHED_FRAGMENT_LIMIT", "3"))
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def transcription_key(sample: dict[str, Any]) -> str:
    source_key = source_key_from_item(sample)
    return "|".join(
        str(part or "")
        for part in (
            source_key,
            sample.get("id"),
            sample.get("window"),
            sample.get("path"),
        )
    )


def note_name(midi: int) -> str:
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[midi % 12]}{octave}"


def midi_from_hz(value: float) -> int:
    return int(round(69 + 12 * math.log2(float(value) / 440.0)))


def valid_frame_midi(value: Any, voiced: bool, probability: float) -> int | None:
    if not voiced or value is None or probability < MIN_VOICED_PROBABILITY:
        return None
    try:
        frequency = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(frequency) or frequency <= 0:
        return None
    midi = midi_from_hz(frequency)
    if midi < VIOLIN_MIN_MIDI or midi > VIOLIN_MAX_MIDI:
        return None
    return midi


def compact_counts(values: list[str], limit: int = 60) -> dict[str, int]:
    return dict(Counter(values).most_common(limit))


def ngrams(values: list[str], size: int, limit: int = 90) -> dict[str, int]:
    if len(values) < size:
        return {}
    grams = [" ".join(values[index : index + size]) for index in range(len(values) - size + 1)]
    return compact_counts(grams, limit)


def cosine_counts(left: dict[str, int], right: dict[str, int]) -> float:
    if not left or not right:
        return 0.0
    keys = set(left) | set(right)
    dot = sum(float(left.get(key, 0)) * float(right.get(key, 0)) for key in keys)
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left.values()))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def jaccard_keys(left: dict[str, int], right: dict[str, int]) -> float:
    if not left or not right:
        return 0.0
    left_keys = set(left)
    right_keys = set(right)
    return len(left_keys & right_keys) / max(1, len(left_keys | right_keys))


def compare_fingerprints(left: dict[str, Any], right: dict[str, Any]) -> float:
    pitch_hist = cosine_counts(left.get("pitchClassHistogram", {}), right.get("pitchClassHistogram", {}))
    pitch_grams = jaccard_keys(left.get("pitchClassNgrams", {}), right.get("pitchClassNgrams", {}))
    interval_grams = jaccard_keys(left.get("intervalNgrams", {}), right.get("intervalNgrams", {}))
    rhythm_grams = jaccard_keys(left.get("rhythmNgrams", {}), right.get("rhythmNgrams", {}))
    return round((0.30 * pitch_hist) + (0.30 * pitch_grams) + (0.30 * interval_grams) + (0.10 * rhythm_grams), 3)


def event_fingerprint(events: list[dict[str, Any]], tempo_bpm: float) -> dict[str, Any]:
    midi_values = [int(event["midi"]) for event in events if isinstance(event.get("midi"), int)]
    pitch_classes = [NOTE_NAMES[midi % 12] for midi in midi_values]
    intervals = [
        str(max(-12, min(12, midi_values[index + 1] - midi_values[index])))
        for index in range(len(midi_values) - 1)
    ]
    beat_seconds = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5
    rhythms = [
        str(max(1, min(16, round(float(event.get("durationSeconds") or 0.0) / beat_seconds * 4))))
        for event in events
    ]
    contour = []
    for interval in intervals:
        value = int(interval)
        contour.append("U" if value > 1 else "D" if value < -1 else "R")
    return {
        "noteCount": len(midi_values),
        "pitchClassHistogram": compact_counts(pitch_classes, 12),
        "pitchClassNgrams": ngrams(pitch_classes, 4),
        "intervalNgrams": ngrams(intervals, 5),
        "rhythmNgrams": ngrams(rhythms, 4),
        "contourNgrams": ngrams(contour, 6),
        "firstNotes": [note_name(midi) for midi in midi_values[:24]],
    }


def extract_audio_wav(source: Path, target: Path) -> tuple[bool, str]:
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-t",
            str(MAX_TRANSCRIPTION_SECONDS),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-f",
            "wav",
            str(target),
        ],
        timeout=300,
    )
    return code == 0 and target.exists() and target.stat().st_size > 44, output


def parsed_window_duration(value: str) -> int:
    raw = str(value or "")
    if "*" not in raw:
        return 0
    try:
        start_raw, end_raw = raw.split("*", 1)[1].split("-", 1)
        start = int(float(start_raw))
        end = int(float(end_raw))
    except (IndexError, TypeError, ValueError):
        return 0
    return max(0, end - start)


def active_windows_for_sample(sample: dict[str, Any], state: dict[str, Any]) -> list[dict[str, float]]:
    sample_id = str(sample.get("id") or "").strip()
    if not sample_id:
        return []
    base_start = parse_window_start(str(sample.get("window") or ""))
    sample_duration = parsed_window_duration(str(sample.get("window") or ""))
    sections = state.get("review", {}).get("notableSections", [])
    windows: list[dict[str, float]] = []
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict) or str(section.get("sampleId") or "") != sample_id:
            continue
        if section.get("status") != "candidate_playing_section":
            continue
        try:
            start = float(section.get("startSeconds") or 0) - base_start
            end = float(section.get("endSeconds") or 0) - base_start
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        padded_start = max(0.0, start - ACTIVE_SECTION_PADDING_SECONDS)
        padded_end = end + ACTIVE_SECTION_PADDING_SECONDS
        if sample_duration:
            padded_end = min(float(sample_duration), padded_end)
        if padded_end - padded_start >= 0.5:
            windows.append({"start": round(padded_start, 3), "end": round(padded_end, 3)})
    windows.sort(key=lambda item: item["start"])
    merged: list[dict[str, float]] = []
    for window in windows:
        if not merged or window["start"] - merged[-1]["end"] > ACTIVE_SECTION_MERGE_GAP_SECONDS:
            merged.append(dict(window))
            continue
        merged[-1]["end"] = max(merged[-1]["end"], window["end"])
    return merged[:MAX_ACTIVE_TRANSCRIPTION_SECTIONS]


def estimate_tempo(y: Any, sr: int, librosa: Any) -> float:
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, "item"):
            tempo = tempo.item()
        return round(float(tempo), 1) if float(tempo) > 0 else 0.0
    except Exception:
        return 0.0


def merge_adjacent_same_note_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for event in events:
        if not merged:
            merged.append(dict(event))
            continue
        previous = merged[-1]
        gap = float(event.get("startSeconds") or 0.0) - float(previous.get("endSeconds") or 0.0)
        if event.get("midi") != previous.get("midi") or gap > NOTE_MERGE_GAP_SECONDS:
            merged.append(dict(event))
            continue
        previous_duration = float(previous.get("durationSeconds") or 0.0)
        event_duration = float(event.get("durationSeconds") or 0.0)
        total_duration = max(0.001, previous_duration + gap + event_duration)
        confidence = (
            (float(previous.get("confidence") or 0.0) * previous_duration)
            + (float(event.get("confidence") or 0.0) * event_duration)
        ) / max(0.001, previous_duration + event_duration)
        previous["endSeconds"] = event.get("endSeconds")
        previous["durationSeconds"] = round(total_duration, 3)
        previous["confidence"] = round(confidence, 3)
    return merged


def event_midi(event: dict[str, Any]) -> int | None:
    try:
        midi = int(event.get("midi"))
    except (TypeError, ValueError):
        return None
    if midi < VIOLIN_MIN_MIDI or midi > VIOLIN_MAX_MIDI:
        return None
    return midi


def pitch_sanity_filter(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Remove obvious tracker artifacts without pretending the remaining notes are final score truth."""
    ordered = sorted(
        (dict(event) for event in events if isinstance(event, dict)),
        key=lambda event: float(event.get("startSeconds") or 0.0),
    )
    dropped_glitches = 0
    kept: list[dict[str, Any]] = []
    for event in ordered:
        duration = float(event.get("durationSeconds") or 0.0)
        confidence = float(event.get("confidence") or 0.0)
        if duration <= LOW_CONFIDENCE_GLITCH_SECONDS and confidence < LOW_CONFIDENCE_GLITCH_THRESHOLD:
            detector = str(event.get("detectorSource") or "")
            spectral_score = float(event.get("spectralRelativeScore") or 0.0)
            spectral_min_duration = YIN_TRANSITION_MIN_SECONDS if detector.startswith("spectral_micro") else SPECTRAL_MIN_SEGMENT_SECONDS
            if detector.startswith("spectral_") and duration >= spectral_min_duration and spectral_score >= SPECTRAL_MIN_CONFIDENCE:
                event["uncertain"] = True
                reasons = event.get("uncertaintyReasons")
                event["uncertaintyReasons"] = [*(reasons if isinstance(reasons, list) else []), "short_fast_spectral_note"]
                kept.append(event)
                continue
            dropped_glitches += 1
            continue
        kept.append(event)

    octave_adjusted = 0
    for index in range(1, len(kept) - 1):
        previous_midi = event_midi(kept[index - 1])
        current_midi = event_midi(kept[index])
        next_midi = event_midi(kept[index + 1])
        if previous_midi is None or current_midi is None or next_midi is None:
            continue
        if abs(previous_midi - next_midi) > NEIGHBOR_AGREEMENT_SEMITONES:
            continue
        if (
            abs(current_midi - previous_midi) < OCTAVE_FLIP_MIN_SEMITONES
            or abs(current_midi - next_midi) < OCTAVE_FLIP_MIN_SEMITONES
        ):
            continue
        candidates = [
            shifted
            for shifted in (current_midi - 24, current_midi - 12, current_midi, current_midi + 12, current_midi + 24)
            if VIOLIN_MIN_MIDI <= shifted <= VIOLIN_MAX_MIDI
        ]
        current_score = abs(current_midi - previous_midi) + abs(current_midi - next_midi)
        best_midi = min(candidates, key=lambda midi: abs(midi - previous_midi) + abs(midi - next_midi))
        best_score = abs(best_midi - previous_midi) + abs(best_midi - next_midi)
        if best_midi == current_midi or current_score - best_score < OCTAVE_ADJUSTMENT_MIN_GAIN:
            continue
        event = kept[index]
        event["rawMidi"] = current_midi
        event["rawNote"] = event.get("note") or note_name(current_midi)
        event["midi"] = best_midi
        event["note"] = note_name(best_midi)
        event["confidence"] = round(min(float(event.get("confidence") or 0.0), 0.62), 3)
        event["uncertain"] = True
        reasons = event.get("uncertaintyReasons")
        event["uncertaintyReasons"] = [*(reasons if isinstance(reasons, list) else []), "octave_flip_adjusted"]
        octave_adjusted += 1

    midi_values = [event_midi(event) for event in kept]
    midi_values = [midi for midi in midi_values if midi is not None]
    intervals = [abs(midi_values[index + 1] - midi_values[index]) for index in range(len(midi_values) - 1)]
    confidence_values = sorted(float(event.get("confidence") or 0.0) for event in kept)
    median_confidence = (
        confidence_values[len(confidence_values) // 2]
        if confidence_values
        else 0.0
    )
    low_confidence_count = sum(1 for value in confidence_values if value < LOW_CONFIDENCE_GLITCH_THRESHOLD)
    quality = {
        "rawSelectedEventCount": len(ordered),
        "sanityGlitchDroppedCount": dropped_glitches,
        "sanityOctaveAdjustedCount": octave_adjusted,
        "sanityLargeLeapCount": sum(1 for interval in intervals if interval >= LARGE_LEAP_SEMITONES),
        "sanityLowConfidenceNoteCount": low_confidence_count,
        "sanityMedianConfidence": round(median_confidence, 3),
    }
    return kept[:MAX_STORED_NOTES], quality


def longest_value_run(values: list[int]) -> int:
    longest = 0
    current = 0
    previous: int | None = None
    for value in values:
        if previous is None or value != previous:
            current = 1
            previous = value
        else:
            current += 1
        longest = max(longest, current)
    return longest


def pitch_collapse_report(events: list[dict[str, Any]], detected_onset_count: int = 0) -> dict[str, Any]:
    midi_values = [event_midi(event) for event in events if isinstance(event, dict)]
    midi_values = [midi for midi in midi_values if midi is not None]
    if not midi_values:
        return {
            "pitchCollapseDetected": False,
            "pitchCollapseReason": "",
            "pitchCollapseDominantNote": "",
            "pitchCollapseDominantRatio": 0.0,
            "pitchCollapseLongestRun": 0,
            "pitchCollapseUniquePitchClasses": 0,
        }
    pitch_classes = [midi % 12 for midi in midi_values]
    midi_counts = Counter(midi_values)
    dominant_midi, dominant_count = midi_counts.most_common(1)[0]
    dominant_ratio = dominant_count / max(1, len(midi_values))
    unique_pitch_classes = len(set(pitch_classes))
    longest_midi_run = longest_value_run(midi_values)
    longest_pitch_class_run = longest_value_run(pitch_classes)
    enough_events = len(midi_values) >= PITCH_COLLAPSE_MIN_EVENTS
    repeated_single_pitch = (
        dominant_ratio >= PITCH_COLLAPSE_DOMINANT_RATIO
        and unique_pitch_classes <= PITCH_COLLAPSE_MAX_PITCH_CLASSES
    )
    long_run = (
        longest_midi_run >= PITCH_COLLAPSE_MIN_RUN
        or longest_pitch_class_run >= PITCH_COLLAPSE_MIN_RUN
    )
    onset_rich_trace = detected_onset_count >= max(PITCH_COLLAPSE_MIN_EVENTS, int(len(midi_values) * 0.65))
    collapsed = enough_events and repeated_single_pitch and (long_run or onset_rich_trace)
    reason = ""
    if collapsed:
        reason = (
            "The pitch tracker produced a near-single-note stream despite many note events/onsets; "
            "this is not acceptable sheet-music transcription."
        )
    return {
        "pitchCollapseDetected": collapsed,
        "pitchCollapseReason": reason,
        "pitchCollapseDominantNote": note_name(dominant_midi),
        "pitchCollapseDominantCount": dominant_count,
        "pitchCollapseDominantRatio": round(dominant_ratio, 3),
        "pitchCollapseLongestRun": int(max(longest_midi_run, longest_pitch_class_run)),
        "pitchCollapseUniqueMidiCount": len(midi_counts),
        "pitchCollapseUniquePitchClasses": unique_pitch_classes,
        "pitchCollapseEventCount": len(midi_values),
        "pitchCollapseDetectedOnsetCount": int(detected_onset_count),
    }


def pitch_diversity(events: list[dict[str, Any]]) -> dict[str, Any]:
    midi_values = [event_midi(event) for event in events if isinstance(event, dict)]
    midi_values = [midi for midi in midi_values if midi is not None]
    if not midi_values:
        return {
            "count": 0,
            "uniqueMidi": 0,
            "uniquePitchClasses": 0,
            "dominantRatio": 0.0,
            "longestRun": 0,
        }
    counts = Counter(midi_values)
    _, dominant_count = counts.most_common(1)[0]
    pitch_classes = [midi % 12 for midi in midi_values]
    return {
        "count": len(midi_values),
        "uniqueMidi": len(counts),
        "uniquePitchClasses": len(set(pitch_classes)),
        "dominantRatio": round(dominant_count / max(1, len(midi_values)), 3),
        "longestRun": longest_value_run(midi_values),
    }


def numpy_median_fallback(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(int(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (float(ordered[middle - 1]) + float(ordered[middle])) / 2.0


def normalize_audio_signal(y: Any, librosa: Any) -> Any:
    try:
        return librosa.util.normalize(y)
    except Exception:
        return y


def compact_onset_frames(frames: list[int], min_gap: int = FAST_ONSET_MIN_FRAME_GAP) -> list[int]:
    compact: list[int] = []
    for frame in sorted(set(int(value) for value in frames if int(value) >= 0)):
        if compact and frame - compact[-1] <= max(0, int(min_gap)):
            continue
        compact.append(frame)
    return compact


def onset_frames_for_signal(y: Any, sr: int, hop_length: int, librosa: Any, numpy: Any) -> list[int]:
    frames: list[int] = []
    try:
        detected = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length, units="frames")
        frames.extend(int(frame) for frame in detected)
    except Exception:
        pass
    try:
        dense = librosa.onset.onset_detect(
            y=y,
            sr=sr,
            hop_length=hop_length,
            units="frames",
            backtrack=True,
            pre_max=1,
            post_max=1,
            pre_avg=2,
            post_avg=2,
            delta=FAST_ONSET_DELTA,
            wait=FAST_ONSET_WAIT_FRAMES,
        )
        frames.extend(int(frame) for frame in dense)
    except Exception:
        pass
    return compact_onset_frames(frames)


def merge_onset_frame_sets(*frame_sets: list[int]) -> list[int]:
    frames: list[int] = []
    for frame_set in frame_sets:
        frames.extend(int(frame) for frame in frame_set)
    return compact_onset_frames(frames)


def event_start_seconds(event: dict[str, Any]) -> float:
    try:
        return float(event.get("startSeconds") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def event_end_seconds(event: dict[str, Any]) -> float:
    try:
        return float(event.get("endSeconds") or event.get("startSeconds") or 0.0)
    except (TypeError, ValueError):
        return event_start_seconds(event)


def event_midpoint_seconds(event: dict[str, Any]) -> float:
    return (event_start_seconds(event) + event_end_seconds(event)) / 2.0


def events_match_for_audio_agreement(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_midi = event_midi(left)
    right_midi = event_midi(right)
    if left_midi is None or right_midi is None:
        return False
    if abs(left_midi - right_midi) > AUDIO_AGREEMENT_MIDI_TOLERANCE:
        return False
    left_start = event_start_seconds(left)
    left_end = event_end_seconds(left)
    right_start = event_start_seconds(right)
    right_end = event_end_seconds(right)
    overlap = min(left_end, right_end) - max(left_start, right_start)
    if overlap > 0:
        return True
    return abs(left_start - right_start) <= AUDIO_AGREEMENT_SECONDS or abs(event_midpoint_seconds(left) - event_midpoint_seconds(right)) <= AUDIO_AGREEMENT_SECONDS


def mark_audio_agreement(
    events: list[dict[str, Any]],
    selected_source: str,
    peer_groups: list[tuple[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    if selected_source.startswith("spectral_onset") or selected_source.startswith("spectral_fast") or selected_source.startswith("spectral_octave"):
        selected_family = "spectral_onset"
    elif selected_source.startswith("spectral_micro"):
        selected_family = "spectral_micro"
    else:
        selected_family = selected_source
    marked: list[dict[str, Any]] = []
    for event in events:
        item = dict(event)
        item["detectorSource"] = selected_source
        sources: set[str] = set()
        for source, peers in peer_groups:
            if source == selected_family:
                continue
            for peer in peers:
                if events_match_for_audio_agreement(item, peer):
                    sources.add(source)
                    break
        if sources:
            item["audioAgreement"] = True
            item["agreementSources"] = sorted(sources)
            item["agreementSourceCount"] = len(sources)
        else:
            item["audioAgreement"] = False
            item["agreementSources"] = []
            item["agreementSourceCount"] = 0
        marked.append(item)
    return marked


def spectral_candidate_score(
    magnitudes: Any,
    frequencies: Any,
    candidate_hz: float,
    numpy: Any,
) -> float:
    score = 0.0
    nyquist = float(frequencies[-1]) if len(frequencies) else 0.0
    for harmonic in range(1, max(1, SPECTRAL_HARMONIC_COUNT) + 1):
        target = candidate_hz * harmonic
        if not nyquist or target >= nyquist:
            break
        weight = 1.0 / harmonic
        score += weight * float(numpy.interp(target, frequencies, magnitudes))
    return score


def spectral_pitch_for_segment(segment: Any, sr: int, librosa: Any, numpy: Any) -> dict[str, Any] | None:
    if segment.size <= 0:
        return None
    try:
        cleaned = librosa.util.normalize(segment)
    except Exception:
        cleaned = segment
    rms = float(numpy.sqrt(numpy.mean(numpy.square(cleaned)))) if cleaned.size else 0.0
    if rms <= 0.002:
        return None
    window = numpy.hanning(cleaned.size)
    magnitudes = numpy.abs(numpy.fft.rfft(cleaned * window))
    frequencies = numpy.fft.rfftfreq(cleaned.size, 1.0 / sr)
    if magnitudes.size <= 4 or frequencies.size != magnitudes.size:
        return None
    scores: list[tuple[float, int]] = []
    for midi in range(VIOLIN_MIN_MIDI, VIOLIN_MAX_MIDI + 1):
        hz = float(librosa.midi_to_hz(midi))
        scores.append((spectral_candidate_score(magnitudes, frequencies, hz, numpy), midi))
    scores.sort(reverse=True)
    best_score, best_midi = scores[0]
    if best_score <= 0:
        return None
    scores_by_midi = {midi: score for score, midi in scores}
    raw_midi = int(best_midi)
    octave_rescued = False
    for shift in (24, 12):
        shifted = raw_midi + shift
        shifted_score = scores_by_midi.get(shifted)
        if (
            shifted_score is not None
            and shifted >= SPECTRAL_OCTAVE_RESCUE_MIN_MIDI
            and shifted_score >= best_score * SPECTRAL_OCTAVE_RESCUE_RATIO
        ):
            best_score = shifted_score
            best_midi = shifted
            octave_rescued = True
            break
    second_score = scores[1][0] if len(scores) > 1 else 0.0
    total_top = sum(score for score, _ in scores[:8]) or best_score
    confidence = max(0.0, min(1.0, (best_score - second_score) / max(best_score, 1e-9)))
    relative = best_score / max(total_top, 1e-9)
    if relative < SPECTRAL_MIN_CONFIDENCE:
        return None
    event = {
        "midi": int(best_midi),
        "note": note_name(int(best_midi)),
        "confidence": round(max(confidence, relative), 3),
        "spectralRelativeScore": round(relative, 3),
    }
    if octave_rescued:
        event["rawMidi"] = raw_midi
        event["rawNote"] = note_name(raw_midi)
        event["uncertain"] = True
        event["uncertaintyReasons"] = ["spectral_octave_rescue"]
    return event


def spectral_stream_quality(events: list[dict[str, Any]]) -> float:
    if not events:
        return -999.0
    diversity = pitch_diversity(events)
    midi_values = [event_midi(event) for event in events if isinstance(event, dict)]
    midi_values = [midi for midi in midi_values if midi is not None]
    intervals = [abs(midi_values[index + 1] - midi_values[index]) for index in range(len(midi_values) - 1)]
    average_confidence = sum(float(event.get("confidence") or 0.0) for event in events) / max(1, len(events))
    large_leaps = sum(1 for interval in intervals if interval >= LARGE_LEAP_SEMITONES)
    octave_rescues = sum(1 for event in events if "spectral_octave_rescue" in (event.get("uncertaintyReasons") if isinstance(event.get("uncertaintyReasons"), list) else []))
    return (
        len(events) * 1.3
        + float(diversity["uniquePitchClasses"]) * 3.0
        + average_confidence * 5.0
        + octave_rescues * 0.7
        - float(diversity["dominantRatio"]) * 2.0
        - large_leaps * 1.5
    )


def annotated_spectral_events(events: list[dict[str, Any]], signal_name: str) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for event in events:
        item = dict(event)
        item["spectralSignal"] = signal_name
        annotated.append(item)
    return annotated


def choose_spectral_event_stream(
    harmonic_events: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    harmonic = annotated_spectral_events(harmonic_events, "harmonic")
    source = annotated_spectral_events(source_events, "source")
    if not source:
        return harmonic, "harmonic"
    if not harmonic:
        return source, "source"
    source_quality = spectral_stream_quality(source)
    harmonic_quality = spectral_stream_quality(harmonic)
    if source_quality >= harmonic_quality - 0.75:
        return source, "source"
    return harmonic, "harmonic"


def spectral_onset_events(
    y: Any,
    onset_frames: Any,
    sr: int,
    hop_length: int,
    librosa: Any,
    numpy: Any,
) -> list[dict[str, Any]]:
    frame_count = max(1, int(math.ceil(len(y) / max(1, hop_length))))
    raw_boundaries = [0]
    for frame in onset_frames:
        try:
            index = int(frame)
        except (TypeError, ValueError):
            continue
        if 0 < index < frame_count:
            raw_boundaries.append(index)
    raw_boundaries.append(frame_count)
    boundaries = sorted(set(raw_boundaries))
    events: list[dict[str, Any]] = []
    for start_frame, end_frame in zip(boundaries, boundaries[1:]):
        if end_frame <= start_frame:
            continue
        start_sample = int(start_frame * hop_length)
        end_sample = min(len(y), int(end_frame * hop_length))
        if end_sample <= start_sample:
            continue
        start = float(start_sample / sr)
        end = float(end_sample / sr)
        duration = end - start
        if duration < SPECTRAL_MIN_SEGMENT_SECONDS:
            continue
        segment = y[start_sample:end_sample]
        pitch = spectral_pitch_for_segment(segment, sr, librosa, numpy)
        if not pitch:
            continue
        event = {
            "startSeconds": round(start, 3),
            "endSeconds": round(end, 3),
            "durationSeconds": round(duration, 3),
            "midi": pitch["midi"],
            "note": pitch["note"],
            "confidence": pitch["confidence"],
            "spectralRelativeScore": pitch["spectralRelativeScore"],
        }
        for key in ("rawMidi", "rawNote", "uncertain", "uncertaintyReasons"):
            if key in pitch:
                event[key] = pitch[key]
        events.append(event)
        if len(events) >= MAX_STORED_NOTES:
            break
    return events


def stabilize_micro_pitch_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stabilized = [dict(frame) for frame in frames]
    for index in range(1, len(stabilized) - 1):
        previous_midi = event_midi(stabilized[index - 1])
        current_midi = event_midi(stabilized[index])
        next_midi = event_midi(stabilized[index + 1])
        if previous_midi is None or current_midi is None or next_midi is None:
            continue
        if previous_midi != next_midi:
            continue
        if abs(current_midi - previous_midi) > VIBRATO_SEMITONE_RANGE:
            continue
        current_confidence = float(stabilized[index].get("confidence") or 0.0)
        neighbor_confidence = max(
            float(stabilized[index - 1].get("confidence") or 0.0),
            float(stabilized[index + 1].get("confidence") or 0.0),
        )
        if current_confidence > neighbor_confidence + 0.12:
            continue
        stabilized[index]["rawMidi"] = current_midi
        stabilized[index]["rawNote"] = stabilized[index].get("note") or note_name(current_midi)
        stabilized[index]["midi"] = previous_midi
        stabilized[index]["note"] = note_name(previous_midi)
        stabilized[index]["uncertain"] = True
        reasons = stabilized[index].get("uncertaintyReasons")
        stabilized[index]["uncertaintyReasons"] = [
            *(reasons if isinstance(reasons, list) else []),
            "micro_vibrato_neighbor_absorbed",
        ]
    return stabilized


def spectral_micro_events(
    y: Any,
    sr: int,
    librosa: Any,
    numpy: Any,
) -> list[dict[str, Any]]:
    if y.size <= 0:
        return []
    window_samples = max(256, int(round(SPECTRAL_MICRO_WINDOW_SECONDS * sr)))
    hop_samples = max(96, int(round(SPECTRAL_MICRO_HOP_SECONDS * sr)))
    if len(y) < window_samples:
        return []
    frame_rms: list[float] = []
    starts = list(range(0, max(1, len(y) - window_samples + 1), hop_samples))
    if starts and starts[-1] + window_samples < len(y):
        starts.append(len(y) - window_samples)
    for start_sample in starts:
        segment = y[start_sample : start_sample + window_samples]
        frame_rms.append(float(numpy.sqrt(numpy.mean(numpy.square(segment)))) if segment.size else 0.0)
    active_rms = [value for value in frame_rms if value > 0]
    if not active_rms:
        return []
    rms_threshold = max(0.004, float(numpy.percentile(numpy.array(active_rms), 62)) * SPECTRAL_MICRO_MIN_RMS_RATIO)
    frame_candidates: list[dict[str, Any]] = []
    for start_sample, rms_value in zip(starts, frame_rms):
        if rms_value < rms_threshold:
            continue
        segment = y[start_sample : start_sample + window_samples]
        pitch = spectral_pitch_for_segment(segment, sr, librosa, numpy)
        if not pitch:
            continue
        midi = int(pitch["midi"])
        if midi < SPECTRAL_MICRO_MIN_MIDI:
            continue
        start = float(start_sample / sr)
        end = float((start_sample + window_samples) / sr)
        event = {
            "startSeconds": round(start, 3),
            "endSeconds": round(end, 3),
            "durationSeconds": round(end - start, 3),
            "midi": midi,
            "note": pitch["note"],
            "confidence": pitch["confidence"],
            "spectralRelativeScore": pitch["spectralRelativeScore"],
            "microRms": round(rms_value, 5),
        }
        for key in ("rawMidi", "rawNote", "uncertain", "uncertaintyReasons"):
            if key in pitch:
                event[key] = pitch[key]
        frame_candidates.append(event)
        if len(frame_candidates) >= MAX_STORED_NOTES:
            break
    if not frame_candidates:
        return []

    stabilized = stabilize_micro_pitch_frames(frame_candidates)
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_confidences: list[float] = []
    current_scores: list[float] = []
    current_rms: list[float] = []

    def close_current() -> None:
        nonlocal current, current_confidences, current_scores, current_rms
        if not current:
            return
        duration = max(0.0, float(current.get("endSeconds") or 0.0) - float(current.get("startSeconds") or 0.0))
        if duration >= SPECTRAL_MIN_SEGMENT_SECONDS:
            current["durationSeconds"] = round(duration, 3)
            current["confidence"] = round(sum(current_confidences) / max(1, len(current_confidences)), 3)
            current["spectralRelativeScore"] = round(sum(current_scores) / max(1, len(current_scores)), 3)
            current["microRms"] = round(sum(current_rms) / max(1, len(current_rms)), 5)
            current["detectorSource"] = "spectral_micro"
            events.append(current)
        current = None
        current_confidences = []
        current_scores = []
        current_rms = []

    for candidate in stabilized:
        midi = event_midi(candidate)
        if midi is None:
            continue
        if current and event_midi(current) == midi:
            current["endSeconds"] = candidate.get("endSeconds")
            current_confidences.append(float(candidate.get("confidence") or 0.0))
            current_scores.append(float(candidate.get("spectralRelativeScore") or 0.0))
            current_rms.append(float(candidate.get("microRms") or 0.0))
            if candidate.get("uncertain"):
                current["uncertain"] = True
                reasons = current.get("uncertaintyReasons")
                current["uncertaintyReasons"] = sorted(
                    {
                        *(reasons if isinstance(reasons, list) else []),
                        *(candidate.get("uncertaintyReasons") if isinstance(candidate.get("uncertaintyReasons"), list) else []),
                    }
                )
            continue
        close_current()
        current = dict(candidate)
        current_confidences = [float(candidate.get("confidence") or 0.0)]
        current_scores = [float(candidate.get("spectralRelativeScore") or 0.0)]
        current_rms = [float(candidate.get("microRms") or 0.0)]
    close_current()

    for index in range(len(events) - 1):
        next_start = float(events[index + 1].get("startSeconds") or 0.0)
        current_start = float(events[index].get("startSeconds") or 0.0)
        current_end = float(events[index].get("endSeconds") or 0.0)
        if current_end > next_start:
            adjusted_end = max(current_start + YIN_TRANSITION_MIN_SECONDS, next_start)
            events[index]["endSeconds"] = round(adjusted_end, 3)
            events[index]["durationSeconds"] = round(max(0.0, adjusted_end - current_start), 3)
    return events[:MAX_STORED_NOTES]


def choose_spectral_detail_stream(
    onset_events: list[dict[str, Any]],
    micro_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if not micro_events:
        return onset_events, "onset"
    if not onset_events:
        return micro_events, "micro"
    onset_diversity = pitch_diversity(onset_events)
    micro_diversity = pitch_diversity(micro_events)
    micro_midi_values = [event_midi(event) for event in micro_events if isinstance(event, dict)]
    micro_midi_values = [midi for midi in micro_midi_values if midi is not None]
    micro_high_register = bool(micro_midi_values) and min(micro_midi_values) >= SPECTRAL_MICRO_MIN_MIDI
    micro_adds_detail = (
        len(micro_events) >= max(SPECTRAL_MICRO_MIN_EVENTS, len(onset_events) + 2)
        and micro_diversity["uniquePitchClasses"] >= max(3, onset_diversity["uniquePitchClasses"])
        and micro_diversity["dominantRatio"] <= 0.80
    )
    micro_prevents_collapse = (
        len(micro_events) >= SPECTRAL_MICRO_MIN_EVENTS
        and micro_diversity["uniquePitchClasses"] >= onset_diversity["uniquePitchClasses"] + 2
        and onset_diversity["dominantRatio"] >= 0.60
    )
    if micro_high_register and (micro_adds_detail or micro_prevents_collapse):
        return micro_events, "micro"
    return onset_events, "onset"


def yin_transition_events(
    y: Any,
    sr: int,
    hop_length: int,
    librosa: Any,
    numpy: Any,
) -> list[dict[str, Any]]:
    if y.size <= 0:
        return []
    try:
        yin = librosa.yin(
            y,
            fmin=librosa.midi_to_hz(VIOLIN_MIN_MIDI),
            fmax=librosa.midi_to_hz(VIOLIN_MAX_MIDI),
            sr=sr,
            frame_length=PITCH_FRAME_LENGTH,
            hop_length=hop_length,
        )
        rms = librosa.feature.rms(y=y, frame_length=PITCH_FRAME_LENGTH, hop_length=hop_length, center=True)[0]
    except Exception:
        return []
    if len(yin) == 0 or len(rms) == 0:
        return []
    active_rms = [float(value) for value in rms if float(value) > 0]
    if not active_rms:
        return []
    threshold = max(0.006, float(numpy.percentile(numpy.array(active_rms), 70)) * YIN_TRANSITION_RMS_RATIO)
    frame_seconds = hop_length / sr
    events: list[dict[str, Any]] = []
    current_midi: int | None = None
    current_start: float | None = None
    current_energy: list[float] = []

    def close(end_seconds: float) -> None:
        nonlocal current_midi, current_start, current_energy
        if current_midi is None or current_start is None:
            current_midi = None
            current_start = None
            current_energy = []
            return
        duration = max(0.0, end_seconds - current_start)
        if duration >= YIN_TRANSITION_MIN_SECONDS:
            confidence = min(0.86, max(0.54, sum(current_energy) / max(1, len(current_energy)) / max(threshold, 1e-9) * 0.18))
            events.append(
                {
                    "startSeconds": round(current_start, 3),
                    "endSeconds": round(end_seconds, 3),
                    "durationSeconds": round(duration, 3),
                    "midi": int(current_midi),
                    "note": note_name(int(current_midi)),
                    "confidence": round(confidence, 3),
                    "detectorSource": "yin_transition_trace",
                    "candidateOnly": True,
                }
            )
        current_midi = None
        current_start = None
        current_energy = []

    for index, value in enumerate(yin):
        if index >= len(rms):
            break
        energy = float(rms[index])
        time_seconds = float(index * frame_seconds)
        try:
            frequency = float(value)
        except (TypeError, ValueError):
            close(time_seconds)
            continue
        if energy < threshold or math.isnan(frequency) or frequency <= 0:
            close(time_seconds)
            continue
        midi = midi_from_hz(frequency)
        if midi < VIOLIN_MIN_MIDI or midi > VIOLIN_MAX_MIDI:
            close(time_seconds)
            continue
        if current_midi is None:
            current_midi = midi
            current_start = time_seconds
            current_energy = [energy]
            continue
        if midi == current_midi:
            current_energy.append(energy)
            continue
        close(time_seconds)
        current_midi = midi
        current_start = time_seconds
        current_energy = [energy]
        if len(events) >= MAX_STORED_NOTES:
            break
    close(float(len(yin) * frame_seconds))
    return merge_adjacent_same_note_events(events)[:MAX_STORED_NOTES]


def transcription_failure_state(events: list[dict[str, Any]], quality: dict[str, Any]) -> dict[str, Any]:
    collapse = pitch_collapse_report(events, int(quality.get("detectedOnsetCount") or 0))
    if collapse.get("pitchCollapseDetected"):
        return {
            "failed": True,
            "status": "failed_pitch_collapse",
            "failureMode": "repeated_pitch_collapse",
            "failureLabel": "pitch collapse",
            "failureLimit": (
                "Machine pitch extraction was rejected because the note stream collapsed into repeated "
                f"{collapse.get('pitchCollapseDominantNote') or 'single-pitch'} events. "
                "Use the matched clip evidence; do not treat these notes as the played passage."
            ),
            **collapse,
        }
    return {"failed": False, **collapse}


def f0_to_events(f0: Any, voiced_flag: Any, voiced_prob: Any, sr: int, hop_length: int, numpy: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_start: float | None = None
    midi_buffer: list[int] = []
    prob_buffer: list[float] = []
    pending_start: float | None = None
    pending_midi: int | None = None
    pending_midi_buffer: list[int] = []
    pending_prob_buffer: list[float] = []
    last_time = 0.0
    frame_seconds = hop_length / sr

    def median_midi(values: list[int]) -> int:
        return int(round(float(numpy.median(numpy.array(values)))))

    def reset_pending() -> None:
        nonlocal pending_start, pending_midi, pending_midi_buffer, pending_prob_buffer
        pending_start = None
        pending_midi = None
        pending_midi_buffer = []
        pending_prob_buffer = []

    def absorb_pending_as_current() -> None:
        nonlocal pending_midi_buffer, pending_prob_buffer
        if pending_midi_buffer:
            midi_buffer.extend(pending_midi_buffer)
            prob_buffer.extend(pending_prob_buffer)
        reset_pending()

    def required_change_frames(from_midi: int, to_midi: int) -> int:
        if abs(int(from_midi) - int(to_midi)) <= VIBRATO_SEMITONE_RANGE:
            return max(NOTE_CHANGE_CONFIRM_FRAMES, VIBRATO_CHANGE_CONFIRM_FRAMES)
        return NOTE_CHANGE_CONFIRM_FRAMES

    def close_event(end_time: float) -> None:
        nonlocal current_start, midi_buffer, prob_buffer
        if current_start is None or not midi_buffer:
            current_start = None
            midi_buffer = []
            prob_buffer = []
            return
        start = float(current_start)
        duration = max(0.0, end_time - start)
        if duration >= MIN_NOTE_SECONDS:
            midi = median_midi(midi_buffer)
            events.append(
                {
                    "startSeconds": round(start, 3),
                    "endSeconds": round(end_time, 3),
                    "durationSeconds": round(duration, 3),
                    "midi": midi,
                    "note": note_name(midi),
                    "confidence": round(sum(prob_buffer) / max(1, len(prob_buffer)), 3),
                }
            )
        current_start = None
        midi_buffer = []
        prob_buffer = []

    for index, value in enumerate(f0):
        time_seconds = float(index * hop_length / sr)
        last_time = time_seconds
        voiced = bool(voiced_flag[index]) if index < len(voiced_flag) else False
        probability = float(voiced_prob[index]) if index < len(voiced_prob) and not math.isnan(float(voiced_prob[index])) else 0.0
        midi = valid_frame_midi(value, voiced, probability)
        if midi is None:
            absorb_pending_as_current()
            close_event(time_seconds)
            continue
        if current_start is None:
            current_start = time_seconds
            midi_buffer = [midi]
            prob_buffer = [probability]
            reset_pending()
            continue
        current_midi = median_midi(midi_buffer)
        if midi == current_midi:
            absorb_pending_as_current()
            midi_buffer.append(midi)
            prob_buffer.append(probability)
            continue
        if pending_midi == midi:
            pending_midi_buffer.append(midi)
            pending_prob_buffer.append(probability)
        else:
            absorb_pending_as_current()
            pending_start = time_seconds
            pending_midi = midi
            pending_midi_buffer = [midi]
            pending_prob_buffer = [probability]
        if (
            pending_midi is not None
            and len(pending_midi_buffer) >= required_change_frames(current_midi, pending_midi)
            and pending_start is not None
        ):
            next_start = pending_start
            next_midi_buffer = [*pending_midi_buffer]
            next_prob_buffer = [*pending_prob_buffer]
            close_event(next_start)
            current_start = next_start
            midi_buffer = next_midi_buffer
            prob_buffer = next_prob_buffer
            reset_pending()
    if (
        pending_midi_buffer
        and pending_midi is not None
        and pending_start is not None
        and midi_buffer
        and len(pending_midi_buffer) >= required_change_frames(median_midi(midi_buffer), pending_midi)
    ):
        next_start = pending_start
        next_midi_buffer = [*pending_midi_buffer]
        next_prob_buffer = [*pending_prob_buffer]
        close_event(next_start)
        current_start = next_start
        midi_buffer = next_midi_buffer
        prob_buffer = next_prob_buffer
    else:
        absorb_pending_as_current()
    close_event(last_time + frame_seconds)
    return merge_adjacent_same_note_events(events)[:MAX_STORED_NOTES]


def f0_to_onset_events(
    f0: Any,
    voiced_flag: Any,
    voiced_prob: Any,
    onset_frames: Any,
    sr: int,
    hop_length: int,
    numpy: Any,
) -> list[dict[str, Any]]:
    frame_count = len(f0)
    if not frame_count:
        return []
    frame_seconds = hop_length / sr
    raw_boundaries = [0]
    for frame in onset_frames:
        try:
            index = int(frame)
        except (TypeError, ValueError):
            continue
        if 0 < index < frame_count:
            raw_boundaries.append(index)
    raw_boundaries.append(frame_count)
    boundaries = sorted(set(raw_boundaries))
    events: list[dict[str, Any]] = []
    for start_frame, end_frame in zip(boundaries, boundaries[1:]):
        if end_frame <= start_frame:
            continue
        midi_values: list[int] = []
        probabilities: list[float] = []
        first_voiced: int | None = None
        last_voiced: int | None = None
        for index in range(start_frame, end_frame):
            voiced = bool(voiced_flag[index]) if index < len(voiced_flag) else False
            probability = float(voiced_prob[index]) if index < len(voiced_prob) and not math.isnan(float(voiced_prob[index])) else 0.0
            midi = valid_frame_midi(f0[index], voiced, probability)
            if midi is None:
                continue
            if first_voiced is None:
                first_voiced = index
            last_voiced = index
            midi_values.append(midi)
            probabilities.append(probability)
        if len(midi_values) < ONSET_MIN_VOICED_FRAMES or first_voiced is None or last_voiced is None:
            continue
        segment_frames = max(1, end_frame - start_frame)
        voiced_fraction = len(midi_values) / segment_frames
        event_start_frame = start_frame if voiced_fraction >= 0.35 else first_voiced
        event_end_frame = end_frame if voiced_fraction >= 0.35 else last_voiced + 1
        start = float(event_start_frame * frame_seconds)
        end = float(event_end_frame * frame_seconds)
        duration = max(0.0, end - start)
        if duration < MIN_ONSET_NOTE_SECONDS:
            end = start + MIN_ONSET_NOTE_SECONDS
            duration = MIN_ONSET_NOTE_SECONDS
        midi = int(round(float(numpy.median(numpy.array(midi_values)))))
        events.append(
            {
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
                "durationSeconds": round(duration, 3),
                "midi": midi,
                "note": note_name(midi),
                "confidence": round(sum(probabilities) / max(1, len(probabilities)), 3),
            }
        )
        if len(events) >= MAX_STORED_NOTES:
            break
    return events


def choose_transcription_events(
    pitch_events: list[dict[str, Any]],
    onset_events: list[dict[str, Any]],
    spectral_events: list[dict[str, Any]] | None = None,
    spectral_family: str = "spectral_onset",
) -> tuple[list[dict[str, Any]], str]:
    spectral_events = spectral_events or []
    spectral_diversity = pitch_diversity(spectral_events)
    pitch_diversity_state = pitch_diversity(pitch_events)
    onset_diversity_state = pitch_diversity(onset_events)
    pitch_collapsed = pitch_collapse_report(pitch_events, len(onset_events)).get("pitchCollapseDetected")
    onset_collapsed = pitch_collapse_report(onset_events, len(onset_events)).get("pitchCollapseDetected")
    base_events = onset_events if onset_events else pitch_events
    base_diversity = onset_diversity_state if onset_events else pitch_diversity_state
    base_midi_values = [event_midi(event) for event in base_events if isinstance(event, dict)]
    base_midi_values = [midi for midi in base_midi_values if midi is not None]
    spectral_midi_values = [event_midi(event) for event in spectral_events if isinstance(event, dict)]
    spectral_midi_values = [midi for midi in spectral_midi_values if midi is not None]
    if base_midi_values and spectral_midi_values:
        base_counts = Counter(base_midi_values)
        spectral_counts = Counter(spectral_midi_values)
        base_midi, _ = base_counts.most_common(1)[0]
        spectral_midi, spectral_count = spectral_counts.most_common(1)[0]
        spectral_ratio = spectral_count / max(1, len(spectral_midi_values))
        if (
            spectral_midi > base_midi
            and (spectral_midi - base_midi) in {12, 24}
            and spectral_midi % 12 == base_midi % 12
            and base_diversity["uniquePitchClasses"] <= 2
            and spectral_ratio >= 0.55
            and any(float(event.get("confidence") or 0.0) >= SPECTRAL_MIN_CONFIDENCE for event in spectral_events)
        ):
            return spectral_events[:MAX_STORED_NOTES], "spectral_micro_octave_rescue" if spectral_family == "spectral_micro" else "spectral_octave_rescue"
        base_median = int(round(float(numpy_median_fallback(base_midi_values))))
        spectral_median = int(round(float(numpy_median_fallback(spectral_midi_values))))
        spectral_high_register = spectral_median >= SPECTRAL_OCTAVE_RESCUE_MIN_MIDI
        octave_shifted_trace = (
            spectral_high_register
            and 10 <= spectral_median - base_median <= 14
            and spectral_diversity["uniquePitchClasses"] >= max(3, base_diversity["uniquePitchClasses"] - 1)
            and len(spectral_events) >= max(SPECTRAL_FAST_MIN_EVENTS, int(len(base_events) * 0.55))
        )
        if octave_shifted_trace:
            return spectral_events[:MAX_STORED_NOTES], "spectral_micro_octave_rescue" if spectral_family == "spectral_micro" else "spectral_octave_rescue"
    spectral_is_useful = (
        len(spectral_events) >= MIN_ACTIVE_WINDOW_NOTES
        and spectral_diversity["uniquePitchClasses"] >= max(3, pitch_diversity_state["uniquePitchClasses"])
        and spectral_diversity["dominantRatio"] <= 0.72
    )
    spectral_fast_trace = (
        len(spectral_events) >= max(SPECTRAL_FAST_MIN_EVENTS, int(len(base_events) * 0.65))
        and spectral_diversity["uniquePitchClasses"] >= max(3, base_diversity["uniquePitchClasses"] + 1)
        and spectral_diversity["dominantRatio"] <= 0.78
    )
    if spectral_is_useful and (pitch_collapsed or onset_collapsed):
        return spectral_events[:MAX_STORED_NOTES], "spectral_micro_rescue" if spectral_family == "spectral_micro" else "spectral_onset_rescue"
    if spectral_fast_trace:
        return spectral_events[:MAX_STORED_NOTES], "spectral_micro_high_rescue" if spectral_family == "spectral_micro" else "spectral_fast_note_rescue"
    if spectral_is_useful and spectral_diversity["uniquePitchClasses"] > onset_diversity_state["uniquePitchClasses"] + 1:
        return spectral_events[:MAX_STORED_NOTES], "spectral_micro" if spectral_family == "spectral_micro" else "spectral_onset"
    if not onset_events:
        return pitch_events, "pitch_hysteresis"
    if len(onset_events) >= max(len(pitch_events) + 4, int(len(pitch_events) * ONSET_EVENT_MULTIPLIER)):
        return onset_events[:MAX_STORED_NOTES], "onset_segmented_pyin"
    if not pitch_events and onset_events:
        return onset_events[:MAX_STORED_NOTES], "onset_segmented_pyin"
    return pitch_events, "pitch_hysteresis"


def notation_text(events: list[dict[str, Any]], tempo_bpm: float) -> str:
    if not events:
        return ""
    beat_seconds = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5
    tokens = []
    for event in events[:80]:
        beats = max(0.25, float(event.get("durationSeconds") or 0.0) / beat_seconds)
        tokens.append(f"{event.get('note')}:{beats:.2f}b")
    return " ".join(tokens)


def pitch_tracking_signal(y: Any, librosa: Any, numpy: Any) -> tuple[Any, str]:
    normalized = normalize_audio_signal(y, librosa)
    try:
        harmonic = librosa.effects.harmonic(normalized, margin=HARMONIC_MARGIN)
        harmonic_rms = float(numpy.sqrt(numpy.mean(numpy.square(harmonic)))) if harmonic.size else 0.0
        source_rms = float(numpy.sqrt(numpy.mean(numpy.square(normalized)))) if normalized.size else 0.0
        if harmonic.size == normalized.size and harmonic_rms >= max(0.01, source_rms * 0.08):
            return librosa.util.normalize(harmonic), "trimmed_normalized_harmonic"
    except Exception:
        pass
    return normalized, "trimmed_normalized"


def stable_single_note_fragments(y: Any, sr: int, librosa: Any, numpy: Any) -> list[dict[str, Any]]:
    if y.size <= 0:
        return []
    frame_length = MATCHED_FRAGMENT_FRAME_LENGTH
    hop_length = MATCHED_FRAGMENT_HOP_LENGTH
    try:
        f0, voiced_flag, voiced_prob = librosa.pyin(
            y,
            fmin=librosa.midi_to_hz(VIOLIN_MIN_MIDI),
            fmax=librosa.midi_to_hz(VIOLIN_MAX_MIDI),
            sr=sr,
            frame_length=frame_length,
            hop_length=hop_length,
        )
        yin = librosa.yin(
            y,
            fmin=librosa.midi_to_hz(VIOLIN_MIN_MIDI),
            fmax=librosa.midi_to_hz(VIOLIN_MAX_MIDI),
            sr=sr,
            frame_length=frame_length,
            hop_length=hop_length,
        )
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length, center=True)[0]
    except Exception:
        return []
    if len(f0) == 0:
        return []
    try:
        rms_floor = max(0.003, float(numpy.percentile(rms, 55)) * 0.60) if len(rms) else 0.003
    except Exception:
        rms_floor = 0.003
    frame_seconds = hop_length / sr
    accepted: list[dict[str, Any]] = []
    for index, frequency in enumerate(f0):
        probability = (
            float(voiced_prob[index])
            if index < len(voiced_prob) and not math.isnan(float(voiced_prob[index]))
            else 0.0
        )
        voiced = bool(voiced_flag[index]) if index < len(voiced_flag) else False
        rms_value = float(rms[index]) if index < len(rms) else 0.0
        midi = valid_frame_midi(frequency, voiced, probability)
        if midi is None or probability < MATCHED_FRAGMENT_MIN_PROBABILITY or rms_value < rms_floor:
            accepted.append({"ok": False})
            continue
        try:
            yin_value = float(yin[index])
            yin_midi = midi_from_hz(yin_value)
        except (TypeError, ValueError):
            accepted.append({"ok": False})
            continue
        if abs(midi - yin_midi) > 0:
            accepted.append({"ok": False})
            continue
        accepted.append(
            {
                "ok": True,
                "midi": midi,
                "frequency": float(frequency),
                "probability": probability,
                "rms": rms_value,
            }
        )

    fragments: list[dict[str, Any]] = []
    index = 0
    while index < len(accepted):
        frame = accepted[index]
        if not frame.get("ok"):
            index += 1
            continue
        midi = int(frame["midi"])
        end_index = index + 1
        while (
            end_index < len(accepted)
            and accepted[end_index].get("ok")
            and int(accepted[end_index].get("midi") or -1) == midi
        ):
            end_index += 1
        duration = (end_index - index) * frame_seconds
        if MATCHED_FRAGMENT_MIN_SECONDS <= duration <= MATCHED_FRAGMENT_MAX_SECONDS:
            run = accepted[index:end_index]
            frequencies = numpy.array([float(item.get("frequency") or 0.0) for item in run if item.get("frequency")])
            probabilities = [float(item.get("probability") or 0.0) for item in run]
            rms_values = [float(item.get("rms") or 0.0) for item in run]
            if frequencies.size:
                cents = 1200 * numpy.log2(frequencies / float(librosa.midi_to_hz(midi)))
                pitch_std = float(numpy.std(cents))
                median_cents = float(numpy.median(cents))
            else:
                pitch_std = 999.0
                median_cents = 999.0
            median_probability = sum(probabilities) / max(1, len(probabilities))
            if (
                pitch_std <= MATCHED_FRAGMENT_MAX_PITCH_STD_CENTS
                and abs(median_cents) <= MATCHED_FRAGMENT_MAX_MEDIAN_ABS_CENTS
                and median_probability >= MATCHED_FRAGMENT_MIN_PROBABILITY
            ):
                start = index * frame_seconds
                end = end_index * frame_seconds
                fragments.append(
                    {
                        "status": "audio_matched",
                        "kind": "stable_single_note",
                        "startSeconds": round(start, 3),
                        "endSeconds": round(end, 3),
                        "durationSeconds": round(end - start, 3),
                        "midi": midi,
                        "note": note_name(midi),
                        "confidence": round(min(0.999, median_probability), 3),
                        "pitchStdCents": round(pitch_std, 2),
                        "medianPitchOffsetCents": round(median_cents, 2),
                        "voicedFrameCount": len(run),
                        "medianRms": round(sum(rms_values) / max(1, len(rms_values)), 5),
                        "detectors": ["pyin", "yin"],
                        "verification": "pyin_yin_same_semitone_stable_pitch_window",
                        "displayLimit": "Single-note fragment only. Full-session transcription remains withheld.",
                    }
                )
        index = max(end_index, index + 1)
    fragments.sort(
        key=lambda item: (
            float(item.get("confidence") or 0.0),
            -abs(float(item.get("medianPitchOffsetCents") or 0.0)),
            -float(item.get("pitchStdCents") or 0.0),
            float(item.get("durationSeconds") or 0.0),
        ),
        reverse=True,
    )
    return fragments[:MATCHED_FRAGMENT_LIMIT]


def transcribe_audio_array(y: Any, sr: int, librosa: Any, numpy: Any) -> dict[str, Any]:
    source_y = normalize_audio_signal(y, librosa)
    pitch_y, preprocessing = pitch_tracking_signal(y, librosa, numpy)
    hop_length = PITCH_HOP_LENGTH
    f0, voiced_flag, voiced_prob = librosa.pyin(
        pitch_y,
        fmin=librosa.midi_to_hz(VIOLIN_MIN_MIDI),
        fmax=librosa.midi_to_hz(VIOLIN_MAX_MIDI),
        sr=sr,
        frame_length=PITCH_FRAME_LENGTH,
        hop_length=hop_length,
    )
    tempo = estimate_tempo(y, sr, librosa)
    harmonic_onset_frames = onset_frames_for_signal(pitch_y, sr, hop_length, librosa, numpy)
    source_onset_frames = onset_frames_for_signal(source_y, sr, hop_length, librosa, numpy)
    onset_frames = merge_onset_frame_sets(harmonic_onset_frames, source_onset_frames)
    pitch_events = f0_to_events(f0, voiced_flag, voiced_prob, sr, hop_length, numpy)
    onset_events = f0_to_onset_events(f0, voiced_flag, voiced_prob, onset_frames, sr, hop_length, numpy)
    harmonic_spectral_events = spectral_onset_events(pitch_y, onset_frames, sr, hop_length, librosa, numpy)
    source_spectral_events = spectral_onset_events(source_y, onset_frames, sr, hop_length, librosa, numpy)
    spectral_onset_stream_events, spectral_onset_stream_source = choose_spectral_event_stream(
        harmonic_spectral_events,
        source_spectral_events,
    )
    harmonic_micro_events = spectral_micro_events(pitch_y, sr, librosa, numpy)
    source_micro_events = spectral_micro_events(source_y, sr, librosa, numpy)
    spectral_micro_stream_events, spectral_micro_stream_source = choose_spectral_event_stream(
        harmonic_micro_events,
        source_micro_events,
    )
    spectral_events, spectral_detail_source = choose_spectral_detail_stream(
        spectral_onset_stream_events,
        spectral_micro_stream_events,
    )
    spectral_family = "spectral_micro" if spectral_detail_source == "micro" else "spectral_onset"
    spectral_stream_source = (
        f"micro_{spectral_micro_stream_source}"
        if spectral_family == "spectral_micro"
        else spectral_onset_stream_source
    )
    transition_events = yin_transition_events(pitch_y, sr, hop_length, librosa, numpy)
    raw_events, segmentation_source = choose_transcription_events(
        pitch_events,
        onset_events,
        spectral_events,
        spectral_family=spectral_family,
    )
    peer_groups = [
        ("pitch_hysteresis", pitch_events),
        ("onset_segmented_pyin", onset_events),
        ("spectral_onset", spectral_onset_stream_events),
        ("spectral_micro", spectral_micro_stream_events),
    ]
    raw_events = mark_audio_agreement(raw_events, segmentation_source, peer_groups)
    marked_transition_events = mark_audio_agreement(transition_events, "yin_transition_trace", peer_groups)
    score_match_candidate_events, transition_quality = pitch_sanity_filter(marked_transition_events)
    events, sanity_quality = pitch_sanity_filter(raw_events)
    voiced_ratio = round(float(numpy.nanmean(voiced_flag)) if len(voiced_flag) else 0.0, 3)
    spectral_agreed_count = sum(
        1
        for event in events
        if str(event.get("detectorSource") or "").startswith("spectral_")
        or bool({"spectral_onset", "spectral_micro"} & set(event.get("agreementSources") if isinstance(event.get("agreementSources"), list) else []))
    )
    quality = {
        "preprocessing": preprocessing,
        "segmentationSource": segmentation_source,
        "pitchEventCount": len(pitch_events),
        "onsetEventCount": len(onset_events),
        "spectralEventCount": len(spectral_events),
        "harmonicSpectralEventCount": len(harmonic_spectral_events),
        "sourceSpectralEventCount": len(source_spectral_events),
        "spectralOnsetStreamEventCount": len(spectral_onset_stream_events),
        "spectralMicroEventCount": len(spectral_micro_stream_events),
        "harmonicSpectralMicroEventCount": len(harmonic_micro_events),
        "sourceSpectralMicroEventCount": len(source_micro_events),
        "transitionTraceEventCount": len(transition_events),
        "transitionTraceSelectedEventCount": len(score_match_candidate_events),
        "rawSelectedEventCount": len(raw_events),
        "selectedEventCount": len(events),
        "audioAgreementEventCount": sum(1 for event in events if event.get("audioAgreement")),
        "spectralAgreedEventCount": spectral_agreed_count,
        "detectedOnsetCount": len(onset_frames),
        "denseHarmonicOnsetCount": len(harmonic_onset_frames),
        "denseSourceOnsetCount": len(source_onset_frames),
        "spectralStreamSource": spectral_stream_source,
        "spectralDetailSource": spectral_detail_source,
        "pitchDiversity": pitch_diversity(pitch_events),
        "onsetDiversity": pitch_diversity(onset_events),
        "spectralDiversity": pitch_diversity(spectral_events),
        "spectralOnsetStreamDiversity": pitch_diversity(spectral_onset_stream_events),
        "spectralMicroDiversity": pitch_diversity(spectral_micro_stream_events),
        "transitionTraceDiversity": pitch_diversity(score_match_candidate_events),
        "transitionTraceSanityGlitchDroppedCount": int(transition_quality.get("sanityGlitchDroppedCount") or 0),
        "transitionTraceSanityOctaveAdjustedCount": int(transition_quality.get("sanityOctaveAdjustedCount") or 0),
        **sanity_quality,
    }
    failure = transcription_failure_state(events, quality)
    return {
        "events": events,
        "scoreMatchCandidateNotes": score_match_candidate_events[:MAX_STORED_NOTES],
        "tempoBpm": tempo,
        "voicedFrameRatio": voiced_ratio,
        "quality": {**quality, **failure},
    }


def transcribe_active_windows(
    y: Any,
    sr: int,
    active_windows: list[dict[str, float]],
    librosa: Any,
    numpy: Any,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    score_match_candidate_notes: list[dict[str, Any]] = []
    tempos: list[float] = []
    voiced_ratios: list[float] = []
    quality_totals = Counter()
    failure_modes = Counter()
    collapse_notes = Counter()
    failure_limits: set[str] = set()
    preprocessing = set()
    segmentation = set()
    total_seconds = 0.0
    used_windows: list[dict[str, float]] = []
    duration = float(len(y) / sr)
    for window in active_windows:
        start = max(0.0, min(duration, float(window.get("start") or 0.0)))
        end = max(start, min(duration, float(window.get("end") or 0.0)))
        if end - start < 0.5:
            continue
        start_index = int(start * sr)
        end_index = int(end * sr)
        chunk = y[start_index:end_index]
        if chunk.size == 0:
            continue
        chunk, trim_index = librosa.effects.trim(chunk, top_db=35)
        if chunk.size == 0:
            continue
        trim_offset = start + (float(trim_index[0]) / sr if len(trim_index) else 0.0)
        result = transcribe_audio_array(chunk, sr, librosa, numpy)
        chunk_events = result["events"]
        quality = result.get("quality", {})
        preprocessing.add(str(quality.get("preprocessing") or ""))
        segmentation.add(str(quality.get("segmentationSource") or ""))
        for key in (
            "pitchEventCount",
            "onsetEventCount",
            "spectralEventCount",
            "harmonicSpectralEventCount",
            "sourceSpectralEventCount",
            "spectralOnsetStreamEventCount",
            "spectralMicroEventCount",
            "harmonicSpectralMicroEventCount",
            "sourceSpectralMicroEventCount",
            "transitionTraceEventCount",
            "transitionTraceSelectedEventCount",
            "rawSelectedEventCount",
            "selectedEventCount",
            "audioAgreementEventCount",
            "spectralAgreedEventCount",
            "detectedOnsetCount",
            "denseHarmonicOnsetCount",
            "denseSourceOnsetCount",
            "sanityGlitchDroppedCount",
            "sanityOctaveAdjustedCount",
            "sanityLargeLeapCount",
            "sanityLowConfidenceNoteCount",
            "pitchCollapseEventCount",
            "pitchCollapseDetectedOnsetCount",
            "transitionTraceSanityGlitchDroppedCount",
            "transitionTraceSanityOctaveAdjustedCount",
        ):
            quality_totals[key] += int(quality.get(key) or 0)
        if quality.get("failed"):
            failure_modes[str(quality.get("failureMode") or "transcription_failed")] += 1
            if quality.get("pitchCollapseDominantNote"):
                collapse_notes[str(quality.get("pitchCollapseDominantNote"))] += 1
            if quality.get("failureLimit"):
                failure_limits.add(str(quality.get("failureLimit")))
        chunk_candidate_notes: list[dict[str, Any]] = []
        for event in result.get("scoreMatchCandidateNotes", []) if isinstance(result.get("scoreMatchCandidateNotes"), list) else []:
            if not isinstance(event, dict):
                continue
            shifted = dict(event)
            shifted["startSeconds"] = round(trim_offset + float(event.get("startSeconds") or 0.0), 3)
            shifted["endSeconds"] = round(trim_offset + float(event.get("endSeconds") or 0.0), 3)
            chunk_candidate_notes.append(shifted)
        score_match_candidate_notes.extend(chunk_candidate_notes)
        if len(chunk_events) < MIN_ACTIVE_WINDOW_NOTES:
            quality_totals["omittedSparseWindowCount"] += 1
            total_seconds += end - start
            used_windows.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "notation": "omitted_sparse",
                    "scoreMatchCandidateCount": len(chunk_candidate_notes),
                }
            )
            continue
        for event in chunk_events:
            shifted = dict(event)
            shifted["startSeconds"] = round(trim_offset + float(event.get("startSeconds") or 0.0), 3)
            shifted["endSeconds"] = round(trim_offset + float(event.get("endSeconds") or 0.0), 3)
            events.append(shifted)
        if result["tempoBpm"]:
            tempos.append(float(result["tempoBpm"]))
        voiced_ratios.append(float(result["voicedFrameRatio"] or 0.0))
        total_seconds += end - start
        used_windows.append({"start": round(start, 3), "end": round(end, 3), "notation": "included"})
    return {
        "events": events[:MAX_STORED_NOTES],
        "scoreMatchCandidateNotes": score_match_candidate_notes[:MAX_STORED_NOTES],
        "tempoBpm": round(float(numpy.median(numpy.array(tempos))), 1) if tempos else 0.0,
        "voicedFrameRatio": round(sum(voiced_ratios) / max(1, len(voiced_ratios)), 3),
        "durationSeconds": round(total_seconds, 2),
        "activeWindows": used_windows,
        "quality": {
            "preprocessing": "+".join(sorted(item for item in preprocessing if item)) or "none",
            "segmentationSource": "+".join(sorted(item for item in segmentation if item)) or "none",
            "pitchEventCount": int(quality_totals["pitchEventCount"]),
            "onsetEventCount": int(quality_totals["onsetEventCount"]),
            "spectralEventCount": int(quality_totals["spectralEventCount"]),
            "harmonicSpectralEventCount": int(quality_totals["harmonicSpectralEventCount"]),
            "sourceSpectralEventCount": int(quality_totals["sourceSpectralEventCount"]),
            "transitionTraceEventCount": int(quality_totals["transitionTraceEventCount"]),
            "transitionTraceSelectedEventCount": int(quality_totals["transitionTraceSelectedEventCount"]),
            "rawSelectedEventCount": int(quality_totals["rawSelectedEventCount"]),
            "selectedEventCount": int(quality_totals["selectedEventCount"]),
            "audioAgreementEventCount": int(quality_totals["audioAgreementEventCount"]),
            "spectralAgreedEventCount": int(quality_totals["spectralAgreedEventCount"]),
            "detectedOnsetCount": int(quality_totals["detectedOnsetCount"]),
            "denseHarmonicOnsetCount": int(quality_totals["denseHarmonicOnsetCount"]),
            "denseSourceOnsetCount": int(quality_totals["denseSourceOnsetCount"]),
            "sanityGlitchDroppedCount": int(quality_totals["sanityGlitchDroppedCount"]),
            "sanityOctaveAdjustedCount": int(quality_totals["sanityOctaveAdjustedCount"]),
            "sanityLargeLeapCount": int(quality_totals["sanityLargeLeapCount"]),
            "sanityLowConfidenceNoteCount": int(quality_totals["sanityLowConfidenceNoteCount"]),
            "omittedSparseWindowCount": int(quality_totals["omittedSparseWindowCount"]),
            "failed": bool(failure_modes),
            "failureMode": failure_modes.most_common(1)[0][0] if failure_modes else "",
            "failureLabel": "pitch collapse" if failure_modes.get("repeated_pitch_collapse") else "",
            "failureLimit": sorted(failure_limits)[0] if failure_limits else "",
            "pitchCollapseDetected": bool(failure_modes.get("repeated_pitch_collapse")),
            "pitchCollapseDominantNote": collapse_notes.most_common(1)[0][0] if collapse_notes else "",
            "pitchCollapseWindowCount": int(sum(failure_modes.values())),
            "pitchCollapseEventCount": int(quality_totals["pitchCollapseEventCount"]),
            "pitchCollapseDetectedOnsetCount": int(quality_totals["pitchCollapseDetectedOnsetCount"]),
            "transitionTraceSanityGlitchDroppedCount": int(quality_totals["transitionTraceSanityGlitchDroppedCount"]),
            "transitionTraceSanityOctaveAdjustedCount": int(quality_totals["transitionTraceSanityOctaveAdjustedCount"]),
        },
    }


def transcribe_path(path: Path, active_windows: list[dict[str, float]] | None = None) -> dict[str, Any]:
    try:
        import librosa  # type: ignore
        import numpy  # type: ignore
    except Exception as exc:
        return {"status": "blocked", "blocker": "transcription_dependencies_missing", "detail": str(exc)[:180]}

    if not path.exists():
        return {"status": "blocked", "blocker": "media_sample_missing"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        wav_path = Path(temp.name)
    try:
        ok, output = extract_audio_wav(path, wav_path)
        if not ok:
            return {"status": "blocked", "blocker": "audio_extract_failed", "detail": output[-500:]}
        y, sr = librosa.load(str(wav_path), sr=22050, mono=True, duration=MAX_TRANSCRIPTION_SECONDS)
        if y.size == 0:
            return {"status": "blocked", "blocker": "empty_audio"}
        matched_fragments = stable_single_note_fragments(y, sr, librosa, numpy)
        if active_windows:
            transcription = transcribe_active_windows(y, sr, active_windows, librosa, numpy)
            window_mode = "detected_active_sections"
        else:
            y, _ = librosa.effects.trim(y, top_db=35)
            if y.size == 0:
                return {"status": "blocked", "blocker": "no_audible_audio"}
            transcription = transcribe_audio_array(y, sr, librosa, numpy)
            transcription["durationSeconds"] = round(float(len(y) / sr), 2)
            transcription["activeWindows"] = []
            window_mode = "whole_sample_window"
        events = transcription["events"]
        tempo = transcription["tempoBpm"]
        quality = transcription["quality"]
        failure = transcription_failure_state(events, quality)
        if quality.get("failed") and not failure.get("failed"):
            failure = {
                "failed": True,
                "status": "failed_pitch_collapse"
                if quality.get("failureMode") == "repeated_pitch_collapse"
                else "failed_transcription_quality",
                "failureMode": quality.get("failureMode") or "transcription_failed",
                "failureLabel": quality.get("failureLabel") or "machine pitch rejected",
                "failureLimit": quality.get("failureLimit")
                or "Machine pitch extraction did not pass score/audio verification and is not used as sheet music.",
            }
        status = str(failure.get("status") or ("transcribed" if events else "no_stable_notes"))
        fingerprint = event_fingerprint(events, tempo) if status == "transcribed" else {}
        return {
            "status": status,
            "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
            "method": "librosa_active_section_onset_pyin_spectral_pitch_with_audio_agreement_gate",
            "durationSeconds": transcription["durationSeconds"],
            "tempoBpm": tempo,
            "voicedFrameRatio": transcription["voicedFrameRatio"],
            "noteCount": len(events),
            "notes": events,
            "scoreMatchCandidateNotes": transcription.get("scoreMatchCandidateNotes", []),
            "fingerprint": fingerprint,
            "quality": {
                "range": f"{note_name(VIOLIN_MIN_MIDI)}-{note_name(VIOLIN_MAX_MIDI)}",
                "minimumVoicedProbability": MIN_VOICED_PROBABILITY,
                "noteChangeConfirmFrames": NOTE_CHANGE_CONFIRM_FRAMES,
                "vibratoChangeConfirmFrames": VIBRATO_CHANGE_CONFIRM_FRAMES,
                "vibratoSemitoneRange": VIBRATO_SEMITONE_RANGE,
                "minimumNoteSeconds": MIN_NOTE_SECONDS,
                "minimumOnsetNoteSeconds": MIN_ONSET_NOTE_SECONDS,
                "pitchFrameLength": PITCH_FRAME_LENGTH,
                "pitchHopLength": PITCH_HOP_LENGTH,
                "noteMergeGapSeconds": NOTE_MERGE_GAP_SECONDS,
                "lowConfidenceGlitchSeconds": LOW_CONFIDENCE_GLITCH_SECONDS,
                "lowConfidenceGlitchThreshold": LOW_CONFIDENCE_GLITCH_THRESHOLD,
                "octaveFlipMinSemitones": OCTAVE_FLIP_MIN_SEMITONES,
                "minimumActiveWindowNotes": MIN_ACTIVE_WINDOW_NOTES,
                "pitchCollapseMinEvents": PITCH_COLLAPSE_MIN_EVENTS,
                "pitchCollapseDominantRatio": PITCH_COLLAPSE_DOMINANT_RATIO,
                "fastOnsetDelta": FAST_ONSET_DELTA,
                "fastOnsetWaitFrames": FAST_ONSET_WAIT_FRAMES,
                "spectralOctaveRescueRatio": SPECTRAL_OCTAVE_RESCUE_RATIO,
                "spectralOctaveRescueMinMidi": SPECTRAL_OCTAVE_RESCUE_MIN_MIDI,
                "spectralFastMinEvents": SPECTRAL_FAST_MIN_EVENTS,
                "spectralMicroWindowSeconds": SPECTRAL_MICRO_WINDOW_SECONDS,
                "spectralMicroHopSeconds": SPECTRAL_MICRO_HOP_SECONDS,
                "spectralMicroMinMidi": SPECTRAL_MICRO_MIN_MIDI,
                "windowMode": window_mode,
                "activeWindowCount": len(transcription["activeWindows"]),
                "activeWindows": transcription["activeWindows"],
                "audioMatchedFragmentCount": len(matched_fragments),
                **quality,
                **failure,
            },
            "matchedFragments": matched_fragments,
            "notation": {
                "format": "note:beats",
                "text": notation_text(events, tempo),
                "limit": (
                    str(failure.get("failureLimit"))
                    if failure.get("failed")
                    else "Pitch-sanity-filtered monophonic draft from detected active sections; octave-adjusted or low-confidence notes remain uncertain until score alignment verifies them."
                ),
            },
        }
    finally:
        wav_path.unlink(missing_ok=True)


def learned_reference_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    transcriptions = state.get("transcriptions", {}).get("items", [])
    if not isinstance(transcriptions, list):
        transcriptions = []
    learned: list[dict[str, Any]] = []
    for item in transcriptions:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "transcribed":
            continue
        if item.get("pipelineVersion") != TRANSCRIPTION_PIPELINE_VERSION:
            continue
        if not isinstance(item.get("fingerprint"), dict):
            continue
        if int(item.get("noteCount") or 0) < 8:
            continue
        calibration = calibration_anchor_for_item(item)
        accepted_title = str(item.get("acceptedTitle") or calibration.get("title") or "").strip()
        if not accepted_title:
            continue
        learned.append(
            {
                **item,
                "acceptedTitle": accepted_title,
                "referenceKind": item.get("referenceKind") or calibration.get("referenceKind") or "source_confirmed_reference",
                "materialType": item.get("materialType") or calibration.get("materialType") or "repertoire",
            }
        )
    return [*learned, *symbolic_reference_items()]


def reference_matches_for(transcription: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    fingerprint = transcription.get("fingerprint")
    if not isinstance(fingerprint, dict):
        return []
    own_id = transcription.get("transcriptionId")
    matches = []
    for learned in learned_reference_items(state):
        if learned.get("transcriptionId") == own_id:
            continue
        score = compare_fingerprints(fingerprint, learned.get("fingerprint", {}))
        if score >= PITCH_MATCH_THRESHOLD:
            matches.append(
                {
                    "title": learned.get("acceptedTitle"),
                    "sourceTitle": learned.get("sourceTitle"),
                    "score": score,
                    "basis": "pitch_rhythm_fingerprint",
                    "referenceKind": learned.get("referenceKind") or "",
                    "materialType": learned.get("materialType") or "",
                }
            )
    return sorted(matches, key=lambda item: float(item.get("score") or 0.0), reverse=True)[:5]


def build_transcription(sample: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(sample.get("path") or ""))
    active_windows = active_windows_for_sample(sample, state)
    result = transcribe_path(path, active_windows=active_windows)
    correction = correction_for_item(state, sample)
    base_start = parse_window_start(str(sample.get("window") or ""))
    for event in result.get("notes", []) if isinstance(result.get("notes"), list) else []:
        if not isinstance(event, dict):
            continue
        event["sourceStartSeconds"] = base_start + float(event.get("startSeconds") or 0.0)
        event["sourceEndSeconds"] = base_start + float(event.get("endSeconds") or 0.0)
    for event in result.get("scoreMatchCandidateNotes", []) if isinstance(result.get("scoreMatchCandidateNotes"), list) else []:
        if not isinstance(event, dict):
            continue
        event["sourceStartSeconds"] = base_start + float(event.get("startSeconds") or 0.0)
        event["sourceEndSeconds"] = base_start + float(event.get("endSeconds") or 0.0)
    for fragment in result.get("matchedFragments", []) if isinstance(result.get("matchedFragments"), list) else []:
        if not isinstance(fragment, dict):
            continue
        fragment["sourceStartSeconds"] = base_start + float(fragment.get("startSeconds") or 0.0)
        fragment["sourceEndSeconds"] = base_start + float(fragment.get("endSeconds") or 0.0)
    item = {
        **result,
        "transcriptionId": transcription_key(sample),
        "pipelineVersion": result.get("pipelineVersion") or TRANSCRIPTION_PIPELINE_VERSION,
        "sampleId": sample.get("id"),
        "sourceKey": source_key_from_item(sample),
        "sourceTitle": sample.get("title") or sample.get("sourceTitle") or "",
        "sourceUrl": sample.get("url") or sample.get("sourceUrl") or "",
        "sourceWindow": sample.get("window") or "",
        "createdAt": utc_now(),
    }
    calibration = calibration_anchor_for_item(sample)
    accepted_title = str(correction.get("acceptedTitle") or calibration.get("title") or "").strip()
    reference_target = correction.get("referenceTarget") if isinstance(correction.get("referenceTarget"), dict) else {}
    if not reference_target and isinstance(calibration.get("referenceTarget"), dict):
        reference_target = calibration.get("referenceTarget") or {}
    item.update(
        {
            "acceptedTitle": accepted_title,
            "referenceKind": "source_confirmed_reference" if correction.get("acceptedTitle") else calibration.get("referenceKind") or "",
            "materialType": "repertoire" if correction.get("acceptedTitle") else calibration.get("materialType") or "",
            "calibrationAnchor": calibration,
            "referenceTarget": reference_target,
        }
    )
    item["referenceMatches"] = reference_matches_for(item, state)
    return item


def transcription_prior_hint(state: dict[str, Any], sample: dict[str, Any]) -> str:
    items = state.get("transcriptions", {}).get("items", [])
    if not isinstance(items, list):
        return ""
    sample_key = transcription_key(sample)
    source_key = source_key_from_item(sample)
    candidates = [
        item
        for item in items
        if isinstance(item, dict)
        and (
            item.get("transcriptionId") == sample_key
            or (source_key and item.get("sourceKey") == source_key)
            or (sample.get("id") and item.get("sampleId") == sample.get("id"))
        )
    ]
    candidates.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    for item in candidates:
        matches = item.get("referenceMatches") if isinstance(item.get("referenceMatches"), list) else []
        if matches:
            match = matches[0]
            return (
                f"pitch/rhythm fingerprint nearest learned source: {match.get('title')} "
                f"from {match.get('sourceTitle')} (score {match.get('score')}); verify by audible notes/rhythm."
            )
        accepted = str(item.get("acceptedTitle") or "").strip()
        if accepted and item.get("status") == "transcribed":
            return f"pitch/rhythm transcription exists for confirmed source: {accepted}; use extracted notes/rhythm for passage verification."
    return ""


def transcribe_media_samples(limit: int | None = None, sample_ids: list[str] | None = None) -> dict[str, Any]:
    state = load_state()
    sample_limit = TRANSCRIPTION_SAMPLE_LIMIT if limit is None else int(limit)
    requested_ids = {str(item).strip() for item in (sample_ids or []) if str(item).strip()}
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    existing = [
        item
        for item in state.get("transcriptions", {}).get("items", [])
        if isinstance(item, dict)
    ]
    existing_by_id = {
        str(item.get("transcriptionId")): item
        for item in existing
        if item.get("transcriptionId")
    }
    selected: list[dict[str, Any]] = []
    for sample in samples:
        if not sample.get("path") or not sample_is_violin_positive(sample):
            continue
        key = transcription_key(sample)
        sample_id = str(sample.get("id") or "").strip()
        source_key = source_key_from_item(sample)
        requested = bool(
            requested_ids
            and (
                sample_id in requested_ids
                or key in requested_ids
                or source_key in requested_ids
            )
        )
        stale_or_missing = key not in existing_by_id or existing_by_id[key].get("pipelineVersion") != TRANSCRIPTION_PIPELINE_VERSION
        if requested or (not requested_ids and stale_or_missing):
            selected.append(sample)
        if len(selected) >= sample_limit:
            break
    results = [build_transcription(sample, state) for sample in selected]
    replaced_ids = {item.get("transcriptionId") for item in results if item.get("transcriptionId")}
    items = [*results, *[item for item in existing if item.get("transcriptionId") not in replaced_ids]][:80]
    state["transcriptions"] = {
        "items": items,
        "updatedAt": utc_now(),
        "method": "librosa_active_section_onset_pyin_spectral_pitch_with_audio_agreement_gate",
        "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
        "limit": "Machine pitch/rhythm extraction is stored only as hidden evidence. Repeated-pitch collapse is rejected and cannot train piece matching; score-level claims require alignment verification.",
    }
    run = {
        "startedAt": utc_now(),
        "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
        "status": (
            "transcribed"
            if any(item.get("status") == "transcribed" for item in results)
            else "no_new_samples"
            if not selected
            else "failed_quality_gates"
            if any(str(item.get("status") or "").startswith("failed_") for item in results)
            else "blocked"
        ),
        "sampleCount": len(selected),
        "requestedSampleIds": sorted(requested_ids),
        "reprocessedCount": sum(1 for sample in selected if transcription_key(sample) in existing_by_id),
        "transcribedCount": sum(1 for item in results if item.get("status") == "transcribed"),
        "failedQualityCount": sum(1 for item in results if str(item.get("status") or "").startswith("failed_")),
        "noteCount": sum(int(item.get("noteCount") or 0) for item in results),
        "blockers": list(
            dict.fromkeys(
                str(item.get("blocker"))
                for item in results
                if item.get("status") == "blocked" and item.get("blocker")
            )
        ),
        "results": [
            {
                "transcriptionId": item.get("transcriptionId"),
                "sampleId": item.get("sampleId"),
                "sourceTitle": item.get("sourceTitle"),
                "status": item.get("status"),
                "noteCount": item.get("noteCount"),
                "tempoBpm": item.get("tempoBpm"),
                "acceptedTitle": item.get("acceptedTitle"),
                "failureMode": item.get("quality", {}).get("failureMode") if isinstance(item.get("quality"), dict) else "",
                "referenceMatches": item.get("referenceMatches", [])[:3],
            }
            for item in results
        ],
    }
    state["lastTranscriptionRun"] = run
    save_state(state)
    return run
