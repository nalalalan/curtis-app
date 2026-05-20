from __future__ import annotations

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


def requested_score_copy_records() -> list[dict[str, Any]]:
    """Training-only source-copy packets for notation-copy review.

    These records are intentionally not practice evidence. They give Curtis a
    controlled source/copy lane for exact visual notation copying across varied
    keys, accidentals, durations, and repertoire names while real source crops
    are acquired separately.
    """

    records: list[dict[str, Any]] = []
    for index, piece in enumerate(REQUESTED_SCORE_COPY_REPERTOIRE, start=1):
        title = str(piece["title"])
        notes = list(piece["notes"])
        abc = str(piece["abc"])
        records.append(
            {
                "practiceDay": "source-copy",
                "trainingOnly": True,
                "pieces": [
                    {
                        "title": title,
                        "sourceTitle": title,
                        "score": {
                            "scoreAssetId": f"source-copy-{index:02d}",
                            "scoreSource": "notation-copy training source",
                            "keySignature": piece["keySignature"],
                            "symbolicScore": {
                                "title": title,
                                "sourceSnippets": [
                                    {
                                        "measureLabel": "source-copy packet",
                                        "sourceStatus": "training_fixture_pending_original_crop",
                                        "sourceReviewKind": "notation_copy_training_fixture",
                                        "visibleScoreExactNoteSequence": notes,
                                        "sourceNotationAbc": abc,
                                        "copyNotationAbc": abc,
                                        "notationCopyAspects": NOTATION_COPY_ASPECTS,
                                        "sourcePieceTrainingOnly": True,
                                        "originalScoreSnippet": False,
                                        "sourceImageRequiredForOriginalScore": True,
                                        "status": "notation_copy_training_only",
                                    }
                                ],
                            },
                        },
                    }
                ],
            }
        )
    return records
