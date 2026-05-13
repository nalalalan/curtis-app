import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.daily_records import detected_note_series, score_reference_audit_for_pieces, score_sequence_matches_for_series
from backend.app.symbolic_scores import parse_musicxml_score, symbolic_score_audit, symbolic_score_from_target


NOTE_CLASS = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}


def midi_for_note(name):
    pitch = name[:-1]
    octave = int(name[-1])
    return (octave + 1) * 12 + NOTE_CLASS[pitch]


def note(name, start, end, confidence=0.92):
    return {
        "note": name,
        "midi": midi_for_note(name),
        "startSeconds": start,
        "endSeconds": end,
        "durationSeconds": end - start,
        "confidence": confidence,
    }


TEST_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <work><work-title>Symbolic Test Piece</work-title></work>
  <part-list>
    <score-part id="P1"><part-name>Violin</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><key><fifths>0</fifths></key><clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
      <note><pitch><step>B</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
    <measure number="2">
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
      <note><pitch><step>C</step><alter>1</alter><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


class SymbolicScoreTests(unittest.TestCase):
    def test_musicxml_parser_extracts_treble_pitch_classes_and_measures(self):
        score = parse_musicxml_score(TEST_MUSICXML, source_id="test-score")

        self.assertEqual(score["title"], "Symbolic Test Piece")
        self.assertEqual([item["note"] for item in score["notes"][:5]], ["D4", "G4", "B4", "A4", "E5"])
        self.assertEqual([item["pitchClass"] for item in score["notes"][:5]], ["D", "G", "B", "A", "E"])
        self.assertEqual(score["notes"][6]["note"], "C#5")
        self.assertEqual(score["notes"][0]["measure"], "1")
        self.assertEqual(score["notes"][5]["measure"], "2")

    def test_symbolic_score_phrase_match_requires_sequence_not_single_pitch(self):
        target = {
            "symbolicScore": {
                "sourceId": "test-score",
                "musicXml": TEST_MUSICXML,
                "source": "test MusicXML",
            }
        }
        one_note_series = detected_note_series(
            [
                {
                    "transcriptionId": "one-a",
                    "sampleId": "sample-a",
                    "sourceWindow": "*0-10",
                    "notes": [note("A4", 0.0, 0.4)],
                }
            ],
            max_series=None,
        )
        phrase_series = detected_note_series(
            [
                {
                    "transcriptionId": "phrase",
                    "sampleId": "sample-phrase",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("D4", 0.0, 0.2),
                        note("G4", 0.2, 0.4),
                        note("B4", 0.4, 0.6),
                        note("A4", 0.6, 0.8),
                        note("E5", 0.8, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        self.assertEqual(score_sequence_matches_for_series(one_note_series, [{"title": "Test", "score": target}]), [])
        matches = score_sequence_matches_for_series(phrase_series, [{"title": "Test", "score": target}])

        self.assertEqual(matches[0]["status"], "symbolic_score_phrase_match")
        self.assertEqual(matches[0]["minimumMatchedNoteRun"], 5)
        self.assertEqual(matches[0]["minimumDistinctPitchClasses"], 3)
        self.assertEqual(matches[0]["detectedPitchClassSequence"], "D G B A E")
        self.assertEqual(matches[0]["scorePitchClassSequence"], "D G B A E")
        self.assertTrue(matches[0]["scoreLocationVerified"])
        self.assertEqual(matches[0]["score"]["cropStatus"], "exact_score_location_verified")
        self.assertEqual(matches[0]["score"]["measureLabel"], "m. 1")
        self.assertTrue(matches[0]["score"]["imageUrl"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual([item["note"] for item in matches[0]["scoreMatchedNotes"]], ["D4", "G4", "B4", "A4", "E5"])

    def test_symbolic_phrase_match_rejects_repeated_single_pitch_and_wrong_order(self):
        target = {"symbolicScore": {"musicXml": TEST_MUSICXML}}
        repeated = detected_note_series(
            [
                {
                    "transcriptionId": "repeated",
                    "sampleId": "sample-repeated",
                    "sourceWindow": "*0-10",
                    "notes": [note("D4", index * 0.1, index * 0.1 + 0.05) for index in range(8)],
                }
            ],
            max_series=None,
        )
        wrong_order = detected_note_series(
            [
                {
                    "transcriptionId": "wrong-order",
                    "sampleId": "sample-wrong",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("D4", 0.0, 0.2),
                        note("B4", 0.2, 0.4),
                        note("G4", 0.4, 0.6),
                        note("A4", 0.6, 0.8),
                        note("E5", 0.8, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        self.assertEqual(score_sequence_matches_for_series(repeated, [{"title": "Test", "score": target}]), [])
        self.assertEqual(score_sequence_matches_for_series(wrong_order, [{"title": "Test", "score": target}]), [])

    def test_symbolic_score_audit_reports_missing_until_real_score_notes_exist(self):
        self.assertEqual(symbolic_score_audit({})["status"], "symbolic_score_missing")
        audit = symbolic_score_audit({"symbolicScore": {"musicXml": TEST_MUSICXML, "sourceId": "test-score"}})
        self.assertEqual(audit["status"], "symbolic_score_ready")
        self.assertEqual(audit["symbolicScoreNoteCount"], 8)
        self.assertEqual(audit["symbolicScoreSourceId"], "test-score")
        piece_audit = score_reference_audit_for_pieces([{"score": {"symbolicScore": {"musicXml": TEST_MUSICXML}}}])
        self.assertEqual(piece_audit["status"], "symbolic_score_ready")
        self.assertEqual(piece_audit["exactScoreLocationCount"], 0)

    def test_symbolic_score_can_load_local_musicxml_path(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "score.musicxml"
            path.write_text(TEST_MUSICXML, encoding="utf-8")
            score = symbolic_score_from_target({"symbolicScore": {"musicXmlPath": str(path), "sourceId": "local-score"}})

        self.assertEqual(score["sourceId"], "local-score")
        self.assertEqual([item["pitchClass"] for item in score["notes"][:5]], ["D", "G", "B", "A", "E"])


if __name__ == "__main__":
    unittest.main()
