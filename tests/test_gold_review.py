import unittest

from backend.app.gold_review import (
    MAX_ADAPTIVE_REVIEW_QUEUE,
    best_review_note_slice,
    build_gold_review_loop,
    record_gold_review_item,
)


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
        self.assertEqual(review["queueStatus"], "current_batch_covered_by_review")
        self.assertEqual(review["queueCount"], 0)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "accepted_candidate_covered")

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
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["labelSource"], "human_review")
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["labelNoiseModel"], "noisy_human_visual_audio_review")
        self.assertGreater(review["trainingSet"]["recentExamples"][0]["humanSignalWeight"], 0)

    def test_latest_review_label_wins_when_user_corrects_mistake(self):
        state = {}
        base = {
            "reviewItemId": "gold-correctable-label",
            "type": "audio_phrase",
            "sampleId": "sample-correctable",
            "detectedNotes": ["A4", "D5", "E5"],
            "acceptedNotes": ["A4", "D5", "E5"],
            "startSeconds": 30.0,
            "endSeconds": 31.0,
        }

        record_gold_review_item(state, {**base, "status": "accepted_truth"})
        flipped = record_gold_review_item(
            state,
            {
                **base,
                "status": "rejected_mismatch",
                "reason": "mistaken accept corrected by reviewer",
            },
        )
        review = build_gold_review_loop(state, {"records": []})

        self.assertEqual(review["labelCount"], 1)
        self.assertEqual(review["acceptedCount"], 0)
        self.assertEqual(review["rejectedCount"], 1)
        self.assertEqual(review["correctedLabelCount"], 1)
        self.assertEqual(review["reviewRevisionCount"], 1)
        self.assertEqual(review["trainingExampleCount"], 1)
        self.assertEqual(review["trainingPositiveCount"], 0)
        self.assertEqual(review["trainingNegativeCount"], 1)
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["label"], "negative")
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["labelRevision"], 2)
        self.assertTrue(review["trainingSet"]["recentExamples"][0]["correctedLabel"])
        self.assertEqual(flipped["goldReviewItem"]["previousStatus"], "accepted_truth")
        self.assertEqual(flipped["goldReviewItem"]["labelHistory"][0]["status"], "accepted_truth")
        truth = state["truthWorkbench"]["items"][0]
        self.assertEqual(truth["itemId"], "gold-correctable-label")
        self.assertEqual(truth["status"], "rejected_mismatch")

    def test_corrected_rejection_can_become_positive_training_example(self):
        state = {}
        base = {
            "reviewItemId": "gold-correctable-reject",
            "type": "audio_phrase",
            "sampleId": "sample-correctable-reject",
            "detectedNotes": ["D5", "E5", "F#5"],
            "acceptedNotes": ["D5", "E5", "F#5"],
        }

        record_gold_review_item(state, {**base, "status": "rejected_mismatch"})
        record_gold_review_item(state, {**base, "status": "accepted_truth"})
        review = build_gold_review_loop(state, {"records": []})

        self.assertEqual(review["labelCount"], 1)
        self.assertEqual(review["acceptedCount"], 1)
        self.assertEqual(review["rejectedCount"], 0)
        self.assertEqual(review["correctedLabelCount"], 1)
        self.assertEqual(review["trainingPositiveCount"], 1)
        self.assertEqual(review["trainingNegativeCount"], 0)
        self.assertEqual(review["recentItems"][0]["previousStatus"], "rejected_mismatch")

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

    def test_score_copy_review_queue_from_source_snippet(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "pieces": [
                        {
                            "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "sourceTitle": "5-3-26",
                            "score": {
                                "scoreAssetId": "wieniawski-vln",
                                "scoreSource": "local IMSLP solo part",
                                "keySignature": {
                                    "accidentalType": "flat",
                                    "accidentals": ["Bb", "Eb"],
                                },
                                "symbolicScore": {
                                    "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                                    "sourceSnippets": [
                                        {
                                            "measureLabel": "m. 16",
                                            "imageUrl": "/assets/score/m16-source.png",
                                            "sourceReviewImageUrl": "/assets/score/m16-review.png",
                                            "visibleScoreExactNoteSequence": ["Eb5", "D5", "C5"],
                                            "status": "source_score_copy_candidate",
                                        }
                                    ],
                                },
                            },
                        }
                    ],
                }
            ]
        }

        review = build_gold_review_loop({}, daily_records)
        candidate = review["queue"][0]

        self.assertEqual(candidate["reviewType"], "score_copy")
        self.assertEqual(candidate["reviewTask"], "score_copy_exact_notation")
        self.assertEqual(candidate["reviewTrainingLane"], "score_copy")
        self.assertEqual(candidate["scoreNotes"], ["Eb5", "D5", "C5"])
        self.assertEqual(candidate["detectedNotes"], ["Eb5", "D5", "C5"])
        self.assertEqual(candidate["sourceReviewImageUrl"], "/assets/score/m16-review.png")
        self.assertTrue(candidate["originalScoreSnippet"])
        self.assertFalse(candidate["sourceImageRequiredForOriginalScore"])
        self.assertEqual(candidate["scoreLocation"], "m. 16")
        self.assertIn("tuplets", candidate["notationCopyAspects"])
        self.assertEqual(review["scoreCopyQueueCount"], 1)
        self.assertEqual(review["scoreQueueCount"], 0)

    def test_score_copy_review_queue_allows_single_source_note(self):
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "pieces": [
                        {
                            "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                            "score": {
                                "symbolicScore": {
                                    "sourceSnippets": [
                                        {
                                            "measureLabel": "m. 16",
                                            "sourceReviewImageUrl": "/assets/score/m16-a4.png",
                                            "visibleScoreExactNoteSequence": ["A4"],
                                        }
                                    ],
                                },
                            },
                        }
                    ],
                }
            ]
        }

        review = build_gold_review_loop({}, daily_records)

        self.assertEqual(review["scoreCopyQueueCount"], 1)
        self.assertEqual(review["queue"][0]["reviewType"], "score_copy")
        self.assertEqual(review["queue"][0]["scoreNotes"], ["A4"])

    def test_score_copy_acceptance_trains_source_copy_without_score_evidence(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-score-copy-m16",
                "type": "score_copy",
                "status": "accepted_truth",
                "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                "scoreLocation": "m. 16",
                "scoreImageUrl": "/assets/score/m16-source.png",
                "sourceReviewImageUrl": "/assets/score/m16-review.png",
                "detectedNotes": ["Eb5", "D5", "C5"],
                "acceptedNotes": ["Eb5", "D5", "C5"],
                "scoreNotes": ["Eb5", "D5", "C5"],
            },
        )

        review = build_gold_review_loop(state, {"records": []})
        truth = state["truthWorkbench"]["items"][0]

        self.assertEqual(review["acceptedScoreCopyCount"], 1)
        self.assertEqual(review["acceptedScorePhraseCount"], 0)
        self.assertEqual(review["scoreReadyTruthCount"], 0)
        self.assertEqual(review["acceptedEvidenceReadyCount"], 0)
        self.assertEqual(review["trainingScoreCopyExampleCount"], 1)
        self.assertEqual(review["trainingSet"]["recentExamples"][0]["task"], "score_copy_exact_notation")
        self.assertFalse(truth["gateState"]["acceptedEvidenceReady"])

    def test_requested_repertoire_score_copy_catalog_is_training_only(self):
        review = build_gold_review_loop({}, {"records": []}, limit=20, include_source_copy_catalog=True)

        titles = {item["pieceTitle"] for item in review["scoreCopyQueue"]}

        self.assertEqual(review["audioQueueCount"], 0)
        self.assertGreaterEqual(review["sourceCopyTrainingQueueCount"], 13)
        self.assertIn("Haydn Symphony No. 94, IV, Violin I", titles)
        self.assertIn("Paganini Moto Perpetuo, Op. 11, Solo violin", titles)
        self.assertIn("Mozart Le nozze di Figaro Overture, Violin I", titles)
        first = review["scoreCopyQueue"][0]
        self.assertEqual(first["reviewTask"], "score_copy_exact_notation")
        self.assertEqual(first["reviewTrainingLane"], "score_copy")
        self.assertTrue(first["sourcePieceTrainingOnly"])
        self.assertTrue(first["notationCopyOnly"])
        self.assertFalse(first["originalScoreSnippet"])
        self.assertTrue(first["sourceImageRequiredForOriginalScore"])
        self.assertTrue(first["sourceNotationAbc"])
        self.assertTrue(first["copyNotationAbc"])
        self.assertIn("durations", first["notationCopyAspects"])
        self.assertIn("stem_directions", first["notationCopyAspects"])

    def test_score_copy_review_does_not_suppress_audio_review_for_same_notes(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-score-copy-source-only",
                "type": "score_copy",
                "status": "accepted_truth",
                "scoreLocation": "m. 16",
                "scoreImageUrl": "/assets/score/m16-source.png",
                "detectedNotes": ["Eb5", "D5", "C5"],
                "acceptedNotes": ["Eb5", "D5", "C5"],
                "scoreNotes": ["Eb5", "D5", "C5"],
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "audio-still-needs-review",
                                "mediaUrl": "/api/curtis/media/sample/audio-still-needs-review",
                                "audioUrl": "/api/curtis/media/sample/audio-still-needs-review/clip?start=0&end=1",
                                "startSeconds": 10.0,
                                "endSeconds": 11.0,
                                "localStartSeconds": 0.0,
                                "localEndSeconds": 1.0,
                                "notes": [
                                    note("Eb5", 75, 0.0),
                                    note("D5", 74, 0.2),
                                    note("C5", 72, 0.4),
                                ],
                            }
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(review["queueCount"], 1)
        self.assertEqual(review["queue"][0]["reviewType"], "audio_phrase")
        self.assertEqual(review["queue"][0]["reviewLearningStatus"], "new_pattern")

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

    def test_single_rejected_pattern_is_hidden_from_active_queue(self):
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
        self.assertEqual(review["queueStatus"], "current_batch_exhausted_by_learning")
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["softRejectedPatternCount"], 0)
        self.assertEqual(review["rejectedPatternCount"], 1)
        self.assertEqual(review["rejectionDigest"]["hiddenRejectedPatternCount"], 1)
        self.assertEqual(review["reviewLearningStatus"], "reducing_review_load")
        self.assertEqual(review["suppressionThreshold"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "rejected_pattern_hidden")

    def test_repeated_rejected_pattern_is_suppressed_instead_of_requeued(self):
        state = {}
        for index, sample_id in enumerate(["old-sample-a", "old-sample-b"]):
            record_gold_review_item(
                state,
                {
                    "reviewItemId": f"gold-reject-pattern-{index}",
                    "type": "audio_phrase",
                    "status": "rejected_mismatch",
                    "sampleId": sample_id,
                    "detectedNotes": ["Eb5", "Eb5", "C5"],
                    "reason": "repeated wrong pattern should not keep returning",
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
        self.assertEqual(review["queueStatus"], "current_batch_exhausted_by_learning")
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["reviewLearningStatus"], "reducing_review_load")
        self.assertEqual(review["rejectionDigest"]["hiddenRejectedPatternCount"], 1)
        self.assertEqual(review["suppressionThreshold"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningKey"], "75 72")

    def test_rejected_clip_fingerprint_is_hidden_even_when_detected_notes_change(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-window",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "same-visible-clip",
                "startSeconds": 120.0,
                "endSeconds": 120.75,
                "detectedNotes": ["A4", "B4", "C5"],
                "reason": "same clip should not keep coming back with a different bad guess",
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "same-visible-clip",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("D5", 74, 0.0),
                                    note("E5", 76, 0.2),
                                    note("F5", 77, 0.4),
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
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "rejected_candidate_hidden")
        self.assertGreater(review["rejectionDigest"]["hiddenRejectedCandidateFingerprintCount"], 0)

    def test_later_acceptance_marks_previously_rejected_clip_fingerprint_as_covered(self):
        state = {}
        rejected = {
            "reviewItemId": "gold-reject-window",
            "type": "audio_phrase",
            "status": "rejected_mismatch",
            "sampleId": "same-visible-clip",
            "startSeconds": 120.0,
            "endSeconds": 120.75,
            "detectedNotes": ["A4", "B4", "C5"],
        }
        record_gold_review_item(state, rejected)
        record_gold_review_item(
            state,
            {
                **rejected,
                "reviewItemId": "gold-accept-window",
                "status": "accepted_truth",
                "acceptedNotes": ["D5", "E5", "F5"],
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "same-visible-clip",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("D5", 74, 0.0),
                                    note("E5", 76, 0.2),
                                    note("F5", 77, 0.4),
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
        self.assertEqual(review["queueStatus"], "current_batch_covered_by_review")
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "accepted_candidate_covered")

    def test_overlapping_rejected_clip_window_is_hidden_even_when_item_id_and_notes_shift(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-overlap",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "same-bad-area",
                "startSeconds": 8843.047,
                "endSeconds": 8846.737,
                "detectedNotes": ["D6", "F5", "A#4", "A4"],
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "same-bad-area",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 8835.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("F5", 77, 8.639),
                                    note("A#4", 70, 8.9),
                                    note("A4", 69, 9.1),
                                    note("A6", 93, 10.3),
                                    note("G6", 91, 11.0),
                                    note("F#6", 90, 11.587),
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
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "rejected_candidate_hidden")
        self.assertTrue(review["suppressedQueuePreview"][0]["reviewCandidateRejectedOverlapKeys"])

    def test_non_overlapping_window_from_same_sample_stays_reviewable(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-overlap",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "same-sample-new-area",
                "startSeconds": 8843.047,
                "endSeconds": 8846.737,
                "detectedNotes": ["D6", "F5", "A#4", "A4"],
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "same-sample-new-area",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 8855.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("D5", 74, 0.0),
                                    note("E5", 76, 0.2),
                                    note("F5", 77, 0.4),
                                    note("G5", 79, 0.6),
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
        self.assertEqual(review["suppressedByLearningCount"], 0)

    def test_later_acceptance_marks_overlapping_clip_window_as_already_covered(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-reject-overlap",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "sampleId": "same-bad-area",
                "startSeconds": 8843.047,
                "endSeconds": 8846.737,
                "detectedNotes": ["D6", "F5", "A#4", "A4"],
            },
        )
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-accept-overlap",
                "type": "audio_phrase",
                "status": "accepted_truth",
                "sampleId": "same-bad-area",
                "startSeconds": 8843.6,
                "endSeconds": 8846.6,
                "acceptedNotes": ["F5", "A#4", "A4", "A6"],
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "same-bad-area",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 8835.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("F5", 77, 8.639),
                                    note("A#4", 70, 8.9),
                                    note("A4", 69, 9.1),
                                    note("A6", 93, 10.3),
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
        self.assertEqual(review["suppressedByLearningCount"], 1)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "accepted_candidate_covered")
        self.assertTrue(review["suppressedQueuePreview"][0]["reviewCandidateAcceptedOverlapKeys"])

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

    def test_rejected_primary_window_suppresses_overlapping_adaptive_windows(self):
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

        self.assertEqual(review["queueStatus"], "current_batch_exhausted_by_learning")
        self.assertFalse(review["adaptiveMode"])
        self.assertEqual(review["queueCount"], 0)
        self.assertGreater(review["adaptiveSuppressedByLearningCount"], 0)
        self.assertEqual(review["suppressedQueuePreview"][0]["reviewLearningStatus"], "rejected_candidate_hidden")

    def test_adaptive_review_generates_fresh_windows_when_primary_queue_is_only_soft_rejected(self):
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
                                "sampleId": f"soft-reject-refresh-{sample_index}",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 120.0 + sample_index,
                                "localStartSeconds": 0.0,
                                "notes": [note(name, midi, index * 0.2) for index, (name, midi) in enumerate(zip(names, midis))],
                            }
                            for sample_index in range(3)
                        ]
                    },
                }
            ]
        }
        primary = build_gold_review_loop(state, daily_records)["queue"][0]
        for sample_index in range(3):
            record_gold_review_item(
                state,
                {
                    **primary,
                    "reviewItemId": f"gold-audio-phrase-soft-reject-refresh-{sample_index}-0-6",
                    "sampleId": f"soft-reject-refresh-{sample_index}",
                    "type": primary["reviewType"],
                    "status": "rejected_mismatch",
                    "reason": "human review negative but not infallible",
                },
            )

        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(review["queueStatus"], "adaptive_review_ready")
        self.assertEqual(review["adaptiveReason"], "primary_queue_suppressed_by_learning")
        self.assertGreater(review["adaptiveCandidateCount"], 0)
        self.assertTrue(review["queue"][0]["adaptiveReview"])
        self.assertNotIn("soft_rejected_pattern", [item["reviewLearningStatus"] for item in review["queue"][:3]])

    def test_overlapping_adaptive_windows_do_not_requeue_rejected_repeated_note_area(self):
        state = {}
        names = ["C6", "C6", "C6", "C6", "C6", "C6", "D5", "E5", "F5", "G5", "A5", "B5"]
        midis = [84, 84, 84, 84, 84, 84, 74, 76, 77, 79, 81, 83]
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "adaptive-quality",
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

        self.assertEqual(review["queueStatus"], "current_batch_exhausted_by_learning")
        self.assertEqual(review["queueCount"], 0)
        self.assertGreater(review["adaptiveSuppressedByLearningCount"], 0)

    def test_adaptive_review_penalizes_wild_fast_register_jumps_from_rejections(self):
        state = {}
        record_gold_review_item(
            state,
            {
                "reviewItemId": "gold-fast-bad",
                "type": "audio_phrase",
                "status": "rejected_mismatch",
                "practiceDay": "2026-05-03",
                "sampleId": "fast-bad",
                "startSeconds": 10,
                "endSeconds": 14,
                "detectedNotes": ["C4", "G#3", "A3", "C4", "E6", "B5", "G#5", "G5", "G#5", "A5", "G#5", "A#5"],
                "reason": "one_or_more_notes_wrong",
            },
        )
        daily_records = {
            "records": [
                {
                    "practiceDay": "2026-05-03",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": "fast-bad",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 10.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("C4", 60, 0.0),
                                    note("G#3", 56, 0.2),
                                    note("A3", 57, 0.4),
                                    note("C4", 60, 0.6),
                                    note("E6", 88, 0.8),
                                    note("B5", 83, 1.0),
                                    note("G#5", 80, 1.2),
                                    note("G5", 79, 1.4),
                                    note("G#5", 80, 1.6),
                                    note("A5", 81, 1.8),
                                    note("G#5", 80, 2.0),
                                    note("A#5", 82, 2.2),
                                ],
                            },
                            {
                                "sampleId": "steady-window",
                                "sourceTitle": "5-3-26",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": 20.0,
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note("E5", 76, 0.0),
                                    note("F#5", 78, 0.2),
                                    note("G5", 79, 0.4),
                                    note("A5", 81, 0.6),
                                    note("B5", 83, 0.8),
                                    note("C6", 84, 1.0),
                                ],
                            },
                        ]
                    },
                }
            ]
        }

        review = build_gold_review_loop(state, daily_records)

        self.assertEqual(review["rejectionInsights"]["dominantIssue"], "rejected_fast_dense_unstable_windows")
        self.assertEqual(review["rejectionInsights"]["rejectedFastDenseCount"], 1)
        self.assertEqual(review["rejectionInsights"]["rejectedUnstableRegisterCount"], 1)
        first = review["queue"][0]
        self.assertEqual(first["sampleId"], "steady-window")
        self.assertLess(first.get("unstableFastPenalty", 0), 1)

    def test_adaptive_review_queue_is_capped_after_quality_ranking(self):
        state = {}
        records = []
        for series_index in range(MAX_ADAPTIVE_REVIEW_QUEUE + 12):
            names = ["D5", "E5", "F5", "G5", "A5", "B5", "C6", "D6"]
            midis = [74, 76, 77, 79, 81, 83, 84, 86]
            records.append(
                {
                    "practiceDay": f"2026-05-{series_index % 9 + 1:02d}",
                    "transcription": {
                        "detectedSeries": [
                            {
                                "sampleId": f"adaptive-cap-{series_index}",
                                "sourceTitle": "practice",
                                "sourceUrl": "https://www.youtube.com/watch?v=abc",
                                "startSeconds": float(series_index * 10),
                                "localStartSeconds": 0.0,
                                "notes": [
                                    note(name, midi, note_index * 0.2)
                                    for note_index, (name, midi) in enumerate(zip(names, midis))
                                ],
                            }
                        ]
                    },
                }
            )
        daily_records = {"records": records}
        primary = build_gold_review_loop(state, daily_records, limit=200)["queue"]
        for candidate in primary:
            record_gold_review_item(
                state,
                {
                    **candidate,
                    "type": candidate["reviewType"],
                    "status": "rejected_mismatch",
                    "reason": "primary batch reviewed",
                },
            )

        review = build_gold_review_loop(state, daily_records, limit=200)

        self.assertEqual(review["queueStatus"], "current_batch_exhausted_by_learning")
        self.assertEqual(review["queueCount"], 0)
        self.assertGreaterEqual(review["adaptiveSuppressedByLearningCount"], MAX_ADAPTIVE_REVIEW_QUEUE)


if __name__ == "__main__":
    unittest.main()
