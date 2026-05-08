import unittest

from backend.app.scanner import derive_review
from backend.app.study_packets import build_practice_study, build_practice_totals
from backend.app.transcription import (
    compare_fingerprints,
    event_fingerprint,
    reference_matches_for,
    transcription_prior_hint,
)


def fingerprint_for(midi_values):
    events = [
        {
            "startSeconds": index * 0.5,
            "endSeconds": (index + 1) * 0.5,
            "durationSeconds": 0.5,
            "midi": midi,
            "note": str(midi),
            "confidence": 0.9,
        }
        for index, midi in enumerate(midi_values)
    ]
    return event_fingerprint(events, 120.0)


class TranscriptionTrainingTests(unittest.TestCase):
    def test_pitch_rhythm_fingerprint_matches_repeated_material(self):
        first = fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81])
        second = fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81])
        unrelated = fingerprint_for([60, 64, 67, 72, 67, 64, 60, 55, 60, 64, 67, 72])

        self.assertGreaterEqual(compare_fingerprints(first, second), 0.95)
        self.assertLess(compare_fingerprints(first, unrelated), 0.65)

    def test_reference_matches_use_learned_transcription_fingerprints(self):
        learned = {
            "transcriptionId": "5-2",
            "sourceTitle": "5-2-26",
            "acceptedTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
            "status": "transcribed",
            "noteCount": 12,
            "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
        }
        incoming = {
            "transcriptionId": "5-3",
            "status": "transcribed",
            "noteCount": 12,
            "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
        }

        matches = reference_matches_for(incoming, {"transcriptions": {"items": [learned]}})

        self.assertEqual(matches[0]["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(matches[0]["basis"], "pitch_rhythm_fingerprint")

    def test_training_state_reports_pitch_rhythm_windows_without_claiming_score_match(self):
        state = {
            "transcriptions": {
                "items": [
                    {
                        "transcriptionId": "title:5 3 26|local|*600-645|sample.mp4",
                        "sampleId": "local",
                        "sourceKey": "title:5 3 26",
                        "sourceTitle": "5-3-26",
                        "sourceWindow": "*600-645",
                        "status": "transcribed",
                        "noteCount": 12,
                        "tempoBpm": 120.0,
                        "acceptedTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                        "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
                    }
                ]
            }
        }

        review = derive_review({"youtube": []}, {}, [], state)
        training = review["training"]
        by_source = {anchor["sourceTitle"]: anchor for anchor in training["anchors"]}

        self.assertEqual(training["pitchRhythmWindowCount"], 1)
        self.assertEqual(training["scoreAlignedWindowCount"], 0)
        self.assertEqual(training["label"], "3 refs / 1 pitch windows")
        self.assertEqual(by_source["5-3-26"]["status"], "pitch_rhythm_extracted")
        self.assertTrue(by_source["5-3-26"]["scoreAlignment"]["pitchRhythmExtracted"])

    def test_piece_prompt_can_receive_nearest_learned_fingerprint_hint(self):
        state = {
            "transcriptions": {
                "items": [
                    {
                        "transcriptionId": "new-sample",
                        "sampleId": "new-sample",
                        "sourceKey": "title:new sample",
                        "sourceTitle": "new sample",
                        "status": "transcribed",
                        "noteCount": 12,
                        "referenceMatches": [
                            {
                                "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
                                "sourceTitle": "5-2-26",
                                "score": 0.91,
                                "basis": "pitch_rhythm_fingerprint",
                            }
                        ],
                    }
                ]
            }
        }

        hint = transcription_prior_hint(state, {"id": "new-sample", "title": "new sample"})

        self.assertIn("pitch/rhythm fingerprint", hint)
        self.assertIn("Wieniawski Scherzo-Tarantelle", hint)

    def test_practice_study_packet_pairs_transcription_score_and_clip(self):
        state = {
            "transcriptions": {
                "items": [
                    {
                        "transcriptionId": "title:5 3 26|local|*600-645|sample.mp4",
                        "sampleId": "local",
                        "sourceKey": "title:5 3 26",
                        "sourceTitle": "5-3-26",
                        "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                        "sourceWindow": "*600-645",
                        "status": "transcribed",
                        "noteCount": 12,
                        "tempoBpm": 120.0,
                        "acceptedTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
                        "notes": [
                            {
                                "note": "E5",
                                "durationSeconds": 0.25,
                                "startSeconds": 0,
                                "endSeconds": 0.25,
                            },
                            {
                                "note": "F#5",
                                "durationSeconds": 0.25,
                                "startSeconds": 0.25,
                                "endSeconds": 0.5,
                            },
                        ],
                        "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
                    }
                ]
            }
        }
        inventory = {
            "youtube": [
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "practiceCandidate": True,
                }
            ]
        }

        study = build_practice_study(state, inventory, [], [])
        packet = next(item for item in study["days"] if item["practiceDay"] == "2026-05-03")
        snippet = packet["snippets"][0]

        self.assertEqual(packet["pieceTitle"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(packet["transcription"]["status"], "transcribed")
        self.assertIn("E5", packet["transcription"]["cleanText"])
        self.assertEqual(snippet["score"]["assetId"], "wieniawski-scherzo-tarantelle-vln")
        self.assertEqual(snippet["score"]["page"], 2)
        self.assertTrue(snippet["score"]["imageUrl"].endswith("/wieniawski-scherzo-tarantelle-vln/2"))
        self.assertEqual(snippet["audio"]["startSeconds"], 600)
        self.assertIn("Pitch/rhythm extracted", snippet["readiness"])

    def test_practice_study_packet_exists_before_transcription(self):
        inventory = {
            "youtube": [
                {
                    "id": "wDfVpTU4I_I",
                    "title": "5-1-26",
                    "url": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                    "practiceCandidate": True,
                }
            ]
        }

        study = build_practice_study({}, inventory, [], [])
        packet = next(item for item in study["days"] if item["practiceDay"] == "2026-05-01")
        snippet = packet["snippets"][0]

        self.assertEqual(packet["pieceTitle"], "Haydn Symphony No. 94, IV. Finale, Violin I part")
        self.assertEqual(packet["transcription"]["status"], "pending")
        self.assertEqual(snippet["score"]["assetId"], "haydn-94-finale-score")
        self.assertEqual(snippet["score"]["page"], 45)
        self.assertTrue(snippet["score"]["boxes"])
        self.assertEqual(snippet["audio"]["url"], "https://www.youtube.com/watch?v=wDfVpTU4I_I")

    def test_practice_totals_start_at_violin_one_and_exclude_unrelated_long_videos(self):
        inventory = {
            "youtube": [
                {
                    "id": "unrelated",
                    "title": "alan makes the reading decoration bday present",
                    "url": "https://www.youtube.com/watch?v=unrelated00",
                    "publishedAt": "2025-12-21T21:42:04Z",
                    "durationSeconds": 24610,
                    "practiceCandidate": True,
                },
                {
                    "id": "old-cover",
                    "title": "Violin Cover",
                    "url": "https://www.youtube.com/watch?v=oldcover000",
                    "publishedAt": "2013-11-26T09:14:30Z",
                    "durationSeconds": 148,
                    "practiceCandidate": True,
                },
                {
                    "id": "otHfHMgDo2g",
                    "title": "violin 1",
                    "url": "https://www.youtube.com/watch?v=otHfHMgDo2g",
                    "publishedAt": "2025-12-20T19:47:20Z",
                    "durationSeconds": 3608,
                    "practiceCandidate": True,
                },
                {
                    "id": "wDfVpTU4I_I",
                    "title": "5-1-26",
                    "url": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                    "publishedAt": "2026-05-03T10:20:47Z",
                    "durationSeconds": 16421,
                    "practiceCandidate": True,
                },
            ]
        }

        totals = build_practice_totals(inventory)

        self.assertEqual(totals["status"], "ready")
        self.assertEqual(totals["sinceTitle"], "violin 1")
        self.assertEqual(totals["videoCount"], 2)
        self.assertEqual(totals["totalPracticeSeconds"], 20029)
        self.assertEqual([video["title"] for video in totals["videos"]], ["5-1-26", "violin 1"])
        self.assertNotIn("reading decoration", " ".join(video["title"] for video in totals["videos"]))

    def test_practice_study_adds_pending_rows_for_every_practice_log_since_marker(self):
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
                    "id": "later",
                    "title": "4-18-26",
                    "url": "https://www.youtube.com/watch?v=later000000",
                    "publishedAt": "2026-04-21T17:48:03Z",
                    "durationSeconds": 8052,
                    "practiceCandidate": True,
                },
            ]
        }

        study = build_practice_study({}, inventory, [], [])
        by_title = {item["sourceTitle"]: item for item in study["days"]}

        self.assertEqual(study["practiceTotals"]["videoCount"], 2)
        self.assertEqual(by_title["violin 1"]["status"], "transcription_pending")
        self.assertEqual(by_title["4-18-26"]["totalPracticeSeconds"], 8052)
        self.assertEqual(by_title["4-18-26"]["pieceTitle"], "Piece being identified")


if __name__ == "__main__":
    unittest.main()
