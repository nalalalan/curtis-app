import unittest

from backend.app.media import sample_id, sample_window, sample_windows


class MediaSamplingTests(unittest.TestCase):
    def test_sample_window_keeps_legacy_first_window_shape(self):
        item = {"id": "video", "durationSeconds": 3600}

        self.assertEqual(sample_window(item), "*600-690")

    def test_sample_windows_spread_across_long_practice_video(self):
        item = {"id": "video", "durationSeconds": 18000}

        windows = sample_windows(item, max_windows=4)

        self.assertEqual(windows, ["*600-690", "*5940-6030", "*11880-11970", "*17880-17970"])

    def test_sample_id_includes_window_start(self):
        self.assertEqual(sample_id("abc", "*5940-6030"), "abc-5940")


if __name__ == "__main__":
    unittest.main()
