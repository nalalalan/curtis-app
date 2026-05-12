import unittest

from backend.app.piece_id import apply_source_correction_gate, source_hint_text
from backend.app.scanner import accepted_source_pieces, derive_review, enriched_pieces
from backend.app.corrections import correction_for_item, title_rejected_for_item


class PieceTitleGuardTests(unittest.TestCase):
    def test_model_only_identification_is_withheld(self):
        result = {
            "status": "piece_identified",
            "title": "Wrong Composer - Wrong Piece",
            "proposedTitle": "Wrong Composer - Wrong Piece",
            "confidence": "clear",
            "confidenceScore": 96,
            "completionPercent": 88,
            "todayCompletionPercent": 88,
            "evidenceQuality": "verified_piece_id",
            "sourceUrl": "https://www.youtube.com/watch?v=test999",
            "sampleId": "test999-1",
            "sourceStartSeconds": 120,
            "sourceEndSeconds": 165,
        }

        gated = apply_source_correction_gate({}, result)

        self.assertEqual(gated["status"], "piece_unconfirmed_title")
        self.assertEqual(gated["title"], "Piece being identified")
        self.assertEqual(gated["completionPercent"], 0)
        self.assertEqual(gated["todayCompletionPercent"], 0)
        self.assertEqual(gated["evidenceQuality"], "unconfirmed_model_title")
        self.assertEqual(gated.get("withheldTitle"), "Wrong Composer - Wrong Piece")
        self.assertEqual(gated.get("proposedTitle"), "")
        self.assertEqual(gated.get("candidateTitle"), "")
        self.assertEqual(gated.get("topCandidates"), [])

    def test_old_verified_piece_rows_are_not_repertoire(self):
        old_piece = {
            "title": "Old False Positive",
            "confidence": "clear",
            "confidenceScore": 93,
            "completionPercent": 88,
            "todayCompletionPercent": 88,
            "evidenceQuality": "verified_piece_id",
            "reviewVersion": "audio_piece_id_v8",
            "sourceUrl": "https://www.youtube.com/watch?v=old999",
            "sampleId": "old999-1",
            "sourceStartSeconds": 20,
            "sourceEndSeconds": 60,
            "candidateEvidence": "Old model-only title.",
            "daily": {
                "2026-05-01": {
                    "completionPercent": 88,
                    "tip": "Old label-specific tip.",
                },
            },
        }

        normalized = enriched_pieces([old_piece], "2026-05-01", [])[0]

        self.assertEqual(normalized["title"], "Piece being identified")
        self.assertEqual(normalized["confidence"], "unknown")
        self.assertEqual(normalized["completionPercent"], 0)
        self.assertEqual(normalized["evidenceQuality"], "weak")
        self.assertEqual(normalized.get("candidateTitle"), "")
        self.assertEqual(normalized["daily"]["2026-05-01"]["completionPercent"], 0)
        self.assertEqual(
            normalized["daily"]["2026-05-01"]["tip"],
            "Piece identification pending verified source evidence.",
        )

    def test_confirmed_five_one_haydn_label_survives(self):
        result = {
            "status": "piece_identified",
            "title": "Wrong Composer - Wrong Piece",
            "proposedTitle": "Wrong Composer - Wrong Piece",
            "confidence": "clear",
            "confidenceScore": 91,
            "completionPercent": 88,
            "todayCompletionPercent": 88,
            "evidenceQuality": "verified_piece_id",
            "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
            "sourceTitle": "5-1-26",
            "sampleId": "wDfVpTU4I_I-1",
            "sourceStartSeconds": 120,
            "sourceEndSeconds": 165,
        }

        accepted = apply_source_correction_gate({}, result)

        self.assertEqual(accepted["status"], "piece_identified")
        self.assertEqual(
            accepted["title"],
            "Haydn Symphony No. 94, IV. Finale, Violin I part",
        )
        self.assertEqual(accepted["evidenceQuality"], "human_verified_source_label")
        self.assertEqual(accepted["completionPercent"], 0)
        self.assertEqual(accepted["todayCompletionPercent"], 0)
        self.assertIn("Haydn finale", accepted["immediateTip"])

    def test_five_two_wieniawski_label_is_source_confirmed(self):
        result = {
            "status": "piece_identified",
            "title": "Piece being identified",
            "proposedTitle": "",
            "confidence": "unknown",
            "confidenceScore": 0,
            "completionPercent": 88,
            "todayCompletionPercent": 88,
            "evidenceQuality": "verified_piece_id",
            "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
            "sourceTitle": "5-2-26",
            "sampleId": "K38CgZhvF3Q-600",
            "sourceStartSeconds": 600,
            "sourceEndSeconds": 690,
        }

        accepted = apply_source_correction_gate({}, result)

        self.assertEqual(accepted["status"], "piece_identified")
        self.assertEqual(accepted["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(accepted["evidenceQuality"], "human_verified_source_label")
        self.assertEqual(accepted["completionPercent"], 0)
        self.assertEqual(accepted["todayCompletionPercent"], 0)
        self.assertIn("Scherzo-Tarantelle", accepted["immediateTip"])
        self.assertNotIn("Haydn", accepted["immediateTip"])

    def test_wieniawski_is_rejected_for_five_one_but_not_five_two(self):
        five_one = {
            "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
            "sourceTitle": "5-1-26",
            "sampleId": "wDfVpTU4I_I-1",
        }
        five_two = {
            "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
            "sourceTitle": "5-2-26",
            "sampleId": "K38CgZhvF3Q-600",
        }

        self.assertTrue(
            title_rejected_for_item("Wieniawski Scherzo-Tarantelle, Op. 16", {}, five_one)
        )
        self.assertFalse(
            title_rejected_for_item("Wieniawski Scherzo-Tarantelle, Op. 16", {}, five_two)
        )
        self.assertEqual(
            correction_for_item({}, five_two)["acceptedTitle"],
            "Wieniawski Scherzo-Tarantelle, Op. 16",
        )

    def test_source_confirmed_daily_tips_are_source_specific(self):
        pieces = derive_review({"youtube": []}, {}, [], {})["pieces"]
        by_title = {piece["title"]: piece for piece in pieces}

        haydn = by_title["Haydn Symphony No. 94, IV. Finale, Violin I part"]
        wieniawski = by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]

        self.assertIn("Haydn finale", haydn["tip"])
        self.assertIn("Scherzo-Tarantelle", wieniawski["tip"])
        self.assertNotIn("Haydn", wieniawski["tip"])
        self.assertEqual(
            wieniawski["daily"]["2026-05-02"]["tip"],
            "Scherzo-Tarantelle: keep the bow stroke small, even, and rhythm-first before tempo.",
        )
        self.assertEqual(
            wieniawski["daily"]["2026-05-03"]["tip"],
            "Scherzo-Tarantelle: preserve the bounce without letting repetitions grow large.",
        )

    def test_training_state_separates_source_anchors_from_audio_matches(self):
        media_samples = [
            {
                "id": "K38CgZhvF3Q-600",
                "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                "title": "5-2-26",
                "window": "*600-645",
            }
        ]
        existing = {
            "pieceIdentifications": [
                {
                    "status": "piece_identified",
                    "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                    "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "sourceTitle": "5-2-26",
                    "sampleId": "K38CgZhvF3Q-600",
                    "evidenceQuality": "human_verified_source_label",
                }
            ]
        }

        review = derive_review({"youtube": []}, existing, media_samples, {})
        training = review["training"]
        by_source = {anchor["sourceTitle"]: anchor for anchor in training["anchors"]}

        self.assertEqual(training["confirmedSourceCount"], 3)
        self.assertEqual(training["referenceTargetCount"], 3)
        self.assertEqual(training["blindAudioMatchCount"], 0)
        self.assertEqual(training["scoreAlignedWindowCount"], 0)
        self.assertEqual(training["label"], "3 refs / 0 score alignments")
        self.assertEqual(by_source["5-2-26"]["sampleCount"], 1)
        self.assertEqual(by_source["5-3-26"]["sampleCount"], 0)
        self.assertEqual(
            by_source["5-2-26"]["status"],
            "source_label_only",
        )
        self.assertEqual(
            by_source["5-2-26"]["scoreAlignment"]["status"],
            "not_configured",
        )
        self.assertEqual(
            by_source["5-2-26"]["referenceTargetStatus"],
            "reference_target_ready",
        )
        self.assertIn(
            "main theme bars 5-9",
            by_source["5-2-26"]["scoreAlignment"]["referenceTarget"]["passageVocabulary"],
        )

    def test_training_state_counts_only_pre_correction_audio_matches(self):
        media_samples = [
            {
                "id": "K38CgZhvF3Q-600",
                "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                "title": "5-2-26",
                "window": "*600-645",
            }
        ]
        existing = {
            "pieceIdentifications": [
                {
                    "status": "piece_identified",
                    "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                    "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "sourceTitle": "5-2-26",
                    "sampleId": "K38CgZhvF3Q-600",
                    "evidenceQuality": "human_verified_source_label",
                    "modelMatchedAcceptedTitle": True,
                }
            ]
        }

        review = derive_review({"youtube": []}, existing, media_samples, {})

        self.assertEqual(review["training"]["blindAudioMatchCount"], 1)
        self.assertEqual(review["training"]["scoreAlignedWindowCount"], 0)

    def test_five_three_scherzo_tarantelle_is_source_confirmed_by_date_title(self):
        result = {
            "status": "piece_identified",
            "title": "Piece being identified",
            "proposedTitle": "",
            "confidence": "unknown",
            "confidenceScore": 0,
            "completionPercent": 91,
            "todayCompletionPercent": 91,
            "evidenceQuality": "verified_piece_id",
            "sourceTitle": "5-3-26",
            "sampleId": "local-5-3-26-600",
            "sourceStartSeconds": 600,
            "sourceEndSeconds": 690,
        }

        accepted = apply_source_correction_gate({}, result)

        self.assertEqual(accepted["status"], "piece_identified")
        self.assertEqual(accepted["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(accepted["evidenceQuality"], "human_verified_source_label")
        self.assertEqual(accepted["completionPercent"], 0)
        self.assertIn("Scherzo-Tarantelle", accepted["immediateTip"])

    def test_five_three_title_only_sample_counts_as_wieniawski_anchor(self):
        media_samples = [
            {
                "id": "local-5-3-26-600",
                "title": "5-3-26",
                "window": "*600-645",
            }
        ]

        review = derive_review({"youtube": []}, {}, media_samples, {})
        by_source = {anchor["sourceTitle"]: anchor for anchor in review["training"]["anchors"]}
        by_title = {piece["title"]: piece for piece in review["pieces"]}

        self.assertEqual(by_source["5-3-26"]["sampleCount"], 1)
        self.assertEqual(by_source["5-3-26"]["status"], "source_label_only")
        self.assertIn("2026-05-02", by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]["daily"])
        self.assertIn("2026-05-03", by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]["daily"])

    def test_source_hint_includes_reference_alignment_target(self):
        sample = {
            "id": "K38CgZhvF3Q-600",
            "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
            "title": "5-2-26",
            "window": "*600-645",
        }

        hint = source_hint_text(sample)

        self.assertIn("Wieniawski Scherzo-Tarantelle", hint)
        self.assertIn("score target", hint)
        self.assertIn("main theme bars 5-9", hint)

    def test_source_hint_includes_five_three_same_day_prior(self):
        sample = {
            "id": "local-5-3-26-600",
            "title": "5-3-26",
            "window": "*600-645",
        }

        hint = source_hint_text(sample)

        self.assertIn("5/3 violin footage", hint)
        self.assertIn("Wieniawski Scherzo-Tarantelle", hint)


if __name__ == "__main__":
    unittest.main()
