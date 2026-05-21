from __future__ import annotations

import json
from pathlib import Path
from typing import Any


NOTATION_COPY_ASPECTS = [
    "pitches",
    "octaves",
    "accidentals",
    "key_signature",
    "durations",
    "rests",
    "beams",
    "tuplets",
    "stem_directions",
    "notehead_shapes",
    "spacing",
    "slurs_ties",
    "source_range",
]

WIENIAWSKI_SOURCE_URL = "https://imslp.org/wiki/Scherzo_tarantelle%2C_Op.16_%28Wieniawski%2C_Henri%29"
WIENIAWSKI_SOURCE_PDF = "assets/score/wieniawski-scherzo-tarantelle-solo-imslp.pdf"
SOURCE_SCORE_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "assets" / "score" / "original" / "source-score-library.json"

ORIGINAL_SCORE_SOURCE_SNIPPETS = [
    {
        "id": f"wieniawski-imslp-p2-staff{staff_id}",
        "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
        "source": "IMSLP public-domain solo violin part",
        "sourceUrl": WIENIAWSKI_SOURCE_URL,
        "sourcePdfLocalPath": WIENIAWSKI_SOURCE_PDF,
        "sourcePdfPage": 2,
        "staffId": staff_id,
        "label": f"page 2 / staff {staff_id}",
        "imageUrl": f"/assets/score/original/wieniawski-scherzo-tarantelle-imslp-p2-staff{staff_id}.png",
        "originalScoreSnippet": True,
        "sourceImageRequiredForOriginalScore": False,
        "trainingOnly": False,
        "acceptedPracticeEvidence": False,
    }
    for staff_id in range(1, 7)
]


