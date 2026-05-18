from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .analyzer import run_process
from .long_phrase_truth import note_window_continuity
from .settings import ROOT_DIR, RUNTIME_DIR
from .state import utc_now


AUDIT_DIR = RUNTIME_DIR / "staff4-audit"
PACKAGED_AUDIT_DIR = ROOT_DIR / "assets" / "staff4-audit"
OWNER_MEDIA_DIR = RUNTIME_DIR / "owner-media"
STAFF4_AUDIT_VERSION = "staff4_phrase_audit_v3"
OWNER_MEDIA_SUFFIXES = (".webm", ".mp4", ".mov", ".m4a", ".mp3", ".wav")


def safe_slug(value: Any, fallback: str = "packet") -> str:
    raw = str(value or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")
    return slug[:96] or fallback


def artifact_url(packet_id: str, filename: str) -> str:
    return f"/api/curtis/staff4-audit/artifacts/{safe_slug(packet_id)}/{safe_slug(filename)}"


def packet_artifact_path(packet_id: str, filename: str) -> Path:
    return AUDIT_DIR / safe_slug(packet_id) / safe_slug(filename)


def packaged_packet_artifact_path(packet_id: str, filename: str) -> Path:
    return PACKAGED_AUDIT_DIR / safe_slug(packet_id) / safe_slug(filename)


def packet_json_path(packet_id: str) -> Path:
    return packet_artifact_path(packet_id, "packet.json")


def packaged_packet_json_path(packet_id: str) -> Path:
    return packaged_packet_artifact_path(packet_id, "packet.json")


def resolve_packet_artifact_path(packet_id: str, filename: str) -> Path | None:
    for root in (AUDIT_DIR, PACKAGED_AUDIT_DIR):
        try:
            target = (root / safe_slug(packet_id) / safe_slug(filename)).resolve(strict=True)
            safe_root = root.resolve()
        except OSError:
            continue
        if target.is_file() and safe_root in target.parents:
            return target
    return None


def load_packaged_audit_packet(packet_id: str) -> dict[str, Any]:
    path = packaged_packet_json_path(packet_id)
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(packet, dict):
        return {}
    if packet.get("version") != STAFF4_AUDIT_VERSION:
        return {}
    if str(packet.get("packetId") or "") != safe_slug(packet_id):
        return {}
    return packet


def packaged_artifacts_ready(packet_id: str) -> bool:
    return bool(
        resolve_packet_artifact_path(packet_id, "packet.json")
        and resolve_packet_artifact_path(packet_id, "staff4-audit.wav")
        and resolve_packet_artifact_path(packet_id, "staff4-audit.mp4")
    )


def with_packaged_audit_fallback(packet: dict[str, Any]) -> dict[str, Any]:
    packet_id = str(packet.get("packetId") or "").strip()
    if not packet_id or not packaged_artifacts_ready(packet_id):
        return packet
    packaged = load_packaged_audit_packet(packet_id)
    if not packaged:
        return packet
    if str(packet.get("auditFocus") or packaged.get("auditFocus") or "") != str(packaged.get("auditFocus") or ""):
        return packet
    merged = dict(packaged)
    merged["packagedArtifactFallback"] = True
    return merged


def safe_media_sample_id(value: Any) -> str:
    raw = str(value or "").strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")


def owner_media_path_for_sample_id(sample_id: str) -> Path | None:
    safe_id = safe_media_sample_id(sample_id)
    if not safe_id:
        return None
    candidates: list[Path] = []
    for suffix in OWNER_MEDIA_SUFFIXES:
        candidates.append(OWNER_MEDIA_DIR / f"{safe_id}-browser{suffix}")
        candidates.append(OWNER_MEDIA_DIR / f"{safe_id}{suffix}")
    try:
        owner_dir = OWNER_MEDIA_DIR.resolve()
    except OSError:
        return None
    for candidate in candidates:
        try:
            path = candidate.resolve(strict=True)
        except OSError:
            continue
        if path.is_file() and (path == owner_dir or owner_dir in path.parents):
            return path
    return None


def owner_media_sample_for_id(sample_id: str) -> dict[str, Any]:
    path = owner_media_path_for_sample_id(sample_id)
    if not path:
        return {}
    return {
        "id": str(sample_id or "").strip(),
        "path": str(path),
        "status": "media_sample_ready",
        "source": "owner_media_fallback",
    }


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


def frequency_for_midi(midi: int | float | None) -> float | None:
    if midi is None:
        return None
    try:
        value = float(midi)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return 440.0 * (2.0 ** ((value - 69.0) / 12.0))


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


def sequence_notes(value: Any) -> list[str]:
    return [item for item in sequence_label(value).split() if item]


def failure_source_note(failure: dict[str, Any]) -> str:
    index = int_or_none(failure.get("failedNoteIndex"))
    notes = sequence_notes(failure.get("targetSequence"))
    if index is not None and 0 <= index < len(notes):
        return notes[index]
    return str(failure.get("expectedSourceNote") or failure.get("expectedNote") or "")


def first_failure_from_completion(completion: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for key_path in (
        ("staff4SourceAudioRescanAdjacentFirstFailure",),
        ("staff4SourceAudioRescan", "guidedAdjacentFirstFailure"),
        ("staff4AdjacentMining", "sourceAudioRescanGuidedAdjacentFirstFailure"),
    ):
        current: Any = completion
        for key in key_path:
            current = current.get(key) if isinstance(current, dict) else None
        if isinstance(current, dict) and current.get("targetMidiSequence"):
            candidates.append(current)
    if not candidates:
        return {}

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
        direction = str(item.get("direction") or "")
        direction_rank = 0 if direction == "right-1" else 1 if direction == "right-2" else 2
        return (
            direction_rank,
            int(item.get("failedNoteIndex") or 999),
            int(item.get("targetNoteCount") or len(item.get("targetMidiSequence") or []) or 999),
        )

    failure = dict(sorted(candidates, key=sort_key)[0])
    failure["expectedSourceNote"] = failure_source_note(failure)
    return failure


def failure_from_current_expansion(current: dict[str, Any]) -> dict[str, Any]:
    mismatch_index = first_mismatch_index(current)
    expected_current_midi = int_or_none(current.get("expectedNextScoreMidi"))
    observed_current_midi = int_or_none(current.get("observedNextAudioMidi"))
    if mismatch_index < 0 and expected_current_midi is not None and observed_current_midi is not None and expected_current_midi != observed_current_midi:
        anchor_len = len(sequence_notes(current.get("anchorSequence")))
        target_len = len(current.get("targetMidiSequence")) if isinstance(current.get("targetMidiSequence"), list) else 0
        mismatch_index = min(max(0, anchor_len), max(0, target_len - 1))
    if mismatch_index < 0:
        return {}
    target_midis = current.get("targetMidiSequence") if isinstance(current.get("targetMidiSequence"), list) else []
    best_midis = current.get("bestAudioMidiSequence") if isinstance(current.get("bestAudioMidiSequence"), list) else []
    expected_midi = expected_current_midi or list_int_at(target_midis, mismatch_index)
    observed_midi = observed_current_midi or list_int_at(best_midis, mismatch_index)
    target_notes = sequence_notes(current.get("targetSequence"))
    expected_note = (
        target_notes[mismatch_index]
        if 0 <= mismatch_index < len(target_notes)
        else note_label_for_midi(expected_midi, prefer_flats=True)
    )
    return {
        "direction": str(current.get("direction") or "current"),
        "targetReferenceStart": current.get("targetReferenceStart"),
        "targetReferenceEnd": current.get("targetReferenceEnd"),
        "targetSequence": sequence_label(current.get("targetSequence")),
        "targetMidiSequence": target_midis,
        "targetNoteCount": len(target_midis),
        "reproducedNoteCount": mismatch_index,
        "failedNoteIndex": mismatch_index,
        "expectedMidi": expected_midi,
        "expectedNote": expected_note,
        "expectedSourceNote": expected_note,
        "reason": current.get("status") or "current_expansion_mismatch",
        "failureKind": "wrong_midi_detected" if observed_midi is not None and observed_midi != expected_midi else "stored_run_unverified",
        "bestAttemptStartSeconds": (
            current.get("bestAudioNotes", [{}])[mismatch_index].get("startSeconds")
            if isinstance(current.get("bestAudioNotes"), list) and 0 <= mismatch_index < len(current.get("bestAudioNotes"))
            else None
        ),
        "bestAttemptEndSeconds": (
            current.get("bestAudioNotes", [{}])[mismatch_index].get("endSeconds")
            if isinstance(current.get("bestAudioNotes"), list) and 0 <= mismatch_index < len(current.get("bestAudioNotes"))
            else None
        ),
        "bestAttemptObservedMidi": [observed_midi] if observed_midi is not None else [],
        "bestAttemptObservedNotes": [note_label_for_midi(observed_midi)] if observed_midi is not None else [],
        "bestAttemptObservedConsensusMidi": observed_midi or 0,
        "bestAttemptObservedConsensusNote": note_label_for_midi(observed_midi) if observed_midi is not None else "",
    }


def failure_observed_midi(failure: dict[str, Any]) -> int | None:
    consensus = int_or_none(failure.get("bestAttemptObservedConsensusMidi"))
    if consensus:
        return consensus
    observed = failure.get("bestAttemptObservedMidi") if isinstance(failure.get("bestAttemptObservedMidi"), list) else []
    for value in observed:
        midi = int_or_none(value)
        if midi is not None:
            return midi
    return None


def failure_observed_note(failure: dict[str, Any]) -> str:
    note = str(failure.get("bestAttemptObservedConsensusNote") or "")
    if note:
        return note
    midi = failure_observed_midi(failure)
    if midi is not None:
        return note_label_for_midi(midi)
    observed_notes = (
        failure.get("bestAttemptObservedNotes")
        if isinstance(failure.get("bestAttemptObservedNotes"), list)
        else []
    )
    return str(observed_notes[0]) if observed_notes else ""


def list_int_at(values: Any, index: int | None) -> int | None:
    if index is None or not isinstance(values, list) or not (0 <= index < len(values)):
        return None
    return int_or_none(values[index])


def int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    out: list[int] = []
    for value in values:
        parsed = int_or_none(value)
        if parsed is None:
            return []
        out.append(parsed)
    return out


def staff4_current_has_exact_audio_phrase(current: dict[str, Any]) -> bool:
    target_midis = int_list(current.get("targetMidiSequence"))
    audio_midis = int_list(current.get("bestAudioMidiSequence"))
    if len(target_midis) < 5 or target_midis != audio_midis:
        return False
    notes = current.get("bestAudioNotes") if isinstance(current.get("bestAudioNotes"), list) else []
    if len(notes) < len(target_midis):
        return bool(current.get("audioAgreed"))
    note_midis = [int_or_none(note.get("midi")) if isinstance(note, dict) else None for note in notes[: len(target_midis)]]
    if note_midis != target_midis:
        return False
    continuity = note_window_continuity([note for note in notes[: len(target_midis)] if isinstance(note, dict)])
    return bool(continuity.get("continuous")) and all(
        isinstance(note, dict) and note.get("audioAgreement") is True for note in notes[: len(target_midis)]
    )


def staff4_current_has_exact_midi_sequence(current: dict[str, Any]) -> bool:
    target_midis = int_list(current.get("targetMidiSequence"))
    audio_midis = int_list(current.get("bestAudioMidiSequence"))
    if len(target_midis) < 5 or target_midis != audio_midis:
        return False
    notes = current.get("bestAudioNotes") if isinstance(current.get("bestAudioNotes"), list) else []
    if len(notes) < len(target_midis):
        return bool(current.get("audioAgreed"))
    note_midis = [int_or_none(note.get("midi")) if isinstance(note, dict) else None for note in notes[: len(target_midis)]]
    return note_midis == target_midis and all(
        isinstance(note, dict) and note.get("audioAgreement") is True for note in notes[: len(target_midis)]
    )


def staff4_audit_failure_for_completion(completion: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if staff4_current_has_exact_audio_phrase(current) or staff4_current_has_exact_midi_sequence(current):
        return {}
    return first_failure_from_completion(completion) or failure_from_current_expansion(current)


def staff4_full_phrase_audit_decision(packet: dict[str, Any]) -> dict[str, Any]:
    target_midis = int_list(packet.get("targetMidiSequence"))
    audio_midis = int_list(packet.get("bestAudioMidiSequence"))
    stored_notes = packet.get("storedAudioNotes") if isinstance(packet.get("storedAudioNotes"), list) else []
    stored_midis = [
        int_or_none(note.get("midi")) if isinstance(note, dict) else None for note in stored_notes[: len(target_midis)]
    ]
    stored_audio_ready = (
        len(target_midis) >= 5
        and target_midis == audio_midis
        and stored_midis == target_midis
        and all(isinstance(note, dict) and note.get("audioAgreement") is True for note in stored_notes[: len(target_midis)])
    )
    continuity = note_window_continuity([note for note in stored_notes[: len(target_midis)] if isinstance(note, dict)])
    stored_audio_phrase_ready = stored_audio_ready and bool(continuity.get("continuous"))
    source_crop_ready = bool(packet.get("score", {}).get("sourceCropReady")) if isinstance(packet.get("score"), dict) else False
    truth_ready = bool(packet.get("score", {}).get("truthEvidenceAccepted")) if isinstance(packet.get("score"), dict) else False
    status = "queued_gold_review"
    outcome = "manual_review_required"
    truth_decision = "pending_review"
    accepted = False
    can_extend = False
    if stored_audio_ready and not continuity.get("continuous"):
        status = "blocked_discontinuous_audio_phrase"
        outcome = "full_phrase_exact_midi_not_temporally_continuous"
    elif stored_audio_phrase_ready and source_crop_ready and truth_ready:
        status = "accepted_truth_candidate"
        outcome = "accept_full_audio_agreed_source_phrase"
        truth_decision = "accepted"
        accepted = True
        can_extend = True
    elif stored_audio_phrase_ready and source_crop_ready:
        status = "pending_source_lock"
        outcome = "full_audio_agreed_source_phrase_pending_truth_lock"
    elif stored_audio_phrase_ready:
        status = "blocked_source_crop_required"
        outcome = "full_audio_agreed_phrase_missing_source_crop"
    elif target_midis and audio_midis:
        status = "queued_gold_review"
        outcome = "full_phrase_audio_sequence_needs_review"
    return {
        "status": status,
        "outcome": outcome,
        "truthDecision": truth_decision,
        "accepted": accepted,
        "rejected": False,
        "canExtendStaff4Lane": can_extend,
        "fullPhraseExactAudio": stored_audio_phrase_ready,
        "fullPhraseExactMidi": stored_audio_ready,
        "phraseContinuity": continuity,
        "targetNoteCount": len(target_midis),
        "audioNoteCount": len(audio_midis),
        "targetMidiSequence": target_midis,
        "audioMidiSequence": audio_midis,
        "goldReviewRequired": status in {"pending_source_lock", "queued_gold_review", "blocked_source_crop_required"},
        "limit": (
            "Accepted extension requires exact full-phrase audio, source crop, and truth lock."
            if status == "pending_source_lock"
            else "Full phrase accepted from exact audio, source crop, and truth lock."
            if accepted
            else str(continuity.get("limit") or "Exact MIDI is not one continuous phrase.")
            if status == "blocked_discontinuous_audio_phrase"
            else "No full-phrase acceptance without exact audio and source evidence."
        ),
    }


def staff4_audit_decision(packet: dict[str, Any], analysis: dict[str, Any], failure: dict[str, Any]) -> dict[str, Any]:
    expected_midi = int_or_none(failure.get("expectedMidi")) or int_or_none(packet.get("expectedNextScoreMidi"))
    expected_note = failure_source_note(failure) or str(packet.get("expectedNextScoreNote") or "")
    observed_midi = failure_observed_midi(failure)
    observed_note = failure_observed_note(failure) or str(packet.get("observedNextAudioNote") or "")
    mismatch = analysis.get("mismatchWindow") if isinstance(analysis.get("mismatchWindow"), dict) else {}
    detector_votes = mismatch.get("detectorVotes") if isinstance(mismatch.get("detectorVotes"), dict) else {}
    pitch_diagnostic = (
        packet.get("failedNotePitchDiagnostic")
        if isinstance(packet.get("failedNotePitchDiagnostic"), dict)
        else {}
    )
    exact_expected_votes = int(detector_votes.get("expected") or 0)
    exact_observed_votes = int(detector_votes.get("observed") or 0)
    failure_kind = str(failure.get("failureKind") or "")
    reason = str(failure.get("reason") or "")
    failed_index = int_or_none(failure.get("failedNoteIndex"))
    stored_expected_midi = list_int_at(packet.get("targetMidiSequence"), failed_index)
    stored_audio_midi = list_int_at(packet.get("bestAudioMidiSequence"), failed_index)
    stored_run_exact_at_failure = (
        expected_midi is not None
        and stored_expected_midi == expected_midi
        and stored_audio_midi == expected_midi
    )
    outcome = "review_required"
    status = "queued_gold_review"
    truth_decision = "pending_review"
    accepted = False
    rejected = False
    can_extend = False
    regression_case = None

    if expected_midi is not None and observed_midi is not None and observed_midi != expected_midi and (
        failure_kind == "wrong_midi_detected" or exact_observed_votes >= 2
    ):
        outcome = "reject_audio_score_mismatch"
        status = "rejected_mismatch"
        truth_decision = "rejected_mismatch"
        rejected = True
        regression_case = {
            "regressionId": safe_slug(
                f"rejected-staff4-{packet.get('practiceDay')}-{packet.get('sampleId')}-{packet.get('targetReferenceStart')}-{packet.get('targetReferenceEnd')}-{expected_note}-vs-{observed_note}",
                "rejected-staff4-audio-mismatch",
            ),
            "kind": "staff4_first_failure_audio_mismatch",
            "expectedNote": expected_note,
            "expectedMidi": expected_midi,
            "observedNote": observed_note,
            "observedMidi": observed_midi,
            "basis": "First-failure audit heard a different MIDI value than the verified Staff 4 source note.",
        }
    elif (
        failure_kind in {"outside_scan", "no_detector_votes"}
        or reason == "current_detectors_did_not_reproduce_exact_midi"
    ) and observed_midi is None and exact_expected_votes == 0:
        outcome = "rescan_window_required"
        status = "queued_gold_review"
    elif stored_run_exact_at_failure and exact_expected_votes == 0:
        outcome = "stored_audio_run_exact_but_current_audit_unverified"
        status = "queued_gold_review"
    elif expected_midi is not None and (
        exact_expected_votes >= 2
    ):
        if packet.get("score", {}).get("sourceCropReady") and packet.get("score", {}).get("truthEvidenceAccepted"):
            outcome = "accept_audio_agreed_source_note"
            status = "accepted_truth_candidate"
            truth_decision = "accepted"
            accepted = True
            can_extend = True
        else:
            outcome = "audio_agreed_but_source_crop_or_truth_lock_missing"
            status = "pending_source_lock"
    else:
        outcome = "manual_review_required"
        status = "queued_gold_review"

    return {
        "status": status,
        "outcome": outcome,
        "truthDecision": truth_decision,
        "accepted": accepted,
        "rejected": rejected,
        "canExtendStaff4Lane": can_extend,
        "storedRunExactAtFailure": stored_run_exact_at_failure,
        "failedNoteIndex": failed_index,
        "expectedNote": expected_note,
        "expectedMidi": expected_midi,
        "observedNote": observed_note,
        "observedMidi": observed_midi,
        "failureKind": failure_kind,
        "reason": reason,
        "detectorVotes": detector_votes,
        "pitchDiagnosticClass": pitch_diagnostic.get("diagnosticClass") or "",
        "pitchDiagnosticConclusion": pitch_diagnostic.get("conclusion") or "",
        "regressionCase": regression_case,
        "goldReviewRequired": status == "queued_gold_review",
        "limit": (
            "Accepted extension requires exact audio MIDI plus source crop/truth lock."
            if status == "pending_source_lock"
            else "Rejected extension is locked as a regression case."
            if rejected
            else "No acceptance or rejection without inspectable audio evidence."
        ),
    }


def attach_staff4_audit_decision(
    packet: dict[str, Any],
    analysis: dict[str, Any],
    failure: dict[str, Any],
) -> dict[str, Any]:
    if not failure:
        return packet
    decision = staff4_audit_decision(packet, analysis, failure)
    packet["decision"] = decision
    packet["truthDecision"] = decision.get("truthDecision") or "pending_review"
    packet["canExtendStaff4Lane"] = bool(decision.get("canExtendStaff4Lane"))
    packet["expectedFailedScoreNote"] = decision.get("expectedNote") or ""
    packet["expectedFailedScoreMidi"] = decision.get("expectedMidi")
    packet["observedFailureAudioNote"] = decision.get("observedNote") or ""
    packet["observedFailureAudioMidi"] = decision.get("observedMidi")
    if decision.get("regressionCase"):
        packet["regressionCase"] = decision["regressionCase"]
    if decision.get("goldReviewRequired"):
        packet["goldReviewCandidate"] = {
            "status": "queued",
            "packetId": packet.get("packetId") or "",
            "kind": "staff4_first_failure_audio_score_audit",
            "expectedNote": decision.get("expectedNote") or "",
            "expectedMidi": decision.get("expectedMidi"),
            "observedNote": decision.get("observedNote") or "",
            "observedMidi": decision.get("observedMidi"),
            "targetSequence": packet.get("targetSequence") or "",
            "bestAudioSequence": packet.get("bestAudioSequence") or "",
            "clip": packet.get("clip") if isinstance(packet.get("clip"), dict) else {},
            "reason": decision.get("outcome") or decision.get("reason") or "",
        }
    if str(packet.get("status") or "") in {"generated", "needs_manual_audio_review", "detectors_disagree_with_stored_run", "detector_split_review_required"}:
        packet["status"] = str(decision.get("status") or packet.get("status") or "queued_gold_review")
    return packet


def attach_staff4_full_phrase_decision(packet: dict[str, Any]) -> dict[str, Any]:
    decision = staff4_full_phrase_audit_decision(packet)
    packet["decision"] = decision
    packet["truthDecision"] = decision.get("truthDecision") or "pending_review"
    packet["canExtendStaff4Lane"] = bool(decision.get("canExtendStaff4Lane"))
    packet["fullPhraseCheck"] = {
        "targetNoteCount": decision.get("targetNoteCount"),
        "audioNoteCount": decision.get("audioNoteCount"),
        "targetMidiSequence": decision.get("targetMidiSequence") or [],
        "audioMidiSequence": decision.get("audioMidiSequence") or [],
        "exactAudio": bool(decision.get("fullPhraseExactAudio")),
        "exactMidi": bool(decision.get("fullPhraseExactMidi")),
        "phraseContinuity": decision.get("phraseContinuity") if isinstance(decision.get("phraseContinuity"), dict) else {},
        "sourceCropReady": bool(packet.get("score", {}).get("sourceCropReady")) if isinstance(packet.get("score"), dict) else False,
        "truthEvidenceAccepted": bool(packet.get("score", {}).get("truthEvidenceAccepted")) if isinstance(packet.get("score"), dict) else False,
    }
    if decision.get("goldReviewRequired"):
        packet["goldReviewCandidate"] = {
            "status": "queued",
            "packetId": packet.get("packetId") or "",
            "kind": "staff4_full_phrase_audio_score_audit",
            "targetSequence": packet.get("targetSequence") or "",
            "bestAudioSequence": packet.get("bestAudioSequence") or "",
            "targetMidiSequence": decision.get("targetMidiSequence") or [],
            "audioMidiSequence": decision.get("audioMidiSequence") or [],
            "clip": packet.get("clip") if isinstance(packet.get("clip"), dict) else {},
            "reason": decision.get("outcome") or "",
        }
    if str(packet.get("status") or "") in {"generated", "needs_manual_audio_review", "detectors_disagree_with_stored_run", "detector_split_review_required"}:
        packet["status"] = str(decision.get("status") or packet.get("status") or "queued_gold_review")
    return packet


def attach_staff4_source_crop_reverification_decision(packet: dict[str, Any]) -> dict[str, Any]:
    target_midis = int_list(packet.get("targetMidiSequence"))
    audio_midis = int_list(packet.get("bestAudioMidiSequence"))
    decision = {
        "status": "pending_source_crop_reverification",
        "outcome": "source_crop_reverification_required",
        "truthDecision": "pending_review",
        "accepted": False,
        "rejected": False,
        "canExtendStaff4Lane": False,
        "targetMidiSequence": target_midis,
        "audioMidiSequence": audio_midis,
        "targetSequence": packet.get("targetSequence") or "",
        "bestAudioSequence": packet.get("bestAudioSequence") or "",
        "sourceCropRejected": True,
        "goldReviewRequired": True,
        "limit": "Visible source crop, boxed noteheads, rendered transcription, and paired audio must agree before Staff 4 can become accepted evidence again.",
    }
    packet["decision"] = decision
    packet["truthDecision"] = "pending_review"
    packet["canExtendStaff4Lane"] = False
    packet["sourceCropReverification"] = {
        "status": "pending_review",
        "targetSequence": packet.get("targetSequence") or "",
        "bestAudioSequence": packet.get("bestAudioSequence") or "",
        "targetMidiSequence": target_midis,
        "audioMidiSequence": audio_midis,
        "scoreImageUrl": (
            packet.get("score", {}).get("sourceImageUrl")
            if isinstance(packet.get("score"), dict)
            else ""
        ),
        "acceptanceRule": decision["limit"],
    }
    packet["goldReviewCandidate"] = {
        "status": "queued",
        "packetId": packet.get("packetId") or "",
        "kind": "staff4_source_crop_reverification",
        "targetSequence": packet.get("targetSequence") or "",
        "bestAudioSequence": packet.get("bestAudioSequence") or "",
        "targetMidiSequence": target_midis,
        "audioMidiSequence": audio_midis,
        "clip": packet.get("clip") if isinstance(packet.get("clip"), dict) else {},
        "reason": decision["outcome"],
    }
    if str(packet.get("status") or "") in {"generated", "needs_manual_audio_review", "detectors_disagree_with_stored_run", "detector_split_review_required"}:
        packet["status"] = "queued_source_crop_reverification"
    return packet


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


def source_crop_reverification_current(completion: dict[str, Any]) -> dict[str, Any]:
    target = (
        completion.get("sourceCropReverificationTarget")
        if isinstance(completion.get("sourceCropReverificationTarget"), dict)
        else {}
    )
    if not target:
        return {}
    target_midis = int_list(target.get("targetMidiSequence"))
    detected_midis = int_list(target.get("bestAudioMidiSequence") or target.get("detectedMidiSequence"))
    if not target_midis or not detected_midis:
        return {}
    detected_notes = sequence_notes(target.get("bestAudioSequence") or target.get("detectedSequence"))
    raw_windows = target.get("bestAudioNotes") if isinstance(target.get("bestAudioNotes"), list) else []
    best_notes: list[dict[str, Any]] = []
    for index, window in enumerate(raw_windows):
        if not isinstance(window, dict):
            continue
        midi = detected_midis[index] if index < len(detected_midis) else int_or_none(window.get("midi"))
        note = (
            detected_notes[index]
            if index < len(detected_notes)
            else str(window.get("note") or note_label_for_midi(midi))
        )
        best_notes.append(
            {
                "note": note,
                "midi": midi,
                "startSeconds": window.get("startSeconds"),
                "endSeconds": window.get("endSeconds"),
                "confidence": window.get("confidence"),
                "audioAgreement": False,
                "agreementSourceCount": 0,
                "agreementSources": [],
                "detectorSource": str(window.get("detectorSource") or "visible_mismatch_reverification_queue"),
            }
        )
    return {
        "status": "queued_source_crop_reverification",
        "sourceCropReverification": True,
        "auditFocus": "staff4_source_crop_reverification",
        "practiceDay": target.get("practiceDay") or "",
        "pieceTitle": target.get("pieceTitle") or "",
        "targetReferenceStart": target.get("targetReferenceStart"),
        "targetReferenceEnd": target.get("targetReferenceEnd"),
        "targetSequence": sequence_label(target.get("targetSequence")),
        "targetMidiSequence": target_midis,
        "bestAudioSequence": sequence_label(target.get("bestAudioSequence") or target.get("detectedSequence")),
        "bestAudioMidiSequence": detected_midis,
        "sampleId": target.get("sampleId") or "",
        "sourceWindow": target.get("sourceWindow") or "",
        "audioRunSource": "visible_mismatch_reverification_queue",
        "audioLocalStartSeconds": target.get("audioLocalStartSeconds"),
        "audioLocalEndSeconds": target.get("audioLocalEndSeconds"),
        "sourceImageUrl": target.get("sourceImageUrl") or "",
        "sourceCropReady": False,
        "sourceCropRejected": True,
        "truthEvidenceAccepted": False,
        "bestAudioNotes": best_notes,
        "rejectedRegressionId": target.get("rejectedRegressionId") or "",
        "acceptanceRule": target.get("acceptanceRule") or "",
        "limit": target.get("limit") or "Visible source crop must be reverified before Staff 4 can be accepted.",
    }


def is_source_crop_reverification_current(current: dict[str, Any]) -> bool:
    return bool(current.get("sourceCropReverification")) or str(current.get("auditFocus") or "") == "staff4_source_crop_reverification"


def packet_id_for_current(current: dict[str, Any], failure: dict[str, Any] | None = None) -> str:
    focus = failure if isinstance(failure, dict) and failure else current
    sample_id = str(current.get("sampleId") or focus.get("sampleId") or "sample")
    prefix = "staff4-source-crop-review" if is_source_crop_reverification_current(current) else "staff4"
    return safe_slug(
        "-".join(
            [
                prefix,
                str(current.get("practiceDay") or "day"),
                sample_id,
                str(focus.get("targetReferenceStart") or current.get("targetReferenceStart") or "start"),
                str(focus.get("targetReferenceEnd") or current.get("targetReferenceEnd") or "end"),
            ]
        )
    )


def media_sample_for_id(state: dict[str, Any], sample_id: str) -> dict[str, Any]:
    samples = state.get("mediaSamples") if isinstance(state.get("mediaSamples"), list) else []
    target = str(sample_id or "").strip()
    for sample in samples:
        if isinstance(sample, dict) and str(sample.get("id") or "").strip() == target:
            return sample
    return owner_media_sample_for_id(target)


def source_media_path(sample: dict[str, Any]) -> Path | None:
    raw = str(sample.get("path") or "").strip()
    if not raw:
        return owner_media_path_for_sample_id(str(sample.get("id") or ""))
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


def analyze_audio_clip(
    audio_path: Path,
    current: dict[str, Any],
    clip_start: float,
    audit_failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
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

    failure = audit_failure if isinstance(audit_failure, dict) else {}
    mismatch_index = int_or_none(failure.get("failedNoteIndex")) if failure else first_mismatch_index(current)
    if mismatch_index is None:
        mismatch_index = -1
    best_notes = current.get("bestAudioNotes") if isinstance(current.get("bestAudioNotes"), list) else []
    mismatch_note = best_notes[mismatch_index] if 0 <= mismatch_index < len(best_notes) and isinstance(best_notes[mismatch_index], dict) else {}
    failure_start = number_or_none(failure.get("bestAttemptStartSeconds")) if failure else None
    failure_end = number_or_none(failure.get("bestAttemptEndSeconds")) if failure else None
    note_start = failure_start if failure_start is not None else number_or_none(mismatch_note.get("startSeconds"))
    note_end = failure_end if failure_end is not None else number_or_none(mismatch_note.get("endSeconds"))
    mismatch_start = max(0.0, (note_start or clip_start) - clip_start)
    mismatch_end = max(mismatch_start, (note_end or note_start or clip_start) - clip_start)
    if mismatch_end <= mismatch_start:
        mismatch_end = min(duration, mismatch_start + 0.18)
    expected_midi = int_or_none(failure.get("expectedMidi")) if failure else None
    if expected_midi is None:
        expected_midi = int_or_none(current.get("expectedNextScoreMidi"))
    observed_midi = failure_observed_midi(failure) if failure else None
    if observed_midi is None:
        observed_midi = int_or_none(current.get("observedNextAudioMidi"))
    expected_note = failure_source_note(failure) if failure else ""
    if not expected_note:
        expected_note = note_label_for_midi(expected_midi, prefer_flats=True)
    observed_note = failure_observed_note(failure) if failure else ""
    if not observed_note:
        observed_note = note_label_for_midi(observed_midi)
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
            "expectedNote": expected_note,
            "observedMidi": observed_midi,
            "observedNote": observed_note,
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


def harmonic_pitch_energy(
    y: Any,
    sr: int,
    midi: int,
    np: Any,
    *,
    harmonics: int = 5,
    bandwidth_ratio: float = 0.015,
) -> dict[str, Any]:
    if len(y) < 32:
        return {
            "midi": midi,
            "note": note_label_for_midi(midi, prefer_flats=True),
            "fundamentalHz": frequency_for_midi(midi),
            "fundamentalEnergy": 0.0,
            "harmonicEnergy": 0.0,
            "harmonicCount": 0,
        }
    fft_size = 1
    while fft_size < len(y) * 8:
        fft_size *= 2
    window = np.hanning(len(y))
    magnitude = np.abs(np.fft.rfft(y * window, n=fft_size))
    freqs = np.fft.rfftfreq(fft_size, 1.0 / float(sr))
    fundamental = frequency_for_midi(midi)
    if not fundamental:
        return {
            "midi": midi,
            "note": note_label_for_midi(midi, prefer_flats=True),
            "fundamentalHz": None,
            "fundamentalEnergy": 0.0,
            "harmonicEnergy": 0.0,
            "harmonicCount": 0,
        }
    harmonic_energy = 0.0
    fundamental_energy = 0.0
    harmonic_count = 0
    nyquist = float(sr) / 2.0
    for harmonic in range(1, harmonics + 1):
        target = fundamental * harmonic
        if target >= nyquist:
            continue
        low = target * (1.0 - bandwidth_ratio)
        high = target * (1.0 + bandwidth_ratio)
        mask = (freqs >= low) & (freqs <= high)
        peak = float(magnitude[mask].max(initial=0.0))
        if harmonic == 1:
            fundamental_energy = peak
        harmonic_energy += peak / math.sqrt(harmonic)
        harmonic_count += 1
    return {
        "midi": midi,
        "note": note_label_for_midi(midi, prefer_flats=True),
        "fundamentalHz": round(fundamental, 3),
        "fundamentalEnergy": round(fundamental_energy, 6),
        "harmonicEnergy": round(harmonic_energy, 6),
        "harmonicCount": harmonic_count,
    }


def failed_note_pitch_diagnostic(
    audio_path: Path,
    failure: dict[str, Any],
    clip_start: float,
) -> dict[str, Any]:
    expected_midi = int_or_none(failure.get("expectedMidi"))
    observed_midi = failure_observed_midi(failure)
    if expected_midi is None:
        return {"status": "unavailable", "reason": "missing_expected_midi"}
    if not audio_path.exists():
        return {"status": "unavailable", "reason": "audit_audio_missing"}
    try:
        import librosa
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment boundary
        return {"status": "unavailable", "reason": "dependency_unavailable", "detail": str(exc)[:180]}
    try:
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    except Exception as exc:
        return {"status": "unavailable", "reason": "audio_load_failed", "detail": str(exc)[:180]}
    if getattr(y, "size", 0) == 0:
        return {"status": "unavailable", "reason": "empty_audio"}

    failure_start = number_or_none(failure.get("bestAttemptStartSeconds"))
    failure_end = number_or_none(failure.get("bestAttemptEndSeconds"))
    local_start = max(0.0, (failure_start if failure_start is not None else clip_start) - clip_start)
    local_end = max(local_start + 0.08, (failure_end if failure_end is not None else failure_start or clip_start) - clip_start)
    duration = float(librosa.get_duration(y=y, sr=sr))
    local_start = max(0.0, min(duration, local_start))
    local_end = max(local_start + 0.08, min(duration, local_end))
    segment = y[int(local_start * sr) : int(local_end * sr)]
    if len(segment) < 32:
        return {
            "status": "unavailable",
            "reason": "analysis_window_too_short",
            "analysisWindow": {
                "clipLocalStartSeconds": round(local_start, 3),
                "clipLocalEndSeconds": round(local_end, 3),
            },
        }

    candidate_midis = set(range(max(43, expected_midi - 12), min(97, expected_midi + 13)))
    if observed_midi is not None:
        candidate_midis.update(range(max(43, observed_midi - 3), min(97, observed_midi + 4)))
    target_midis = failure.get("targetMidiSequence") if isinstance(failure.get("targetMidiSequence"), list) else []
    for midi in target_midis:
        value = int_or_none(midi)
        if value is not None:
            candidate_midis.add(value)
    energies = [harmonic_pitch_energy(segment, sr, midi, np) for midi in sorted(candidate_midis)]
    ranked = sorted(energies, key=lambda item: float(item.get("harmonicEnergy") or 0.0), reverse=True)
    expected_energy = next((item for item in energies if item.get("midi") == expected_midi), {})
    observed_energy = next((item for item in energies if item.get("midi") == observed_midi), {}) if observed_midi is not None else {}
    dominant = ranked[0] if ranked else {}

    expected_value = float(expected_energy.get("harmonicEnergy") or 0.0)
    observed_value = float(observed_energy.get("harmonicEnergy") or 0.0)
    dominant_value = float(dominant.get("harmonicEnergy") or 0.0)
    observed_neighbor_value = 0.0
    if observed_midi is not None:
        observed_neighbor_value = max(
            float(item.get("harmonicEnergy") or 0.0)
            for item in energies
            if abs(int(item.get("midi") or 0) - observed_midi) <= 1
        )
    expected_to_observed = expected_value / observed_value if observed_value > 0 else None
    expected_to_dominant = expected_value / dominant_value if dominant_value > 0 else None

    diagnostic_class = "insufficient_pitch_energy"
    conclusion = "Expected source pitch is not supported strongly enough to decide."
    if expected_value > 0 and observed_neighbor_value >= expected_value * 3.0:
        diagnostic_class = "observed_region_dominates"
        conclusion = "The failed window is dominated by the observed audio pitch region, not the expected source pitch."
    elif expected_to_observed is not None and expected_to_observed >= 0.65:
        diagnostic_class = "expected_pitch_present"
        conclusion = "Expected source pitch is present strongly enough for manual review before rejection."
    elif expected_to_observed is not None and expected_to_observed >= 0.25:
        diagnostic_class = "expected_pitch_possible_under_observed"
        conclusion = "Expected source pitch may be present under a stronger neighboring pitch and needs gold review."
    elif dominant_value > 0:
        diagnostic_class = "expected_pitch_not_supported"
        conclusion = "Expected source pitch is far weaker than the dominant pitch evidence."

    return {
        "status": "ready",
        "diagnosticClass": diagnostic_class,
        "conclusion": conclusion,
        "analysisWindow": {
            "clipLocalStartSeconds": round(local_start, 3),
            "clipLocalEndSeconds": round(local_end, 3),
            "durationSeconds": round(max(0.0, local_end - local_start), 3),
        },
        "expectedMidi": expected_midi,
        "expectedNote": failure_source_note(failure) or note_label_for_midi(expected_midi, prefer_flats=True),
        "observedMidi": observed_midi,
        "observedNote": note_label_for_midi(observed_midi, prefer_flats=True) if observed_midi is not None else "",
        "expectedHarmonicEnergy": expected_energy,
        "observedHarmonicEnergy": observed_energy,
        "dominantPitch": dominant,
        "expectedToObservedRatio": round(expected_to_observed, 6) if expected_to_observed is not None else None,
        "expectedToDominantRatio": round(expected_to_dominant, 6) if expected_to_dominant is not None else None,
        "rankedPitchEnergies": [
            {
                **item,
                "relativeToDominant": round((float(item.get("harmonicEnergy") or 0.0) / dominant_value), 6)
                if dominant_value > 0
                else None,
            }
            for item in ranked[:12]
        ],
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
    source_crop_reverification = False
    if not current:
        current = source_crop_reverification_current(completion)
        source_crop_reverification = bool(current)
    if not current:
        harness = completion.get("phraseExpansionHarness") if isinstance(completion.get("phraseExpansionHarness"), dict) else {}
        extent_exhausted = str(harness.get("status") or "") == "source_extent_exhausted"
        accepted_anchor_note_count = int_or_none(harness.get("acceptedAnchorNoteCount")) or 0
        packet = {
            "version": STAFF4_AUDIT_VERSION,
            "status": "blocked_source_extent_exhausted" if extent_exhausted else "blocked_no_staff4_expansion",
            "createdAt": utc_now(),
            "acceptedAnchorNoteCount": accepted_anchor_note_count,
            "limit": (
                f"The accepted Staff 4 lane reaches the current {accepted_anchor_note_count}-note symbolic source extent; verify more MusicXML/source notes before another audit packet can be generated."
                if extent_exhausted
                else "No current Staff 4 phrase expansion target is available."
            ),
        }
        state["staff4PhraseAuditLatest"] = packet
        return packet

    first_failure = {} if source_crop_reverification else staff4_audit_failure_for_completion(completion, current)
    packet_id = packet_id_for_current(current, first_failure)
    existing_path = packet_json_path(packet_id)
    if existing_path.exists() and not force:
        try:
            packet = json.loads(existing_path.read_text(encoding="utf-8"))
            if packet.get("version") == STAFF4_AUDIT_VERSION:
                packet = with_packaged_audit_fallback(packet)
                state["staff4PhraseAuditLatest"] = packet
                return packet
        except (OSError, json.JSONDecodeError):
            pass

    sample_id = str(current.get("sampleId") or first_failure.get("sampleId") or "").strip()
    sample = media_sample_for_id(state, sample_id)
    source_path = source_media_path(sample)
    target_midis = (
        first_failure.get("targetMidiSequence")
        if isinstance(first_failure.get("targetMidiSequence"), list)
        else current.get("targetMidiSequence")
        if isinstance(current.get("targetMidiSequence"), list)
        else []
    )
    best_midis = current.get("bestAudioMidiSequence") if isinstance(current.get("bestAudioMidiSequence"), list) else []
    best_notes = current.get("bestAudioNotes") if isinstance(current.get("bestAudioNotes"), list) else []
    compact_notes = [compact_note_event(note, index) for index, note in enumerate(best_notes)]
    local_start = number_or_none(current.get("audioLocalStartSeconds"))
    local_end = number_or_none(current.get("audioLocalEndSeconds"))
    failure_start = number_or_none(first_failure.get("bestAttemptStartSeconds")) if first_failure else None
    failure_end = number_or_none(first_failure.get("bestAttemptEndSeconds")) if first_failure else None
    if failure_start is not None and failure_end is not None and failure_end > failure_start:
        local_start = failure_start
        local_end = failure_end
    if local_start is None and compact_notes:
        local_start = number_or_none(compact_notes[0].get("startSeconds"))
    if local_end is None and compact_notes:
        local_end = number_or_none(compact_notes[-1].get("endSeconds"))
    local_start = max(0.0, local_start or 0.0)
    local_end = max(local_start + 0.25, local_end or (local_start + 2.0))
    clip_start = max(0.0, local_start - 0.35)
    clip_max_seconds = max(8.0, min(24.0, (local_end - local_start) + 1.0))
    clip_end = min(local_end + 0.45, clip_start + clip_max_seconds)
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
    target_sequence = sequence_label(first_failure.get("targetSequence") or current.get("targetSequence"))
    expected_failed_note = failure_source_note(first_failure) if first_failure else str(current.get("expectedNextScoreNote") or "")
    expected_failed_midi = int_or_none(first_failure.get("expectedMidi")) if first_failure else int_or_none(current.get("expectedNextScoreMidi"))
    observed_failure_note = failure_observed_note(first_failure) if first_failure else str(current.get("observedNextAudioNote") or "")
    observed_failure_midi = failure_observed_midi(first_failure) if first_failure else int_or_none(current.get("observedNextAudioMidi"))

    packet: dict[str, Any] = {
        "version": STAFF4_AUDIT_VERSION,
        "packetId": packet_id,
        "createdAt": utc_now(),
        "practiceDay": current.get("practiceDay") or first_failure.get("practiceDay") or "",
        "pieceTitle": current.get("pieceTitle") or first_failure.get("pieceTitle") or "",
        "sampleId": sample_id,
        "sourceWindow": current.get("sourceWindow") or first_failure.get("sourceWindow") or sample.get("window") or "",
        "sourceTitle": sample.get("title") or current.get("sourceTitle") or first_failure.get("sourceTitle") or "",
        "sourceUrl": sample.get("url") or "",
        "status": "generated",
        "auditFocus": (
            "staff4_source_crop_reverification"
            if source_crop_reverification
            else "staff4_first_failed_adjacent_note"
            if first_failure
            else "staff4_full_exact_phrase"
        ),
        "truthDecision": "not_accepted",
        "gate": current.get("status") or "",
        "limit": current.get("limit") or "",
        "targetReferenceStart": first_failure.get("targetReferenceStart") or current.get("targetReferenceStart"),
        "targetReferenceEnd": first_failure.get("targetReferenceEnd") or current.get("targetReferenceEnd"),
        "targetSequence": target_sequence,
        "bestAudioSequence": sequence_label(current.get("bestAudioSequence")),
        "targetMidiSequence": target_midis,
        "bestAudioMidiSequence": best_midis,
        "expectedNextScoreNote": expected_failed_note,
        "expectedNextScoreMidi": expected_failed_midi,
        "observedNextAudioNote": observed_failure_note,
        "observedNextAudioMidi": observed_failure_midi,
        "expectedFailedScoreNote": expected_failed_note,
        "expectedFailedScoreMidi": expected_failed_midi,
        "observedFailureAudioNote": observed_failure_note,
        "observedFailureAudioMidi": observed_failure_midi,
        "firstFailure": first_failure,
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
            "sourceCropRejected": bool(current.get("sourceCropRejected")),
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
        if source_crop_reverification:
            attach_staff4_source_crop_reverification_decision(packet)
        elif first_failure:
            attach_staff4_audit_decision(packet, {}, first_failure)
        else:
            attach_staff4_full_phrase_decision(packet)
        packet = with_packaged_audit_fallback(packet)
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
        if source_crop_reverification:
            attach_staff4_source_crop_reverification_decision(packet)
        elif first_failure:
            attach_staff4_audit_decision(packet, {}, first_failure)
        else:
            attach_staff4_full_phrase_decision(packet)
        packet = with_packaged_audit_fallback(packet)
        existing_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
        state["staff4PhraseAuditLatest"] = packet
        return packet

    analysis = analyze_audio_clip(audio_path, current, clip_start, first_failure)
    packet["audioAnalysis"] = analysis
    if first_failure:
        packet["failedNotePitchDiagnostic"] = failed_note_pitch_diagnostic(audio_path, first_failure, clip_start)
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
    if source_crop_reverification:
        attach_staff4_source_crop_reverification_decision(packet)
    elif first_failure:
        attach_staff4_audit_decision(packet, analysis, first_failure)
    else:
        attach_staff4_full_phrase_decision(packet)
    packet["nextAction"] = (
        "Reverify the visible Staff 4 source crop against the transcription and paired audio before reopening this lane."
        if source_crop_reverification
        else
        "Lock this Staff 4 failure as rejected; do not extend the lane from this window."
        if packet.get("decision", {}).get("rejected")
        else "Do not extend the Staff 4 lane until this packet is accepted from exact audio and source-score evidence."
    )
    existing_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    state["staff4PhraseAuditLatest"] = packet
    return packet


def latest_staff4_phrase_audit_packet(state: dict[str, Any]) -> dict[str, Any]:
    packet = state.get("staff4PhraseAuditLatest") if isinstance(state.get("staff4PhraseAuditLatest"), dict) else {}
    if packet:
        return with_packaged_audit_fallback(packet)
    return {
        "version": STAFF4_AUDIT_VERSION,
        "status": "not_generated",
        "limit": "Run the Staff 4 phrase audit packet generator.",
    }


def latest_staff4_phrase_audit_packet_for_completion(state: dict[str, Any], completion: dict[str, Any]) -> dict[str, Any]:
    current = current_staff4_expansion(completion)
    if not current:
        current = source_crop_reverification_current(completion)
    if not current:
        return latest_staff4_phrase_audit_packet(state)
    current_packet_id = packet_id_for_current(current, staff4_audit_failure_for_completion(completion, current))
    packet = state.get("staff4PhraseAuditLatest") if isinstance(state.get("staff4PhraseAuditLatest"), dict) else {}
    if packet and str(packet.get("packetId") or "") == current_packet_id and packet.get("version") == STAFF4_AUDIT_VERSION:
        return with_packaged_audit_fallback(packet)
    packet_path = packet_json_path(current_packet_id)
    if packet_path.exists():
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            if isinstance(packet, dict) and packet.get("version") == STAFF4_AUDIT_VERSION:
                packet = with_packaged_audit_fallback(packet)
                state["staff4PhraseAuditLatest"] = packet
                return packet
        except (OSError, json.JSONDecodeError):
            pass
    packaged = load_packaged_audit_packet(current_packet_id)
    if packaged and packaged_artifacts_ready(current_packet_id):
        packaged = with_packaged_audit_fallback(packaged)
        state["staff4PhraseAuditLatest"] = packaged
        return packaged
    return {
        "version": STAFF4_AUDIT_VERSION,
        "status": "not_generated",
        "packetId": "",
        "currentPacketId": current_packet_id,
        "stalePacketId": str(packet.get("packetId") or "") if packet else "",
        "limit": (
            "Run the Staff 4 source-crop reverification packet before restoring any accepted Staff 4 anchor."
            if is_source_crop_reverification_current(current)
            else "Run the Staff 4 phrase audit packet generator for the current adjacent phrase window."
        ),
    }
