from __future__ import annotations

import re
from collections import Counter
from typing import Any


NOTE_CLASS = {
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
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_STEPS = (0, 2, 4, 5, 7, 9, 11, 12)
MINOR_STEPS = (0, 2, 3, 5, 7, 8, 10, 12)
ARPEGGIO_STEPS = {
    "major": (0, 4, 7, 12, 7, 4, 0),
    "minor": (0, 3, 7, 12, 7, 3, 0),
}
KEY_SIGNATURES = {
    ("C", "major"): {"label": "C major / no accidentals", "accidentalType": "none", "accidentals": []},
    ("G", "major"): {"label": "G major / 1 sharp", "accidentalType": "sharp", "accidentals": ["F#"]},
    ("D", "major"): {"label": "D major / 2 sharps", "accidentalType": "sharp", "accidentals": ["F#", "C#"]},
    ("A", "major"): {"label": "A major / 3 sharps", "accidentalType": "sharp", "accidentals": ["F#", "C#", "G#"]},
    ("E", "major"): {"label": "E major / 4 sharps", "accidentalType": "sharp", "accidentals": ["F#", "C#", "G#", "D#"]},
    ("F", "major"): {"label": "F major / 1 flat", "accidentalType": "flat", "accidentals": ["Bb"]},
    ("BB", "major"): {"label": "Bb major / 2 flats", "accidentalType": "flat", "accidentals": ["Bb", "Eb"]},
    ("A", "minor"): {"label": "A minor / no accidentals", "accidentalType": "none", "accidentals": []},
    ("E", "minor"): {"label": "E minor / 1 sharp", "accidentalType": "sharp", "accidentals": ["F#"]},
    ("G", "minor"): {"label": "G minor / 2 flats", "accidentalType": "flat", "accidentals": ["Bb", "Eb"]},
    ("D", "minor"): {"label": "D minor / 1 flat", "accidentalType": "flat", "accidentals": ["Bb"]},
}

PUBLIC_REFERENCE_SEEDS = [
    {
        "id": "yt-ref-g-major-scale",
        "query": "violin G major scale labeled slow one octave",
        "title": "G major scale",
        "materialType": "public_labeled_scale",
    },
    {
        "id": "yt-ref-g-major-arpeggio",
        "query": "violin G major arpeggio labeled slow",
        "title": "G major arpeggio",
        "materialType": "public_labeled_arpeggio",
    },
    {
        "id": "yt-ref-wieniawski-scherzo-tarantelle",
        "query": "Wieniawski Scherzo-Tarantelle violin labeled",
        "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
        "materialType": "public_labeled_piece",
    },
    {
        "id": "yt-ref-haydn-94-finale-violin-1",
        "query": "Haydn Symphony 94 finale violin 1 part labeled",
        "title": "Haydn Symphony No. 94, IV. Finale, Violin I part",
        "materialType": "public_labeled_orchestral_part",
    },
]


def compact_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9#b]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def display_root(raw: str, accidental: str = "") -> str:
    root = str(raw or "").strip().upper()[:1]
    acc = str(accidental or "").strip().lower()
    if acc in {"sharp", "#"}:
        return f"{root}#"
    if acc in {"flat", "b"}:
        return f"{root}b"
    return root


def normalized_root(root: str) -> str:
    return str(root or "").strip().upper().replace("B", "B", 1).replace("b", "B")


def key_signature(root: str, mode: str) -> dict[str, Any]:
    normalized = normalized_root(root)
    mode_value = str(mode or "").strip().lower()
    signature = KEY_SIGNATURES.get((normalized, mode_value), {})
    return {
        "tonic": root,
        "mode": mode_value,
        "accidentalType": signature.get("accidentalType") or "none",
        "accidentals": signature.get("accidentals") or [],
        "label": signature.get("label") or f"{root} {mode_value}",
    }


def note_name_from_midi(midi: int) -> str:
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[midi % 12]}{octave}"


def base_midi(root: str) -> int:
    normalized = normalized_root(root)
    pitch_class = NOTE_CLASS.get(normalized, NOTE_CLASS["G"])
    octave = 4
    midi = (octave + 1) * 12 + pitch_class
    if midi < 55:
        midi += 12
    return midi


def compact_counts(values: list[str], limit: int = 60) -> dict[str, int]:
    return dict(Counter(values).most_common(limit))


def ngrams(values: list[str], size: int, limit: int = 90) -> dict[str, int]:
    if len(values) < size:
        return {}
    grams = [" ".join(values[index : index + size]) for index in range(len(values) - size + 1)]
    return compact_counts(grams, limit)


def symbolic_fingerprint(midi_values: list[int]) -> dict[str, Any]:
    pitch_classes = [NOTE_NAMES[midi % 12] for midi in midi_values]
    intervals = [str(max(-12, min(12, midi_values[index + 1] - midi_values[index]))) for index in range(len(midi_values) - 1)]
    rhythms = ["4" for _ in midi_values]
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
        "firstNotes": [note_name_from_midi(midi) for midi in midi_values[:24]],
    }


