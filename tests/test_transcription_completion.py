import unittest

from backend.app.scanner import accepted_long_phrase_count, build_transcription_completion


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

    def test_verified_measure_phrase_with_media_counts_as_long_phrase(self):
        daily_records = {
            "recordCount": 1,
            "audioEvidenceRecordCount": 1,
            "transcribedRecordCount": 1,
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "scoreSequenceMatchCount": 1,
                        "scoreLocationVerifiedCount": 1,
                    },
                    "matchGroups": [
                        {
                            "status": "symbolic_score_phrase_match",
                            "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "matchedNoteRun": 5,
                            "minimumMatchedNoteRun": 5,
                            "scoreLocationVerified": True,
                            "scoreSnippetStatus": "exact_score_location_verified",
                            "scoreLocationStatus": "exact_score_location_verified",
                            "scoreSequenceLabel": "m. 12",
                            "referenceStart": 44,
                            "referenceEnd": 49,
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_verified",
                                "measureLabel": "m. 12",
                            },
                            "clip": {
                                "mediaUrl": "/api/curtis/media/sample/sample-phrase",
                                "audioUrl": "/api/curtis/media/sample/sample-phrase/clip?start=0&end=2",
                            },
                            "transcription": {"sampleId": "sample-phrase"},
                        }
                    ],
                }
            ],
        }

        completion = build_transcription_completion(
            {"scoreReferenceTargetCount": 1},
            daily_records,
            {"entries": [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16"}]},
            {
                "ledgerVideoCount": 1,
                "uploadedVideoSeconds": 120,
                "uploadedVideoLabel": "2m",
                "checkedVideoSeconds": 120,
                "checkedVideoLabel": "2m",
                "activePracticeLabel": "2m",
                "estimatedTotalPracticeLabel": "2m",
                "activePracticeScan": {
                    "activeIntervalCount": 1,
                    "sampleResultCount": 1,
                    "activeViolinSampleCount": 1,
                    "checkedNoViolinSampleCount": 0,
                    "pendingWindowCount": 0,
                },
            },
            {"benchmarkCount": 1, "wrongScoreNoteRegressionCount": 1},
            [{"id": "sample-phrase"}],
            [{"transcriptionId": "t1"}],
        )

        self.assertEqual(completion["exactScoreAlignedWindowCount"], 1)
        self.assertEqual(completion["longPhraseAcceptedCount"], 1)
        self.assertTrue(any(item["label"] == "Long phrases" and item["value"] == "1" for item in completion["implementationCurrent"]))
        self.assertGreaterEqual(completion["completionExactPercent"], 45)

    def test_local_source_score_pdf_advances_score_truth_without_accepting_phrase(self):
        completion = build_transcription_completion(
            {"scoreReferenceTargetCount": 1},
            {
                "recordCount": 1,
                "records": [
                    {
                        "transcription": {
                            "scoreReferenceAudit": {
                                "sourcePdfLocalReadyCount": 1,
                                "symbolicScoreNoteCount": 0,
                                "targets": [
                                    {
                                        "scoreAssetId": "wieniawski-scherzo-tarantelle-vln",
                                        "sourcePdfLocalReady": True,
                                    }
                                ],
                            },
                            "scoreSequenceMatchCount": 0,
                            "scoreLocationVerifiedCount": 0,
                        }
                    }
                ],
            },
            {"entries": []},
            {
                "ledgerVideoCount": 1,
                "uploadedVideoSeconds": 120,
                "uploadedVideoLabel": "2m",
                "checkedVideoSeconds": 0,
                "checkedVideoLabel": "0s",
                "activePracticeLabel": "pending",
                "estimatedTotalPracticeLabel": "pending",
                "activePracticeScan": {},
            },
            {},
            [],
            [],
        )

        score_gate = next(item for item in completion["gates"] if item["id"] == "score-truth")
        self.assertEqual(completion["localScoreSourceCount"], 1)
        self.assertEqual(completion["longPhraseAcceptedCount"], 0)
        self.assertGreaterEqual(score_gate["points"], 3)
        self.assertIn("1 local PDFs", score_gate["evidence"])

    def test_single_note_and_unverified_reference_matches_do_not_count_as_long_phrases(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "pitch_anchor_match",
                            "matchedNoteRun": 1,
                            "minimumMatchedNoteRun": 1,
                            "scoreLocationVerified": True,
                            "scoreLocationStatus": "exact_score_location_verified",
                            "clip": {"mediaUrl": "/api/curtis/media/sample/a"},
                        },
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 9,
                            "minimumMatchedNoteRun": 1,
                            "scoreLocationVerified": False,
                            "scoreLocationStatus": "exact_score_location_pending",
                            "clip": {"mediaUrl": "/api/curtis/media/sample/b"},
                        },
                        {
                            "status": "symbolic_score_phrase_match",
                            "matchedNoteRun": 5,
                            "minimumMatchedNoteRun": 5,
                            "scoreLocationVerified": True,
                            "scoreLocationStatus": "exact_score_location_verified",
                            "score": {"cropStatus": "exact_score_location_verified"},
                        },
                    ],
                }
            ]
        }

        self.assertEqual(accepted_long_phrase_count(daily_records), 0)


if __name__ == "__main__":
    unittest.main()
