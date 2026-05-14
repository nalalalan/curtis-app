import unittest

from backend.app.scanner import build_transcription_completion


class TranscriptionCompletionTests(unittest.TestCase):
    def test_completion_reports_weighted_roadmap_and_open_long_phrase_gate(self):
        completion = build_transcription_completion(
            {"scoreReferenceTargetCount": 3},
            {
                "recordCount": 39,
                "audioEvidenceRecordCount": 3,
                "transcribedRecordCount": 1,
                "records": [
                    {
                        "transcription": {
                            "scoreSequenceMatchCount": 15,
                            "scoreLocationVerifiedCount": 0,
                        }
                    }
                ],
            },
            {"entries": [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16"}]},
            {
                "ledgerVideoCount": 46,
                "uploadedVideoSeconds": 768230,
                "uploadedVideoLabel": "213h 23m",
                "checkedVideoSeconds": 7290,
                "checkedVideoLabel": "2h 1m",
                "activePracticeLabel": "1h 58m",
                "estimatedTotalPracticeLabel": "208h 49m",
                "activePracticeScan": {
                    "activeIntervalCount": 215,
                    "sampleResultCount": 81,
                    "activeViolinSampleCount": 72,
                    "checkedNoViolinSampleCount": 9,
                    "pendingWindowCount": 250,
                },
            },
            {"benchmarkCount": 1, "wrongScoreNoteRegressionCount": 1},
            [{"id": "sample"}],
            [{"transcriptionId": "t1"}],
        )

        self.assertGreater(completion["completionPercent"], 0)
        self.assertLess(completion["completionPercent"], 50)
        self.assertGreater(completion["completionExactPercent"], 0)
        self.assertLess(completion["completionExactPercent"], 50)
        self.assertTrue(completion["completionExactLabel"].endswith("%"))
        self.assertIn("weighted points", completion["completedPointsLabel"])
        self.assertEqual(completion["longPhraseAcceptedCount"], 0)
        self.assertEqual(completion["exactScoreAlignedWindowCount"], 0)
        self.assertIn("not a playing-readiness score", completion["basis"])
        self.assertTrue(any(item["id"] == "full-archive-coverage" for item in completion["gates"]))
        self.assertTrue(any(item["label"] == "Full practice-time coverage" for item in completion["implementationPlan"]))
        self.assertTrue(any("full archive" in item for item in completion["remainingSummary"]))
        self.assertIn("Practice-time scanning is working", completion["implementationSummary"])
        self.assertEqual(completion["implementationCurrent"][0]["value"], completion["completionExactLabel"])
        self.assertEqual(completion["implementationCurrent"][0]["detail"], completion["completedPointsLabel"])
        archive_gate = next(item for item in completion["gates"] if item["id"] == "full-archive-coverage")
        self.assertIn("precisePoints", archive_gate)
        self.assertGreater(archive_gate["precisePoints"], archive_gate["points"])
        self.assertEqual(completion["completedPoints"], 32.614)
        self.assertEqual(completion["completionExactLabel"], "32.614%")


if __name__ == "__main__":
    unittest.main()
