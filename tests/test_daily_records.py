import unittest

from backend.app.daily_records import build_daily_records, build_repertoire_evidence
from backend.app.media import practice_candidates


def note(name, start, end, confidence=0.9):
    return {
        "note": name,
        "midi": 72,
        "startSeconds": start,
        "endSeconds": end,
        "durationSeconds": end - start,
        "confidence": confidence,
    }


class DailyRecordTests(unittest.TestCase):
    def test_groups_same_day_videos_and_renders_machine_notation_evidence(self):
        inventory = {
            "youtube": [
                {
                    "id": "otHfHMgDo2g",
                    "title": "violin 1",
                    "url": "https://www.youtube.com/watch?v=otHfHMgDo2g",
                    "publishedAt": "2025-12-20T19:47:20Z",
                    "durationSeconds": 3608,
                    "practiceCandidate": True,
                },
                {
                    "id": "K38CgZhvF3Q",
                    "title": "5-2-26",
                    "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "publishedAt": "2026-05-03T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                },
                {
                    "id": "second520",
                    "title": "5-2-26",
                    "url": "https://www.youtube.com/watch?v=second520",
                    "publishedAt": "2026-05-03T10:10:00Z",
                    "durationSeconds": 300,
                    "practiceCandidate": True,
                },
                {
                    "id": "unrelated",
                    "title": "alan makes the reading decoration bday present",
                    "url": "https://www.youtube.com/watch?v=unrelated00",
                    "publishedAt": "2026-05-03T11:10:00Z",
                    "durationSeconds": 1000,
                    "practiceCandidate": True,
                },
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "K38CgZhvF3Q-1",
                "sampleId": "K38CgZhvF3Q",
                "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                "sourceTitle": "5-2-26",
                "sourceWindow": "*10-30",
                "status": "transcribed",
                "tempoBpm": 72,
                "noteCount": 9,
                "notes": [
                    note("E5", 0.0, 0.3),
                    note("F#5", 0.3, 0.6),
                    note("G5", 1.2, 1.5, 0.4),
                    note("A5", 1.5, 1.8),
                    note("E5", 2.0, 2.3),
                    note("F#5", 2.3, 2.6),
                    note("G5", 2.6, 2.9, 0.5),
                    note("A5", 2.9, 3.2),
                    note("E5", 3.2, 3.5),
                ],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "K38CgZhvF3Q", "path": "sample.mp4", "window": "*10-30"}],
            transcriptions=transcriptions,
            sections=[
                {
                    "sampleId": "K38CgZhvF3Q",
                    "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "window": "*12-14",
                    "meanRms": 0.8,
                    "note": "Audio-active section inside the transcribed window.",
                }
            ],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-02")

        self.assertEqual(daily["activeMeasurementStatus"], "partial")
        self.assertGreater(daily["totalUploadedVideoSeconds"], daily["totalActiveViolinSeconds"])
        self.assertEqual(
            daily["unmeasuredUploadedVideoSeconds"],
            daily["totalUploadedVideoSeconds"] - daily["totalActiveViolinSeconds"],
        )
        self.assertIn("Uploaded archive duration is visible separately", daily["limit"])
        self.assertEqual(record["videoCount"], 2)
        self.assertEqual(record["uploadedVideoSeconds"], 900)
        self.assertLess(record["activeViolinSeconds"], record["uploadedVideoSeconds"])
        self.assertEqual(record["activeTimeStatus"], "measured_from_pitch")
        self.assertEqual(record["transcription"]["status"], "ready")
        self.assertEqual(record["transcription"]["qualityStatus"], "weak_fragment")
        self.assertEqual(record["transcription"]["kind"], "audio_paired_pitch_trace")
        self.assertEqual(record["transcription"]["reliability"], "unverified_pitch_trace")
        self.assertFalse(record["transcription"]["scoreLinked"])
        self.assertEqual(record["transcription"]["clef"], "treble")
        self.assertEqual(record["transcription"]["keySignature"]["label"], "G minor / 2 flats")
        self.assertEqual(record["transcription"]["windowSeconds"], 20)
        self.assertEqual(record["transcription"]["coverageStatus"], "sample_window_only")
        self.assertIn("Not a full-session transcription", record["transcription"]["fullSessionLimit"])
        self.assertTrue(record["transcription"]["notationSystems"])
        self.assertEqual(record["transcription"]["notationSystems"][0]["clip"]["type"], "pitch_trace_snippet")
        self.assertEqual(record["transcription"]["notationSystems"][0]["clip"]["mediaUrl"], "/api/curtis/media/sample/K38CgZhvF3Q")
        self.assertEqual(record["transcription"]["notationSystems"][0]["clip"]["localStartSeconds"], 0)
        self.assertTrue(record["transcription"]["repeatGroups"])
        self.assertIn("x2", record["transcription"]["repeatGroups"][0]["notationLabel"])
        self.assertTrue(any(event["kind"] == "rest" for event in record["transcription"]["events"]))
        self.assertTrue(any(event.get("uncertain") for event in record["transcription"]["events"]))
        self.assertEqual(record["pieces"][0]["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertIn("not enough", record["mainCurtisBlocker"])
        self.assertTrue(record["heatMap"]["layers"])
        self.assertEqual(record["clips"][0]["type"], "transcribed_window")
        self.assertEqual(record["clips"][0]["mediaUrl"], "/api/curtis/media/sample/K38CgZhvF3Q")
        self.assertEqual(record["clips"][0]["localStartSeconds"], 0)
        self.assertEqual(record["clips"][0]["localEndSeconds"], 20)
        self.assertNotIn("reading decoration", " ".join(video["title"] for video in record["videos"]))

    def test_repertoire_promotes_only_confirmed_daily_evidence(self):
        inventory = {
            "youtube": [
                {
                    "id": "otHfHMgDo2g",
                    "title": "violin 1",
                    "url": "https://www.youtube.com/watch?v=otHfHMgDo2g",
                    "publishedAt": "2025-12-20T19:47:20Z",
                    "durationSeconds": 3608,
                    "practiceCandidate": True,
                },
                {
                    "id": "K38CgZhvF3Q",
                    "title": "5-2-26",
                    "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "publishedAt": "2026-05-03T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                },
                {
                    "id": "unknown420",
                    "title": "4-20-26",
                    "url": "https://www.youtube.com/watch?v=unknown420",
                    "publishedAt": "2026-04-21T09:10:00Z",
                    "durationSeconds": 500,
                    "practiceCandidate": True,
                },
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "confirmed",
                "sampleId": "K38CgZhvF3Q",
                "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                "sourceTitle": "5-2-26",
                "sourceWindow": "*10-30",
                "status": "transcribed",
                "tempoBpm": 100,
                "noteCount": 4,
                "notes": [note("E5", 0, 0.3), note("F#5", 0.3, 0.6), note("G5", 0.6, 0.9), note("A5", 0.9, 1.2)],
            },
            {
                "transcriptionId": "uncertain",
                "sampleId": "unknown420",
                "sourceUrl": "https://www.youtube.com/watch?v=unknown420",
                "sourceTitle": "4-20-26",
                "sourceWindow": "*10-30",
                "status": "transcribed",
                "tempoBpm": 100,
                "noteCount": 4,
                "notes": [note("C5", 0, 0.3), note("D5", 0.3, 0.6), note("E5", 0.6, 0.9), note("F5", 0.9, 1.2)],
                "referenceMatches": [{"title": "Unconfirmed Candidate Piece", "score": 0.92}],
            },
        ]

        daily = build_daily_records(inventory=inventory, state={}, media_samples=[], transcriptions=transcriptions, sections=[])
        repertoire = build_repertoire_evidence(daily)
        titles = [entry["title"] for entry in repertoire["entries"]]

        self.assertIn("Wieniawski Scherzo-Tarantelle, Op. 16", titles)
        self.assertNotIn("Unconfirmed Candidate Piece", titles)
        self.assertEqual(repertoire["entries"][0]["progressStatus"], "not_scored")
        self.assertTrue(repertoire["entries"][0]["evidence"])
        self.assertEqual(repertoire["entries"][0]["heatMap"]["status"], "ready")
        self.assertTrue(repertoire["entries"][0]["heatMap"]["fragments"])
        self.assertIn("Practice density", [layer["label"] for layer in repertoire["entries"][0]["heatMap"]["layers"]])

    def test_daily_record_coverage_counts_active_transcribed_audio(self):
        inventory = {
            "youtube": [
                {
                    "id": "K38CgZhvF3Q",
                    "title": "5-2-26",
                    "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "publishedAt": "2026-05-03T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "active-window",
                "sampleId": "K38CgZhvF3Q",
                "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                "sourceTitle": "5-2-26",
                "sourceWindow": "*10-100",
                "status": "transcribed",
                "durationSeconds": 12.4,
                "tempoBpm": 100,
                "noteCount": 4,
                "quality": {"windowMode": "detected_active_sections"},
                "notes": [note("E5", 4, 4.3), note("F#5", 4.3, 4.6), note("G5", 4.6, 4.9), note("A5", 4.9, 5.2)],
            },
            {
                "transcriptionId": "active-window-empty",
                "sampleId": "K38CgZhvF3Q-empty",
                "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                "sourceTitle": "5-2-26",
                "sourceWindow": "*100-190",
                "status": "no_stable_notes",
                "durationSeconds": 44.2,
                "tempoBpm": 0,
                "noteCount": 0,
                "quality": {"windowMode": "detected_active_sections"},
                "notes": [],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "K38CgZhvF3Q", "path": "sample.mp4", "window": "*10-100"}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-02")

        self.assertEqual(record["transcription"]["windowSeconds"], 12)
        self.assertEqual(record["transcription"]["segmentCount"], 1)
        self.assertEqual(record["transcription"]["coverageStatus"], "active_sections_only")
        self.assertIn("active playing", record["transcription"]["coverageLimit"])
        self.assertEqual(record["activeViolinSeconds"], 57)
        self.assertEqual(record["clips"][0]["activeTranscribedSeconds"], 12.4)
        self.assertIn("active audio", record["clips"][0]["reason"])
        self.assertEqual(record["clips"][1]["activeTranscribedSeconds"], 44.2)
        self.assertIn("no stable note notation", record["clips"][1]["reason"])

    def test_media_probe_uses_title_confirmed_ledger_not_broad_candidates(self):
        state = {
            "inventory": {
                "youtube": [
                    {
                        "id": "otHfHMgDo2g",
                        "title": "violin 1",
                        "url": "https://www.youtube.com/watch?v=otHfHMgDo2g",
                        "publishedAt": "2025-12-20T19:47:20Z",
                        "durationSeconds": 3608,
                        "practiceCandidate": True,
                    },
                    {
                        "id": "unrelated",
                        "title": "alan makes the reading decoration bday present",
                        "url": "https://www.youtube.com/watch?v=unrelated00",
                        "publishedAt": "2025-12-21T21:42:04Z",
                        "durationSeconds": 24610,
                        "practiceCandidate": True,
                    },
                ]
            }
        }

        candidates = practice_candidates(state)

        self.assertEqual([item["title"] for item in candidates], ["violin 1"])

    def test_long_transcription_is_split_into_partial_notation_systems(self):
        inventory = {
            "youtube": [
                {
                    "id": "wDfVpTU4I_I",
                    "title": "5-1-26",
                    "url": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                    "publishedAt": "2026-05-02T08:10:00Z",
                    "durationSeconds": 3600,
                    "practiceCandidate": True,
                }
            ]
        }
        names = ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"]
        notes = []
        for index in range(220):
            start = index * 0.18
            notes.append(note(names[index % len(names)], start, start + 0.14, 0.82))
        transcriptions = [
            {
                "transcriptionId": "haydn-long",
                "sampleId": "wDfVpTU4I_I",
                "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                "sourceTitle": "5-1-26",
                "sourceWindow": "*100-180",
                "status": "transcribed",
                "tempoBpm": 120,
                "noteCount": len(notes),
                "notes": notes,
            }
        ]

        daily = build_daily_records(inventory=inventory, state={}, media_samples=[], transcriptions=transcriptions, sections=[])
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-01")
        transcription = record["transcription"]

        self.assertEqual(transcription["keySignature"]["label"], "G major / 1 sharp")
        self.assertEqual(transcription["eventCount"], len(transcription["events"]))
        self.assertGreaterEqual(len(transcription["notationSystems"]), 3)
        self.assertTrue(all(system["clip"]["mediaUrl"] == "/api/curtis/media/sample/wDfVpTU4I_I" for system in transcription["notationSystems"]))
        self.assertLess(transcription["renderedEventCount"], transcription["eventCount"])
        self.assertIn("of", transcription["displayLimit"])


if __name__ == "__main__":
    unittest.main()
