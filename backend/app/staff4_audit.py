from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .analyzer import run_process
from .settings import RUNTIME_DIR
from .state import utc_now


AUDIT_DIR = RUNTIME_DIR / "staff4-audit"
STAFF4_AUDIT_VERSION = "staff4_phrase_audit_v1"


def safe_slug(value: Any, fallback: str = "packet") -> str:
    raw = str(value or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")
    return slug[:96] or fallback


def artifact_url(packet_id: str, filename: str) -> str:
    return f"/api/curtis/staff4-audit/artifacts/{safe_slug(packet_id)}/{safe_slug(filename)}"


def packet_artifact_path(packet_id: str, filename: str) -> Path:
    return AUDIT_DIR / safe_slug(packet_id) / safe_slug(filename)


def packet_json_path(packet_id: str) -> Path:
    return packet_artifact_path(packet_id, "packet.json")


def number_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def note_label_for_midi(midi: int | None, prefer_flats: bool = False) -> str:
    if midi is None:
        return ""
    names = (
        ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
        if prefer_flats
        else ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    )
    octave = (int(midi) // 12) - 1
    return f"{names[int(midi) % 12]}{octave}"


def midi_from_hz(value: float | None) -> float | None:
    if not value or value <= 0 or not math.isfinite(float(value)):
        return None
    return 69.0 + 12.0 * math.log2(float(value) / 440.0)


def rounded_midi(value: float | None) -> int | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return int(round(float(value)))


def median(values: list[float]) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def sequence_label(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if str(item or "").strip())
    return str(value or "").strip()


def compact_note_event(note: dict[str, Any], index: int) -> dict[str, Any]:
    start = number_or_none(note.get("startSeconds")) or 0.0
    end = number_or_none(note.get("endSeconds")) or start
    midi = int_or_none(note.get("midi"))
    return {
        "index": index,
        "note": str(note.get("note") or note_label_for_midi(midi)),
        "midi": midi,
        "startSeconds": round(start, 3),
        "endSeconds": round(end, 3),
        "durationSeconds": round(max(0.0, end - start), 3),
        "confidence": round(number_or_none(note.get("confidence")) or 0.0, 3),
        "audioAgreement": bool(note.get("audioAgreement")),
        "agreementSourceCount": int(note.get("agreementSourceCount") or 0),
        "agreementSources": note.get("agreementSources") if isinstance(note.get("agreementSources"), list) else [],
        "detectorSource": str(note.get("detectorSource") or ""),
    }


def current_staff4_expansion(completion: dict[str, Any]) -> dict[str, Any]:
    harness = completion.get("phraseExpansionHarness") if isinstance(completion.get("phraseExpansionHarness"), dict) else {}
    current = harness.get("currentBest") if isinstance(harness.get("currentBest"), dict) else {}
    if not current:
        return {}
    piece_title = str(current.get("pieceTitle") or "").lower()
    target_sequence = sequence_label(current.get("targetSequence"))
    if "wieniawski" not in piece_title:
        return {}
    if "Eb5 Eb5 C5 Eb5 Eb5" not in target_sequence:
        return {}
    return current


def packet_id_for_current(current: dict[str, Any]) -> str:
    return safe_slug(
        "-".join(
            [
                "staff4",
                str(current.get("practiceDay") or "day"),
                str(current.get("sampleId") or "sample"),
                str(current.get("targetReferenceStart") or "start"),
                str(current.get("targetReferenceEnd") or "end"),
            ]
        )
    )


def media_sample_for_id(state: dict[str, Any], sample_id: str) -> dict[str, Any]:
    samples = state.get("mediaSamples") if isinstance(state.get("mediaSamples"), list) else []
    for sample in samples:
        if isinstance(sample, dict) and str(sample.get("id") or "") == str(sample_id or ""):
            return sample
    return {}


def source_media_path(sample: dict[str, Any]) -> Path | None:
    raw = str(sample.get("path") or "").strip()
    if not raw:
        return None
    try:
        path = Path(raw).resolve(strict=True)
    except OSError:
        return None
    return path if path.is_file() else None


def run_ffmpeg_extract_audio(source: Path, target: Path, start: float, end: float) -> tuple[bool, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-f",
            "wav",
            str(target),
        ],
        timeout=60,
    )
    return code == 0 and target.exists() and target.stat().st_size > 44, output


def run_ffmpeg_extract_video(source: Path, target: Path, start: float, end: float) -> tuple[bool, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source),
            "-vf",
            "scale=480:-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(target),
        ],
        timeout=90,
    )
    return code == 0 and target.exists() and target.stat().st_size > 1000, output


