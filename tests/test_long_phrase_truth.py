import unittest

from backend.app.corrections import wieniawski_reference_target
from backend.app.gold_truth import verify_long_phrase_truth_manifest
from backend.app.long_phrase_truth import exact_midi_phrase_gate, note_midi_sequence
from backend.app.symbolic_scores import symbolic_score_from_target


def detected_note(name, midi, start=0.0, audio=True):
    return {
        "note": name,
        "midi": midi,
        "startSeconds": start,
        "endSeconds": start + 0.12,
        "durationSeconds": 0.12,
        "confidence": 0.94,
        "audioAgreement": audio,
        "agreementSourceCount": 1 if audio else 0,
        "agreementSources": ["spectral_onset"] if audio else [],
    }


class LongPhraseTruthTests(unittest.TestCase):
    def test_manifest_verifies_source_positive_and_blocks_rejected_regressions(self):
        result = verify_long_phrase_truth_manifest()

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["sourceVerifiedCount"], 4)
        self.assertEqual(result["positiveSourcePhraseVerifiedCount"], 4)
        self.assertEqual(result["rejectedRegressionPhraseCount"], 4)
        self.assertEqual(result["rejectedRegressionBlockedCount"], 4)
        self.assertEqual(result["liveAcceptedPhraseCount"], 3)
        self.assertIn("rejected-staff4-right2-audit-eb-vs-d", result["blockedRegressionIds"])

    def test_current_wieniawski_source_map_has_the_reviewed_exact_midi_sequence(self):
        score = symbolic_score_from_target(wieniawski_reference_target())
        notes = score["notes"]

        self.assertEqual(
            [note["note"] for note in notes],
            [
                "A5", "G5", "F5", "A5", "G5", "F5", "A5", "G#5", "F5",
                "Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5", "C5",
            ],
        )
        self.assertEqual(note_midi_sequence(notes), [81, 79, 77, 81, 79, 77, 81, 80, 77, 75, 75, 72, 75, 75, 75, 72])

    def test_gate_accepts_only_full_audio_agreed_exact_midi_phrase(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("G5", 79, 0.00),
            detected_note("F5", 77, 0.12),
            detected_note("A5", 81, 0.24),
            detected_note("G#5", 80, 0.36),
            detected_note("F5", 77, 0.48),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=True, min_exact_notes=5)

        self.assertTrue(gate["accepted"])
        self.assertEqual(gate["status"], "source_score_exact_midi_sequence_verified")
        self.assertEqual(gate["bestOverlap"], 5)
        self.assertEqual(gate["bestOverlapExactSequence"], ["G5", "F5", "A5", "G#5", "F5"])
        self.assertEqual(gate["bestOverlapMidiSequence"], [79, 77, 81, 80, 77])

    def test_gate_accepts_live_staff4_eb_measure_window_by_exact_midi(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("D#5", 75, 0.00),
            detected_note("D#5", 75, 0.12),
            detected_note("C5", 72, 0.24),
            detected_note("D#5", 75, 0.36),
            detected_note("D#5", 75, 0.48),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=True, min_exact_notes=5)

        self.assertTrue(gate["accepted"])
        self.assertEqual(gate["status"], "source_score_exact_midi_sequence_verified")
        self.assertEqual(gate["bestOverlap"], 5)
        self.assertEqual(gate["referenceStart"], 9)
        self.assertEqual(gate["bestOverlapExactSequence"], ["Eb5", "Eb5", "C5", "Eb5", "Eb5"])
        self.assertEqual(gate["bestOverlapMidiSequence"], [75, 75, 72, 75, 75])

    def test_gate_accepts_live_staff4_six_note_right1_window_by_exact_midi(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("D#5", 75, 0.00),
            detected_note("D#5", 75, 0.12),
            detected_note("C5", 72, 0.24),
            detected_note("D#5", 75, 0.36),
            detected_note("D#5", 75, 0.48),
            detected_note("D#5", 75, 0.60),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=True, min_exact_notes=6)

        self.assertTrue(gate["accepted"])
        self.assertEqual(gate["status"], "source_score_exact_midi_sequence_verified")
        self.assertEqual(gate["bestOverlap"], 6)
        self.assertEqual(gate["referenceStart"], 9)
        self.assertEqual(gate["referenceEnd"], 15)
        self.assertEqual(gate["bestOverlapExactSequence"], ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5"])
        self.assertEqual(gate["bestOverlapMidiSequence"], [75, 75, 72, 75, 75, 75])

    def test_gate_accepts_live_staff4_seven_note_full_phrase_by_exact_midi(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("D#5", 75, 0.00),
            detected_note("D#5", 75, 0.12),
            detected_note("C5", 72, 0.24),
            detected_note("D#5", 75, 0.36),
            detected_note("D#5", 75, 0.48),
            detected_note("D#5", 75, 0.60),
            detected_note("C5", 72, 0.72),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=True, min_exact_notes=7)

        self.assertTrue(gate["accepted"])
        self.assertEqual(gate["status"], "source_score_exact_midi_sequence_verified")
        self.assertEqual(gate["bestOverlap"], 7)
        self.assertEqual(gate["referenceStart"], 9)
        self.assertEqual(gate["referenceEnd"], 16)
        self.assertEqual(gate["bestOverlapExactSequence"], ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5", "C5"])
        self.assertEqual(gate["bestOverlapMidiSequence"], [75, 75, 72, 75, 75, 75, 72])

    def test_staff4_extension_rejects_current_audio_after_the_accepted_prefix(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("D#5", 75, 0.00),
            detected_note("D#5", 75, 0.12),
            detected_note("C5", 72, 0.24),
            detected_note("D#5", 75, 0.36),
            detected_note("D#5", 75, 0.48),
            detected_note("D5", 74, 0.60),
            detected_note("D#5", 75, 0.72),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=True, min_exact_notes=7)

        self.assertFalse(gate["accepted"])
        self.assertEqual(gate["status"], "source_score_exact_midi_sequence_not_found")
        self.assertEqual(gate["bestOverlap"], 5)
        self.assertEqual(gate["bestOverlapExactSequence"], ["Eb5", "Eb5", "C5", "Eb5", "Eb5"])
        self.assertEqual(gate["bestOverlapMidiSequence"], [75, 75, 72, 75, 75])

    def test_gate_rejects_pitch_letter_match_in_the_wrong_octave(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("G4", 67, 0.00),
            detected_note("F4", 65, 0.12),
            detected_note("A4", 69, 0.24),
            detected_note("G#4", 68, 0.36),
            detected_note("F4", 65, 0.48),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=True, min_exact_notes=5)

        self.assertFalse(gate["accepted"])
        self.assertEqual(gate["status"], "source_score_exact_midi_sequence_not_found")
        self.assertEqual(gate["bestOverlap"], 0)

    def test_gate_rejects_audio_unagreed_phrase_even_when_midi_matches(self):
        source_notes = symbolic_score_from_target(wieniawski_reference_target())["notes"]
        detected = [
            detected_note("G5", 79, 0.00, audio=False),
            detected_note("F5", 77, 0.12, audio=False),
            detected_note("A5", 81, 0.24, audio=False),
            detected_note("G#5", 80, 0.36, audio=False),
            detected_note("F5", 77, 0.48, audio=False),
        ]

        gate = exact_midi_phrase_gate(detected, source_notes, audio_agreed=False, min_exact_notes=5)

        self.assertFalse(gate["accepted"])
        self.assertEqual(gate["status"], "source_audio_agreement_missing")
        self.assertEqual(gate["bestOverlap"], 5)


if __name__ == "__main__":
    unittest.main()
