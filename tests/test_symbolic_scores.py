import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.daily_records import detected_note_series, score_reference_audit_for_pieces, score_sequence_matches_for_series
from backend.app.corrections import wieniawski_reference_target
from backend.app.symbolic_scores import (
    parse_musicxml_score,
    score_map_candidate_audit,
    symbolic_score_audit,
    symbolic_score_from_target,
)


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


def note(name, start, end, confidence=0.92, **extra):
    return {
        "note": name,
        "midi": midi_for_note(name),
        "startSeconds": start,
        "endSeconds": end,
        "durationSeconds": end - start,
        "confidence": confidence,
        "audioAgreement": True,
        "agreementSourceCount": 1,
        "agreementSources": ["pitch_hysteresis"],
        "detectorSource": "spectral_onset",
        **extra,
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
        self.assertFalse(matches[0]["scoreLocationVerified"])
        self.assertEqual(matches[0]["score"]["cropStatus"], "actual_source_snippet_pending")
        self.assertEqual(matches[0]["score"]["measureLabel"], "m. 1")
        self.assertEqual(matches[0]["score"]["imageUrl"], "")
        self.assertTrue(matches[0]["score"]["generatedNotationImageUrl"].startswith("data:image/svg+xml;base64,"))
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

    def test_written_flats_keep_score_staff_position_while_matching_pitch_class(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Violin</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><key><fifths>-2</fifths></key><clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""
        score = parse_musicxml_score(xml, source_id="flat-test")

        self.assertEqual(score["notes"][0]["note"], "Bb4")
        self.assertEqual(score["notes"][0]["pitchClass"], "A#")

    def test_wieniawski_symbolic_opening_motif_is_source_ready(self):
        target = wieniawski_reference_target()
        score = symbolic_score_from_target(target)
        audit = symbolic_score_audit(target)
        candidate_audit = score_map_candidate_audit(target)

        self.assertEqual(audit["status"], "symbolic_score_ready")
        self.assertEqual(audit["symbolicScoreNoteCount"], 7)
        self.assertEqual(audit["symbolicScoreSourceSnippetCount"], 0)
        self.assertEqual(candidate_audit["status"], "score_map_candidates_ready")
        self.assertGreaterEqual(candidate_audit["scoreMapCandidateGlyphCount"], 1)
        self.assertGreaterEqual(candidate_audit["scoreMapCandidateStaffCount"], 1)
        self.assertGreaterEqual(candidate_audit["scoreMapNoteHypothesisCount"], 1)
        self.assertGreaterEqual(candidate_audit["scoreMapNoteHypothesisStaffCount"], 1)
        self.assertGreaterEqual(candidate_audit["scoreMapReviewPacketCount"], 1)
        self.assertFalse(candidate_audit["scoreMapCandidatesAccepted"])
        self.assertEqual(
            [item["note"] for item in score["notes"]],
            ["D6", "C6", "Bb5", "D6", "C6", "Bb5", "D6"],
        )
        self.assertEqual([item["pitchClass"] for item in score["notes"]], ["D", "C", "A#", "D", "C", "A#", "D"])

    def test_wieniawski_symbolic_measure_can_match_four_note_source_sequence(self):
        target = wieniawski_reference_target()
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-source-motif",
                    "sampleId": "sample-source-motif",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("D6", 0.0, 0.25),
                        note("C6", 0.25, 0.5),
                        note("A#5", 0.5, 0.75),
                        note("D6", 0.75, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        matches = score_sequence_matches_for_series(
            series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertEqual(matches[0]["status"], "symbolic_score_phrase_match")
        self.assertEqual(matches[0]["minimumMatchedNoteRun"], 4)
        self.assertEqual(matches[0]["minimumDistinctPitchClasses"], 3)
        self.assertEqual(matches[0]["detectedPitchClassSequence"], "D C A# D")
        self.assertEqual(matches[0]["scorePitchClassSequence"], "D C A# D")
        self.assertEqual([item["note"] for item in matches[0]["scoreMatchedNotes"]], ["D6", "C6", "Bb5", "D6"])
        self.assertFalse(matches[0]["scoreVisualAgreement"])
        self.assertEqual(matches[0]["scoreVisualAgreementBasis"], "actual_source_snippet_required")
        self.assertEqual(matches[0]["score"]["imageUrl"], "")
        self.assertTrue(matches[0]["score"]["generatedNotationImageUrl"].startswith("data:image/svg+xml;base64,"))

    def test_wieniawski_lower_octave_opening_map_is_rejected(self):
        target = wieniawski_reference_target()
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-lower-octave-source-motif",
                    "sampleId": "sample-lower-octave-source-motif",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("D5", 0.0, 0.25),
                        note("C5", 0.25, 0.5),
                        note("A#4", 0.5, 0.75),
                        note("D5", 0.75, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        matches = score_sequence_matches_for_series(
            series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertFalse(any(match["status"] == "symbolic_score_phrase_match" for match in matches))

    def test_wieniawski_symbolic_opening_rejects_phrase_when_one_note_fails_audio_gate(self):
        target = wieniawski_reference_target()
        weak_c = note("C6", 0.4, 0.6, audioAgreement=False, agreementSourceCount=0, agreementSources=[])
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-long-phrase",
                    "sampleId": "sample-long-phrase",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("A#5", 0.0, 0.2),
                        note("D6", 0.2, 0.4),
                        weak_c,
                        note("A#5", 0.6, 0.8),
                        note("D6", 0.8, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        matches = score_sequence_matches_for_series(
            series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertFalse(any(match["status"] == "symbolic_score_phrase_match" for match in matches))

    def test_hidden_transition_candidate_can_match_score_when_audio_gate_passes(self):
        target = wieniawski_reference_target()
        agreed = {
            "audioAgreement": True,
            "agreementSourceCount": 1,
            "agreementSources": ["spectral_onset"],
            "detectorSource": "yin_transition_trace",
        }
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-transition-candidate",
                    "sampleId": "sample-transition-candidate",
                    "sourceWindow": "*0-10",
                    "status": "failed_pitch_collapse",
                    "notes": [note("D6", index * 0.1, index * 0.1 + 0.08) for index in range(20)],
                    "scoreMatchCandidateNotes": [
                        note("A#5", 0.0, 0.2, **agreed),
                        note("D6", 0.2, 0.4, **agreed),
                        note("C6", 0.4, 0.6, **agreed),
                        note("A#5", 0.6, 0.8, **agreed),
                        note("D6", 0.8, 1.0, **agreed),
                    ],
                }
            ],
            max_series=None,
        )

        candidate_series = [item for item in series if item.get("candidateOnly")]
        matches = score_sequence_matches_for_series(
            candidate_series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertTrue(candidate_series)
        self.assertEqual(matches[0]["status"], "symbolic_score_phrase_match")
        self.assertEqual(matches[0]["matchedNoteRun"], 5)
        self.assertEqual([item["note"] for item in matches[0]["displayDetectedNotes"]], ["Bb5", "D6", "C6", "Bb5", "D6"])
        self.assertFalse(matches[0]["scoreVisualAgreement"])
        self.assertEqual(matches[0]["score"]["cropStatus"], "actual_source_snippet_pending")

    def test_hidden_transition_candidate_rejects_unagreed_fast_note(self):
        target = wieniawski_reference_target()
        agreed = {
            "audioAgreement": True,
            "agreementSourceCount": 1,
            "agreementSources": ["spectral_onset"],
            "detectorSource": "yin_transition_trace",
        }
        weak = {
            "audioAgreement": False,
            "agreementSourceCount": 0,
            "agreementSources": [],
            "detectorSource": "yin_transition_trace",
        }
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-transition-candidate",
                    "sampleId": "sample-transition-candidate",
                    "sourceWindow": "*0-10",
                    "status": "failed_pitch_collapse",
                    "scoreMatchCandidateNotes": [
                        note("A#5", 0.0, 0.2, **agreed),
                        note("D6", 0.2, 0.4, **agreed),
                        note("C6", 0.4, 0.6, **weak),
                        note("A#5", 0.6, 0.8, **agreed),
                        note("D6", 0.8, 1.0, **agreed),
                    ],
                }
            ],
            max_series=None,
        )

        candidate_series = [item for item in series if item.get("candidateOnly")]
        matches = score_sequence_matches_for_series(
            candidate_series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertTrue(candidate_series)
        self.assertEqual(candidate_series[0]["candidateAudioRejectedNoteCount"], 1)
        self.assertFalse(any(match["status"] == "symbolic_score_phrase_match" for match in matches))

    def test_symbolic_match_rejects_uncertain_octave_corrected_candidate(self):
        target = wieniawski_reference_target()
        uncertain = note("C6", 0.2, 0.4)
        uncertain["uncertain"] = True
        uncertain["rawNote"] = "C5"
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-uncertain-candidate",
                    "sampleId": "sample-uncertain-candidate",
                    "sourceWindow": "*0-10",
                    "scoreMatchCandidateNotes": [
                        note("D6", 0.0, 0.2),
                        uncertain,
                        note("A#5", 0.6, 0.8),
                        note("D6", 0.8, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        matches = score_sequence_matches_for_series(
            series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertFalse(any(match["status"] == "symbolic_score_phrase_match" for match in matches))

    def test_wieniawski_symbolic_match_rejects_pitch_class_only_octave_mismatch(self):
        target = wieniawski_reference_target()
        series = detected_note_series(
            [
                {
                    "transcriptionId": "wieniawski-wrong-octave",
                    "sampleId": "sample-wrong-octave",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("A#4", 0.0, 0.2),
                        note("D4", 0.2, 0.4),
                        note("C4", 0.4, 0.6),
                        note("A#4", 0.6, 0.8),
                        note("D4", 0.8, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        matches = score_sequence_matches_for_series(
            series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )

        self.assertFalse(any(match["status"] == "symbolic_score_phrase_match" for match in matches))
        self.assertFalse(any(match.get("scoreVisualAgreement") for match in matches))

    def test_rejected_wieniawski_d_bflat_g_d_source_sequence_no_longer_matches(self):
        target = wieniawski_reference_target()
        series = detected_note_series(
            [
                {
                    "transcriptionId": "old-wrong-source-motif",
                    "sampleId": "sample-old-wrong-source-motif",
                    "sourceWindow": "*0-10",
                    "notes": [
                        note("D4", 0.0, 0.25),
                        note("A#4", 0.25, 0.5),
                        note("G4", 0.5, 0.75),
                        note("D4", 0.75, 1.0),
                    ],
                }
            ],
            max_series=None,
        )

        matches = score_sequence_matches_for_series(
            series,
            [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16", "score": target}],
        )
        self.assertFalse(any(match["status"] == "symbolic_score_phrase_match" for match in matches))
        self.assertTrue(all(match.get("scoreLocationStatus") == "exact_score_location_pending" for match in matches))


if __name__ == "__main__":
    unittest.main()
