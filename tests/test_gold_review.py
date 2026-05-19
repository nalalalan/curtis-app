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
        self.assertEqual(candidate["acceptanceMode"], "binary_exact_claim")
        self.assertTrue(candidate["binaryOnly"])
        self.assertEqual(candidate["detectedNotes"], ["G5", "F5", "A5", "G#5", "F5"])
        self.assertEqual(candidate["detectedMidiSequence"], [79, 77, 81, 80, 77])
        self.assertEqual(candidate["clip"]["audioUrl"], "/api/curtis/media/sample/sample-a/clip?start=0.000&end=1.150")

    def test_review_queue_can_surface_long_binary_phrase_candidates(self):
        names = ["Eb5", "D5", "C5", "Bb4", "D5", "Eb5", "F5", "G5", "F5", "Eb5", "D5", "C5"]
        midis = [75, 74, 72, 70, 74, 75, 77, 79, 77, 75, 74, 72]
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "pieces": [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16"}],
                    "transcription": {
                        "detectedSeries": [
                            {
                                "id": "series-long",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "sampleId": "sample-long",
                                "startSeconds": 180.0,
                                "localStartSeconds": 0.0,
                                "notes": [note(name, midi, index * 0.18) for index, (name, midi) in enumerate(zip(names, midis))],
                            }
                        ]
                    },
                }
            ]
        }

        candidate = build_gold_review_loop({}, daily_records)["queue"][0]

        self.assertEqual(candidate["reviewKind"], "long_audio_phrase_candidate")
        self.assertEqual(candidate["acceptanceMode"], "binary_exact_claim")
        self.assertTrue(candidate["binaryOnly"])
        self.assertGreaterEqual(candidate["detectedNoteCount"], 10)
        self.assertIn("Reject if one note is wrong", candidate["reviewQuestion"])

    def test_review_queue_only_publishes_playable_clip_windows(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "sample-long",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 200.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("D5", 74, 0.0),
                                    note("E5", 76, 3.0),
                                    note("F5", 77, 6.0),
                                    note("G5", 79, 9.0),
                                    note("A5", 81, 12.0),
                                    note("B5", 83, 16.0),
                                    note("C6", 84, 18.0),
                                ],
                            }
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop({}, daily_records)

        self.assertEqual(review["queueCount"], 1)
        clip = review["queue"][0]["clip"]
        self.assertLessEqual(clip["localEndSeconds"] - clip["localStartSeconds"], 15.0)
        self.assertEqual(review["queue"][0]["detectedNotes"], ["D5", "E5", "F5", "G5", "A5"])

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
        self.assertEqual(result["goldReviewItem"]["trainingLabel"], "positive")
        self.assertEqual(result["goldReviewItem"]["reviewTask"], "audio_exact_notes")
        self.assertEqual(result["truthMirror"]["truthItem"]["status"], "accepted_truth")
        self.assertEqual(review["acceptedCount"], 1)
        self.assertEqual(review["acceptedAudioPhraseCount"], 1)
        self.assertEqual(review["trainingExampleCount"], 1)
        self.assertEqual(review["trainingPositiveCount"], 1)
        self.assertEqual(review["queueStatus"], "adaptive_review_ready")
        self.assertGreater(review["queueCount"], 0)

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

    def test_score_phrase_acceptance_collapses_repeated_detected_notes(self):
        state = {}

        result = record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-score-duplicate-d",
                "type": "score_phrase",
                "status": "accepted_truth",
                "sampleId": "sample-dup",
                "practiceDay": "2026-05-03",
                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                "sourceTitle": "5-3-26",
                "startSeconds": 10.0,
                "endSeconds": 11.0,
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "acceptedNotes": ["D5", "D5"],
                "scoreNotes": ["D5"],
                "scoreLocation": "m. 16",
                "scoreSource": "IMSLP source PDF",
                "scoreImageUrl": "/assets/score/m16.png",
            },
        )

        item = result["goldReviewItem"]
        self.assertEqual(item["status"], "accepted_truth")
        self.assertEqual(item["normalizedAcceptedMidiSequence"], [74])
        self.assertEqual(item["normalizedScoreMidiSequence"], [74])
        self.assertEqual(result["truthMirror"]["truthItem"]["status"], "accepted_truth")

    def test_score_phrase_acceptance_still_rejects_wrong_order_after_duplicate_collapse(self):
        state = {}

        with self.assertRaises(ValueError):
            record_gold_review_item(
                state,
                {
                    "reviewItemId": "gold-score-wrong-eb",
                    "type": "score_phrase",
                    "status": "accepted_truth",
                    "sampleId": "sample-wrong",
                    "acceptedNotes": ["Eb5", "D5", "C5"],
                    "scoreNotes": ["Eb5", "Eb5", "C5"],
                    "scoreLocation": "m. 16",
                    "scoreImageUrl": "/assets/score/m16.png",
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
        self.assertEqual(review["trainingExampleCount"], 1)
        self.assertEqual(review["trainingNegativeCount"], 1)
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["label"], "negative")
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["task"], "audio_exact_notes")

    def test_binary_long_phrase_review_becomes_training_example(self):
        state = {}

        result = record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-long-negative",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "sample-long",
                "detectedNotes": ["Eb5", "D5", "C5", "Bb4", "D5", "Eb5"],
                "startSeconds": 20.0,
                "endSeconds": 23.0,
            },
        )
        review = build_gold_review_loop(state, {"records": []})

        self.assertEqual(result["goldReviewItem"]["reviewTask"], "audio_long_phrase_exact_notes")
        self.assertEqual(result["goldReviewItem"]["trainingLabel"], "negative")
        self.assertEqual(review["trainingLongPhraseExampleCount"], 1)
        self.assertEqual(review["trainingSet"]["negativeLongPhraseCount"], 1)

    def test_score_review_becomes_score_alignment_training_example(self):
        state = {}

        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-score-negative",
                "type": "audio_score_match",
                "status": "rejected_mismatch",
                "sampleId": "sample-score",
                "detectedNotes": ["A4"],
                "scoreNotes": ["B4"],
                "scoreLocation": "m. 16",
            },
        )
        review = build_gold_review_loop(state, {"records": []})

        self.assertEqual(review["trainingScoreExampleCount"], 1)
        self.assertEqual(review["trainingNegativeScoreExampleCount"], 1)
        self.assertEqual(review["trainingPositiveScoreExampleCount"], 0)
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["task"], "audio_score_exact_match")
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["label"], "negative")

    def test_candidate_group_extracts_score_labels_into_score_review(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "pieces": [{"title": "Wieniawski Scherzo-Tarantelle, Op. 16"}],
                    "candidateMatchGroups": [
                        {
                            "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "scoreExactNoteSequenceLabel": "Eb5 Eb5 C5 Eb5 Eb5",
                            "scoreSequenceLabel": "m. 16",
                            "clip": {
                                "sampleId": "sample-score-candidate",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "sourceTitle": "5-3-26",
                                "mediaUrl": "/api/curtis/media/sample/sample-score-candidate",
                                "audioUrl": "/api/curtis/media/sample/sample-score-candidate/clip?start=0.000&end=2.500",
                                "startSeconds": 8835.0,
                                "endSeconds": 8837.5,
                                "localStartSeconds": 20.0,
                                "localEndSeconds": 22.5,
                            },
                            "transcription": {
                                "sampleId": "sample-score-candidate",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "notes": [
                                    note("Eb5", 75, 20.0),
                                    note("Eb5", 75, 20.2),
                                    note("C5", 72, 20.4),
                                    note("Eb5", 75, 20.6),
                                    note("Eb5", 75, 20.8),
                                ],
                            },
                        }
                    ],
                }
            ]
        }

        candidate = build_gold_review_loop({}, daily_records)["queue"][0]

        self.assertEqual(candidate["reviewType"], "audio_score_match")
        self.assertEqual(candidate["reviewTask"], "audio_score_exact_match")
        self.assertEqual(candidate["scoreNotes"], ["Eb5", "Eb5", "C5", "Eb5", "Eb5"])
        self.assertEqual(candidate["scoreLocation"], "m. 16")
        self.assertEqual(candidate["reviewTrainingLane"], "score_alignment")
        self.assertEqual(candidate["scoreAgreementStatus"], "exact_midi_agreement")
        self.assertTrue(candidate["scoreAgreement"])

    def test_score_review_candidates_rank_before_audio_only_candidates(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "candidateMatchGroups": [
                        {
                            "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "scoreExactNoteSequenceLabel": "Eb5 Eb5 C5 Eb5 Eb5",
                            "scoreSequenceLabel": "m. 16",
                            "clip": {
                                "sampleId": "score-sample",
                                "mediaUrl": "/api/curtis/media/sample/score-sample",
                                "audioUrl": "/api/curtis/media/sample/score-sample/clip?start=0&end=2",
                                "startSeconds": 100.0,
                                "endSeconds": 102.0,
                                "localStartSeconds": 0.0,
                                "localEndSeconds": 2.0,
                            },
                            "transcription": {
                                "sampleId": "score-sample",
                                "notes": [
                                    note("Eb5", 75, 0.0),
                                    note("Eb5", 75, 0.2),
                                    note("C5", 72, 0.4),
                                    note("Eb5", 75, 0.6),
                                    note("Eb5", 75, 0.8),
                                ],
                            },
                        }
                    ],
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "audio-sample",
                                "mediaUrl": "/api/curtis/media/sample/audio-sample",
                                "audioUrl": "/api/curtis/media/sample/audio-sample/clip?start=0&end=2",
                                "startSeconds": 200.0,
                                "endSeconds": 202.0,
                                "notes": [
                                    note("A4", 69, 0.0),
                                    note("B4", 71, 0.2),
                                    note("C5", 72, 0.4),
                                    note("D5", 74, 0.6),
                                    note("E5", 76, 0.8),
                                ],
                            }
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop({}, daily_records)

        self.assertEqual(review["scoreQueueCount"], 1)
        self.assertEqual(review["scoreExactAgreementQueueCount"], 1)
        self.assertEqual(review["queue"][0]["reviewTask"], "audio_score_exact_match")
        self.assertEqual(review["queue"][0]["sampleId"], "score-sample")

    def test_rejected_pattern_suppresses_future_matching_candidates(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-pattern",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "old-sample",
                "detectedNotes": ["Eb5", "Eb5", "C5"],
                "reason": "same wrong pattern should not keep returning",
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "new-sample",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("Eb5", 75, 0.0),
                                    note("Eb5", 75, 0.2),
                                    note("C5", 72, 0.4),
                                ],
                            }
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(review["rawQueueCount"], 1)
        self.assertEqual(review["queueCount"], 0)
        self.assertEqual(review["queueStatus"], "current_batch_exhausted_by_rejections")
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["reviewLearningStatus"], "reducing_review_load")
        self.assertEqual(review["rejectionDigest"]["hiddenRejectedPatternCount"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "rejected_pattern")

    def test_later_acceptance_releases_previously_rejected_pattern(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-pattern",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "old-sample",
                "detectedNotes": ["D5", "D5"],
            },
        )
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-accept-pattern",
                "type": "audio_phrase",
                "status": "accepted_truth",
                "sampleId": "accepted-sample",
                "acceptedNotes": ["D5"],
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "new-sample",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("D5", 74, 0.0),
                                    note("D5", 74, 0.2),
                                    note("D5", 74, 0.4),
                                ],
                            }
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(review["rawQueueCount"], 1)
        self.assertEqual(review["queueCount"], 1)
        self.assertEqual(review["queueStatus"], "review_queue_ready")
        self.assertEqual(review["suppressedByLearningCount"], 0)
        self.assertEqual(review["queue"][0]["reviewLearningStatus"], "accepted_pattern")

    def test_adaptive_review_generates_more_windows_after_primary_candidate_is_rejected(self):
        state = {}
        names = ["D5", "E5", "F5", "G5", "A5", "B5", "C6", "D6"]
        midis = [74, 76, 77, 79, 81, 83, 84, 86]
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "adaptive-sample",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0,
                                "localStartSeconds": 0.0,
                                "notes": [note(name, midi, index * 0.2) for index, (name, midi) in enumerate(zip(names, midis))],
                            }
                        ]
                    },
                }
            ]
        }
        first = build_gold_review_loop(state, daily_records)["queue"][0]
        record_gold_review_item(
            state,
            {
                **first,
                "type": first["reviewType"],
                "status": "rejected_mismatch",
                "reason": "primary window is wrong",
            },
        )

        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(review["queueStatus"], "adaptive_review_ready")
        self.assertTrue(review["adaptiveMode"])
        self.assertGreater(review["adaptiveCandidateCount"], 0)
        self.assertGreater(review["queueCount"], 0)
        self.assertTrue(review["queue"][0]["adaptiveReview"])
        self.assertNotEqual(review["queue"][0]["reviewItemId"], first["reviewItemId"])


if __name__ == "__main__":
    unittest.main()
