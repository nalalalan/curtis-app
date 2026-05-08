from __future__ import annotations

import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .analyzer import parse_window_start, run_process
from .corrections import correction_for_item, source_key_from_item
from .state import load_state, save_state, utc_now


MAX_TRANSCRIPTION_SECONDS = int(os.getenv("CURTIS_TRANSCRIPTION_MAX_SECONDS", "180"))
TRANSCRIPTION_SAMPLE_LIMIT = int(os.getenv("CURTIS_TRANSCRIPTION_SAMPLE_LIMIT", "8"))
TRANSCRIPTION_PIPELINE_VERSION = "violin_harmonic_pyin_onset_v4"
MIN_NOTE_SECONDS = float(os.getenv("CURTIS_MIN_NOTE_SECONDS", "0.08"))
MIN_ONSET_NOTE_SECONDS = float(os.getenv("CURTIS_MIN_ONSET_NOTE_SECONDS", "0.04"))
MAX_STORED_NOTES = int(os.getenv("CURTIS_MAX_STORED_NOTES", "240"))
PITCH_MATCH_THRESHOLD = float(os.getenv("CURTIS_PITCH_MATCH_THRESHOLD", "0.58"))
VIOLIN_MIN_MIDI = int(os.getenv("CURTIS_VIOLIN_MIN_MIDI", "55"))
VIOLIN_MAX_MIDI = int(os.getenv("CURTIS_VIOLIN_MAX_MIDI", "108"))
MIN_VOICED_PROBABILITY = float(os.getenv("CURTIS_MIN_VOICED_PROBABILITY", "0.50"))
NOTE_CHANGE_CONFIRM_FRAMES = int(os.getenv("CURTIS_NOTE_CHANGE_CONFIRM_FRAMES", "3"))
NOTE_MERGE_GAP_SECONDS = float(os.getenv("CURTIS_NOTE_MERGE_GAP_SECONDS", "0.07"))
ONSET_EVENT_MULTIPLIER = float(os.getenv("CURTIS_ONSET_EVENT_MULTIPLIER", "1.12"))
ONSET_MIN_VOICED_FRAMES = int(os.getenv("CURTIS_ONSET_MIN_VOICED_FRAMES", "1"))
HARMONIC_MARGIN = float(os.getenv("CURTIS_HARMONIC_MARGIN", "8.0"))
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
        if len(pending_midi_buffer) >= NOTE_CHANGE_CONFIRM_FRAMES and pending_start is not None:
            next_start = pending_start
            next_midi_buffer = [*pending_midi_buffer]
            next_prob_buffer = [*pending_prob_buffer]
            close_event(next_start)
            current_start = next_start
            midi_buffer = next_midi_buffer
            prob_buffer = next_prob_buffer
            reset_pending()
    if pending_midi_buffer and pending_start is not None and len(pending_midi_buffer) >= NOTE_CHANGE_CONFIRM_FRAMES:
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
) -> tuple[list[dict[str, Any]], str]:
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
    try:
        normalized = librosa.util.normalize(y)
    except Exception:
        normalized = y
    try:
        harmonic = librosa.effects.harmonic(normalized, margin=HARMONIC_MARGIN)
        harmonic_rms = float(numpy.sqrt(numpy.mean(numpy.square(harmonic)))) if harmonic.size else 0.0
        source_rms = float(numpy.sqrt(numpy.mean(numpy.square(normalized)))) if normalized.size else 0.0
        if harmonic.size == normalized.size and harmonic_rms >= max(0.01, source_rms * 0.08):
            return librosa.util.normalize(harmonic), "trimmed_normalized_harmonic"
    except Exception:
        pass
    return normalized, "trimmed_normalized"