def sequence_from_frame_midis(times: list[float], midi_values: list[float | None], max_items: int = 16) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    current_midi: int | None = None
    current_start = 0.0
    last_time = 0.0
    for time_value, midi_value in zip(times, midi_values):
        rounded = rounded_midi(midi_value)
        if rounded is None:
            continue
        if current_midi is None:
            current_midi = rounded
            current_start = float(time_value)
        elif rounded != current_midi:
            sequence.append(
                {
                    "note": note_label_for_midi(current_midi),
                    "midi": current_midi,
                    "startSeconds": round(current_start, 3),
                    "endSeconds": round(last_time, 3),
                }
            )
            current_midi = rounded
            current_start = float(time_value)
        last_time = float(time_value)
        if len(sequence) >= max_items:
            break
    if current_midi is not None and len(sequence) < max_items:
        sequence.append(
            {
                "note": note_label_for_midi(current_midi),
                "midi": current_midi,
                "startSeconds": round(current_start, 3),
                "endSeconds": round(last_time, 3),
            }
        )
    return sequence


def detector_window_median(
    frames: list[dict[str, Any]],
    *,
    local_start: float,
    local_end: float,
) -> dict[str, Any]:
    values = [
        float(frame["midi"])
        for frame in frames
        if frame.get("midi") is not None
        and local_start <= float(frame.get("timeSeconds") or 0.0) <= max(local_start, local_end)
    ]
    med = median(values)
    midi = rounded_midi(med)
    return {
        "medianMidi": round(med, 3) if med is not None else None,
        "roundedMidi": midi,
        "note": note_label_for_midi(midi),
        "frameCount": len(values),
    }


