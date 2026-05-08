import unittest

from backend.app.piece_id import apply_source_correction_gate
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
        pieces = accepted_source_pieces({}, {"youtube": []}, [])
        by_title = {piece["title"]: piece for piece in pieces}

        haydn = by_title["Haydn Symphony No. 94, IV. Finale, Violin I part"]
        wieniawski = by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]

        self.assertIn("Haydn finale", haydn["tip"])
        self.assertIn("Scherzo-Tarantelle", wieniawski["tip"])
        self.assertNotIn("Haydn", wieniawski["tip"])
        self.assertEqual(
            wieniawski["daily"]["2026-05-02"]["tip"],
            wieniawski["tip"],
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
        by_title = {anchor["title"]: anchor for anchor in training["anchors"]}

        self.assertEqual(training["confirmedSourceCount"], 2)
        self.assertEqual(training["blindAudioMatchCount"], 0)
        self.assertEqual(training["scoreAlignedWindowCount"], 0)
        self.assertEqual(training["label"], "2 anchors / 0 score matches")
        self.assertEqual(by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]["sampleCount"], 1)
        self.assertEqual(
            by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]["status"],
            "source_label_only",
        )
        self.assertEqual(
            by_title["Wieniawski Scherzo-Tarantelle, Op. 16"]["scoreAlignment"]["status"],
            "not_configured",
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


if __name__ == "__main__":
    unittest.main()