def transcribe_path(path: Path) -> dict[str, Any]:
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
        y, _ = librosa.effects.trim(y, top_db=35)
        if y.size == 0:
            return {"status": "blocked", "blocker": "no_audible_audio"}
        pitch_y, preprocessing = pitch_tracking_signal(y, librosa, numpy)
        hop_length = 512
        f0, voiced_flag, voiced_prob = librosa.pyin(
            pitch_y,
            fmin=librosa.midi_to_hz(VIOLIN_MIN_MIDI),
            fmax=librosa.midi_to_hz(VIOLIN_MAX_MIDI),
            sr=sr,
            frame_length=2048,
            hop_length=hop_length,
        )
        tempo = estimate_tempo(y, sr, librosa)
        try:
            onset_frames = librosa.onset.onset_detect(y=pitch_y, sr=sr, hop_length=hop_length, units="frames")
        except Exception:
            onset_frames = []
        pitch_events = f0_to_events(f0, voiced_flag, voiced_prob, sr, hop_length, numpy)
        onset_events = f0_to_onset_events(f0, voiced_flag, voiced_prob, onset_frames, sr, hop_length, numpy)
        events, segmentation_source = choose_transcription_events(pitch_events, onset_events)
        voiced_ratio = round(float(numpy.nanmean(voiced_flag)) if len(voiced_flag) else 0.0, 3)
        return {
            "status": "transcribed" if events else "no_stable_notes",
            "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
            "method": "librosa_harmonic_pyin_violin_range_onset_aware_note_segmentation",
            "durationSeconds": round(float(len(y) / sr), 2),
            "tempoBpm": tempo,
            "voicedFrameRatio": voiced_ratio,
            "noteCount": len(events),
            "notes": events,
            "fingerprint": event_fingerprint(events, tempo),
            "quality": {
                "range": f"{note_name(VIOLIN_MIN_MIDI)}-{note_name(VIOLIN_MAX_MIDI)}",
                "minimumVoicedProbability": MIN_VOICED_PROBABILITY,
                "noteChangeConfirmFrames": NOTE_CHANGE_CONFIRM_FRAMES,
                "minimumNoteSeconds": MIN_NOTE_SECONDS,
                "minimumOnsetNoteSeconds": MIN_ONSET_NOTE_SECONDS,
                "noteMergeGapSeconds": NOTE_MERGE_GAP_SECONDS,
                "segmentationSource": segmentation_source,
                "pitchEventCount": len(pitch_events),
                "onsetEventCount": len(onset_events),
                "selectedEventCount": len(events),
                "detectedOnsetCount": len(onset_frames),
                "preprocessing": preprocessing,
            },
            "notation": {
                "format": "note:beats",
                "text": notation_text(events, tempo),
                "limit": "Harmonic-isolated monophonic violin-range draft transcription; verify against score before treating as final notation.",
            },
        }
    finally:
        wav_path.unlink(missing_ok=True)


def learned_reference_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    transcriptions = state.get("transcriptions", {}).get("items", [])
    if not isinstance(transcriptions, list):
        return []
    return [
        item
        for item in transcriptions
        if isinstance(item, dict)
        and item.get("acceptedTitle")
        and item.get("status") == "transcribed"
        and item.get("pipelineVersion") == TRANSCRIPTION_PIPELINE_VERSION
        and isinstance(item.get("fingerprint"), dict)
        and int(item.get("noteCount") or 0) >= 8
    ]


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
                }
            )
    return sorted(matches, key=lambda item: float(item.get("score") or 0.0), reverse=True)[:5]


def build_transcription(sample: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(sample.get("path") or ""))
    result = transcribe_path(path)
    correction = correction_for_item(state, sample)
    base_start = parse_window_start(str(sample.get("window") or ""))
    for event in result.get("notes", []) if isinstance(result.get("notes"), list) else []:
        if not isinstance(event, dict):
            continue
        event["sourceStartSeconds"] = base_start + float(event.get("startSeconds") or 0.0)
        event["sourceEndSeconds"] = base_start + float(event.get("endSeconds") or 0.0)
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
        "acceptedTitle": correction.get("acceptedTitle") or "",
        "referenceTarget": correction.get("referenceTarget") if isinstance(correction.get("referenceTarget"), dict) else {},
    }
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


def transcribe_media_samples(limit: int | None = None) -> dict[str, Any]:
    state = load_state()
    sample_limit = TRANSCRIPTION_SAMPLE_LIMIT if limit is None else int(limit)
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
    selected = [
        sample
        for sample in samples
        if sample.get("path")
        and (
            transcription_key(sample) not in existing_by_id
            or existing_by_id[transcription_key(sample)].get("pipelineVersion") != TRANSCRIPTION_PIPELINE_VERSION
        )
    ][:sample_limit]
    results = [build_transcription(sample, state) for sample in selected]
    replaced_ids = {item.get("transcriptionId") for item in results if item.get("transcriptionId")}
    items = [*results, *[item for item in existing if item.get("transcriptionId") not in replaced_ids]][:80]
    state["transcriptions"] = {
        "items": items,
        "updatedAt": utc_now(),
        "method": "librosa_harmonic_pyin_violin_range_onset_aware_note_segmentation",
        "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
        "limit": "Harmonic-isolated monophonic violin-range note/rhythm extraction is draft evidence for matching; score-level claims require alignment verification.",
    }
    run = {
        "startedAt": utc_now(),
        "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
        "status": "transcribed" if any(item.get("status") == "transcribed" for item in results) else "no_new_samples" if not selected else "blocked",
        "sampleCount": len(selected),
        "reprocessedCount": sum(1 for sample in selected if transcription_key(sample) in existing_by_id),
        "transcribedCount": sum(1 for item in results if item.get("status") == "transcribed"),
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
                "referenceMatches": item.get("referenceMatches", [])[:3],
            }
            for item in results
        ],
    }
    state["lastTranscriptionRun"] = run
    save_state(state)
    return run