def analyze_audio_clip(audio_path: Path, current: dict[str, Any], clip_start: float) -> dict[str, Any]:
    try:
        import librosa
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment boundary
        return {"status": "blocked_dependency", "detail": str(exc)[:180]}

    try:
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    except Exception as exc:
        return {"status": "blocked_audio_load", "detail": str(exc)[:180]}
    if y.size == 0:
        return {"status": "blocked_empty_audio"}

    hop_length = 128
    duration = float(librosa.get_duration(y=y, sr=sr))
    times = librosa.frames_to_time(np.arange(max(1, 1 + len(y) // hop_length)), sr=sr, hop_length=hop_length)
    times_list = [float(item) for item in times]

    pyin_frames: list[dict[str, Any]] = []
    yin_frames: list[dict[str, Any]] = []
    spectral_frames: list[dict[str, Any]] = []
    onset_times: list[float] = []
    try:
        f0, voiced, probability = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("G3"),
            fmax=librosa.note_to_hz("C8"),
            sr=sr,
            hop_length=hop_length,
        )
        pyin_times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
        for time_value, hz, is_voiced, prob in zip(pyin_times, f0, voiced, probability):
            midi = midi_from_hz(float(hz)) if is_voiced and not np.isnan(hz) else None
            if midi is not None:
                pyin_frames.append(
                    {
                        "timeSeconds": round(float(time_value), 3),
                        "midi": round(float(midi), 3),
                        "note": note_label_for_midi(rounded_midi(midi)),
                        "probability": round(float(prob) if not np.isnan(prob) else 0.0, 3),
                    }
                )
    except Exception:
        pyin_frames = []

    try:
        f0_yin = librosa.yin(
            y,
            fmin=librosa.note_to_hz("G3"),
            fmax=librosa.note_to_hz("C8"),
            sr=sr,
            hop_length=hop_length,
        )
        yin_times = librosa.frames_to_time(np.arange(len(f0_yin)), sr=sr, hop_length=hop_length)
        for time_value, hz in zip(yin_times, f0_yin):
            midi = midi_from_hz(float(hz))
            if midi is not None:
                yin_frames.append(
                    {
                        "timeSeconds": round(float(time_value), 3),
                        "midi": round(float(midi), 3),
                        "note": note_label_for_midi(rounded_midi(midi)),
                    }
                )
    except Exception:
        yin_frames = []

    try:
        stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        valid = np.where((freqs >= librosa.note_to_hz("G3")) & (freqs <= librosa.note_to_hz("C8")))[0]
        spec_times = librosa.frames_to_time(np.arange(stft.shape[1]), sr=sr, hop_length=hop_length)
        for frame_index, time_value in enumerate(spec_times):
            column = stft[valid, frame_index]
            if column.size == 0 or float(column.max()) <= 0:
                continue
            peak_freq = float(freqs[valid[int(column.argmax())]])
            midi = midi_from_hz(peak_freq)
            if midi is not None:
                spectral_frames.append(
                    {
                        "timeSeconds": round(float(time_value), 3),
                        "midi": round(float(midi), 3),
                        "note": note_label_for_midi(rounded_midi(midi)),
                    }
                )
    except Exception:
        spectral_frames = []

    try:
        onset_times = [
            round(float(item), 3)
            for item in librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length, units="time")
        ]
    except Exception:
        onset_times = []

    mismatch_index = first_mismatch_index(current)
    best_notes = current.get("bestAudioNotes") if isinstance(current.get("bestAudioNotes"), list) else []
    mismatch_note = best_notes[mismatch_index] if 0 <= mismatch_index < len(best_notes) and isinstance(best_notes[mismatch_index], dict) else {}
    mismatch_start = max(0.0, (number_or_none(mismatch_note.get("startSeconds")) or clip_start) - clip_start)
    mismatch_end = max(mismatch_start, (number_or_none(mismatch_note.get("endSeconds")) or clip_start) - clip_start)
    expected_midi = int_or_none(current.get("expectedNextScoreMidi"))
    observed_midi = int_or_none(current.get("observedNextAudioMidi"))
    detector_windows = {
        "pyin": detector_window_median(pyin_frames, local_start=mismatch_start, local_end=mismatch_end),
        "yin": detector_window_median(yin_frames, local_start=mismatch_start, local_end=mismatch_end),
        "spectralPeak": detector_window_median(spectral_frames, local_start=mismatch_start, local_end=mismatch_end),
    }
    votes = {"expected": 0, "observed": 0, "other": 0, "missing": 0}
    for result in detector_windows.values():
        rounded = result.get("roundedMidi")
        if rounded is None:
            votes["missing"] += 1
        elif expected_midi is not None and rounded == expected_midi:
            votes["expected"] += 1
        elif observed_midi is not None and rounded == observed_midi:
            votes["observed"] += 1
        else:
            votes["other"] += 1
    status = "needs_manual_audio_review"
    if votes["observed"] >= 2 and not votes["expected"]:
        status = "blocked_audio_mismatch_confirmed"
    elif votes["expected"] >= 2:
        status = "detectors_disagree_with_stored_run"
    elif votes["expected"] and votes["observed"]:
        status = "detector_split_review_required"

    return {
        "status": status,
        "durationSeconds": round(duration, 3),
        "sampleRate": int(sr),
        "onsetTimes": onset_times[:64],
        "mismatchWindow": {
            "index": mismatch_index,
            "clipLocalStartSeconds": round(mismatch_start, 3),
            "clipLocalEndSeconds": round(mismatch_end, 3),
            "expectedMidi": expected_midi,
            "expectedNote": note_label_for_midi(expected_midi, prefer_flats=True),
            "observedMidi": observed_midi,
            "observedNote": note_label_for_midi(observed_midi),
            "detectorVotes": votes,
            "detectors": detector_windows,
        },
        "detectors": {
            "pyin": {
                "frameCount": len(pyin_frames),
                "sequence": sequence_from_frame_midis(
                    [float(frame["timeSeconds"]) for frame in pyin_frames],
                    [float(frame["midi"]) for frame in pyin_frames],
                ),
            },
            "yin": {
                "frameCount": len(yin_frames),
                "sequence": sequence_from_frame_midis(
                    [float(frame["timeSeconds"]) for frame in yin_frames],
                    [float(frame["midi"]) for frame in yin_frames],
                ),
            },
            "spectralPeak": {
                "frameCount": len(spectral_frames),
                "sequence": sequence_from_frame_midis(
                    [float(frame["timeSeconds"]) for frame in spectral_frames],
                    [float(frame["midi"]) for frame in spectral_frames],
                ),
            },
        },
        "frames": {
            "pyin": pyin_frames[:: max(1, len(pyin_frames) // 240 or 1)],
            "yin": yin_frames[:: max(1, len(yin_frames) // 240 or 1)],
            "spectralPeak": spectral_frames[:: max(1, len(spectral_frames) // 240 or 1)],
        },
    }


def first_mismatch_index(current: dict[str, Any]) -> int:
    target = current.get("targetMidiSequence") if isinstance(current.get("targetMidiSequence"), list) else []
    observed = current.get("bestAudioMidiSequence") if isinstance(current.get("bestAudioMidiSequence"), list) else []
    for index, (expected, actual) in enumerate(zip(target, observed)):
        if int_or_none(expected) != int_or_none(actual):
            return index
    return -1


def write_pitch_trace_svg(target: Path, packet: dict[str, Any], analysis: dict[str, Any]) -> None:
    frames_by_name = analysis.get("frames") if isinstance(analysis.get("frames"), dict) else {}
    all_frames = [
        frame
        for frames in frames_by_name.values()
        if isinstance(frames, list)
        for frame in frames
        if isinstance(frame, dict) and frame.get("midi") is not None
    ]
    target_midis = packet.get("targetMidiSequence") if isinstance(packet.get("targetMidiSequence"), list) else []
    observed_midis = packet.get("bestAudioMidiSequence") if isinstance(packet.get("bestAudioMidiSequence"), list) else []
    midi_values = [float(frame["midi"]) for frame in all_frames]
    midi_values.extend(float(item) for item in target_midis + observed_midis if item is not None)
    if not midi_values:
        midi_values = [72.0, 75.0]
    min_midi = math.floor(min(midi_values) - 2)
    max_midi = math.ceil(max(midi_values) + 2)
    if max_midi <= min_midi:
        max_midi = min_midi + 4
    duration = max(0.5, number_or_none((analysis.get("durationSeconds") if isinstance(analysis, dict) else 0)) or 0.5)

    def x_for_time(value: float) -> float:
        return 52 + (max(0.0, min(duration, value)) / duration) * 720

    def y_for_midi(value: float) -> float:
        return 260 - ((value - min_midi) / (max_midi - min_midi)) * 210

    def points(frames: list[dict[str, Any]]) -> str:
        values = []
        for frame in frames:
            midi = number_or_none(frame.get("midi"))
            time_value = number_or_none(frame.get("timeSeconds"))
            if midi is None or time_value is None:
                continue
            values.append(f"{x_for_time(time_value):.1f},{y_for_midi(midi):.1f}")
        return " ".join(values)

    detector_paths = []
    colors = {"pyin": "#111111", "yin": "#4477AA", "spectralPeak": "#AA5544"}
    for name in ("pyin", "yin", "spectralPeak"):
        frames = frames_by_name.get(name) if isinstance(frames_by_name.get(name), list) else []
        pts = points(frames)
        if pts:
            detector_paths.append(f'<polyline points="{pts}" fill="none" stroke="{colors[name]}" stroke-width="2" opacity="0.9"/>')

    grid = []
    for midi in range(min_midi, max_midi + 1):
        y = y_for_midi(midi)
        grid.append(
            f'<line x1="52" x2="772" y1="{y:.1f}" y2="{y:.1f}" stroke="#ddd" stroke-width="1"/>'
            f'<text x="16" y="{y + 4:.1f}" font-size="12">{note_label_for_midi(midi)}</text>'
        )
    mismatch = analysis.get("mismatchWindow") if isinstance(analysis.get("mismatchWindow"), dict) else {}
    mx1 = x_for_time(number_or_none(mismatch.get("clipLocalStartSeconds")) or 0.0)
    mx2 = x_for_time(number_or_none(mismatch.get("clipLocalEndSeconds")) or 0.0)
    expected_midi = int_or_none(mismatch.get("expectedMidi"))
    observed_midi = int_or_none(mismatch.get("observedMidi"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 310" role="img">',
                '<rect width="820" height="310" fill="#fffdf8"/>',
                '<text x="52" y="28" font-size="18" font-weight="700">Staff 4 phrase audit pitch trace</text>',
                '<text x="52" y="48" font-size="13" fill="#555">black pYIN / blue YIN / rust spectral peak</text>',
                f'<rect x="{mx1:.1f}" y="56" width="{max(2.0, mx2 - mx1):.1f}" height="214" fill="#F2D9D4" opacity="0.5"/>',
                *grid,
                *detector_paths,
                f'<line x1="52" x2="772" y1="{y_for_midi(expected_midi):.1f}" y2="{y_for_midi(expected_midi):.1f}" stroke="#2F6B45" stroke-width="2" stroke-dasharray="6 6"/>'
                if expected_midi is not None
                else "",
                f'<line x1="52" x2="772" y1="{y_for_midi(observed_midi):.1f}" y2="{y_for_midi(observed_midi):.1f}" stroke="#9A3A2E" stroke-width="2" stroke-dasharray="3 5"/>'
                if observed_midi is not None
                else "",
                '<text x="52" y="292" font-size="12">Expected source note and observed audio note are shown as horizontal dashed lines.</text>',
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )


def write_spectrogram_svg(target: Path, audio_path: Path) -> bool:
    try:
        import librosa
        import numpy as np
    except Exception:
        return False
    try:
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=40, hop_length=256, n_fft=1024)
        db = librosa.power_to_db(mel, ref=np.max)
    except Exception:
        return False
    if db.size == 0:
        return False
    cols = db.shape[1]
    stride = max(1, cols // 120)
    db = db[:, ::stride]
    rows, cols = db.shape
    width = 760
    height = 220
    cell_w = width / max(1, cols)
    cell_h = height / max(1, rows)
    rects = []
    for row in range(rows):
        for col in range(cols):
            value = float(db[rows - row - 1, col])
            norm = max(0.0, min(1.0, (value + 80.0) / 80.0))
            shade = int(250 - (norm * 210))
            rust = int(245 - (norm * 110))
            rects.append(
                f'<rect x="{30 + col * cell_w:.1f}" y="{50 + row * cell_h:.1f}" width="{cell_w + 0.3:.1f}" height="{cell_h + 0.3:.1f}" fill="rgb({rust},{shade},{shade})"/>'
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 310" role="img">',
                '<rect width="820" height="310" fill="#fffdf8"/>',
                '<text x="30" y="28" font-size="18" font-weight="700">Staff 4 phrase audit spectrogram</text>',
                *rects,
                '<text x="30" y="292" font-size="12" fill="#555">Mel spectrogram from the generated audit audio clip.</text>',
                "</svg>",
            ]
        ),
        encoding="utf-8",
    )
    return True


def ensure_staff4_phrase_audit_packet(
    state: dict[str, Any],
    completion: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    current = current_staff4_expansion(completion)
    if not current:
        packet = {
            "version": STAFF4_AUDIT_VERSION,
            "status": "blocked_no_staff4_expansion",
            "createdAt": utc_now(),
            "limit": "No current Staff 4 phrase expansion target is available.",
        }
        state["staff4PhraseAuditLatest"] = packet
        return packet

    packet_id = packet_id_for_current(current)
    existing_path = packet_json_path(packet_id)
    if existing_path.exists() and not force:
        try:
            packet = json.loads(existing_path.read_text(encoding="utf-8"))
            state["staff4PhraseAuditLatest"] = packet
            return packet
        except (OSError, json.JSONDecodeError):
            pass

    sample_id = str(current.get("sampleId") or "").strip()
    sample = media_sample_for_id(state, sample_id)
    source_path = source_media_path(sample)
    target_midis = current.get("targetMidiSequence") if isinstance(current.get("targetMidiSequence"), list) else []
    best_midis = current.get("bestAudioMidiSequence") if isinstance(current.get("bestAudioMidiSequence"), list) else []
    best_notes = current.get("bestAudioNotes") if isinstance(current.get("bestAudioNotes"), list) else []
    compact_notes = [compact_note_event(note, index) for index, note in enumerate(best_notes)]
    local_start = number_or_none(current.get("audioLocalStartSeconds"))
    local_end = number_or_none(current.get("audioLocalEndSeconds"))
    if local_start is None and compact_notes:
        local_start = number_or_none(compact_notes[0].get("startSeconds"))
    if local_end is None and compact_notes:
        local_end = number_or_none(compact_notes[-1].get("endSeconds"))
    local_start = max(0.0, local_start or 0.0)
    local_end = max(local_start + 0.25, local_end or (local_start + 2.0))
    clip_start = max(0.0, local_start - 0.35)
    clip_end = min(local_end + 0.45, clip_start + 8.0)
    if clip_end <= clip_start:
        clip_end = clip_start + 2.0

    packet_dir = AUDIT_DIR / packet_id
    packet_dir.mkdir(parents=True, exist_ok=True)
    audio_name = "staff4-audit.wav"
    video_name = "staff4-audit.mp4"
    pitch_name = "pitch-trace.svg"
    spectrogram_name = "spectrogram.svg"
    audio_path = packet_artifact_path(packet_id, audio_name)
    video_path = packet_artifact_path(packet_id, video_name)
    pitch_path = packet_artifact_path(packet_id, pitch_name)
    spectrogram_path = packet_artifact_path(packet_id, spectrogram_name)

    packet: dict[str, Any] = {
        "version": STAFF4_AUDIT_VERSION,
        "packetId": packet_id,
        "createdAt": utc_now(),
        "practiceDay": current.get("practiceDay") or "",
        "pieceTitle": current.get("pieceTitle") or "",
        "sampleId": sample_id,
        "sourceWindow": current.get("sourceWindow") or "",
        "sourceTitle": sample.get("title") or current.get("sourceTitle") or "",
        "sourceUrl": sample.get("url") or "",
        "status": "generated",
        "truthDecision": "not_accepted",
        "gate": current.get("status") or "",
        "limit": current.get("limit") or "",
        "targetReferenceStart": current.get("targetReferenceStart"),
        "targetReferenceEnd": current.get("targetReferenceEnd"),
        "targetSequence": sequence_label(current.get("targetSequence")),
        "bestAudioSequence": sequence_label(current.get("bestAudioSequence")),
        "targetMidiSequence": target_midis,
        "bestAudioMidiSequence": best_midis,
        "expectedNextScoreNote": current.get("expectedNextScoreNote") or "",
        "expectedNextScoreMidi": current.get("expectedNextScoreMidi"),
        "observedNextAudioNote": current.get("observedNextAudioNote") or "",
        "observedNextAudioMidi": current.get("observedNextAudioMidi"),
        "audioRunSource": current.get("audioRunSource") or "",
        "clip": {
            "startSeconds": current.get("audioAbsoluteStartSeconds"),
            "endSeconds": current.get("audioAbsoluteEndSeconds"),
            "localStartSeconds": round(clip_start, 3),
            "localEndSeconds": round(clip_end, 3),
            "noteLocalStartSeconds": round(local_start, 3),
            "noteLocalEndSeconds": round(local_end, 3),
            "mediaUrl": f"/api/curtis/media/sample/{sample_id}" if sample_id else "",
            "audioUrl": artifact_url(packet_id, audio_name),
        },
        "score": {
            "sourceImageUrl": current.get("sourceImageUrl") or "",
            "sourceCropReady": bool(current.get("sourceCropReady")),
            "truthEvidenceAccepted": bool(current.get("truthEvidenceAccepted")),
        },
        "storedAudioNotes": compact_notes,
        "artifacts": {
            "packetJsonUrl": artifact_url(packet_id, "packet.json"),
            "audioClipUrl": artifact_url(packet_id, audio_name),
        },
    }

    if not source_path:
        packet["status"] = "blocked_media_missing"
        packet["limit"] = "The current Staff 4 sample is not present in runtime media storage, so audio/video artifacts cannot be generated."
        existing_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
        state["staff4PhraseAuditLatest"] = packet
        return packet

    audio_ok, audio_output = run_ffmpeg_extract_audio(source_path, audio_path, clip_start, clip_end)
    video_ok, _video_output = run_ffmpeg_extract_video(source_path, video_path, clip_start, clip_end)
    if video_ok:
        packet["clip"]["videoUrl"] = artifact_url(packet_id, video_name)
        packet["artifacts"]["videoClipUrl"] = artifact_url(packet_id, video_name)
    else:
        packet["clip"]["videoUrl"] = f"/api/curtis/media/sample/{sample_id}" if sample_id else ""
        packet["clip"]["videoFragment"] = f"#t={clip_start:.2f},{clip_end:.2f}"
    if not audio_ok:
        packet["status"] = "blocked_audio_extract_failed"
        packet["limit"] = f"Audit audio extraction failed: {audio_output[-180:]}"
        existing_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
        state["staff4PhraseAuditLatest"] = packet
        return packet

    analysis = analyze_audio_clip(audio_path, current, clip_start)
    packet["audioAnalysis"] = analysis
    if analysis.get("status") in {
        "blocked_audio_mismatch_confirmed",
        "detectors_disagree_with_stored_run",
        "detector_split_review_required",
        "needs_manual_audio_review",
    }:
        packet["status"] = str(analysis.get("status"))
    write_pitch_trace_svg(pitch_path, packet, analysis)
    packet["artifacts"]["pitchTraceSvgUrl"] = artifact_url(packet_id, pitch_name)
    if write_spectrogram_svg(spectrogram_path, audio_path):
        packet["artifacts"]["spectrogramSvgUrl"] = artifact_url(packet_id, spectrogram_name)
    packet["nextAction"] = (
        "Store this Staff 4 right-2 expansion as rejected and move outward only if a later audit finds Eb5 at the sixth note."
        if packet["status"] == "blocked_audio_mismatch_confirmed"
        else "Review this packet before accepting, rejecting, or re-running the Staff 4 expansion."
    )
    existing_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    state["staff4PhraseAuditLatest"] = packet
    return packet


def latest_staff4_phrase_audit_packet(state: dict[str, Any]) -> dict[str, Any]:
    packet = state.get("staff4PhraseAuditLatest") if isinstance(state.get("staff4PhraseAuditLatest"), dict) else {}
    if packet:
        return packet
    return {
        "version": STAFF4_AUDIT_VERSION,
        "status": "not_generated",
        "limit": "Run the Staff 4 phrase audit packet generator.",
    }
