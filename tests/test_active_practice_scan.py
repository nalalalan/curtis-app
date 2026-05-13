import math
import struct
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.active_practice_scan import active_intervals_from_sample
from backend.app.evidence_ledger import build_active_practice_coverage


def write_test_wav(path: Path) -> None:
    sample_rate = 16000
    samples: list[int] = []
    for second in range(5):
        for index in range(sample_rate):
            if 1 <= second < 4:
                value = int(9000 * math.sin(2 * math.pi * 440 * (index / sample_rate)))
            else:
                value = 0
            samples.append(value)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))


class ActivePracticeScanTests(unittest.TestCase):
    def test_positive_sample_persists_active_audio_subinterval(self):
        with TemporaryDirectory() as directory:
            wav_path = Path(directory) / "sample.wav"
            write_test_wav(wav_path)
            intervals, result = active_intervals_from_sample(
                {
                    "id": "v1-60",
                    "url": "https://www.youtube.com/watch?v=v1",
                    "title": "5-3-26",
                    "window": "*60-65",
                    "containsViolin": True,
                    "path": str(wav_path),
                }
            )

        self.assertEqual(result["status"], "active_violin")
        self.assertEqual(result["activeIntervalCount"], 1)
        self.assertEqual(intervals[0]["sampleId"], "v1-60")
        self.assertEqual(intervals[0]["sourceVideoId"], "v1")
        self.assertEqual(intervals[0]["startSeconds"], 61.0)
        self.assertEqual(intervals[0]["endSeconds"], 64.0)
        self.assertEqual(intervals[0]["durationSeconds"], 3.0)

    def test_negative_sample_records_checked_without_active_time(self):
        intervals, result = active_intervals_from_sample(
            {
                "id": "v1-0",
                "url": "https://www.youtube.com/watch?v=v1",
                "title": "5-3-26",
                "window": "*0-90",
                "containsViolin": False,
            }
        )

        self.assertEqual(intervals, [])
        self.assertEqual(result["status"], "checked_no_violin")
        self.assertEqual(result["activeSeconds"], 0)

    def test_active_practice_coverage_uses_persisted_scan_intervals(self):
        inventory = {
            "youtube": [
                {
                    "id": "v1",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=v1",
                    "publishedAt": "2026-05-03T09:00:00Z",
                    "durationSeconds": 120,
                    "practiceCandidate": True,
                }
            ]
        }
        samples = [
            {
                "id": "v1-60",
                "url": "https://www.youtube.com/watch?v=v1",
                "title": "5-3-26",
                "window": "*60-65",
                "containsViolin": True,
            }
        ]
        active_scan = {
            "version": "active_practice_scan_v1",
            "intervals": [
                {
                    "intervalId": "active_1",
                    "id": "v1",
                    "sourceKey": "youtube:v1",
                    "sourceVideoId": "v1",
                    "sourceUrl": "https://www.youtube.com/watch?v=v1",
                    "sourceTitle": "5-3-26",
                    "sampleId": "v1-60",
                    "status": "active_violin",
                    "startSeconds": 61,
                    "endSeconds": 64,
                    "durationSeconds": 3,
                }
            ],
            "sampleResults": [],
            "pendingWindows": [],
        }

        coverage = build_active_practice_coverage(inventory, samples, [], [], active_scan)

        self.assertEqual(coverage["checkedVideoSeconds"], 5)
        self.assertEqual(coverage["activePracticeSeconds"], 3)
        self.assertEqual(coverage["activePracticeScan"]["activeIntervalCount"], 1)
        self.assertEqual(coverage["videos"][0]["activeScanSeconds"], 3)
        self.assertEqual(coverage["videos"][0]["status"], "active_measured")

    def test_active_practice_coverage_caps_active_and_estimate_to_checked_video(self):
        inventory = {
            "youtube": [
                {
                    "id": "v1",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=v1",
                    "publishedAt": "2026-05-03T09:00:00Z",
                    "durationSeconds": 100,
                    "practiceCandidate": True,
                }
            ]
        }
        samples = [
            {
                "id": "v1-0",
                "url": "https://www.youtube.com/watch?v=v1",
                "title": "5-3-26",
                "window": "*0-10",
                "containsViolin": True,
            }
        ]
        transcriptions = [
            {
                "transcriptionId": "too-long",
                "sampleId": "v1-0",
                "sourceUrl": "https://www.youtube.com/watch?v=v1",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*0-10",
                "status": "transcribed",
                "quality": {"windowMode": "detected_active_sections"},
                "durationSeconds": 30,
            }
        ]

        coverage = build_active_practice_coverage(inventory, samples, transcriptions, [])

        self.assertEqual(coverage["checkedVideoSeconds"], 10)
        self.assertEqual(coverage["activePracticeSeconds"], 10)
        self.assertLessEqual(coverage["estimatedPracticeRatio"], 1.0)
        self.assertEqual(coverage["estimatedTotalPracticeSeconds"], 100)
        self.assertEqual(coverage["videos"][0]["activePracticeSeconds"], 10)

    def test_active_practice_scan_supersedes_noisy_transcription_duration(self):
        inventory = {
            "youtube": [
                {
                    "id": "v1",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=v1",
                    "publishedAt": "2026-05-03T09:00:00Z",
                    "durationSeconds": 100,
                    "practiceCandidate": True,
                }
            ]
        }
        samples = [
            {
                "id": "v1-0",
                "url": "https://www.youtube.com/watch?v=v1",
                "title": "5-3-26",
                "window": "*0-10",
                "containsViolin": True,
            }
        ]
        transcriptions = [
            {
                "transcriptionId": "too-long",
                "sampleId": "v1-0",
                "sourceUrl": "https://www.youtube.com/watch?v=v1",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*0-10",
                "status": "transcribed",
                "quality": {"windowMode": "detected_active_sections"},
                "durationSeconds": 30,
            }
        ]
        active_scan = {
            "version": "active_practice_scan_v1",
            "intervals": [
                {
                    "intervalId": "active_1",
                    "sourceVideoId": "v1",
                    "sourceUrl": "https://www.youtube.com/watch?v=v1",
                    "sourceTitle": "5-3-26",
                    "sampleId": "v1-0",
                    "status": "active_violin",
                    "startSeconds": 2,
                    "endSeconds": 5,
                    "durationSeconds": 3,
                }
            ],
            "sampleResults": [
                {
                    "sampleId": "v1-0",
                    "sourceVideoId": "v1",
                    "sourceUrl": "https://www.youtube.com/watch?v=v1",
                    "sourceTitle": "5-3-26",
                    "sourceWindow": "*0-10",
                    "detectorVersion": "active_practice_scan_v1",
                    "status": "active_violin",
                }
            ],
            "pendingWindows": [],
        }

        coverage = build_active_practice_coverage(inventory, samples, transcriptions, [], active_scan)

        self.assertEqual(coverage["checkedVideoSeconds"], 10)
        self.assertEqual(coverage["activePracticeSeconds"], 3)
        self.assertEqual(coverage["videos"][0]["activePracticeSeconds"], 3)


if __name__ == "__main__":
    unittest.main()
