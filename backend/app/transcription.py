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
MIN_NOTE_SECONDS = float(os.getenv("CURTIS_MIN_NOTE_SECONDS", "0.08"))
MAX_STORED_NOTES = int(os.getenv("CURTIS_MAX_STORED_NOTES", "240"))
PITCH_MATCH_THRESHOLD = float(os.getenv("CURTIS_PITCH_MATCH_THRESHOLD", "0.58"))
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


def f0_to_events(f0: Any, voiced_flag: Any, voiced_prob: Any, sr: int, hop_length: int, numpy: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    midi_buffer: list[int] = []
    prob_buffer: list[float] = []
    last_time = 0.0

    def close_event(end_time: float) -> None:
        nonlocal current, midi_buffer, prob_buffer
        if current is None or not midi_buffer:
            current = None
            midi_buffer = []
            prob_buffer = []
            return
        start = float(current["startSeconds"])
        duration = max(0.0, end_time - start)
        if duration >= MIN_NOTE_SECONDS:
            midi = int(round(float(numpy.median(numpy.array(midi_buffer)))))
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
        current = None
        midi_buffer = []
        prob_buffer = []

    for index, value in enumerate(f0):
        time_seconds = float(index * hop_length / sr)
        last_time = time_seconds
        voiced = bool(voiced_flag[index]) if index < len(voiced_flag) else False
        probability = float(voiced_prob[index]) if index < len(voiced_prob) and not math.isnan(float(voiced_prob[index])) else 0.0
        if not voiced or value is None or math.isnan(float(value)) or probability < 0.45:
            close_event(time_seconds)
            continue
        midi = int(round(69 + 12 * math.log2(float(value) / 440.0)))
        if midi < 43 or midi > 108:
            close_event(time_seconds)
            continue
        if current is None:
            current = {"startSeconds": time_seconds, "midi": midi}
            midi_buffer = [midi]
            prob_buffer = [probability]
            continue
        median_midi = int(round(float(numpy.median(numpy.array(midi_buffer)))))
        if midi == median_midi:
            midi_buffer.append(midi)
            prob_buffer.append(probability)
        else:
            close_event(time_seconds)
            current = {"startSeconds": time_seconds, "midi": midi}
            midi_buffer = [midi]
            prob_buffer = [probability]
    close_event(last_time + (hop_length / sr))
    return events[:MAX_STORED_NOTES]


def notation_text(events: list[dict[str, Any]], tempo_bpm: float) -> str:
    if not events:
        return ""
    beat_seconds = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5
    tokens = []
    for event in events[:80]:
        beats = max(0.25, float(event.get("durationSeconds") or 0.0) / beat_seconds)
        tokens.append(f"{event.get('note')}:{beats:.2f}b")
    return " ".join(tokens)


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
        hop_length = 512
        f0, voiced_flag, voiced_prob = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("G2"),
            fmax=librosa.note_to_hz("C8"),
            sr=sr,
            frame_length=2048,
            hop_length=hop_length,
        )
        tempo = estimate_tempo(y, sr, librosa)
        events = f0_to_events(f0, voiced_flag, voiced_prob, sr, hop_length, numpy)
        voiced_ratio = round(float(numpy.nanmean(voiced_flag)) if len(voiced_flag) else 0.0, 3)
        return {
            "status": "transcribed" if events else "no_stable_notes",
            "durationSeconds": round(float(len(y) / sr), 2),
            "tempoBpm": tempo,
            "voicedFrameRatio": voiced_ratio,
            "noteCount": len(events),
            "notes": events,
            "fingerprint": event_fingerprint(events, tempo),
            "notation": {
                "format": "note:beats",
                "text": notation_text(events, tempo),
                "limit": "Machine transcription from practice audio; verify against score before treating as final notation.",
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


def transcribe_media_samples(limit: int = 3) -> dict[str, Any]:
    state = load_state()
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    existing_ids = {
        item.get("transcriptionId")
        for item in state.get("transcriptions", {}).get("items", [])
        if isinstance(item, dict) and item.get("transcriptionId")
    }
    selected = [
        sample
        for sample in samples
        if sample.get("path") and transcription_key(sample) not in existing_ids
    ][:limit]
    results = [build_transcription(sample, state) for sample in selected]
    existing = [
        item
        for item in state.get("transcriptions", {}).get("items", [])
        if isinstance(item, dict)
    ]
    items = [*results, *existing][:80]
    state["transcriptions"] = {
        "items": items,
        "updatedAt": utc_now(),
        "method": "librosa_pyin_pitch_track_note_segmentation",
        "limit": "Machine note/rhythm extraction is evidence for matching; score-level claims require alignment verification.",
    }
    run = {
        "startedAt": utc_now(),
        "status": "transcribed" if any(item.get("status") == "transcribed" for item in results) else "no_new_samples" if not selected else "blocked",
        "sampleCount": len(selected),
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
