import unittest

from backend.app.scanner import derive_review
from backend.app.transcription import (
    compare_fingerprints,
    event_fingerprint,
    reference_matches_for,
    transcription_prior_hint,
)


def fingerprint_for(midi_values):
    events = [
        {
            "startSeconds": index * 0.5,
            "endSeconds": (index + 1) * 0.5,
            "durationSeconds": 0.5,
            "midi": midi,
            "note": str(midi),
            "confidence": 0.9,
        }
        for index, midi in enumerate(midi_values)
    ]
    return event_fingerprint(events, 120.0)


class TranscriptionTrainingTests(unittest.TestCase):
    def test_pitch_rhythm_fingerprint_matches_repeated_material(self):
        first = fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81])
        second = fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81])
        unrelated = fingerprint_for([60, 64, 67, 72, 67, 64, 60, 55, 60, 64, 67, 72])

        self.assertGreaterEqual(compare_fingerprints(first, second), 0.95)
        self.assertLess(compare_fingerprints(first, unrelated), 0.65)

    def test_reference_matches_use_learned_transcription_fingerprints(self):
        learned = {
            "transcriptionId": "5-2",
            "sourceTitle": "5-2-26",
            "acceptedTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
            "status": "transcribed",
            "noteCount": 12,
            "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
        }
        incoming = {
            "transcriptionId": "5-3",
            "status": "transcribed",
            "noteCount": 12,
            "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
        }

        matches = reference_matches_for(incoming, {"transcriptions": {"items": [learned]}})

        self.assertEqual(matches[0]["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(matches[0]["basis"], "pitch_rhythm_fingerprint")

    def test_training_state_reports_pitch_rhythm_windows_without_claiming_score_match(self):
        state = {
            "transcriptions": {
                "items": [
                    {
                        "transcriptionId": "title:5 3 26|local|*600-645|sample.mp4",
                        "sampleId": "local",
                        "sourceKey": "title:5 3 26",
                        "sourceTitle": "5-3-26",
                        "sourceWindow": "*600-645",
                        "status": "transcribed",
                        "noteCount": 12,
                        "tempoBpm": 120.0,
                        "acceptedTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                        "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
                    }
                ]
            }
        }

        review = derive_review({"youtube": []}, {}, [], state)
        training = review["training"]
        by_source = {anchor["sourceTitle"]: anchor for anchor in training["anchors"]}

        self.assertEqual(training["pitchRhythmWindowCount"], 1)
        self.assertEqual(training["scoreAlignedWindowCount"], 0)
        self.assertEqual(training["label"], "3 refs / 1 pitch windows")
        self.assertEqual(by_source["5-3-26"]["status"], "pitch_rhythm_extracted")
        self.assertTrue(by_source["5-3-26"]["scoreAlignment"]["pitchRhythmExtracted"])

    def test_piece_prompt_can_receive_nearest_learned_fingerprint_hint(self):
        state = {
            "transcriptions": {
                "items": [
                    {
                        "transcriptionId": "new-sample",
                        "sampleId": "new-sample",
                        "sourceKey": "title:new sample",
                        "sourceTitle": "new sample",
                        "status": "transcribed",
                        "noteCount": 12,
                        "referenceMatches": [
                            {
                                "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                                "sourceTitle": "5-2-26",
                                "score": 0.91,
                                "basis": "pitch_rhythm_fingerprint",
                            }
                        ],
                    }
                ]
            }
        }

        hint = transcription_prior_hint(state, {"id": "new-sample", "title": "new sample"})

        self.assertIn("pitch/rhythm fingerprint", hint)
        self.assertIn("Wieniawski Scherzo-Tarantelle", hint)


if __name__ == "__main__":
    unittest.main()