def calibration_target(root: str, mode: str, material: str) -> dict[str, Any]:
    material_label = "scale" if material == "scale" else "arpeggio"
    title = f"{root} {mode} {material_label}"
    return {
        "status": "calibration_target_ready",
        "composer": "",
        "work": title,
        "movement": "",
        "part": "Solo violin",
        "keySignature": key_signature(root, mode),
        "scoreSource": "explicit title-labeled calibration source",
        "scoreUrl": "",
        "scorePdfUrl": "",
        "scoreAssetId": "",
        "scorePage": 0,
        "scoreBoxes": [],
        "referenceAudio": "needed",
        "alignmentGoal": f"Use the labeled {title} source as a pitch/rhythm calibration anchor.",
        "passageVocabulary": [title, f"{root} {mode}", material_label, "calibration anchor"],
    }


def calibration_anchor_for_item(item: dict[str, Any] | None) -> dict[str, Any]:
    item = item or {}
    title = str(item.get("sourceTitle") or item.get("sampleTitle") or item.get("title") or "").strip()
    compact = compact_text(title)
    if not compact:
        return {}

    match = re.search(r"\b([a-g])\s*(sharp|flat|#|b)?\s+(major|minor)\s+(scale|arpeggio)s?\b", compact)
    if match:
        root = display_root(match.group(1), match.group(2) or "")
        mode = match.group(3)
        material = match.group(4)
        material_label = "scale" if material == "scale" else "arpeggio"
        anchor_title = f"{root} {mode} {material_label}"
        return {
            "title": anchor_title,
            "sourceConfidence": "explicit_title_label",
            "sourceTitle": title,
            "sourceUrl": item.get("sourceUrl") or item.get("url") or "",
            "materialType": f"calibration_{material_label}",
            "referenceKind": "title_labeled_calibration",
            "referenceTarget": calibration_target(root, mode, material_label),
        }

    if "open string" in compact or "open strings" in compact:
        return {
            "title": "Open strings",
            "sourceConfidence": "explicit_title_label",
            "sourceTitle": title,
            "sourceUrl": item.get("sourceUrl") or item.get("url") or "",
            "materialType": "calibration_open_strings",
            "referenceKind": "title_labeled_calibration",
            "referenceTarget": {
                "status": "calibration_target_ready",
                "work": "Open strings",
                "part": "Solo violin",
                "keySignature": {"tonic": "", "mode": "", "accidentalType": "none", "accidentals": [], "label": "open strings"},
                "scoreSource": "explicit title-labeled calibration source",
                "referenceAudio": "needed",
                "alignmentGoal": "Use open-string source as violin tone and pitch-register calibration.",
                "passageVocabulary": ["G string", "D string", "A string", "E string", "open strings"],
            },
        }

    if "scherzo tarantelle" in compact or "scherzo tarantella" in compact:
        return {
            "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
            "sourceConfidence": "explicit_title_label",
            "sourceTitle": title,
            "sourceUrl": item.get("sourceUrl") or item.get("url") or "",
            "materialType": "title_labeled_piece",
            "referenceKind": "title_labeled_reference",
            "referenceTarget": {},
        }

    if "haydn" in compact and ("94" in compact or "surprise" in compact) and ("finale" in compact or "movement 4" in compact or "iv" in compact):
        return {
            "title": "Haydn Symphony No. 94, IV. Finale, Violin I part",
            "sourceConfidence": "explicit_title_label",
            "sourceTitle": title,
            "sourceUrl": item.get("sourceUrl") or item.get("url") or "",
            "materialType": "title_labeled_orchestral_part",
            "referenceKind": "title_labeled_reference",
            "referenceTarget": {},
        }

    return {}


def symbolic_reference_items() -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for root, mode in [("G", "major"), ("D", "major"), ("A", "major"), ("E", "minor"), ("G", "minor")]:
        base = base_midi(root)
        scale_steps = MAJOR_STEPS if mode == "major" else MINOR_STEPS
        scale_values = [base + step for step in scale_steps] + [base + step for step in reversed(scale_steps[:-1])]
        arpeggio_values = [base + step for step in ARPEGGIO_STEPS[mode]]
        for material, values in (("scale", scale_values), ("arpeggio", arpeggio_values)):
            title = f"{root} {mode} {material}"
            references.append(
                {
                    "transcriptionId": f"symbolic:{compact_text(title).replace(' ', '-')}",
                    "acceptedTitle": title,
                    "status": "transcribed",
                    "pipelineVersion": "symbolic-reference-v1",
                    "noteCount": len(values),
                    "fingerprint": symbolic_fingerprint(values),
                    "sourceTitle": f"public labeled violin reference: {title}",
                    "sourceUrl": "",
                    "referenceKind": "symbolic_calibration_reference",
                    "materialType": f"calibration_{material}",
                }
            )
    return references


def public_reference_training_state(state: dict[str, Any]) -> dict[str, Any]:
    corpus = state.get("referenceCorpus") if isinstance(state.get("referenceCorpus"), dict) else {}
    stored = corpus.get("publicYouTubeItems") if isinstance(corpus.get("publicYouTubeItems"), list) else []
    blockers = corpus.get("blockers") if isinstance(corpus.get("blockers"), list) else []
    return {
        "status": "metadata_indexed" if stored else "seed_queries_ready",
        "seedQueryCount": len(PUBLIC_REFERENCE_SEEDS),
        "storedItemCount": len(stored),
        "indexedAt": corpus.get("publicYouTubeIndexedAt") or "",
        "blockers": blockers,
        "seeds": PUBLIC_REFERENCE_SEEDS,
        "items": stored[:12],
        "method": "official YouTube Data API metadata search for public labeled violin references plus explicit calibration titles",
        "limit": "Public YouTube labels seed reference targets; audio fingerprints require a permitted media path before they become matching evidence.",
    }
