import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from backend.app.analyzer import sample_is_violin_positive
from backend.app.media import sample_id, sample_window, sample_windows
import tools.curtis_owner_media_sync as owner_sync


class MediaSamplingTests(unittest.TestCase):
    def test_sample_window_keeps_legacy_first_window_shape(self):
        item = {"id": "video", "durationSeconds": 3600}

        self.assertEqual(sample_window(item), "*600-690")

    def test_sample_windows_spread_across_long_practice_video(self):
        item = {"id": "video", "durationSeconds": 18000}

        windows = sample_windows(item, max_windows=4)

        self.assertEqual(windows, ["*600-690", "*5940-6030", "*11880-11970", "*17880-17970"])

    def test_dense_sample_windows_include_early_practice_probes(self):
        item = {"id": "video", "durationSeconds": 18000}

        windows = sample_windows(item, max_windows=8)

        self.assertIn("*300-390", windows)
        self.assertIn("*900-990", windows)
        self.assertLess(windows.index("*300-390"), windows.index("*5940-6030"))

    def test_sample_id_includes_window_start(self):
        self.assertEqual(sample_id("abc", "*5940-6030"), "abc-5940")

    def test_violin_presence_gate_accepts_only_positive_samples(self):
        self.assertTrue(sample_is_violin_positive({"violinPresence": "violin_positive"}))
        self.assertTrue(sample_is_violin_positive({"containsViolin": True}))
        self.assertFalse(sample_is_violin_positive({"violinPresence": "not_violin_or_unclear"}))
        self.assertFalse(sample_is_violin_positive({"violinPresence": "unverified"}))

    def test_owner_sync_prioritizes_cached_violin_positive_samples(self):
        with TemporaryDirectory() as directory:
            media_dir = Path(directory)
            cached = media_dir / "video123-11400-browser.webm"
            cached.write_bytes(b"cached media")
            ops = {
                "inventory": {
                    "youtube": [
                        {
                            "id": "video123",
                            "url": "https://youtube.test/watch?v=video123",
                            "title": "5-1-26",
                            "durationSeconds": 18000,
                            "practiceCandidate": True,
                            "publishedAt": "2026-05-01T00:00:00Z",
                        }
                    ]
                },
                "media": {"sampleIndex": []},
            }
            presence = {
                "containsViolin": True,
                "violinPresence": "violin_positive",
                "violinSamplerScore": 77.0,
            }
            with mock.patch.object(owner_sync, "MEDIA_DIR", media_dir), mock.patch.object(
                owner_sync,
                "local_violin_presence",
                return_value=presence,
            ):
                candidates = owner_sync.media_candidates(ops)

            self.assertEqual(candidates[0]["sampleId"], "video123-11400")
            self.assertEqual(candidates[0]["sampleWindow"], "*11400-11490")
            self.assertEqual(candidates[0]["cachedPath"], str(cached))
            self.assertEqual(candidates[0]["localPresence"], presence)


if __name__ == "__main__":
    unittest.main()
