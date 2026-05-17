import unittest

from backend.app.gold_review import best_review_note_slice, build_gold_review_loop, record_gold_review_item


def note(name, midi, start):
    return {
        "note": name,
        "midi": midi,
        "pitchClass": name.rstrip("0123456789"),
        "startSeconds": start,
        "endSeconds": start + 0.2,
        "durationSeconds": 0.2,
        "confidence": 0.93,
        "audioAgreement": True,
        "agreementSources": ["pitch_hysteresis", "spectral_onset"],
    }


class GoldReviewTests(unittest.TestCase):
    def test_best_review_slice_prefers_audio_agreed_distinct_phrase(self):
        notes = [
            note("D5", 74, 0.0),
            note("D5", 74, 0.2),
            note("D5", 74, 0.4),
            note("D5", 74, 0.6),
            note("D5", 74, 0.8),
            note("G5", 79, 1.0),
            note("B5", 83, 1.2),
            note("A5", 81, 1.4),
            note("F#5", 78, 1.6),
            note("E5", 76, 1.8),
        ]

        selected = best_review_note_slice(notes, min_notes=5, max_notes=5)

        self.assertEqual([item["note"] for item in selected], ["G5", "B5", "A5", "F#5", "E5"])

    def test_builds_audio_phrase_review_queue_from_detected_series(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "pieces": [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16"}],
                    "transcription": {
                        "detectedSeries": [
                            {
                                "id": "series-a",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "sourceWindow": "*120-210",
                                "sampleId": "sample-a",
                                "startSeconds": 120.0,
                                "endSeconds": 122.0,
                                "localStartSeconds": 0.0,
                                "localEndSeconds": 2.0,
                                "noteCount": 6,
                                "notes": [
                                    note("G5", 79, 0.0),
                                    note("F5", 77, 0.2),
                                    note("A5", 81, 0.4),
                                    note("G#5", 80, 0.6),
                                    note("F5", 77, 0.8),
                                ],
                            }
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop({}, daily_records)

        self.assertEqual(review["status"], "ready")
        self.assertEqual(review["queueCount"], 1)
        candidate = review["queue"][0]
        self.assertEqual(candidate["reviewType"], "audio_phrase")
        self.assertEqual(candidate["detectedNotes"], ["G5", "F5", "A5", "G#5", "F5"])
        self.assertEqual(candidate["detectedMidiSequence"], [79, 77, 81, 80, 77])
        self.assertEqual(candidate["clip"]["audioUrl"], "/api/curtis/media/sample/sample-a/clip?start=0.000&end=1.150")

    def test_recording_audio_phrase_removes_candidate_and_mirrors_truth_item(self):
        state = {}
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "sample-a",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("G5", 79, 0.0),
                                    note("F5", 77, 0.2),
                                    note("A5", 81, 0.4),
                                    note("G#5", 80, 0.6),
                                    note("F5", 77, 0.8),
                                ],
                            }
                        ]
                    },
                }
            ]
        }
        candidate = build_gold_review_loop(state, daily_records)["queue"][0]

        result = record_gold_review_item(
            state,
            {
                **candidate,
                "status": "accepted_truth",
                "type": "audio_phrase",
                "acceptedNotes": candidate["detectedNotes"],
            },
        )
        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(result["goldReviewItem"]["status"], "accepted_truth")
        self.assertEqual(result["truthMirror"]["truthItem"]["status"], "accepted_truth")
        self.assertEqual(review["acceptedCount"], 1)
        self.assertEqual(review["acceptedAudioPhraseCount"], 1)
        self.assertEqual(review["queueCount"], 0)

    def test_score_phrase_acceptance_requires_matching_score_notes(self):
        state = {}

        with self.assertRaises(ValueError):
            record_gold_review_item(
                state,
                {
                    "reviewItemId": "gold-score-a",
                    "type": "score_phrase",
                    "status": "accepted_truth",
                    "sampleId": "sample-a",
                    "acceptedNotes": ["A4"],
                    "scoreNotes": ["A5"],
                    "scoreLocation": "m. 5",
                    "scoreImageUrl": "/assets/score/m5.png",
                },
            )

    def test_exact_score_phrase_acceptance_becomes_score_ready_truth(self):
        state = {}

        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-score-b",
                "type": "score_phrase",
                "status": "accepted_truth",
                "sampleId": "sample-b",
                "practiceDay": "2026-05-03",
                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                "sourceTitle": "5-3-26",
                "startSeconds": 10.0,
                "endSeconds": 11.5,
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "acceptedNotes": ["Bb4", "D5", "C5", "Bb4", "D5"],
                "scoreNotes": ["Bb4", "D5", "C5", "Bb4", "D5"],
                "scoreLocation": "m. 2",
                "scoreSource": "IMSLP source PDF",
                "scoreImageUrl": "/assets/score/m2.png",
            },
        )

        review = build_gold_review_loop(state, {"records": []})

        self.assertEqual(review["acceptedCount"], 1)
        self.assertEqual(review["acceptedScorePhraseCount"], 1)
        self.assertEqual(review["scoreReadyTruthCount"], 1)
        self.assertEqual(review["acceptedEvidenceReadyCount"], 1)

    def test_rejected_mismatch_is_stored_without_becoming_accepted_truth(self):
        state = {}

        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-a",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "sample-c",
                "detectedNotes": ["A4", "D5"],
                "reason": "audio does not match detected notes",
            },
        )

        review = build_gold_review_loop(state, {"records": []})

        self.assertEqual(review["rejectedCount"], 1)
        self.assertEqual(review["acceptedCount"], 0)
        self.assertEqual(review["acceptedEvidenceReadyCount"], 0)


if __name__ == "__main__":
    unittest.main()
