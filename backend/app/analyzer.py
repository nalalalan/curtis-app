from __future__ import annotations

import math
import os
import re
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from .state import load_state, save_state, utc_now


WINDOW_RE = re.compile(r"\*(\d+)-(\d+)")
VIOLIN_PRESENCE_VERSION = "violin_presence_v1"
VIOLIN_POSITIVE_SCORE = float(os.getenv("CURTIS_VIOLIN_POSITIVE_SCORE", "45"))
VIOLIN_MIN_ACTIVE_SECONDS = float(os.getenv("CURTIS_VIOLIN_MIN_ACTIVE_SECONDS", "10"))
VIOLIN_MIN_VOICED_RATIO = float(os.getenv("CURTIS_VIOLIN_MIN_VOICED_RATIO", "0.12"))
VIOLIN_MAX_CLASSIFY_SECONDS = float(os.getenv("CURTIS_VIOLIN_CLASSIFY_SECONDS", "45"))
VIOLIN_MIN_MIDI = int(os.getenv("CURTIS_VIOLIN_MIN_MIDI", "55"))
VIOLIN_MAX_MIDI = int(os.getenv("CURTIS_VIOLIN_MAX_MIDI", "108"))
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


def run_process(args: list[str], timeout: int = 120) -> tuple[int, str]:
    completed = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout


def parse_window_start(value: str) -> int:
    match = WINDOW_RE.search(value or "")
    if not match:
        return 0
    return int(match.group(1))


def extract_wav(source: Path, target: Path) -> tuple[bool, str]:
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(target),
        ],
        timeout=180,
    )
    return code == 0 and target.exists() and target.stat().st_size > 44, output


def rms_windows(wav_path: Path, window_seconds: float = 1.0) -> list[dict[str, float]]:
    windows: list[dict[str, float]] = []
    with wave.open(str(wav_path), "rb") as handle:
        frame_rate = handle.getframerate()
        sample_width = handle.getsampwidth()
        if sample_width != 2:
            return windows
        frames_per_window = max(1, int(frame_rate * window_seconds))
        index = 0
        while True:
            frames = handle.readframes(frames_per_window)
            if not frames:
                break
            sample_count = len(frames) // sample_width
            if not sample_count:
                break
            samples = struct.unpack(f"<{sample_count}h", frames)
            mean_square = sum(float(sample) * float(sample) for sample in samples) / sample_count
            rms = math.sqrt(mean_square)
            dbfs = 20 * math.log10(max(rms, 1.0) / 32768.0)
            windows.append({"start": index * window_seconds, "end": (index + 1) * window_seconds, "rms": rms, "dbfs": dbfs})
            index += 1
    return windows