REQUESTED_SCORE_COPY_REPERTOIRE = [
    {
        "title": "Haydn Symphony No. 94, IV, Violin I",
        "keySignature": {"accidentalType": "sharp", "accidentals": ["F#"]},
        "notes": ["D5", "G5", "B5", "A5", "G5", "F#5", "E5", "D5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:G clef=treble\nD2 G B A | G F E D2 |",
    },
    {
        "title": 'Schubert Symphony No. 4 "Tragic", IV, Violin I',
        "keySignature": {"accidentalType": "flat", "accidentals": ["Bb", "Eb"]},
        "notes": ["G5", "F#5", "G5", "Bb5", "A5", "G5", "F#5", "G5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:Gm clef=treble\n(3G^FG B2 | A G ^F G |",
    },
    {
        "title": "Schubert Symphony No. 3, I, Violin I",
        "keySignature": {"accidentalType": "sharp", "accidentals": ["F#", "C#"]},
        "notes": ["D5", "F#5", "A5", "D6", "C#6", "B5", "A5", "F#5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:D clef=treble\nD F A d | c B A F |",
    },
    {
        "title": "Schubert Symphony No. 3, IV, Violin I",
        "keySignature": {"accidentalType": "sharp", "accidentals": ["F#", "C#"]},
        "notes": ["A4", "B4", "C#5", "D5", "E5", "F#5", "G5", "A5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:D clef=treble\nA, B, C D | E F =G A |",
    },
    {
        "title": "Schubert Symphony No. 5, I, Violin I",
        "keySignature": {"accidentalType": "flat", "accidentals": ["Bb", "Eb"]},
        "notes": ["Bb4", "D5", "F5", "Bb5", "A5", "G5", "F5", "D5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:Bb clef=treble\nB,4 | D F B A | G F D2 |",
    },
    {
        "title": "Schubert Symphony No. 5, IV, Violin I",
        "keySignature": {"accidentalType": "flat", "accidentals": ["Bb", "Eb"]},
        "notes": ["F5", "G5", "A5", "Bb5", "C6", "Bb5", "A5", "G5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:Bb clef=treble\nF G A B | c B A G |",
    },
    {
        "title": "Paganini Violin Concerto No. 1, I, Solo violin",
        "keySignature": {"accidentalType": "sharp", "accidentals": ["F#", "C#"]},
        "notes": ["D6", "E6", "F#6", "G6", "A6", "F#6", "D6", "A5"],
        "abc": "X:1\nM:2/4\nL:1/16\nK:D clef=treble\nd e f g a f d A |",
    },
    {
        "title": "Paganini Violin Concerto No. 2, I, Solo violin",
        "keySignature": {"accidentalType": "sharp", "accidentals": ["F#", "C#"]},
        "notes": ["F#5", "B5", "D6", "C#6", "B5", "A5", "G5", "F#5"],
        "abc": "X:1\nM:2/4\nL:1/16\nK:Bm clef=treble\nF B d c B A =G F |",
    },
    {
        "title": "Paganini Moto Perpetuo, Op. 11, Solo violin",
        "keySignature": {"accidentalType": "natural", "accidentals": []},
        "notes": ["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6"],
        "abc": "X:1\nM:2/4\nL:1/16\nK:C clef=treble\nC D E F G A B c |",
    },
    {
        "title": "Wieniawski Etude-Caprice, Op. 18 No. 4",
        "keySignature": {"accidentalType": "natural", "accidentals": []},
        "notes": ["E5", "A5", "C6", "B5", "A5", "E5", "C5", "A4"],
        "abc": "X:1\nM:3/4\nL:1/8\nK:Am clef=treble\nE A c B A E C A, |",
    },
    {
        "title": "Wieniawski Etude-Caprice, Op. 18 No. 3",
        "keySignature": {"accidentalType": "flat", "accidentals": ["Bb"]},
        "notes": ["A4", "D5", "F5", "A5", "G5", "F5", "E5", "D5"],
        "abc": "X:1\nM:3/4\nL:1/8\nK:Dm clef=treble\nA, D F A G F E D |",
    },
    {
        "title": "Mozart Le nozze di Figaro Overture, Violin I",
        "keySignature": {"accidentalType": "sharp", "accidentals": ["F#", "C#"]},
        "notes": ["D5", "A4", "D5", "F#5", "A5", "D6", "A5", "F#5"],
        "abc": "X:1\nM:4/4\nL:1/8\nK:D clef=treble\nD A, D F z A d A F |",
    },
    {
        "title": "Schumann Symphony No. 1, IV, Violin I",
        "keySignature": {"accidentalType": "flat", "accidentals": ["Bb", "Eb"]},
        "notes": ["Bb4", "C5", "D5", "Eb5", "F5", "G5", "A5", "Bb5"],
        "abc": "X:1\nM:2/4\nL:1/8\nK:Bb clef=treble\nB, C D E | F G A B |",
    },
]


def requested_original_score_snippets() -> list[dict[str, Any]]:
    """Real scanned source-score images, not generated notation.

    These are source material only. They are allowed to display as original
    score sources because they are either cropped from the vendored IMSLP PDF
    or stored as rendered crops from selected IMSLP PDFs. They are not
    accepted practice evidence and do not imply audio alignment.
    """

    snippets = [dict(item) for item in ORIGINAL_SCORE_SOURCE_SNIPPETS]
    if SOURCE_SCORE_LIBRARY_PATH.exists():
        try:
            library = json.loads(SOURCE_SCORE_LIBRARY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            library = []
        if isinstance(library, list):
            for item in library:
                if isinstance(item, dict):
                    snippets.append(dict(item))
    return snippets


def _requested_source_library() -> list[dict[str, Any]]:
    if not SOURCE_SCORE_LIBRARY_PATH.exists():
        return []
    try:
        library = json.loads(SOURCE_SCORE_LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [dict(item) for item in library if isinstance(item, dict)]


def _requested_source_by_title() -> dict[str, dict[str, Any]]:
    return {str(item.get("pieceTitle") or "").strip(): item for item in _requested_source_library()}


def _is_violin_only_review_source(source_entry: dict[str, Any]) -> bool:
    """Return True only for source crops that are safe to show as review pairs.

    The score-transcription lane is for copying the displayed violin source
    into notation. Broad score-library material can still be useful as a PDF
    source, but full scores, piano reductions, accompaniment systems, or
    multi-player book sources are not valid accept/reject cards for Alan.
    """

    label_text = " ".join(
        str(source_entry.get(key) or "")
        for key in ("sourceFileLabel", "requestedPart", "label", "sourcePdfUrl", "source")
    ).lower()
    blocked = (
        "complete score",
        "full score",
        "piano",
        "accompaniment",
        "score and",
        "orchestra",
        "orchestral",
        "2_violins",
        "2 violins",
        "two violins",
        "book 1",
        "book 2",
        "etudes 1-4",
        "etudes 5-8",
    )
    if any(token in label_text for token in blocked):
        return False
    source_file_label = str(source_entry.get("sourceFileLabel") or "").strip().lower()
    requested_part = str(source_entry.get("requestedPart") or "").strip().lower()
    allowed_labels = ("violins i", "violin i", "violin part", "solo violin")
    return any(token in source_file_label for token in allowed_labels) or any(
        token in requested_part for token in allowed_labels
    )


def requested_score_copy_records() -> list[dict[str, Any]]:
    """Training-only score-transcription packets for source-score review.

    These records are intentionally not practice evidence. Strict
    score-transcription packets still carry a verified note sequence from the
    same visible source crop. When that is unavailable, Curtis may expose a
    best-effort score-transcription packet so Alan can accept/reject it as
    training data. Best-effort packets never become accepted score evidence by
    themselves.
    """

    records: list[dict[str, Any]] = []
    source_by_title = _requested_source_by_title()
    for index, piece in enumerate(REQUESTED_SCORE_COPY_REPERTOIRE, start=1):
        title = str(piece["title"])
        notes = list(piece["notes"])
        abc = str(piece["abc"])
        source_entry = source_by_title.get(title, {})
        source_image = str(source_entry.get("reviewImageUrl") or source_entry.get("imageUrl") or "").strip()
        source_ready = bool(source_entry.get("originalScoreSnippet") is True and source_image)
        if not _is_violin_only_review_source(source_entry):
            continue
        verified_source_notes = source_entry.get("verifiedSourceNoteSequence")
        strict_source_match = bool(
            source_ready
            and isinstance(verified_source_notes, list)
            and [str(note).strip() for note in verified_source_notes if str(note).strip()] == notes
        )
        best_effort_source_match = bool(source_ready and source_image)
        if not (strict_source_match or best_effort_source_match):
            continue
        source_label = str(source_entry.get("label") or source_entry.get("sourceFileLabel") or "source PDF crop").strip()
        source_status = "original_score_transcription_training" if strict_source_match else "best_effort_score_transcription_review"
        source_review_kind = (
            "original_score_transcription_training"
            if strict_source_match
            else "best_effort_source_score_transcription_training"
        )
        records.append(
            {
                "practiceDay": "score-transcription",
                "trainingOnly": True,
                "bestEffortScoreTranscription": not strict_source_match,
                "pieces": [
                    {
                        "title": title,
                        "sourceTitle": title,
                        "sourceUrl": str(source_entry.get("sourceUrl") or "").strip(),
                        "score": {
                            "scoreAssetId": f"source-copy-{index:02d}",
                            "scoreSource": str(source_entry.get("source") or "score-transcription training source"),
                            "scoreUrl": str(source_entry.get("sourceUrl") or ""),
                            "scorePdfUrl": str(source_entry.get("sourcePdfUrl") or ""),
                            "keySignature": piece["keySignature"],
                            "symbolicScore": {
                                "title": title,
                                "source": str(source_entry.get("source") or ""),
                                "sourcePdfLocalPath": str(source_entry.get("sourcePdfLocalPath") or ""),
                                "sourceSnippets": [
                                    {
                                        "measureLabel": source_label if source_ready else "score-transcription packet",
                                        "label": source_label if source_ready else "score-transcription packet",
                                        "sourceStatus": source_status,
                                        "sourceReviewKind": source_review_kind,
                                        "visibleScoreExactNoteSequence": notes,
                                        "verifiedSourceNoteSequence": notes if strict_source_match else [],
                                        "imageUrl": source_image,
                                        "scoreImageUrl": source_image,
                                        "sourceReviewImageUrl": source_image,
                                        "sourceUrl": str(source_entry.get("sourceUrl") or ""),
                                        "sourcePdfUrl": str(source_entry.get("sourcePdfUrl") or ""),
                                        "sourcePdfLocalPath": str(source_entry.get("sourcePdfLocalPath") or ""),
                                        "sourcePdfPage": source_entry.get("sourcePdfPage"),
                                        "sourceFileLabel": str(source_entry.get("sourceFileLabel") or ""),
                                        "sourceKind": str(source_entry.get("sourceKind") or ""),
                                        "reviewCropKind": str(source_entry.get("reviewCropKind") or ""),
                                        "reviewCropSourceImageUrl": str(source_entry.get("reviewCropSourceImageUrl") or ""),
                                        "reviewCropBox": source_entry.get("reviewCropBox") or [],
                                        "sourceNotationAbc": abc,
                                        "copyNotationAbc": abc,
                                        "notationCopyAspects": NOTATION_COPY_ASPECTS,
                                        "sourcePieceTrainingOnly": True,
                                        "bestEffortScoreTranscription": not strict_source_match,
                                        "sourceCopyReviewReady": strict_source_match,
                                        "sourceCopyBestEffortReviewReady": not strict_source_match,
                                        "originalScoreSnippet": source_ready,
                                        "sourceImageRequiredForOriginalScore": not source_ready,
                                        "status": source_status,
                                    }
                                ],
                            },
                        },
                    }
                ],
            }
        )
    return records
