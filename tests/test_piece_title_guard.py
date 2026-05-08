import unittest

from backend.app.piece_id import apply_source_correction_gate
from backend.app.scanner import enriched_pieces


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


if __name__ == "__main__":
    unittest.main()