def active_ranges(windows: list[dict[str, float]]) -> list[dict[str, Any]]:
    if not windows:
        return []
    rms_values = sorted(window["rms"] for window in windows)
    midpoint = rms_values[len(rms_values) // 2]
    upper = rms_values[max(0, int(len(rms_values) * 0.75) - 1)]
    threshold = max(280.0, min(midpoint * 0.8, upper * 0.6))
    ranges: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for window in windows:
        is_active = window["rms"] >= threshold
        if is_active and current is None:
            current = {
                "start": window["start"],
                "end": window["end"],
                "peakDbfs": window["dbfs"],
                "meanRms": window["rms"],
                "windows": 1,
            }
        elif is_active and current is not None:
            current["end"] = window["end"]
            current["peakDbfs"] = max(current["peakDbfs"], window["dbfs"])
            current["meanRms"] += window["rms"]
            current["windows"] += 1
        elif current is not None:
            current["meanRms"] = current["meanRms"] / max(1, current["windows"])
            if current["end"] - current["start"] >= 2:
                ranges.append(current)
            current = None

    if current is not None:
        current["meanRms"] = current["meanRms"] / max(1, current["windows"])
        if current["end"] - current["start"] >= 2:
            ranges.append(current)
    return ranges[:8]


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


def classify_violin_presence(source: Path) -> dict[str, Any]:
    """Score whether a media window contains usable violin audio.

    This gate is intentionally conservative. A window must contain sustained
    violin-range pitched audio before it can surface as practice evidence.
    """
    if not source.exists():
        return {
            "containsViolin": False,
            "violinPresence": "missing_media",
            "practiceEvidenceStatus": "needs_violin_verification",
            "violinSamplerVersion": VIOLIN_PRESENCE_VERSION,
            "violinSamplerScore": 0,
            "violinSamplerBlocker": "media_sample_missing",
        }

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        wav_path = Path(temp.name)
    try:
        ok, output = extract_wav(source, wav_path)
        if not ok:
            return {
                "containsViolin": False,
                "violinPresence": "audio_extract_failed",
                "practiceEvidenceStatus": "needs_violin_verification",
                "violinSamplerVersion": VIOLIN_PRESENCE_VERSION,
                "violinSamplerScore": 0,
                "violinSamplerBlocker": "audio_extract_failed",
                "violinSamplerDetail": output[-300:],
            }

        windows = rms_windows(wav_path)
        ranges = active_ranges(windows)
        active_seconds = sum(float(item.get("end") or 0) - float(item.get("start") or 0) for item in ranges)
        peak_dbfs = max((float(window.get("dbfs") or -120.0) for window in windows), default=-120.0)
        mean_rms = (
            sum(float(window.get("rms") or 0.0) for window in windows) / max(1, len(windows))
            if windows
            else 0.0
        )

        try:
            import librosa  # type: ignore
            import numpy  # type: ignore
        except Exception as exc:
            return {
                "containsViolin": False,
                "violinPresence": "unverified",
                "practiceEvidenceStatus": "needs_violin_verification",
                "violinSamplerVersion": VIOLIN_PRESENCE_VERSION,
                "violinSamplerScore": 0,
                "violinSamplerBlocker": "violin_classifier_dependencies_missing",
                "violinSamplerDetail": str(exc)[:180],
                "violinSamplerFeatures": {
                    "activeSeconds": round(active_seconds, 2),
                    "peakDbfs": round(peak_dbfs, 1),
                    "meanRms": round(mean_rms, 1),
                    "classifier": "energy_fallback",
                },
            }

        y, sr = librosa.load(str(wav_path), sr=22050, mono=True, duration=VIOLIN_MAX_CLASSIFY_SECONDS)
        if not getattr(y, "size", 0):
            score = 0.0
            features = {
                "activeSeconds": round(active_seconds, 2),
                "peakDbfs": round(peak_dbfs, 1),
                "meanRms": round(mean_rms, 1),
                "classifier": "empty_audio",
            }
        else:
            y, _ = librosa.effects.trim(y, top_db=35)
            duration = float(len(y) / sr) if len(y) else 0.0
            if duration <= 0:
                score = 0.0
                features = {
                    "activeSeconds": round(active_seconds, 2),
                    "peakDbfs": round(peak_dbfs, 1),
                    "meanRms": round(mean_rms, 1),
                    "classifier": "trimmed_empty_audio",
                }
            else:
                f0, voiced_flag, voiced_prob = librosa.pyin(
                    y,
                    fmin=librosa.midi_to_hz(VIOLIN_MIN_MIDI),
                    fmax=librosa.midi_to_hz(min(VIOLIN_MAX_MIDI, 100)),
                    sr=sr,
                    frame_length=2048,
                    hop_length=512,
                )
                valid = numpy.isfinite(f0) & voiced_flag & (voiced_prob > 0.45)
                voiced_ratio = float(numpy.mean(valid)) if len(valid) else 0.0
                midi = librosa.hz_to_midi(f0[valid]) if bool(numpy.any(valid)) else numpy.array([])
                median_midi = float(numpy.median(midi)) if len(midi) else 0.0
                pitch_class_count = len(set((numpy.rint(midi).astype(int) % 12).tolist())) if len(midi) else 0
                centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
                median_centroid = float(numpy.median(centroid)) if len(centroid) else 0.0
                onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
                onset_rate = float(len(onsets) / max(0.001, duration))
                score = (
                    (voiced_ratio * 55.0)
                    + (min(pitch_class_count, 7) * 3.0)
                    + (min(onset_rate, 6.0) * 2.0)
                    + (8.0 if median_centroid >= 900 else 0.0)
                    + (6.0 if active_seconds >= 20 else 3.0 if active_seconds >= VIOLIN_MIN_ACTIVE_SECONDS else 0.0)
                )
                if median_midi and (median_midi < 58 or median_midi > 98):
                    score -= 8.0
                if peak_dbfs < -38 and mean_rms < 500:
                    score -= 8.0
                features = {
                    "activeSeconds": round(active_seconds, 2),
                    "peakDbfs": round(peak_dbfs, 1),
                    "meanRms": round(mean_rms, 1),
                    "voicedFrameRatio": round(voiced_ratio, 3),
                    "medianMidi": round(median_midi, 1),
                    "pitchClassCount": int(pitch_class_count),
                    "medianSpectralCentroid": round(median_centroid, 1),
                    "onsetRate": round(onset_rate, 2),
                    "classifier": "pyin_onset_spectral",
                }

        voiced_ratio = float(features.get("voicedFrameRatio") or 0.0)
        pitch_class_count = int(features.get("pitchClassCount") or 0)
        onset_rate = float(features.get("onsetRate") or 0.0)
        positive = (
            score >= VIOLIN_POSITIVE_SCORE
            and active_seconds >= VIOLIN_MIN_ACTIVE_SECONDS
            and voiced_ratio >= VIOLIN_MIN_VOICED_RATIO
            and pitch_class_count >= 3
            and onset_rate >= 0.8
        )
        return {
            "containsViolin": bool(positive),
            "violinPresence": "violin_positive" if positive else "not_violin_or_unclear",
            "practiceEvidenceStatus": "violin_positive" if positive else "needs_violin_verification",
            "violinSamplerVersion": VIOLIN_PRESENCE_VERSION,
            "violinSamplerScore": round(max(0.0, float(score)), 1),
            "violinSamplerFeatures": features,
        }
    finally:
        wav_path.unlink(missing_ok=True)


def section_key(section: dict[str, Any]) -> str:
    return "|".join(
        [
            str(section.get("sampleId", "")),
            str(section.get("startSeconds", "")),
            str(section.get("endSeconds", "")),
            str(section.get("method", "")),
        ]
    )


def analyze_sample(sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(sample.get("path") or ""))
    if not path.exists():
        return {"status": "blocked", "blocker": "media_sample_missing", "sampleId": sample.get("id")}
    if not sample_is_violin_positive(sample):
        return {
            "status": "withheld",
            "blocker": "violin_presence_not_confirmed",
            "sampleId": sample.get("id"),
            "violinSamplerScore": sample.get("violinSamplerScore"),
        }

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        wav_path = Path(temp.name)
    try:
        ok, output = extract_wav(path, wav_path)
        if not ok:
            return {"status": "blocked", "blocker": "audio_extract_failed", "sampleId": sample.get("id"), "detail": output[-500:]}
        windows = rms_windows(wav_path)
        ranges = active_ranges(windows)
    finally:
        wav_path.unlink(missing_ok=True)

    base_start = parse_window_start(str(sample.get("window") or ""))
    sections = []
    for index, item in enumerate(ranges, start=1):
        start = base_start + int(item["start"])
        end = base_start + int(item["end"])
        sections.append(
            {
                "id": f"{sample.get('id', 'sample')}-{start}-{end}",
                "sampleId": sample.get("id"),
                "url": sample.get("url"),
                "title": sample.get("title"),
                "dimension": "media",
                "judgment": "Unjudged",
                "status": "candidate_playing_section",
                "method": "audio_energy",
                "violinPresence": sample.get("violinPresence"),
                "violinSamplerScore": sample.get("violinSamplerScore"),
                "startSeconds": start,
                "endSeconds": end,
                "peakDbfs": round(float(item["peakDbfs"]), 1),
                "meanRms": round(float(item["meanRms"]), 1),
                "note": f"Audio-active section {index}. Musicianship judgment pending.",
                "createdAt": utc_now(),
            }
        )
    return {"status": "sections_scanned", "sampleId": sample.get("id"), "sections": sections}


def analyze_media_samples(limit: int = 3) -> dict[str, Any]:
    state = load_state()
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    classified: list[dict[str, Any]] = []
    classify_limit = max(limit, int(os.getenv("CURTIS_VIOLIN_CLASSIFY_LIMIT", "8")))
    for sample in samples:
        if len(classified) >= classify_limit:
            break
        if sample.get("violinSamplerVersion") == VIOLIN_PRESENCE_VERSION:
            continue
        path = Path(str(sample.get("path") or ""))
        if not path.exists():
            continue
        metadata = classify_violin_presence(path)
        sample.update(metadata)
        classified.append(
            {
                "sampleId": sample.get("id"),
                "violinPresence": sample.get("violinPresence"),
                "score": sample.get("violinSamplerScore"),
                "containsViolin": sample.get("containsViolin"),
            }
        )

    analyzed_ids = {
        section.get("sampleId")
        for section in state.get("review", {}).get("notableSections", [])
        if isinstance(section, dict) and section.get("sampleId")
    }
    selected = [
        sample
        for sample in samples
        if sample.get("id") not in analyzed_ids and sample_is_violin_positive(sample)
    ][:limit]
    results = [analyze_sample(sample) for sample in selected]
    new_sections = [
        section
        for result in results
        for section in result.get("sections", [])
        if isinstance(section, dict)
    ]

    review = state.setdefault("review", {})
    existing_sections = [section for section in review.get("notableSections", []) if isinstance(section, dict)]
    by_key = {section_key(section): section for section in existing_sections}
    for section in new_sections:
        by_key[section_key(section)] = section
    sections = list(by_key.values())[:80]

    state["mediaSamples"] = samples[:80]
    review["notableSections"] = sections
    if new_sections:
        review["currentWork"] = "Audio/video samples scanned. Musicianship judgment pending."
        review["mediaAccess"] = "sample_ready"
    review["strongestSignal"] = "Unjudged"
    review["weakestRecurringSignal"] = "Unjudged"

    blockers = [result.get("blocker") for result in results if result.get("status") == "blocked" and result.get("blocker")]
    run = {
        "startedAt": utc_now(),
        "status": "sections_scanned" if new_sections else "blocked" if blockers else "no_new_samples",
        "sampleCount": len(selected),
        "sectionCount": len(new_sections),
        "violinClassifiedCount": len(classified),
        "violinPositiveCount": sum(1 for sample in samples if sample_is_violin_positive(sample)),
        "withheldSampleCount": sum(
            1
            for sample in samples
            if sample.get("id")
            and sample.get("violinSamplerVersion") == VIOLIN_PRESENCE_VERSION
            and not sample_is_violin_positive(sample)
        ),
        "classified": classified,
        "blockers": list(dict.fromkeys(blockers)),
        "results": results,
    }
    state["lastAnalysisRun"] = run
    save_state(state)
    return run
