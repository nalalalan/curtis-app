from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .corrections import wieniawski_reference_target
from .long_phrase_truth import exact_midi_phrase_gate, note_midi_sequence
from .symbolic_scores import symbolic_score_from_target


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRUTH_PATH = PROJECT_ROOT / "assets" / "truth" / "curtis-long-phrase-gold.json"


def load_long_phrase_truth(path: str | Path | None = None) -> dict[str, Any]:
    truth_path = Path(path) if path else DEFAULT_TRUTH_PATH
    if not truth_path.is_absolute():
        truth_path = PROJECT_ROOT / truth_path
    try:
        data = json.loads(truth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def source_notes_for_truth_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    target_name = str(source.get("target") or source.get("sourceTarget") or "").strip()
    if target_name != "wieniawski_reference_target":
        return []
    score = symbolic_score_from_target(wieniawski_reference_target())
    notes = score.get("notes") if isinstance(score.get("notes"), list) else []
    return [note for note in notes if isinstance(note, dict)]


def truth_phrase_notes(phrase: dict[str, Any]) -> list[dict[str, Any]]:
    notes = phrase.get("notes") if isinstance(phrase.get("notes"), list) else []
    if notes:
        return [note for note in notes if isinstance(note, dict)]
    exact = phrase.get("sequence") if isinstance(phrase.get("sequence"), list) else []
    midi = phrase.get("midiSequence") if isinstance(phrase.get("midiSequence"), list) else []
    out: list[dict[str, Any]] = []
    for index, value in enumerate(exact):
        note = {"note": str(value)}
        if index < len(midi):
            note["midi"] = midi[index]
        out.append(note)
    return out


def verify_long_phrase_truth_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest = load_long_phrase_truth(path)
    sources = manifest.get("sources") if isinstance(manifest.get("sources"), list) else []
    positives = manifest.get("positiveSourcePhrases") if isinstance(manifest.get("positiveSourcePhrases"), list) else []
    rejected = manifest.get("rejectedRegressionPhrases") if isinstance(manifest.get("rejectedRegressionPhrases"), list) else []
    source_by_id = {str(source.get("id") or ""): source for source in sources if isinstance(source, dict)}
    source_results: list[dict[str, Any]] = []
    source_notes_by_id: dict[str, list[dict[str, Any]]] = {}

    for source_id, source in source_by_id.items():
        notes = source_notes_for_truth_source(source)
        source_notes_by_id[source_id] = notes
        expected_midi = [int(value) for value in source.get("midiSequence", []) if str(value).strip()]
        actual_midi = note_midi_sequence(notes)
        reference_start = int(source.get("referenceStart") or 0)
        reference_end = int(source.get("referenceEnd") or (reference_start + len(expected_midi)))
        actual_slice = actual_midi[reference_start:reference_end]
        exact_match = bool(expected_midi) and actual_slice == expected_midi
        source_results.append(
            {
                "id": source_id,
                "status": "verified_source_excerpt" if exact_match else "source_excerpt_mismatch",
                "expectedNoteCount": len(expected_midi),
                "actualNoteCount": len(actual_midi),
                "referenceStart": reference_start,
                "referenceEnd": reference_end,
                "midiSequence": actual_slice or actual_midi[: len(expected_midi) or len(actual_midi)],
            }
        )

    positive_results: list[dict[str, Any]] = []
    for phrase in positives:
        if not isinstance(phrase, dict):
            continue
        source_id = str(phrase.get("sourceId") or "")
        phrase_notes = truth_phrase_notes(phrase)
        source_notes = source_notes_by_id.get(source_id, [])
        gate = exact_midi_phrase_gate(
            phrase_notes,
            source_notes,
            audio_agreed=True,
            min_exact_notes=int(phrase.get("minimumExactNotes") or 5),
            require_full_query=True,
        )
        positive_results.append(
            {
                "id": str(phrase.get("id") or ""),
                "sourceId": source_id,
                "status": "source_phrase_verified" if gate.get("accepted") else str(gate.get("status") or "source_phrase_rejected"),
                "noteCount": len(phrase_notes),
                "bestOverlap": int(gate.get("bestOverlap") or 0),
                "midiSequence": gate.get("queryMidiSequence") or [],
                "liveAccepted": bool(phrase.get("liveAccepted")),
            }
        )

    rejected_results: list[dict[str, Any]] = []
    for phrase in rejected:
        if not isinstance(phrase, dict):
            continue
        source_id = str(phrase.get("sourceId") or "")
        phrase_notes = truth_phrase_notes(phrase)
        source_notes = source_notes_by_id.get(source_id, [])
        gate = exact_midi_phrase_gate(
            phrase_notes,
            source_notes,
            audio_agreed=bool(phrase.get("audioAgreed", True)),
            min_exact_notes=int(phrase.get("minimumExactNotes") or 5),
            require_full_query=True,
        )
        blocked = not bool(gate.get("accepted"))
        rejected_results.append(
            {
                "id": str(phrase.get("id") or ""),
                "sourceId": source_id,
                "status": "blocked" if blocked else "unexpectedly_accepted",
                "noteCount": len(phrase_notes),
                "bestOverlap": int(gate.get("bestOverlap") or 0),
                "gateStatus": str(gate.get("status") or ""),
                "midiSequence": gate.get("queryMidiSequence") or [],
            }
        )

    source_verified = sum(1 for item in source_results if item.get("status") == "verified_source_excerpt")
    positive_verified = sum(1 for item in positive_results if item.get("status") == "source_phrase_verified")
    rejected_blocked = sum(1 for item in rejected_results if item.get("status") == "blocked")
    live_accepted = sum(1 for item in positive_results if item.get("liveAccepted"))
    manifest_ok = bool(sources) and source_verified == len(source_results) and positive_verified == len(positive_results) and rejected_blocked == len(rejected_results)
    return {
        "version": "curtis_long_phrase_truth_v1",
        "status": "verified" if manifest_ok else "needs_review",
        "schema": str(manifest.get("schema") or ""),
        "path": str((Path(path) if path else DEFAULT_TRUTH_PATH).as_posix()),
        "sourceCount": len(source_results),
        "sourceVerifiedCount": source_verified,
        "positiveSourcePhraseCount": len(positive_results),
        "positiveSourcePhraseVerifiedCount": positive_verified,
        "rejectedRegressionPhraseCount": len(rejected_results),
        "rejectedRegressionBlockedCount": rejected_blocked,
        "liveAcceptedPhraseCount": live_accepted,
        "truthManifestItemCount": len(source_results) + len(positive_results) + len(rejected_results),
        "minimumAcceptedEvidenceRule": str(manifest.get("minimumAcceptedEvidenceRule") or ""),
        "sourceResults": source_results,
        "positiveSourcePhraseResults": positive_results,
        "rejectedRegressionResults": rejected_results,
    }
