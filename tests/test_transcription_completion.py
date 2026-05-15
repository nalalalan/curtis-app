import unittest

from backend.app.scanner import (
    accepted_long_phrase_count,
    accepted_measure_match_count,
    build_transcription_completion,
    reference_phrase_candidate_count,
    reference_phrase_candidate_top,
    source_verification_target_count,
    source_verification_target_top,
)


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
                            "detectedPitchClassSequenceCompact": "D G B A E",
                            "scoreLocationVerified": True,
                            "scoreVisualAgreement": True,
                            "scoreVisualRangeAgreement": True,
                            "scoreSpellingAgreement": True,
                            "scoreActualPieceAgreement": True,
                            "scoreSnippetStatus": "exact_score_location_verified",
                            "scoreLocationStatus": "exact_score_location_verified",
                            "scoreSequenceLabel": "m. 12",
                            "referenceStart": 44,
                            "referenceEnd": 49,
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_verified",
                                "measureLabel": "m. 12",
                                "imageUrl": "/assets/score/m12.png",
                                "actualSourceSnippetDisplayed": True,
                                "visualRangeAgreement": True,
                                "scoreSpellingAgreement": True,
                            },
                            "clip": {
                                "mediaUrl": "/api/curtis/media/sample/sample-phrase",
                                "audioUrl": "/api/curtis/media/sample/sample-phrase/clip?start=0&end=2",
                            },
                            "transcription": {"sampleId": "sample-phrase"},
                        }
                    ],
                    "heatMap": {
                        "fragments": [
                            {
                                "status": "score_location_verified",
                                "label": "m. 12",
                                "scoreImageUrl": "/assets/score/m12.png",
                            }
                        ]
                    },
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
        self.assertEqual(completion["acceptedMeasureMatchCount"], 1)
        self.assertEqual(completion["scoreHeatmapFragmentCount"], 1)
        self.assertEqual(completion["actualSourceScoreSnippetCount"], 1)
        self.assertTrue(any(item["label"] == "Long phrases" and item["value"] == "1" for item in completion["implementationCurrent"]))
        self.assertTrue(any(item["label"] == "Measure target" and item["value"] == "1/1" for item in completion["implementationCurrent"]))
        self.assertTrue(any(item["label"] == "Score heat map" and item["value"] == "1" for item in completion["implementationCurrent"]))
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

    def test_verified_symbolic_measure_with_media_counts_before_long_phrase(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "symbolic_score_phrase_match",
                            "matchedNoteRun": 4,
                            "minimumMatchedNoteRun": 4,
                            "detectedPitchClassSequenceCompact": "D A# G D",
                            "scoreLocationVerified": True,
                            "scoreVisualAgreement": True,
                            "scoreVisualRangeAgreement": True,
                            "scoreSpellingAgreement": True,
                            "scoreActualPieceAgreement": True,
                            "scoreSnippetStatus": "exact_score_location_verified",
                            "scoreLocationStatus": "exact_score_location_verified",
                            "scoreSequenceLabel": "opening motif",
                            "referenceStart": 0,
                            "referenceEnd": 4,
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_verified",
                                "measureLabel": "opening motif",
                                "imageUrl": "/assets/score/opening.png",
                                "actualSourceSnippetDisplayed": True,
                                "visualRangeAgreement": True,
                                "scoreSpellingAgreement": True,
                            },
                            "clip": {
                                "mediaUrl": "/api/curtis/media/sample/source-motif",
                                "audioUrl": "/api/curtis/media/sample/source-motif/clip?start=0&end=1",
                            },
                            "transcription": {"sampleId": "source-motif"},
                        }
                    ],
                }
            ]
        }

        self.assertEqual(accepted_measure_match_count(daily_records), 1)
        self.assertEqual(accepted_long_phrase_count(daily_records), 0)

    def test_reference_phrase_candidates_are_counted_without_accepting_score_evidence(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "scoreSequenceMatchCount": 2,
                        "scoreLocationVerifiedCount": 0,
                    },
                    "matchGroups": [
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 7,
                            "detectedPitchClassSequenceCompact": "D D# D A# G",
                            "detectedPitchClassSequence": "D D D# D D A# G",
                            "scoreLocationVerified": False,
                            "scoreLocationStatus": "exact_score_location_pending",
                            "referenceStart": 30,
                            "referenceEnd": 37,
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_pending",
                            },
                            "clip": {
                                "mediaUrl": "/api/curtis/media/sample/reference-candidate",
                                "audioUrl": "/api/curtis/media/sample/reference-candidate/clip?start=0&end=1",
                            },
                            "transcription": {"sampleId": "reference-candidate"},
                        },
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 9,
                            "detectedPitchClassSequenceCompact": "D D#",
                            "scoreLocationVerified": False,
                            "clip": {"mediaUrl": "/api/curtis/media/sample/repeated"},
                            "transcription": {"sampleId": "repeated"},
                        },
                    ],
                }
            ]
        }

        completion = build_transcription_completion(
            training={},
            daily_records=daily_records,
            repertoire_evidence={"entries": []},
            active_practice_coverage={},
            evidence_progress={},
            media_samples=[],
            transcriptions=[],
        )

        self.assertEqual(reference_phrase_candidate_count(daily_records), 1)
        self.assertEqual(reference_phrase_candidate_top(daily_records)["sequence"], "D D D# D D A# G")
        self.assertEqual(source_verification_target_count(daily_records), 1)
        self.assertEqual(source_verification_target_top(daily_records)["sequence"], "D D D# D D A# G")
        self.assertEqual(completion["referencePhraseCandidateCount"], 1)
        self.assertEqual(completion["referencePhraseCandidateTopSequence"], "D D D# D D A# G")
        self.assertEqual(completion["sourceVerificationTargetCount"], 1)
        self.assertEqual(completion["sourceVerificationTargetTopSequence"], "D D D# D D A# G")
        self.assertEqual(completion["sourceVerificationTargetCheckedCount"], 1)
        self.assertEqual(completion["sourceVerificationTargetVerifiedCount"], 0)
        self.assertTrue(completion["sourceVerificationTargetTopChecked"])
        self.assertFalse(completion["sourceVerificationTargetTopVerified"])
        self.assertEqual(completion["sourceVerificationTargetTopStatus"], "source_score_sequence_not_found")
        self.assertEqual(completion["sourceVerificationTargetTopBestSourceOverlap"], 1)
        self.assertEqual(completion["longPhraseAcceptedCount"], 0)
        phrase_card = next(item for item in completion["implementationCurrent"] if item["label"] == "Phrase candidates")
        self.assertEqual(phrase_card["value"], "1")
        self.assertEqual(phrase_card["detail"], "pending: D D D# D D A# G")
        source_card = next(item for item in completion["implementationCurrent"] if item["label"] == "Source target")
        self.assertEqual(source_card["value"], "7")
        self.assertEqual(source_card["detail"], "D D D# D D A# G")
        check_card = next(item for item in completion["implementationCurrent"] if item["label"] == "Target check")
        self.assertEqual(check_card["value"], "0/1")
        self.assertEqual(check_card["detail"], "1/7 source overlap")
        self.assertEqual(completion["sourceVerificationTargets"][0]["status"], "source_verification_required")
        self.assertIn("not accepted score evidence", completion["sourceVerificationTargets"][0]["limit"])
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreCheckStatus"], "source_score_sequence_not_found")
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreBestOverlap"], 1)
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreReferenceSequence"], "D C A# D C A# D")
        self.assertGreaterEqual(completion["sourceVerificationTargets"][0]["sourceScoreCandidateGlyphCount"], 1)

    def test_source_verification_targets_require_local_unverified_source_runs(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 7,
                            "detectedPitchClassSequenceCompact": "D D D# D D A# G",
                            "scoreLocationVerified": True,
                            "clip": {"mediaUrl": "/api/curtis/media/sample/already-accepted"},
                            "transcription": {"sampleId": "already-accepted"},
                        },
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 7,
                            "detectedPitchClassSequenceCompact": "D D D# D D A# G",
                            "scoreLocationVerified": False,
                            "transcription": {},
                        },
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 3,
                            "detectedPitchClassSequenceCompact": "D D# A",
                            "scoreLocationVerified": False,
                            "clip": {"mediaUrl": "/api/curtis/media/sample/too-short"},
                            "transcription": {"sampleId": "too-short"},
                        },
                    ],
                }
            ]
        }

        self.assertEqual(source_verification_target_count(daily_records), 0)

    def test_source_verification_targets_check_measure_sized_candidates_against_symbolic_score(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 4,
                            "detectedPitchClassSequence": "D C G A",
                            "detectedPitchClassSequenceCompact": "D C G A",
                            "scoreLocationVerified": False,
                            "score": {"assetId": "wieniawski-scherzo-tarantelle-vln"},
                            "clip": {"mediaUrl": "/api/curtis/media/sample/measure-target"},
                            "transcription": {"sampleId": "measure-target"},
                        }
                    ],
                }
            ]
        }

        target = source_verification_target_top(daily_records)

        self.assertEqual(target["sequence"], "D C G A")
        self.assertTrue(target["sourceScoreChecked"])
        self.assertFalse(target["sourceScoreVerified"])
        self.assertEqual(target["sourceScoreBestOverlap"], 2)
        self.assertEqual(target["sourceScoreBestOverlapSequence"], "D C")

    def test_reference_phrase_candidate_top_prefers_actual_displayed_sequence_length(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 12,
                            "detectedPitchClassSequenceCompact": "D D# D A# G",
                            "scoreLocationVerified": False,
                            "clip": {"mediaUrl": "/api/curtis/media/sample/shorter"},
                            "transcription": {"sampleId": "shorter"},
                        },
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 7,
                            "detectedPitchClassSequenceCompact": "D D D# D D A# G",
                            "scoreLocationVerified": False,
                            "clip": {"mediaUrl": "/api/curtis/media/sample/longer"},
                            "transcription": {"sampleId": "longer"},
                        },
                    ],
                }
            ]
        }

        top = reference_phrase_candidate_top(daily_records)

        self.assertEqual(top["sequence"], "D D D# D D A# G")
        self.assertEqual(top["sequenceNoteCount"], 7)

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
