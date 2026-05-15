import unittest

from backend.app.evidence_ledger import (
    build_active_practice_coverage,
    build_evidence_progress,
    build_truth_progress,
    record_evidence_correction,
    record_truth_item,
)


class EvidenceLedgerTests(unittest.TestCase):
    def test_active_practice_coverage_counts_checked_non_playing_windows_separately(self):
        inventory = {
            "youtube": [
                {
                    "id": "v1",
                    "title": "5-2-26",
                    "url": "https://www.youtube.com/watch?v=v1",
                    "publishedAt": "2026-05-03T09:00:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                },
                {
                    "id": "v2",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=v2",
                    "publishedAt": "2026-05-04T09:00:00Z",
                    "durationSeconds": 300,
                    "practiceCandidate": True,
                },
            ]
        }
        samples = [
            {
                "id": "v1-silent",
                "url": "https://www.youtube.com/watch?v=v1",
                "title": "5-2-26",
                "window": "*0-90",
                "containsViolin": False,
            },
            {
                "id": "v1-play",
                "url": "https://www.youtube.com/watch?v=v1",
                "title": "5-2-26",
                "window": "*90-180",
                "containsViolin": True,
            },
            {
                "id": "v2-silent",
                "url": "https://www.youtube.com/watch?v=v2",
                "title": "5-3-26",
                "window": "*0-120",
                "containsViolin": False,
            },
        ]
        transcriptions = [
            {
                "transcriptionId": "t1",
                "sampleId": "v1-play",
                "sourceUrl": "https://www.youtube.com/watch?v=v1",
                "sourceTitle": "5-2-26",
                "sourceWindow": "*90-180",
                "status": "transcribed",
                "quality": {"windowMode": "detected_active_sections"},
                "durationSeconds": 12,
                "notes": [
                    {"note": "A4", "durationSeconds": 0.4, "startSeconds": 0, "endSeconds": 0.4},
                ],
            }
        ]

        coverage = build_active_practice_coverage(inventory, samples, transcriptions, [])

        self.assertEqual(coverage["ledgerVideoCount"], 2)
        self.assertEqual(coverage["uploadedVideoSeconds"], 900)
        self.assertEqual(coverage["checkedVideoSeconds"], 300)
        self.assertEqual(coverage["activePracticeSeconds"], 12)
        self.assertEqual(coverage["activeCandidateSeconds"], 90)
        self.assertEqual(coverage["unmeasuredVideoSeconds"], 600)
        self.assertEqual(coverage["measurementStatus"], "partial")
        self.assertEqual(coverage["estimateStatus"], "estimated_from_checked_windows")
        by_video = {item["videoId"]: item for item in coverage["videos"]}
        self.assertEqual(by_video["v1"]["checkedVideoSeconds"], 180)
        self.assertEqual(by_video["v1"]["activePracticeSeconds"], 12)
        self.assertEqual(by_video["v1"]["status"], "active_measured")
        self.assertEqual(by_video["v2"]["checkedVideoSeconds"], 120)
        self.assertEqual(by_video["v2"]["activePracticeSeconds"], 0)
        self.assertEqual(by_video["v2"]["status"], "checked_no_violin")

    def test_wrong_score_note_correction_creates_regression_benchmark(self):
        state = {}

        result = record_evidence_correction(
            state,
            {
                "type": "score_match",
                "status": "rejected",
                "sourceVideoId": "v1",
                "sampleId": "v1-play",
                "practiceDay": "2026-05-03",
                "startSeconds": 171,
                "endSeconds": 172,
                "observedNote": "A4",
                "displayedScoreNote": "B4",
                "reason": "The score box highlighted B while the audio/transcription note was A.",
                "benchmark": True,
            },
        )
        progress = build_evidence_progress(state)

        self.assertEqual(result["correction"]["status"], "rejected")
        self.assertTrue(result["benchmark"])
        self.assertEqual(progress["correctionCount"], 1)
        self.assertEqual(progress["benchmarkCount"], 1)
        self.assertEqual(progress["rejectedScoreMatchCount"], 1)
        self.assertEqual(progress["wrongScoreNoteRegressionCount"], 1)
        self.assertEqual(progress["recentBenchmarks"][0]["expectedObservedNote"], "A4")
        self.assertEqual(progress["recentBenchmarks"][0]["forbiddenDisplayedScoreNote"], "B4")

    def test_accepted_score_correction_cannot_mismatch_observed_note(self):
        with self.assertRaises(ValueError):
            record_evidence_correction(
                {},
                {
                    "type": "score_match",
                    "status": "accepted",
                    "observedNote": "A4",
                    "displayedScoreNote": "B4",
                },
            )

    def test_truth_item_accepts_only_matching_audio_and_score_sequences(self):
        state = {}

        result = record_truth_item(
            state,
            {
                "type": "audio_score_match",
                "status": "accepted_truth",
                "practiceDay": "2026-05-03",
                "sampleId": "sample-a",
                "startSeconds": 171.0,
                "endSeconds": 172.2,
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "scoreAssetId": "wieniawski-scherzo-tarantelle-vln",
                "scoreLocation": "m. 2",
                "scoreImageUrl": "/assets/score/m2.png",
                "acceptedNotes": ["A4", "D5"],
                "scoreNotes": ["A4", "D5"],
            },
        )
        progress = build_truth_progress(state)

        self.assertEqual(result["truthItem"]["status"], "accepted_truth")
        self.assertTrue(result["truthItem"]["gateState"]["acceptedEvidenceReady"])
        self.assertTrue(result["truthItem"]["gateState"]["audioScoreAgreement"])
        self.assertTrue(result["truthItem"]["gateState"]["exactNoteSequenceAgreement"])
        self.assertEqual(result["truthItem"]["acceptedMidiSequence"], "69 74")
        self.assertEqual(result["truthItem"]["scoreMidiSequence"], "69 74")
        self.assertEqual(progress["truthItemCount"], 1)
        self.assertEqual(progress["acceptedEvidenceReadyCount"], 1)
        self.assertEqual(progress["scoreReadyTruthCount"], 1)

    def test_truth_item_rejects_mismatched_accepted_score_sequence(self):
        with self.assertRaises(ValueError):
            record_truth_item(
                {},
                {
                    "type": "audio_score_match",
                    "status": "accepted_truth",
                    "sampleId": "sample-a",
                    "acceptedNotes": ["A4"],
                    "scoreNotes": ["B4"],
                    "scoreLocation": "m. 2",
                    "scoreImageUrl": "/assets/score/m2.png",
                },
            )

    def test_truth_item_rejects_same_pitch_class_different_octave_score_sequence(self):
        with self.assertRaises(ValueError):
            record_truth_item(
                {},
                {
                    "type": "audio_score_match",
                    "status": "accepted_truth",
                    "sampleId": "sample-a",
                    "acceptedNotes": ["A4"],
                    "scoreNotes": ["A5"],
                    "scoreLocation": "m. 2",
                    "scoreImageUrl": "/assets/score/m2.png",
                },
            )

    def test_truth_item_rejects_score_truth_without_octave(self):
        with self.assertRaises(ValueError):
            record_truth_item(
                {},
                {
                    "type": "audio_score_match",
                    "status": "accepted_truth",
                    "sampleId": "sample-a",
                    "acceptedNotes": ["A4"],
                    "scoreNotes": ["A"],
                    "scoreLocation": "m. 2",
                    "scoreImageUrl": "/assets/score/m2.png",
                },
            )

    def test_pending_truth_item_does_not_become_accepted_evidence(self):
        state = {}

        record_truth_item(
            state,
            {
                "type": "audio_score_match",
                "status": "pending_review",
                "sampleId": "sample-a",
                "detectedNotes": ["A4"],
                "scoreNotes": ["A4"],
                "scoreLocation": "m. 2",
            },
        )
        progress = build_truth_progress(state)

        self.assertEqual(progress["truthItemCount"], 1)
        self.assertEqual(progress["pendingTruthCount"], 1)
        self.assertEqual(progress["acceptedEvidenceReadyCount"], 0)


if __name__ == "__main__":
    unittest.main()
