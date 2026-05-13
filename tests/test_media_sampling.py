import json
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

        self.assertEqual(windows, ["*600-690", "*4500-4590", "*9000-9090", "*11250-11340"])

    def test_dense_sample_windows_prioritize_deep_practice_before_early_probes(self):
        item = {"id": "video", "durationSeconds": 18000}

        windows = sample_windows(item, max_windows=8)

        self.assertIn("*300-390", windows)
        self.assertIn("*900-990", windows)
        self.assertIn("*11250-11340", windows)
        self.assertLess(windows.index("*11250-11340"), windows.index("*300-390"))

    def test_full_check_windows_can_cover_video_without_retention_gap(self):
        item = {"id": "video", "durationSeconds": 600}

        windows = sample_windows(item, max_windows=20)

        self.assertEqual(windows[0], "*0-90")
        self.assertIn("*90-180", windows)
        self.assertIn("*180-270", windows)
        self.assertIn("*270-360", windows)
        self.assertIn("*360-450", windows)
        self.assertIn("*480-570", windows)

    def test_owner_sync_full_check_can_walk_video_in_order(self):
        item = {"id": "video", "durationSeconds": 600}

        with mock.patch.object(owner_sync, "WINDOWS_PER_VIDEO", 20):
            starts = owner_sync.sample_starts(item)

        self.assertEqual(starts[:5], [0, 90, 180, 270, 360])
        self.assertIn(480, starts)

    def test_owner_sync_prioritizes_deep_long_video_windows(self):
        item = {"id": "video", "durationSeconds": 42900}

        starts = owner_sync.sample_starts(item)

        self.assertEqual(starts[:5], [600, 10725, 21450, 26812, 32175])
        self.assertLess(starts.index(10725), starts.index(300))

    def test_owner_sync_expands_around_existing_violin_positive_windows(self):
        with TemporaryDirectory() as directory:
            media_dir = Path(directory)
            ops = {
                "inventory": {
                    "youtube": [
                        {
                            "id": "video123",
                            "url": "https://youtube.test/watch?v=video123",
                            "title": "5-5-26",
                            "durationSeconds": 18000,
                            "practiceCandidate": True,
                            "publishedAt": "2026-05-05T00:00:00Z",
                        }
                    ]
                },
                "media": {
                    "sampleIndex": [
                        {
                            "id": "video123-9000",
                            "url": "https://youtube.test/watch?v=video123",
                            "window": "*9000-9090",
                            "containsViolin": True,
                            "violinPresence": "violin_positive",
                        }
                    ]
                },
            }
            with mock.patch.object(owner_sync, "MEDIA_DIR", media_dir):
                candidates = owner_sync.media_candidates(ops)

            self.assertEqual(candidates[0]["sampleId"], "video123-8910")
            self.assertEqual(candidates[1]["sampleId"], "video123-9090")
            self.assertLess(
                [item["sampleId"] for item in candidates].index("video123-8910"),
                [item["sampleId"] for item in candidates].index("video123-600"),
            )

    def test_owner_sync_prioritizes_active_scan_pending_windows(self):
        ops = {
            "inventory": {
                "youtube": [
                    {
                        "id": "video123",
                        "url": "https://youtube.test/watch?v=video123",
                        "title": "5-3-26",
                        "durationSeconds": 600,
                        "practiceCandidate": True,
                        "publishedAt": "2026-05-03T00:00:00Z",
                    }
                ]
            },
            "media": {"sampleIndex": []},
        }
        active_scan = {
            "pendingWindows": [
                {
                    "sampleId": "video123-270",
                    "sourceVideoId": "video123",
                    "sourceUrl": "https://youtube.test/watch?v=video123",
                    "sourceTitle": "5-3-26",
                    "startSeconds": 270,
                    "endSeconds": 360,
                }
            ]
        }

        candidates = owner_sync.media_candidates(ops, active_scan)

        self.assertEqual(candidates[0]["sampleId"], "video123-270")
        self.assertEqual(candidates[0]["sampleWindow"], "*270-360")
        self.assertEqual(candidates[0]["queueSource"], "active_practice_scan")

    def test_owner_sync_queue_only_uses_cached_pending_samples(self):
        with TemporaryDirectory() as directory:
            media_dir = Path(directory)
            cached = media_dir / "video123-90-browser.webm"
            cached.write_bytes(b"cached media")
            ops = {
                "inventory": {
                    "youtube": [
                        {
                            "id": "video123",
                            "url": "https://youtube.test/watch?v=video123",
                            "title": "5-3-26",
                            "durationSeconds": 12000,
                            "practiceCandidate": True,
                            "publishedAt": "2026-05-03T00:00:00Z",
                        }
                    ]
                },
                "media": {"sampleIndex": []},
            }
            active_scan = {
                "pendingWindows": [
                    {
                        "sampleId": "video123-90",
                        "sourceVideoId": "video123",
                        "sourceUrl": "https://youtube.test/watch?v=video123",
                        "sourceTitle": "5-3-26",
                        "startSeconds": 90,
                        "endSeconds": 180,
                    }
                ]
            }
            with mock.patch.object(owner_sync, "MEDIA_DIR", media_dir), mock.patch.object(
                owner_sync,
                "local_violin_presence",
                return_value={"containsViolin": False, "violinPresence": "not_violin_or_unclear"},
            ):
                candidates = owner_sync.media_candidates(ops, active_scan, queue_only=True)

        self.assertEqual([item["sampleId"] for item in candidates], ["video123-90"])
        self.assertEqual(candidates[0]["cachedPath"], str(cached))
        self.assertEqual(candidates[0]["queueSource"], "active_practice_scan")
        self.assertEqual(candidates[0]["localPresence"]["violinPresence"], "not_violin_or_unclear")

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

    def test_owner_sync_reuses_matching_presence_cache(self):
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
                "violinSamplerVersion": owner_sync.VIOLIN_PRESENCE_VERSION,
            }
            with mock.patch.object(owner_sync, "MEDIA_DIR", media_dir):
                signature = owner_sync.file_signature(cached)
                cache = {
                    "version": owner_sync.VIOLIN_PRESENCE_VERSION,
                    "items": {
                        signature["path"]: {
                            "signature": signature,
                            "presence": presence,
                        }
                    },
                }
                (media_dir / ".violin-presence-cache.json").write_text(json.dumps(cache), encoding="utf-8")
                with mock.patch.object(
                    owner_sync,
                    "local_violin_presence",
                    side_effect=AssertionError("cache miss"),
                ):
                    candidates = owner_sync.media_candidates(ops)

            self.assertEqual(candidates[0]["sampleId"], "video123-11400")
            self.assertEqual(candidates[0]["localPresence"], presence)


if __name__ == "__main__":
    unittest.main()
