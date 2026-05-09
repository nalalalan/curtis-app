import unittest

from backend.app.reference_corpus import calibration_anchor_for_item, public_reference_training_state


class ReferenceCorpusTests(unittest.TestCase):
    def test_scale_title_becomes_calibration_anchor(self):
        anchor = calibration_anchor_for_item({"sourceTitle": "G major scale violin calibration"})

        self.assertEqual(anchor["title"], "G major scale")
        self.assertEqual(anchor["materialType"], "calibration_scale")
        self.assertEqual(anchor["referenceKind"], "title_labeled_calibration")
        self.assertEqual(anchor["referenceTarget"]["keySignature"]["label"], "G major / 1 sharp")

    def test_public_reference_state_reports_metadata_items_without_repertoire_claim(self):
        state = {
            "referenceCorpus": {
                "publicYouTubeIndexedAt": "2026-05-09T03:00:00+00:00",
                "publicYouTubeItems": [
                    {
                        "id": "abc123",
                        "title": "Violin G major scale - slow",
                        "seedTitle": "G major scale",
                        "referenceKind": "public_labeled_youtube_seed",
                        "analysisState": "metadata_ready_media_blocked",
                    }
                ],
                "blockers": ["youtube_data_api_returns_metadata_not_video_media"],
            }
        }

        training = public_reference_training_state(state)

        self.assertEqual(training["status"], "metadata_indexed")
        self.assertEqual(training["storedItemCount"], 1)
        self.assertEqual(training["items"][0]["seedTitle"], "G major scale")
        self.assertIn("audio fingerprints require a permitted media path", training["limit"])
