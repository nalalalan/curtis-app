import unittest
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from backend.app.scanner import (
    accepted_long_phrase_count,
    accepted_measure_match_count,
    build_transcription_completion,
    build_truth_workbench,
    audio_window_search_for_exact_midi,
    media_sample_for_id,
    reference_phrase_candidate_count,
    reference_phrase_candidate_top,
    source_verification_target_count,
    source_verification_target_top,
    staff4_source_audio_rescan_record,
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
    return (int(name[-1]) + 1) * 12 + NOTE_CLASS[name[:-1]]


def note(name, start=0.0):
    return {
        "note": name,
        "midi": midi_for_note(name),
        "startSeconds": start,
        "endSeconds": start + 0.12,
        "durationSeconds": 0.12,
        "confidence": 0.92,
        "audioAgreement": True,
        "agreementSourceCount": 1,
        "agreementSources": ["spectral_onset"],
        "detectorSource": "spectral_onset_test",
    }


def write_tiny_wav(path, seconds=1.0):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * max(1, int(22050 * float(seconds))))


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
                            "scoreVisibleNoteSequenceVerified": True,
                            "scoreVisibleExactNoteSequenceVerified": True,
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
                                "visibleScoreNoteSequenceVerified": True,
                                "visibleScoreExactNoteSequenceVerified": True,
                                "scoreSpellingAgreement": True,
                                "scoreBoxCenterAgreement": True,
                                "audioTranscriptionAgreement": True,
                                "transcriptionScoreAgreement": True,
                                "truthEvidenceAccepted": True,
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

    def test_staff4_phrase_expansion_gate_blocks_adjacent_audio_mismatch(self):
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
                            "minimumDistinctPitchClasses": 2,
                            "detectedPitchClassSequence": "D# D# C D# D#",
                            "detectedPitchClassSequenceCompact": "D# C D#",
                            "scoreLocationVerified": True,
                            "scoreVisualAgreement": True,
                            "scoreVisualRangeAgreement": True,
                            "scoreVisibleNoteSequenceVerified": True,
                            "scoreVisibleExactNoteSequenceVerified": True,
                            "scoreSpellingAgreement": True,
                            "scoreActualPieceAgreement": True,
                            "scoreBoxCenterAgreement": True,
                            "audioTranscriptionAgreement": True,
                            "transcriptionScoreAgreement": True,
                            "truthEvidenceAccepted": True,
                            "scoreSnippetStatus": "exact_score_location_verified",
                            "scoreLocationStatus": "exact_score_location_verified",
                            "scoreSequenceLabel": "m. staff4-packet-1",
                            "referenceStart": 9,
                            "referenceEnd": 14,
                            "detectedSeries": {
                                "sampleId": "Njh8_zq9_DM-8835",
                                "sourceWindow": "*8835-8925",
                                "notes": [
                                    note("D#5", 0.0),
                                    note("D#5", 0.12),
                                    note("C5", 0.24),
                                    note("D#5", 0.36),
                                    note("D#5", 0.48),
                                    note("D5", 0.60),
                                    note("D#5", 0.72),
                                ],
                            },
                            "matchedDetectedNotes": [
                                note("D#5", 0.0),
                                note("D#5", 0.12),
                                note("C5", 0.24),
                                note("D#5", 0.36),
                                note("D#5", 0.48),
                            ],
                            "scoreMatchedNotes": [
                                {"note": "Eb5", "midi": 75},
                                {"note": "Eb5", "midi": 75},
                                {"note": "C5", "midi": 72},
                                {"note": "Eb5", "midi": 75},
                                {"note": "Eb5", "midi": 75},
                            ],
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_verified",
                                "measureLabel": "m. staff4-packet-1",
                                "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-verified.png",
                                "actualSourceSnippetDisplayed": True,
                                "visualRangeAgreement": True,
                                "visibleScoreNoteSequenceVerified": True,
                                "visibleScoreExactNoteSequenceVerified": True,
                                "scoreSpellingAgreement": True,
                                "scoreBoxCenterAgreement": True,
                                "audioTranscriptionAgreement": True,
                                "transcriptionScoreAgreement": True,
                                "truthEvidenceAccepted": True,
                            },
                            "clip": {
                                "mediaUrl": "/api/curtis/media/sample/Njh8_zq9_DM-8835",
                                "audioUrl": "/api/curtis/media/sample/Njh8_zq9_DM-8835/clip?start=20.225&end=22.535",
                            },
                            "transcription": {"sampleId": "Njh8_zq9_DM-8835"},
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.app.staff4_audit.OWNER_MEDIA_DIR", Path(temp_dir) / "owner-media"
        ):
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
                [{"id": "Njh8_zq9_DM-8835"}],
                [{"transcriptionId": "t1"}],
            )

        harness = completion["phraseExpansionHarness"]
        current = harness["currentBest"]
        self.assertEqual(harness["anchorCount"], 1)
        self.assertEqual(harness["status"], "ready")
        self.assertEqual(harness["acceptedAnchorNoteCount"], 7)
        self.assertEqual(harness["targetCount"], 1)
        self.assertEqual(harness["acceptedExpansionCount"], 0)
        self.assertEqual(harness["blockedExpansionCount"], 1)
        self.assertEqual(harness["rejectedRegressionCount"], 0)
        rejected = [item for item in harness["items"] if item["status"] == "rejected_regression"]
        self.assertEqual(len(rejected), 0)
        self.assertEqual(current["status"], "blocked_no_audio_candidate")
        self.assertEqual(current["direction"], "right-1")
        self.assertEqual(current["targetSequence"], "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5 A4")
        self.assertEqual(current["targetMidiSequence"], [75, 75, 72, 75, 75, 75, 72, 69])
        self.assertEqual(current["expectedNextScoreNote"], "A4")
        self.assertEqual(current["expectedNextScoreMidi"], 69)
        self.assertEqual(current["bestAudioSequence"], "")
        self.assertEqual(current["sourceImageUrl"], "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-a-source.png")
        self.assertFalse(current["truthEvidenceAccepted"])
        self.assertEqual(completion["phraseExpansionCurrentStatus"], "blocked_no_audio_candidate")
        self.assertEqual(completion["phraseExpansionRejectedRegressionCount"], 0)
        mining = completion["staff4AdjacentMining"]
        self.assertEqual(mining["status"], "not_found")
        self.assertEqual(mining["exactCandidateCount"], 0)
        self.assertEqual(mining["searchedWindowCount"], 0)
        self.assertEqual(mining.get("nearestWindow") or {}, {})
        self.assertEqual(completion["staff4AdjacentMiningStatus"], "not_found")
        self.assertIn("A4", completion["nextAction"])

    def test_staff4_phrase_expansion_searches_raw_detected_series(self):
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
                        "detectedSeries": [
                            {
                                "sampleId": "raw-staff4-window",
                                "sourceWindow": "*8835-8925",
                                "candidateOnly": False,
                                "notes": [
                                    note("D#5", 0.0),
                                    note("D#5", 0.12),
                                    note("C5", 0.24),
                                    note("D#5", 0.36),
                                    note("D#5", 0.48),
                                    note("D#5", 0.60),
                                    note("C5", 0.72),
                                    note("A4", 0.84),
                                ],
                            }
                        ],
                    },
                    "matchGroups": [
                        {
                            "status": "symbolic_score_phrase_match",
                            "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "matchedNoteRun": 5,
                            "minimumMatchedNoteRun": 5,
                            "minimumDistinctPitchClasses": 2,
                            "detectedPitchClassSequence": "D# D# C D# D#",
                            "detectedPitchClassSequenceCompact": "D# C D#",
                            "scoreLocationVerified": True,
                            "scoreVisualAgreement": True,
                            "scoreVisualRangeAgreement": True,
                            "scoreVisibleNoteSequenceVerified": True,
                            "scoreVisibleExactNoteSequenceVerified": True,
                            "scoreSpellingAgreement": True,
                            "scoreActualPieceAgreement": True,
                            "scoreBoxCenterAgreement": True,
                            "audioTranscriptionAgreement": True,
                            "transcriptionScoreAgreement": True,
                            "truthEvidenceAccepted": True,
                            "scoreSnippetStatus": "exact_score_location_verified",
                            "scoreLocationStatus": "exact_score_location_verified",
                            "scoreSequenceLabel": "m. staff4-packet-1",
                            "referenceStart": 9,
                            "referenceEnd": 14,
                            "detectedSeries": {
                                "sampleId": "accepted-anchor",
                                "sourceWindow": "*8835-8925",
                                "notes": [
                                    note("D#5", 0.0),
                                    note("D#5", 0.12),
                                    note("C5", 0.24),
                                    note("D#5", 0.36),
                                    note("D#5", 0.48),
                                ],
                            },
                            "matchedDetectedNotes": [
                                note("D#5", 0.0),
                                note("D#5", 0.12),
                                note("C5", 0.24),
                                note("D#5", 0.36),
                                note("D#5", 0.48),
                            ],
                            "scoreMatchedNotes": [
                                {"note": "Eb5", "midi": 75},
                                {"note": "Eb5", "midi": 75},
                                {"note": "C5", "midi": 72},
                                {"note": "Eb5", "midi": 75},
                                {"note": "Eb5", "midi": 75},
                            ],
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_verified",
                                "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-verified.png",
                                "actualSourceSnippetDisplayed": True,
                                "visualRangeAgreement": True,
                                "visibleScoreNoteSequenceVerified": True,
                                "visibleScoreExactNoteSequenceVerified": True,
                                "scoreSpellingAgreement": True,
                                "scoreBoxCenterAgreement": True,
                                "audioTranscriptionAgreement": True,
                                "transcriptionScoreAgreement": True,
                                "truthEvidenceAccepted": True,
                            },
                            "clip": {
                                "mediaUrl": "/api/curtis/media/sample/accepted-anchor",
                                "audioUrl": "/api/curtis/media/sample/accepted-anchor/clip?start=20.225&end=22.535",
                            },
                            "transcription": {"sampleId": "accepted-anchor"},
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
            [{"id": "accepted-anchor"}, {"id": "raw-staff4-window"}],
            [{"transcriptionId": "t1"}],
        )

        harness = completion["phraseExpansionHarness"]
        current = harness["currentBest"]
        self.assertEqual(harness["rawDetectedAudioRunCount"], 1)
        self.assertEqual(current["status"], "ready_for_truth_review")
        self.assertEqual(current["direction"], "right-1")
        self.assertEqual(current["targetSequence"], "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5 A4")
        self.assertEqual(current["bestAudioSequence"], "D#5 D#5 C5 D#5 D#5 D#5 C5 A4")
        self.assertEqual(current["bestExactCount"], 8)
        self.assertEqual(current["bestPrefixCount"], 8)
        self.assertEqual(current["audioRunSource"], "raw_detected_series")
        self.assertEqual(current["sourceImageUrl"], "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-a-source.png")
        self.assertEqual(completion["phraseExpansionReadyForReviewCount"], 1)
        self.assertGreaterEqual(completion["phraseExpansionAcceptedCount"], 2)
        mining = completion["staff4AdjacentMining"]
        self.assertEqual(mining["status"], "exact_audio_candidate")
        self.assertGreaterEqual(mining["exactCandidateCount"], 3)
        self.assertEqual(mining["bestCandidate"]["targetDirection"], "right-1")
        self.assertEqual(mining["bestCandidate"]["windowSequence"], "D#5 D#5 C5 D#5 D#5 D#5 C5 A4")
        self.assertEqual(completion["staff4AdjacentMiningStatus"], "exact_audio_candidate")
        self.assertIn("Audit the next Staff 4 8-note expansion", completion["nextAction"])

    def test_staff4_source_audio_rescan_feeds_exact_midi_search(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            fake_transcription = {
                "events": [
                    note("D#5", 0.00),
                    note("D#5", 0.12),
                    note("C5", 0.24),
                    note("D#5", 0.36),
                    note("D#5", 0.48),
                    note("D#5", 0.60),
                    note("C5", 0.72),
                    note("A4", 0.84),
                ],
                "scoreMatchCandidateNotes": [],
                "quality": {
                    "segmentationSource": "patched_staff4_source_rescan",
                    "pitchEventCount": 8,
                    "onsetEventCount": 8,
                    "spectralEventCount": 8,
                    "transitionTraceEventCount": 8,
                    "audioAgreementEventCount": 8,
                },
            }

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
                                "minimumDistinctPitchClasses": 2,
                                "detectedPitchClassSequence": "D# D# C D# D#",
                                "detectedPitchClassSequenceCompact": "D# C D#",
                                "scoreLocationVerified": True,
                                "scoreVisualAgreement": True,
                                "scoreVisualRangeAgreement": True,
                                "scoreVisibleNoteSequenceVerified": True,
                                "scoreVisibleExactNoteSequenceVerified": True,
                                "scoreSpellingAgreement": True,
                                "scoreActualPieceAgreement": True,
                                "scoreBoxCenterAgreement": True,
                                "audioTranscriptionAgreement": True,
                                "transcriptionScoreAgreement": True,
                                "truthEvidenceAccepted": True,
                                "scoreSnippetStatus": "exact_score_location_verified",
                                "scoreLocationStatus": "exact_score_location_verified",
                                "scoreSequenceLabel": "m. staff4-packet-1",
                                "referenceStart": 9,
                                "referenceEnd": 14,
                                "detectedSeries": {
                                    "sampleId": "accepted-anchor",
                                    "sourceWindow": "*8835-8925",
                                    "notes": [
                                        note("D#5", 20.225),
                                        note("D#5", 20.345),
                                        note("C5", 20.465),
                                        note("D#5", 20.585),
                                        note("D#5", 20.705),
                                    ],
                                },
                                "matchedDetectedNotes": [
                                    note("D#5", 20.225),
                                    note("D#5", 20.345),
                                    note("C5", 20.465),
                                    note("D#5", 20.585),
                                    note("D#5", 20.705),
                                ],
                                "scoreMatchedNotes": [
                                    {"note": "Eb5", "midi": 75},
                                    {"note": "Eb5", "midi": 75},
                                    {"note": "C5", "midi": 72},
                                    {"note": "Eb5", "midi": 75},
                                    {"note": "Eb5", "midi": 75},
                                ],
                                "score": {
                                    "assetId": "wieniawski-scherzo-tarantelle-vln",
                                    "cropStatus": "exact_score_location_verified",
                                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-verified.png",
                                    "actualSourceSnippetDisplayed": True,
                                    "visualRangeAgreement": True,
                                    "visibleScoreNoteSequenceVerified": True,
                                    "visibleScoreExactNoteSequenceVerified": True,
                                    "scoreSpellingAgreement": True,
                                    "scoreBoxCenterAgreement": True,
                                    "audioTranscriptionAgreement": True,
                                    "transcriptionScoreAgreement": True,
                                    "truthEvidenceAccepted": True,
                                },
                                "clip": {
                                    "sampleId": "accepted-anchor",
                                    "mediaUrl": "/api/curtis/media/sample/accepted-anchor",
                                    "audioUrl": "/api/curtis/media/sample/accepted-anchor/clip?start=20.225&end=22.535",
                                },
                                "transcription": {"sampleId": "accepted-anchor"},
                            }
                        ],
                    }
                ],
            }

            empty_owner_dir = Path(temp_dir) / "empty-owner-media"
            with patch("backend.app.staff4_audit.OWNER_MEDIA_DIR", empty_owner_dir), patch(
                "backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract
            ), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value=fake_transcription,
            ):
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
                    [{"id": "accepted-anchor", "path": str(source_path), "window": "*8835-8925"}],
                    [{"transcriptionId": "t1"}],
                )

        self.assertEqual(completion["staff4SourceAudioRescanStatus"], "rescanned")
        self.assertEqual(completion["staff4SourceAudioRescanRunCount"], 5)
        self.assertEqual(completion["staff4SourceAudioRescanAnchorStatus"], "reproduced")
        self.assertEqual(completion["staff4SourceAudioRescanAnchorReproducedCount"], 1)
        self.assertEqual(completion["staff4SourceAudioRescan"]["scanWindowCount"], 6)
        self.assertEqual(completion["staff4SourceAudioRescan"]["anchorReproductionStatus"], "reproduced")
        self.assertEqual(
            completion["staff4SourceAudioRescan"]["scanWindowLabels"],
            ["anchor_core", "right_1", "right_2", "right_3", "right_4"],
        )
        self.assertEqual(completion["phraseExpansionSourceAudioRescanRunCount"], 5)
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["audioRunSource"], "staff4_source_audio_rescan")
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["status"], "ready_for_truth_review")
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["direction"], "right-1")
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["targetSequence"], "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5 A4")
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["sourceImageUrl"], "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-a-source.png")
        self.assertEqual(completion["staff4AdjacentMiningStatus"], "exact_audio_candidate")
        self.assertEqual(completion["staff4AdjacentMining"]["bestCandidate"]["audioRunSource"], "staff4_source_audio_rescan")
        self.assertEqual(completion["staff4AdjacentMining"]["bestCandidate"]["windowSequence"], "D#5 D#5 C5 D#5 D#5 D#5 C5 A4")

    def test_staff4_source_audio_rescan_guided_anchor_reproduces_when_broad_pass_misses(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def exact_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                names = {72: "C5", 75: "D#5"}
                return [
                    {
                        "detector": "pyin",
                        "midi": expected_midi,
                        "note": names.get(expected_midi, "D#5"),
                        "confidence": 0.91,
                        "exact": True,
                        "frameCount": 6,
                    },
                    {
                        "detector": "spectral_onset",
                        "midi": expected_midi,
                        "note": names.get(expected_midi, "D#5"),
                        "confidence": 0.88,
                        "exact": True,
                        "frameCount": 1,
                    },
                ]

            fake_transcription = {
                "events": [
                    note("D5", 0.00),
                    note("D5", 0.12),
                    note("C5", 0.24),
                    note("D5", 0.36),
                    note("D5", 0.48),
                ],
                "scoreMatchCandidateNotes": [],
                "quality": {
                    "segmentationSource": "patched_staff4_source_rescan_broad_miss",
                    "pitchEventCount": 5,
                    "onsetEventCount": 5,
                    "spectralEventCount": 5,
                    "transitionTraceEventCount": 5,
                    "audioAgreementEventCount": 5,
                },
            }
            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "Eb5 Eb5 C5 Eb5 Eb5",
                "anchorMidiSequence": [75, 75, 72, 75, 75],
                "sampleId": "accepted-anchor",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 22.481,
                "match": {
                    "detectedSeries": {
                        "sampleId": "accepted-anchor",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value=fake_transcription,
            ), patch("backend.app.scanner.staff4_detector_votes_for_segment", side_effect=exact_detector_votes):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "accepted-anchor", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        guided_runs = [run for run in record["runs"] if run.get("runSource") == "staff4_anchor_guided_current_detector"]
        self.assertEqual(record["status"], "rescanned")
        self.assertEqual(record["guidedAnchorEventCount"], 5)
        self.assertEqual(record["quality"]["guidedAnchorStatus"], "reproduced")
        self.assertEqual(len(guided_runs), 1)
        self.assertEqual([item["midi"] for item in guided_runs[0]["notes"]], [75, 75, 72, 75, 75])
        self.assertTrue(all(item["audioAgreement"] for item in guided_runs[0]["notes"]))
        search = audio_window_search_for_exact_midi(
            record["runs"],
            [75, 75, 72, 75, 75],
            practice_day="2026-05-03",
            anchor_sample_id="accepted-anchor",
            anchor_absolute_start=8855.225,
        )
        exact_audio = [item for item in search["exactCandidates"] if item["audioAgreed"]]
        self.assertEqual(exact_audio[0]["audioRunSource"], "staff4_anchor_guided_current_detector")

    def test_staff4_source_audio_rescan_guided_adjacent_phrase_uses_source_neighbor_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def exact_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                return [
                    {
                        "detector": "pyin",
                        "midi": expected_midi,
                        "note": "C5" if expected_midi == 72 else "D#5",
                        "confidence": 0.91,
                        "exact": True,
                        "frameCount": 6,
                    },
                    {
                        "detector": "spectral_onset",
                        "midi": expected_midi,
                        "note": "C5" if expected_midi == 72 else "D#5",
                        "confidence": 0.89,
                        "exact": True,
                        "frameCount": 1,
                    },
                ]

            fake_transcription = {
                "events": [
                    note("D5", 0.00),
                    note("D5", 0.12),
                    note("C5", 0.24),
                    note("D5", 0.36),
                    note("D5", 0.48),
                ],
                "scoreMatchCandidateNotes": [],
                "quality": {
                    "segmentationSource": "patched_staff4_source_rescan_broad_miss",
                    "pitchEventCount": 5,
                    "onsetEventCount": 5,
                    "spectralEventCount": 5,
                    "transitionTraceEventCount": 5,
                    "audioAgreementEventCount": 5,
                },
            }
            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
            ]
            source_notes = [
                note("A5"),
                note("G5"),
                note("F5"),
                note("D#5"),
                note("D#5"),
                note("C5"),
                note("D#5"),
                note("D#5"),
                note("D#5"),
                note("C5"),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "D#5 D#5 C5 D#5 D#5",
                "anchorMidiSequence": [75, 75, 72, 75, 75],
                "sourceNotes": source_notes,
                "referenceStart": 3,
                "referenceEnd": 8,
                "sampleId": "accepted-anchor",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 22.481,
                "match": {
                    "detectedSeries": {
                        "sampleId": "accepted-anchor",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value=fake_transcription,
            ), patch("backend.app.scanner.staff4_detector_votes_for_segment", side_effect=exact_detector_votes):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "accepted-anchor", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        guided_runs = [run for run in record["runs"] if run.get("runSource") == "staff4_adjacent_guided_current_detector"]
        self.assertEqual(record["guidedAdjacentStatus"], "reproduced")
        self.assertEqual(record["guidedAdjacentTargetCount"], 2)
        self.assertEqual(record["guidedAdjacentReproducedCount"], 2)
        self.assertEqual(record["guidedAdjacentEventCount"], 7)
        self.assertEqual(len(guided_runs), 1)
        self.assertEqual([item["midi"] for item in guided_runs[0]["notes"]], [75, 75, 72, 75, 75, 75, 72])
        self.assertTrue(all(item["audioAgreement"] for item in guided_runs[0]["notes"]))
        search = audio_window_search_for_exact_midi(
            record["runs"],
            [75, 75, 72, 75, 75, 75, 72],
            practice_day="2026-05-03",
            anchor_sample_id="accepted-anchor",
            anchor_absolute_start=8855.225,
        )
        exact_audio = [item for item in search["exactCandidates"] if item["audioAgreed"]]
        self.assertEqual(exact_audio[0]["audioRunSource"], "staff4_adjacent_guided_current_detector")

    def test_staff4_adjacent_guided_phrase_sweeps_inferred_next_note_onset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)
            calls = {"count": 0}

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def offset_sensitive_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                calls["count"] += 1
                if calls["count"] in {11, 18}:
                    return [
                        {
                            "detector": "pyin",
                            "midi": 74,
                            "note": "D5",
                            "confidence": 0.72,
                            "exact": False,
                            "frameCount": 6,
                        },
                        {
                            "detector": "spectral_onset",
                            "midi": 74,
                            "note": "D5",
                            "confidence": 0.74,
                            "exact": False,
                            "frameCount": 1,
                        },
                    ]
                return [
                    {
                        "detector": "pyin",
                        "midi": expected_midi,
                        "note": "C5" if expected_midi == 72 else "D#5",
                        "confidence": 0.91,
                        "exact": True,
                        "frameCount": 6,
                    },
                    {
                        "detector": "spectral_onset",
                        "midi": expected_midi,
                        "note": "C5" if expected_midi == 72 else "D#5",
                        "confidence": 0.89,
                        "exact": True,
                        "frameCount": 1,
                    },
                ]

            fake_transcription = {
                "events": [note("D5", 0.00), note("D5", 0.12), note("C5", 0.24)],
                "scoreMatchCandidateNotes": [],
                "quality": {
                    "segmentationSource": "patched_staff4_source_rescan_broad_miss",
                    "pitchEventCount": 3,
                    "onsetEventCount": 3,
                    "spectralEventCount": 3,
                    "transitionTraceEventCount": 3,
                    "audioAgreementEventCount": 3,
                },
            }
            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
            ]
            source_notes = [
                note("A5"),
                note("G5"),
                note("F5"),
                note("D#5"),
                note("D#5"),
                note("C5"),
                note("D#5"),
                note("D#5"),
                note("D#5"),
                note("C5"),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "D#5 D#5 C5 D#5 D#5",
                "anchorMidiSequence": [75, 75, 72, 75, 75],
                "sourceNotes": source_notes,
                "referenceStart": 3,
                "referenceEnd": 8,
                "sampleId": "accepted-anchor",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 22.481,
                "match": {
                    "detectedSeries": {
                        "sampleId": "accepted-anchor",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value=fake_transcription,
            ), patch("backend.app.scanner.staff4_detector_votes_for_segment", side_effect=offset_sensitive_detector_votes):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "accepted-anchor", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        guided_runs = [run for run in record["runs"] if run.get("runSource") == "staff4_adjacent_guided_current_detector"]
        self.assertEqual(record["guidedAdjacentStatus"], "reproduced")
        self.assertEqual(len(guided_runs), 1)
        self.assertEqual([item["midi"] for item in guided_runs[0]["notes"]], [75, 75, 72, 75, 75, 75, 72])
        self.assertTrue(guided_runs[0]["notes"][5]["timingSweepUsed"])
        self.assertEqual(guided_runs[0]["notes"][5]["timingOffsetSeconds"], -0.06)
        self.assertGreater(len(guided_runs[0]["notes"][5]["detectorAttempts"]), 1)

    def test_staff4_adjacent_guided_failure_exposes_first_failed_source_note(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)
            calls = {"count": 0}

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def failing_next_note_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                calls["count"] += 1
                if calls["count"] in set(range(11, 20)) | set(range(25, 34)):
                    return [
                        {
                            "detector": "pyin",
                            "midi": 74,
                            "note": "D5",
                            "confidence": 0.72,
                            "exact": False,
                            "frameCount": 6,
                        },
                        {
                            "detector": "spectral_onset",
                            "midi": 74,
                            "note": "D5",
                            "confidence": 0.74,
                            "exact": False,
                            "frameCount": 1,
                        },
                    ]
                return [
                    {
                        "detector": "pyin",
                        "midi": expected_midi,
                        "note": "C5" if expected_midi == 72 else "D#5",
                        "confidence": 0.91,
                        "exact": True,
                        "frameCount": 6,
                    },
                    {
                        "detector": "spectral_onset",
                        "midi": expected_midi,
                        "note": "C5" if expected_midi == 72 else "D#5",
                        "confidence": 0.89,
                        "exact": True,
                        "frameCount": 1,
                    },
                ]

            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
            ]
            source_notes = [
                note("A5"),
                note("G5"),
                note("F5"),
                note("D#5"),
                note("D#5"),
                note("C5"),
                note("D#5"),
                note("D#5"),
                note("D#5"),
                note("C5"),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "D#5 D#5 C5 D#5 D#5",
                "anchorMidiSequence": [75, 75, 72, 75, 75],
                "sourceNotes": source_notes,
                "referenceStart": 3,
                "referenceEnd": 8,
                "sampleId": "accepted-anchor",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 22.481,
                "match": {
                    "detectedSeries": {
                        "sampleId": "accepted-anchor",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value={"events": [], "scoreMatchCandidateNotes": [], "quality": {}},
            ), patch("backend.app.scanner.staff4_detector_votes_for_segment", side_effect=failing_next_note_detector_votes):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "accepted-anchor", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        failure = record["guidedAdjacentFirstFailure"]
        self.assertEqual(record["guidedAdjacentStatus"], "not_reproduced")
        self.assertEqual(record["guidedAdjacentReproducedCount"], 0)
        self.assertEqual(failure["direction"], "right-1")
        self.assertEqual(failure["failedNoteIndex"], 5)
        self.assertEqual(failure["expectedMidi"], 75)
        self.assertEqual(failure["expectedNote"], "Eb5")
        self.assertEqual(failure["expectedSourceNote"], "Eb5")
        self.assertEqual(failure["expectedDetectorNote"], "D#5")
        self.assertEqual(failure["targetMidiSequence"], [75, 75, 72, 75, 75, 75])
        self.assertEqual(failure["attemptCount"], 9)
        self.assertEqual(failure["bestAttemptExactSourceCount"], 0)
        self.assertEqual(failure["failureKind"], "wrong_midi_detected")
        self.assertEqual(failure["bestAttemptObservedConsensusMidi"], 74)
        self.assertEqual(failure["bestAttemptObservedConsensusNote"], "D5")
        self.assertIn("current_detectors_did_not_reproduce_exact_midi", failure["reason"])

    def test_staff4_truth_manifest_adjacent_probe_keeps_accepted_anchor_fixed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)
            calls = {"count": 0}

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def no_a4_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                calls["count"] += 1
                self.assertEqual(expected_midi, midi_for_note("A4"))
                return []

            def score_note(label, midi):
                item = note("C5")
                item["note"] = label
                item["midi"] = midi
                return item

            source_notes = [score_note("A5", midi_for_note("A5")) for _ in range(9)] + [
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("C5", midi_for_note("C5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("C5", midi_for_note("C5")),
                score_note("A4", midi_for_note("A4")),
            ]
            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
                note("D#5", 22.829),
                note("C5", 23.117),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5",
                "anchorMidiSequence": [75, 75, 72, 75, 75, 75, 72],
                "sourceNotes": source_notes,
                "referenceStart": 9,
                "referenceEnd": 16,
                "sampleId": "Njh8_zq9_DM-8835",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 23.280,
                "anchorSource": "truth_manifest",
                "match": {
                    "detectedSeries": {
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value={"events": [], "scoreMatchCandidateNotes": [], "quality": {}},
            ), patch("backend.app.scanner.staff4_detector_votes_for_segment", side_effect=no_a4_detector_votes):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "Njh8_zq9_DM-8835", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        target = record["guidedAdjacentTargets"][0]
        failure = record["guidedAdjacentFirstFailure"]
        self.assertEqual(record["guidedAdjacentStatus"], "not_reproduced")
        self.assertEqual(target["seededAnchorNoteCount"], 7)
        self.assertEqual(target["reproducedNoteCount"], 7)
        self.assertEqual(target["sampleId"], "Njh8_zq9_DM-8835")
        self.assertEqual(target["sourceWindow"], "*8835-8925")
        self.assertEqual(failure["sampleId"], "Njh8_zq9_DM-8835")
        self.assertEqual(failure["sourceWindow"], "*8835-8925")
        self.assertEqual(failure["failedNoteIndex"], 7)
        self.assertEqual(failure["expectedMidi"], midi_for_note("A4"))
        self.assertEqual(failure["expectedNote"], "A4")
        self.assertEqual(failure["targetMidiSequence"], [75, 75, 72, 75, 75, 75, 72, 69])
        self.assertEqual(failure["continuationSearchStatus"], "no_prefilter_candidates")
        self.assertEqual(failure["continuationSearchCandidateCount"], 0)
        self.assertEqual(calls["count"], 9)

    def test_staff4_truth_manifest_adjacent_probe_can_promote_exact_a4_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)
            calls = {"count": 0}

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def exact_a4_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                calls["count"] += 1
                self.assertEqual(expected_midi, midi_for_note("A4"))
                return [
                    {
                        "detector": "pyin",
                        "midi": expected_midi,
                        "note": "A4",
                        "confidence": 0.91,
                        "exact": True,
                        "frameCount": 6,
                    },
                    {
                        "detector": "spectral_onset",
                        "midi": expected_midi,
                        "note": "A4",
                        "confidence": 0.88,
                        "exact": True,
                        "frameCount": 1,
                    },
                ]

            def score_note(label, midi):
                item = note("C5")
                item["note"] = label
                item["midi"] = midi
                return item

            source_notes = [score_note("A5", midi_for_note("A5")) for _ in range(9)] + [
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("C5", midi_for_note("C5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("C5", midi_for_note("C5")),
                score_note("A4", midi_for_note("A4")),
            ]
            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
                note("D#5", 22.829),
                note("C5", 23.117),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5",
                "anchorMidiSequence": [75, 75, 72, 75, 75, 75, 72],
                "sourceNotes": source_notes,
                "referenceStart": 9,
                "referenceEnd": 16,
                "sampleId": "Njh8_zq9_DM-8835",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 23.280,
                "anchorSource": "truth_manifest",
                "match": {
                    "detectedSeries": {
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value={"events": [], "scoreMatchCandidateNotes": [], "quality": {}},
            ), patch("backend.app.scanner.staff4_detector_votes_for_segment", side_effect=exact_a4_detector_votes):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "Njh8_zq9_DM-8835", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        guided_runs = [run for run in record["runs"] if run.get("runSource") == "staff4_adjacent_guided_current_detector"]
        self.assertEqual(record["guidedAdjacentStatus"], "reproduced")
        self.assertEqual(record["guidedAdjacentReproducedCount"], 1)
        self.assertEqual(len(guided_runs), 1)
        self.assertEqual([item["midi"] for item in guided_runs[0]["notes"]], [75, 75, 72, 75, 75, 75, 72, 69])
        self.assertTrue(all(item["audioAgreement"] for item in guided_runs[0]["notes"]))
        self.assertEqual(guided_runs[0]["notes"][0]["detectorSource"], "truth_manifest_accepted_audio_window")
        self.assertEqual(guided_runs[0]["notes"][-1]["detectorSource"], "staff4_adjacent_guided_current_detector")
        search = audio_window_search_for_exact_midi(
            record["runs"],
            [75, 75, 72, 75, 75, 75, 72, 69],
            practice_day="2026-05-03",
            anchor_sample_id="Njh8_zq9_DM-8835",
            anchor_absolute_start=8855.225,
        )
        exact_audio = [item for item in search["exactCandidates"] if item["audioAgreed"]]
        self.assertEqual(exact_audio[0]["audioRunSource"], "staff4_adjacent_guided_current_detector")
        self.assertEqual(calls["count"], 1)

    def test_staff4_truth_manifest_adjacent_probe_searches_beyond_bad_inferred_a4_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)
            calls = {"count": 0}

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target, seconds=17)
                return True, ""

            def staged_a4_detector_votes(_segment, expected_midi, _sr, _librosa, _numpy):
                calls["count"] += 1
                self.assertEqual(expected_midi, midi_for_note("A4"))
                if calls["count"] <= 9:
                    return [
                        {
                            "detector": "pyin",
                            "midi": midi_for_note("D5"),
                            "note": "D5",
                            "confidence": 0.81,
                            "exact": False,
                            "frameCount": 5,
                        },
                        {
                            "detector": "spectral_onset",
                            "midi": midi_for_note("D5"),
                            "note": "D5",
                            "confidence": 0.79,
                            "exact": False,
                            "frameCount": 1,
                        },
                    ]
                return [
                    {
                        "detector": "pyin",
                        "midi": expected_midi,
                        "note": "A4",
                        "confidence": 0.92,
                        "exact": True,
                        "frameCount": 6,
                    },
                    {
                        "detector": "spectral_onset",
                        "midi": expected_midi,
                        "note": "A4",
                        "confidence": 0.9,
                        "exact": True,
                        "frameCount": 1,
                    },
                ]

            def continuation_candidates(**kwargs):
                self.assertEqual(kwargs["expected_midi"], midi_for_note("A4"))
                self.assertGreaterEqual(kwargs["search_start"], 23.0)
                return [
                    {
                        "startSeconds": 24.02,
                        "endSeconds": 24.18,
                        "durationSeconds": 0.16,
                        "expectedMidi": midi_for_note("A4"),
                        "expectedNote": "A4",
                        "expectedHarmonicEnergy": 0.8,
                        "dominantMidi": midi_for_note("A4"),
                        "dominantNote": "A4",
                        "dominantHarmonicEnergy": 0.8,
                        "expectedRank": 1,
                        "expectedToDominantRatio": 1.0,
                        "prefilterSource": "test_prefilter",
                    }
                ]

            def score_note(label, midi):
                item = note("C5")
                item["note"] = label
                item["midi"] = midi
                return item

            source_notes = [score_note("A5", midi_for_note("A5")) for _ in range(9)] + [
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("C5", midi_for_note("C5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("Eb5", midi_for_note("D#5")),
                score_note("C5", midi_for_note("C5")),
                score_note("A4", midi_for_note("A4")),
            ]
            anchor_notes = [
                note("D#5", 20.225),
                note("D#5", 20.550),
                note("C5", 20.817),
                note("D#5", 21.629),
                note("D#5", 22.361),
                note("D#5", 22.829),
                note("C5", 23.117),
            ]
            anchor = {
                "practiceDay": "2026-05-03",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "anchorSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5",
                "anchorMidiSequence": [75, 75, 72, 75, 75, 75, 72],
                "sourceNotes": source_notes,
                "referenceStart": 9,
                "referenceEnd": 16,
                "sampleId": "Njh8_zq9_DM-8835",
                "sourceWindow": "*8835-8925",
                "anchorLocalStartSeconds": 20.225,
                "anchorLocalEndSeconds": 23.280,
                "anchorSource": "truth_manifest",
                "match": {
                    "detectedSeries": {
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "notes": anchor_notes,
                    },
                    "matchedDetectedNotes": anchor_notes,
                },
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value={"events": [], "scoreMatchCandidateNotes": [], "quality": {}},
            ), patch("backend.app.scanner.staff4_expected_pitch_prefilter_candidates", side_effect=continuation_candidates), patch(
                "backend.app.scanner.staff4_detector_votes_for_segment", side_effect=staged_a4_detector_votes
            ):
                record = staff4_source_audio_rescan_record(
                    anchor=anchor,
                    sample={"id": "Njh8_zq9_DM-8835", "path": str(source_path), "window": "*8835-8925"},
                    source_path=source_path,
                    scan_window={
                        "label": "anchor_core",
                        "scanLocalStartSeconds": 16.225,
                        "scanLocalEndSeconds": 32.535,
                    },
                )

        guided_runs = [run for run in record["runs"] if run.get("runSource") == "staff4_adjacent_guided_current_detector"]
        self.assertEqual(record["guidedAdjacentStatus"], "reproduced")
        self.assertEqual(record["guidedAdjacentReproducedCount"], 1)
        self.assertEqual(len(guided_runs), 1)
        self.assertEqual([item["midi"] for item in guided_runs[0]["notes"]], [75, 75, 72, 75, 75, 75, 72, 69])
        self.assertEqual(guided_runs[0]["notes"][-1]["detectorSource"], "staff4_adjacent_continuation_search")
        self.assertTrue(guided_runs[0]["notes"][-1]["continuationSearchUsed"])
        self.assertEqual(calls["count"], 10)

    def test_completion_surfaces_staff4_adjacent_failure_without_losing_detector_detail(self):
        failure = {
            "direction": "right-1",
            "targetSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5",
            "targetMidiSequence": [75, 75, 72, 75, 75, 75],
            "failedNoteIndex": 5,
            "expectedMidi": 75,
            "expectedNote": "Eb5",
            "failureKind": "wrong_midi_detected",
            "bestAttemptOffsetSeconds": -0.06,
            "bestAttemptObservedConsensusMidi": 74,
            "bestAttemptObservedConsensusNote": "D5",
        }
        fake_rescan = {
            "version": "staff4_source_audio_rescan_v11",
            "status": "rescanned",
            "runCount": 1,
            "eventCount": 0,
            "candidateEventCount": 0,
            "guidedAnchorEventCount": 5,
            "guidedAdjacentEventCount": 0,
            "guidedAdjacentTargetCount": 1,
            "guidedAdjacentReproducedCount": 0,
            "guidedAdjacentStatus": "not_reproduced",
            "guidedAdjacentFirstFailure": failure,
            "runs": [],
        }
        fake_expansion = {
            "targetCount": 1,
            "acceptedExpansionCount": 0,
            "readyForReviewCount": 0,
            "blockedExpansionCount": 1,
            "rejectedRegressionCount": 1,
            "audioRunCount": 4,
            "rawDetectedAudioRunCount": 0,
            "sourceAudioRescanRunCount": 1,
            "currentBest": {
                "direction": "right-1",
                "targetSequence": "D#5 D#5 C5 D#5 D#5 D#5",
                "anchorSequence": "D#5 D#5 C5 D#5 D#5",
                "expectedNextScoreNote": "D#5",
                "observedNextAudioNote": "D5",
            },
        }
        fake_mining = {
            "status": "not_found",
            "searchedWindowCount": 32,
            "exactCandidateCount": 0,
            "sourceAudioRescanRunCount": 1,
            "sourceAudioRescanEventCount": 5,
            "sourceAudioRescanGuidedAdjacentStatus": "not_reproduced",
            "sourceAudioRescanGuidedAdjacentTargetCount": 1,
            "sourceAudioRescanGuidedAdjacentFirstFailure": failure,
        }
        with patch("backend.app.scanner.staff4_source_audio_rescan", return_value=fake_rescan), patch(
            "backend.app.scanner.source_phrase_expansion_harness",
            return_value=fake_expansion,
        ), patch("backend.app.scanner.staff4_adjacent_phrase_mining", return_value=fake_mining):
            completion = build_transcription_completion(
                {"scoreReferenceTargetCount": 1},
                {"recordCount": 1, "records": []},
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
                [],
                [],
            )

        surfaced = completion["staff4SourceAudioRescanAdjacentFirstFailure"]
        self.assertEqual(surfaced["expectedNote"], "Eb5")
        self.assertEqual(surfaced["bestAttemptObservedConsensusNote"], "D5")
        self.assertEqual(completion["staff4AdjacentMining"]["sourceAudioRescanGuidedAdjacentFirstFailure"], failure)
        self.assertIn("Eb5", completion["nextAction"])
        self.assertIn("D5", completion["nextAction"])

    def test_staff4_truth_manifest_anchor_persists_without_visible_match_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "staff4-source.wav"
            write_tiny_wav(source_path)

            def fake_extract(_source, target, _start, _end):
                write_tiny_wav(target)
                return True, ""

            fake_transcription = {
                "events": [
                    note("D#5", 0.00),
                    note("D#5", 0.12),
                    note("C5", 0.24),
                    note("D#5", 0.36),
                    note("D#5", 0.48),
                    note("D#5", 0.60),
                    note("C5", 0.72),
                ],
                "scoreMatchCandidateNotes": [],
                "quality": {
                    "segmentationSource": "patched_staff4_source_rescan",
                    "pitchEventCount": 7,
                    "onsetEventCount": 7,
                    "spectralEventCount": 7,
                    "transitionTraceEventCount": 7,
                    "audioAgreementEventCount": 7,
                },
            }

            daily_records = {
                "recordCount": 1,
                "audioEvidenceRecordCount": 1,
                "transcribedRecordCount": 1,
                "records": [
                    {
                        "practiceDay": "2026-05-03",
                        "transcription": {
                            "scoreSequenceMatchCount": 0,
                            "scoreLocationVerifiedCount": 0,
                            "detectedSeries": [
                                {
                                    "sampleId": "Njh8_zq9_DM-8835",
                                    "sourceWindow": "*8835-8925",
                                    "sourceTitle": "5-3-26",
                                    "notes": [
                                        note("D#5", 20.225),
                                        note("D#5", 20.345),
                                        note("C5", 20.465),
                                        note("D#5", 20.585),
                                        note("D#5", 20.705),
                                    ],
                                }
                            ],
                        },
                        "matchGroups": [],
                        "candidateMatchGroups": [],
                    }
                ],
            }

            with patch("backend.app.scanner.run_ffmpeg_extract_audio", side_effect=fake_extract), patch(
                "backend.app.scanner.transcribe_audio_array",
                return_value=fake_transcription,
            ):
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
                    [{"id": "Njh8_zq9_DM-8835", "path": str(source_path), "window": "*8835-8925"}],
                    [{"transcriptionId": "t1"}],
                )

        self.assertNotEqual(completion["staff4SourceAudioRescanStatus"], "no_staff4_anchor")
        self.assertEqual(completion["staff4SourceAudioRescanStatus"], "rescanned")
        self.assertEqual(completion["staff4SourceAudioRescanRunCount"], 5)
        self.assertEqual(completion["staff4SourceAudioRescanAnchorStatus"], "reproduced")
        self.assertEqual(completion["staff4SourceAudioRescanAnchorReproducedCount"], 1)
        self.assertEqual(completion["staff4SourceAudioRescan"]["scanWindowCount"], 5)
        self.assertEqual(completion["staff4SourceAudioRescan"]["anchorReproductionStatus"], "reproduced")
        self.assertGreater(completion["staff4SourceAudioRescanEventCount"], 0)
        self.assertGreaterEqual(completion["phraseExpansionHarness"]["anchorCount"], 1)
        self.assertEqual(completion["phraseExpansionHarness"]["status"], "ready")
        self.assertEqual(completion["phraseExpansionHarness"]["acceptedAnchorNoteCount"], 7)
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["status"], "blocked_no_audio_candidate")
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["targetSequence"], "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5 A4")
        self.assertEqual(completion["phraseExpansionHarness"]["currentBest"]["expectedNextScoreNote"], "A4")
        self.assertEqual(completion["staff4AdjacentMining"]["anchorCount"], 1)
        self.assertEqual(completion["staff4AdjacentMiningStatus"], "not_found")
        self.assertEqual(completion["staff4AdjacentMining"]["exactCandidateCount"], 0)
        self.assertNotIn("Convert one local source-score measure", completion["nextAction"])

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
                            "scoreVisibleNoteSequenceVerified": True,
                            "scoreVisibleExactNoteSequenceVerified": True,
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
                                "visibleScoreNoteSequenceVerified": True,
                                "visibleScoreExactNoteSequenceVerified": True,
                                "scoreSpellingAgreement": True,
                                "scoreBoxCenterAgreement": True,
                                "audioTranscriptionAgreement": True,
                                "transcriptionScoreAgreement": True,
                                "truthEvidenceAccepted": True,
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

    def test_actual_source_snippet_requires_visible_note_sequence_verification(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "symbolic_score_phrase_match",
                            "matchedNoteRun": 5,
                            "minimumMatchedNoteRun": 5,
                            "detectedPitchClassSequenceCompact": "A# D C A# D",
                            "scoreLocationVerified": True,
                            "scoreVisualAgreement": True,
                            "scoreVisualRangeAgreement": True,
                            "scoreSpellingAgreement": True,
                            "scoreActualPieceAgreement": True,
                            "scoreSnippetStatus": "exact_score_location_verified",
                            "scoreLocationStatus": "exact_score_location_verified",
                            "scoreSequenceLabel": "mm. 2-4",
                            "referenceStart": 2,
                            "referenceEnd": 7,
                            "score": {
                                "assetId": "wieniawski-scherzo-tarantelle-vln",
                                "cropStatus": "exact_score_location_verified",
                                "measureLabel": "mm. 2-4",
                                "imageUrl": "/assets/score/too-broad.png",
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

        self.assertEqual(accepted_measure_match_count(daily_records), 0)
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
                            "matchedDetectedNotes": [
                                note("D6", 0.00),
                                note("D6", 0.12),
                                note("D#6", 0.24),
                                note("D6", 0.36),
                                note("D6", 0.48),
                                note("A#5", 0.60),
                                note("G5", 0.72),
                            ],
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
        self.assertEqual(completion["sourceVerificationTargetTopStatus"], "source_score_exact_midi_sequence_not_found")
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
        self.assertEqual(check_card["detail"], "1/7 MIDI overlap")
        self.assertEqual(completion["sourceVerificationTargets"][0]["status"], "source_verification_required")
        self.assertIn("not accepted score evidence", completion["sourceVerificationTargets"][0]["limit"])
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreCheckStatus"], "source_score_exact_midi_sequence_not_found")
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreBestOverlap"], 1)
        self.assertEqual(
            completion["sourceVerificationTargets"][0]["sourceScoreReferenceSequence"],
            "A5 G5 F5 A5 G5 F5 A5 G#5 F5 Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5 A4",
        )
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreBestOverlapSequence"], "G5")
        self.assertEqual(completion["sourceVerificationTargets"][0]["sourceScoreMatchCriterion"], "exact_midi_sequence")
        self.assertGreaterEqual(completion["sourceVerificationTargets"][0]["sourceScoreCandidateGlyphCount"], 1)
        workbench = build_truth_workbench({}, daily_records, {"benchmarkCount": 1, "wrongScoreNoteRegressionCount": 1})
        self.assertEqual(workbench["status"], "ready")
        self.assertEqual(workbench["sourceTargetQueueCount"], 1)
        self.assertEqual(workbench["queuedItems"][0]["sequence"], "D D D# D D A# G")
        self.assertEqual(workbench["acceptedEvidenceReadyCount"], 0)

    def test_media_sample_lookup_can_use_owner_media_file_for_truth_anchor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            owner_dir = Path(temp_dir) / "owner-media"
            owner_dir.mkdir()
            sample_path = owner_dir / "Njh8_zq9_DM-8835-browser.webm"
            sample_path.write_bytes(b"owner-media")
            with patch("backend.app.staff4_audit.OWNER_MEDIA_DIR", owner_dir):
                sample = media_sample_for_id([], "Njh8_zq9_DM-8835")

        self.assertEqual(sample["id"], "Njh8_zq9_DM-8835")
        self.assertEqual(sample["source"], "owner_media_fallback")
        self.assertEqual(Path(sample["path"]).name, "Njh8_zq9_DM-8835-browser.webm")

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
                            "detectedPitchClassSequence": "A G D C",
                            "detectedPitchClassSequenceCompact": "A G D C",
                            "matchedDetectedNotes": [
                                note("A5", 0.00),
                                note("G5", 0.12),
                                note("D6", 0.24),
                                note("C6", 0.36),
                            ],
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

        self.assertEqual(target["sequence"], "A G D C")
        self.assertTrue(target["sourceScoreChecked"])
        self.assertFalse(target["sourceScoreVerified"])
        self.assertEqual(target["sourceScoreBestOverlap"], 2)
        self.assertEqual(target["sourceScoreBestOverlapSequence"], "A5 G5")
        self.assertEqual(target["sourceScoreBestOverlapMidiSequence"], "81 79")
        self.assertEqual(target["sourceScoreMatchCriterion"], "exact_midi_sequence")

    def test_source_verification_targets_accept_audio_agreed_exact_midi_phrase(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "matchGroups": [
                        {
                            "status": "reference_sequence_match",
                            "matchedNoteRun": 5,
                            "detectedPitchClassSequence": "G F A G# F",
                            "detectedPitchClassSequenceCompact": "G F A G# F",
                            "matchedDetectedNotes": [
                                note("G5", 0.00),
                                note("F5", 0.12),
                                note("A5", 0.24),
                                note("G#5", 0.36),
                                note("F5", 0.48),
                            ],
                            "scoreLocationVerified": False,
                            "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "score": {"assetId": "wieniawski-scherzo-tarantelle-vln"},
                            "clip": {"mediaUrl": "/api/curtis/media/sample/exact-midi-target"},
                            "transcription": {"sampleId": "exact-midi-target"},
                        }
                    ],
                }
            ]
        }

        target = source_verification_target_top(daily_records)

        self.assertEqual(target["sequence"], "G F A G# F")
        self.assertTrue(target["sourceScoreChecked"])
        self.assertTrue(target["sourceScoreVerified"])
        self.assertTrue(target["sourceScoreAudioAgreed"])
        self.assertEqual(target["sourceScoreCheckStatus"], "source_score_exact_midi_sequence_verified")
        self.assertEqual(target["sourceScoreBestOverlap"], 5)
        self.assertEqual(target["sourceScoreQueryExactSequence"], "G5 F5 A5 G#5 F5")
        self.assertEqual(target["sourceScoreQueryMidiSequence"], "79 77 81 80 77")
        self.assertEqual(target["sourceScoreBestOverlapSequence"], "G5 F5 A5 G#5 F5")
        self.assertEqual(target["sourceScoreBestOverlapMidiSequence"], "79 77 81 80 77")
        self.assertEqual(target["sourceScoreMatchCriterion"], "exact_midi_sequence")

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
