import unittest

from backend.app.daily_records import (
    build_daily_records,
    build_repertoire_evidence,
    detected_note_series,
    pitch_anchor_matches_for_series,
    score_reference_audit_for_pieces,
    score_sequence_matches_for_series,
)
from backend.app.corrections import wieniawski_reference_target
from backend.app.media import practice_candidates
from backend.app.transcription import TRANSCRIPTION_PIPELINE_VERSION


NOTE_CLASS = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def midi_for_note(name):
    pitch = name[:-1]
    octave = int(name[-1])
    return (octave + 1) * 12 + NOTE_CLASS[pitch]


def note(name, start, end, confidence=0.9, **extra):
    return {
        "note": name,
        "midi": midi_for_note(name),
        "startSeconds": start,
        "endSeconds": end,
        "durationSeconds": end - start,
        "confidence": confidence,
        "audioAgreement": True,
        "agreementSourceCount": 1,
        "agreementSources": ["pitch_hysteresis"],
        "detectorSource": "spectral_onset",
        **extra,
    }


class DailyRecordTests(unittest.TestCase):
    def test_groups_same_day_videos_and_fails_unverified_machine_notation(self):
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
                    note("G#4", 0.0, 0.3),
                    note("G#4", 0.3, 0.6),
                    note("G#4", 1.2, 1.5, 0.4),
                    note("G#4", 1.5, 1.8),
                    note("G#4", 2.0, 2.3),
                    note("G#4", 2.3, 2.6),
                    note("G#4", 2.6, 2.9, 0.5),
                    note("G#4", 2.9, 3.2),
                    note("G#4", 3.2, 3.5),
                ],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "K38CgZhvF3Q", "path": "sample.mp4", "window": "*10-30", "containsViolin": True}],
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
            daily["totalUploadedVideoSeconds"] - daily["totalProcessedSampleSeconds"],
        )
        self.assertIn("Total practice time means detected violin-playing footage", daily["limit"])
        self.assertEqual(record["videoCount"], 2)
        self.assertEqual(record["uploadedVideoSeconds"], 900)
        self.assertLess(record["activeViolinSeconds"], record["uploadedVideoSeconds"])
        self.assertEqual(record["activeTimeStatus"], "measured_from_pitch")
        self.assertEqual(daily["transcribedRecordCount"], 0)
        self.assertEqual(daily["failedTranscriptionRecordCount"], 0)
        self.assertEqual(daily["scoreAudioOnlyRecordCount"], 1)
        self.assertEqual(daily["audioEvidenceRecordCount"], 1)
        self.assertEqual(daily["records"][0]["practiceDay"], "2025-12-20")
        self.assertEqual(daily["records"][1]["practiceDay"], "2026-05-02")
        self.assertEqual(daily["totalProcessedSampleSeconds"], 20)
        self.assertEqual(daily["totalAnalyzedVideoSeconds"], daily["totalProcessedSampleSeconds"])
        self.assertEqual(daily["totalPracticeTimeSeconds"], daily["totalActiveViolinSeconds"])
        self.assertEqual(daily["estimatedPracticeStatus"], "estimated_from_checked_windows")
        self.assertGreater(daily["estimatedTotalPracticeTimeSeconds"], daily["totalPracticeTimeSeconds"])
        self.assertIn("detected from", daily["estimatedPracticeBasis"])
        self.assertEqual(record["status"], "active_time_measured")
        self.assertEqual(record["transcription"]["status"], "score_audio_only")
        self.assertEqual(record["transcription"]["qualityStatus"], "score_audio_only")
        self.assertEqual(record["transcription"]["kind"], "score_audio_evidence")
        self.assertEqual(record["transcription"]["reliability"], "score_audio_only")
        self.assertEqual(record["transcription"]["failureMode"], "unverified_machine_pitch")
        self.assertEqual(record["materialStatus"], "confirmed_piece")
        self.assertEqual(record["materialLabel"], "piece confirmed")
        self.assertFalse(record["transcription"]["displayNotation"])
        self.assertFalse(record["transcription"]["transcriptionReady"])
        self.assertFalse(record["transcription"]["scoreLinked"])
        self.assertEqual(record["transcription"]["scoreAlignmentStatus"], "pending_score_alignment")
        self.assertEqual(record["matchingWorkflow"]["scoreSequenceMatchCount"], 0)
        self.assertEqual(record["matchGroups"], [])
        self.assertEqual(record["transcription"]["clef"], "treble")
        self.assertEqual(record["transcription"]["keySignature"]["label"], "G minor / 2 flats")
        self.assertEqual(record["transcription"]["windowSeconds"], 20)
        self.assertEqual(record["transcription"]["coverageStatus"], "sample_window_only")
        self.assertIn("Not a full-session transcription", record["transcription"]["fullSessionLimit"])
        self.assertFalse(record["transcription"]["notationSystems"])
        self.assertEqual(record["transcription"]["repeatGroups"], [])
        self.assertEqual(record["transcription"]["events"], [])
        self.assertEqual(record["transcription"]["hiddenPitchEventCount"], 9)
        self.assertIn("hidden from notation", record["transcription"]["displayLimit"])
        self.assertEqual(record["pieces"][0]["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertIn("score", record["mainCurtisBlocker"])
        self.assertEqual(record["heatMap"]["status"], "pending_score_alignment")
        self.assertEqual(record["heatMap"]["fragments"], [])
        self.assertEqual(record["clips"][0]["type"], "transcribed_window")
        self.assertEqual(record["clips"][0]["mediaUrl"], "/api/curtis/media/sample/K38CgZhvF3Q")
        self.assertEqual(record["clips"][0]["localStartSeconds"], 0)
        self.assertEqual(record["clips"][0]["localEndSeconds"], 20)
        self.assertNotIn("reading decoration", " ".join(video["title"] for video in record["videos"]))

    def test_daily_records_use_canonical_active_practice_coverage_totals(self):
        inventory = {
            "youtube": [
                {
                    "id": "K38CgZhvF3Q",
                    "title": "5-2-26",
                    "url": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
                    "publishedAt": "2026-05-07T17:02:05Z",
                    "durationSeconds": 1000,
                    "practiceCandidate": True,
                }
            ]
        }
        coverage = {
            "uploadedVideoSeconds": 1000,
            "uploadedVideoLabel": "16m 40s",
            "checkedVideoSeconds": 180,
            "checkedVideoLabel": "3m",
            "activePracticeSeconds": 120,
            "activePracticeLabel": "2m",
            "estimatedTotalPracticeSeconds": 667,
            "estimatedTotalPracticeLabel": "11m 7s",
            "estimatedPracticeRatio": 0.6667,
            "unmeasuredVideoSeconds": 820,
            "unmeasuredVideoLabel": "13m 40s",
            "measurementStatus": "partial",
            "estimateStatus": "estimated_from_checked_windows",
            "days": [
                {
                    "practiceDay": "2026-05-02",
                    "checkedVideoSeconds": 180,
                    "activePracticeSeconds": 120,
                    "activeScanSeconds": 120,
                    "activeScanIntervalCount": 2,
                }
            ],
        }

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "K38CgZhvF3Q", "path": "sample.mp4", "window": "*10-20", "containsViolin": True}],
            transcriptions=[],
            sections=[],
            active_practice_coverage=coverage,
        )
        record = daily["records"][0]

        self.assertEqual(daily["checkedVideoSeconds"], 180)
        self.assertEqual(daily["totalAnalyzedVideoSeconds"], 180)
        self.assertEqual(daily["totalPracticeTimeSeconds"], 120)
        self.assertEqual(daily["estimatedTotalPracticeSeconds"], 667)
        self.assertEqual(daily["estimatedTotalPracticeLabel"], "11m 7s")
        self.assertEqual(daily["unmeasuredVideoSeconds"], 820)
        self.assertEqual(daily["measurementStatus"], "partial")
        self.assertEqual(record["processedSampleSeconds"], 180)
        self.assertEqual(record["activeViolinSeconds"], 120)
        self.assertEqual(record["activePracticeScanSeconds"], 120)
        self.assertEqual(record["activePracticeScanIntervalCount"], 2)
        self.assertEqual(record["activeTimeStatus"], "measured_from_active_practice_scan")

    def test_scherzo_rejected_five_note_phrase_stays_candidate_only(self):
        inventory = {
            "youtube": [
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "publishedAt": "2026-05-04T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "Njh8_zq9_DM-1",
                "sampleId": "Njh8_zq9_DM-1",
                "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*10-100",
                "status": "transcribed",
                "tempoBpm": 72,
                "quality": {"windowMode": "detected_active_sections"},
                "durationSeconds": 4.0,
                "noteCount": 5,
                "notes": [
                    note("A#4", 0.0, 0.4),
                    note("D5", 0.5, 0.9),
                    note("C5", 1.0, 1.4, audioAgreement=False, agreementSourceCount=0, agreementSources=[]),
                    note("A#4", 1.5, 1.9),
                    note("D5", 2.0, 2.4),
                ],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "Njh8_zq9_DM-1", "path": "sample.mp4", "window": "*10-100", "containsViolin": True}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-03")

        self.assertEqual(record["pieces"][0]["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(record["matchingWorkflow"]["scoreReferenceStatus"], "symbolic_score_sequence_ready")
        self.assertEqual(record["matchingWorkflow"]["scoreSequenceMatchCount"], 0)
        self.assertEqual(record["matchingWorkflow"]["scoreLocationVerifiedCount"], 0)
        self.assertFalse(record["transcription"]["scoreLinked"])
        self.assertFalse(record["transcription"]["referenceLinked"])
        self.assertEqual(record["transcription"]["scoreAlignmentStatus"], "pending_score_alignment")
        self.assertFalse(any(group["status"] == "symbolic_score_phrase_match" for group in record["matchGroups"]))
        self.assertEqual(record["heatMap"]["status"], "pending_score_alignment")
        self.assertEqual(record["heatMap"]["fragments"], [])
        self.assertNotIn("accepted clip maps to mm. 2-4", record["mainCurtisBlocker"])
        self.assertEqual(record["clips"][0]["mediaUrl"], "/api/curtis/media/sample/Njh8_zq9_DM-1")

    def test_source_sequence_candidate_does_not_become_visible_match_group(self):
        inventory = {
            "youtube": [
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "publishedAt": "2026-05-04T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "candidate-source-sequence",
                "sampleId": "candidate-source-sequence",
                "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*120-210",
                "status": "transcribed",
                "tempoBpm": 96,
                "quality": {"windowMode": "detected_active_sections"},
                "notes": [
                    note("A5", 0.0, 0.14),
                    note("G5", 0.15, 0.29),
                    note("F5", 0.30, 0.44),
                    note("A5", 0.45, 0.59),
                ],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {
                    "id": "candidate-source-sequence",
                    "path": "candidate.mp4",
                    "window": "*120-210",
                    "containsViolin": True,
                }
            ],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-03")

        self.assertEqual(record["matchingWorkflow"]["status"], "source_verification_pending")
        self.assertEqual(record["matchingWorkflow"]["scoreSequenceMatchCount"], 0)
        self.assertEqual(record["matchingWorkflow"]["scoreSequenceCandidateCount"], 1)
        self.assertEqual(record["transcription"]["scoreSequenceMatchCount"], 0)
        self.assertEqual(record["transcription"]["scoreSequenceCandidateCount"], 1)
        self.assertFalse(record["transcription"]["scoreLinked"])
        self.assertFalse(record["transcription"]["referenceLinked"])
        self.assertEqual(record["matchGroups"], [])
        self.assertEqual(len(record["candidateMatchGroups"]), 1)
        self.assertEqual(record["candidateMatchGroups"][0]["detectedPitchClassSequenceCompact"], "A G F A")
        self.assertEqual(record["transcription"]["scoreAlignmentStatus"], "source_verification_pending")
        self.assertEqual(record["heatMap"]["fragments"], [])

    def test_score_free_exercise_days_are_not_forced_into_score_matching(self):
        inventory = {
            "youtube": [
                {
                    "id": "exercise520",
                    "title": "5-20-26",
                    "url": "https://www.youtube.com/watch?v=exercise520",
                    "publishedAt": "2026-05-20T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                }
            ]
        }

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "exercise520", "path": "sample.mp4", "window": "*100-190", "containsViolin": True}],
            transcriptions=[],
            sections=[
                {
                    "sampleId": "exercise520",
                    "url": "https://www.youtube.com/watch?v=exercise520",
                    "window": "*112-132",
                    "title": "5-20-26",
                    "meanRms": 0.8,
                    "note": "Audio-active section inside the sampled window.",
                }
            ],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-20")

        self.assertEqual(record["materialStatus"], "piece_or_exercise_pending")
        self.assertEqual(record["materialLabel"], "piece or exercise pending")
        self.assertEqual(record["evidenceStatus"], "piece_or_exercise_pending")
        self.assertEqual(record["transcription"]["scoreAlignmentStatus"], "pending_piece_or_exercise_alignment")
        self.assertIn("score-free technique exercise", record["transcription"]["reliabilityLimit"])
        self.assertEqual(record["heatMap"]["status"], "pending_piece_or_exercise_alignment")
        self.assertIn("score-free exercises", record["heatMap"]["limit"])

    def test_score_sequence_matches_rank_distinct_phrase_candidates_before_repeated_pitch_runs(self):
        series = detected_note_series(
            [
                {
                    "transcriptionId": "repeated-pitch-run",
                    "sampleId": "sample-repeated",
                    "sourceWindow": "*0-5",
                    "notes": [
                        note("D4", 0.0, 0.2),
                        note("D4", 0.2, 0.4),
                        note("D4", 0.4, 0.6),
                        note("D#4", 0.6, 0.8),
                        note("D4", 0.8, 1.0),
                    ],
                },
                {
                    "transcriptionId": "real-phrase-run",
                    "sampleId": "sample-phrase",
                    "sourceWindow": "*5-10",
                    "notes": [
                        note("C4", 0.0, 0.2),
                        note("D4", 0.2, 0.4),
                        note("E4", 0.4, 0.6),
                        note("F4", 0.6, 0.8),
                        note("G4", 0.8, 1.0),
                    ],
                },
            ],
            max_series=None,
        )
        pieces = [
            {
                "title": "Reference candidate",
                "score": {
                    "referencePitchClassSequences": [
                        {
                            "label": "reference audio",
                            "source": "local reference audio transcription",
                            "values": ["D", "D", "D", "D#", "D", "C", "D", "E", "F", "G"],
                        }
                    ]
                },
            }
        ]

        matches = score_sequence_matches_for_series(series, pieces, max_matches=2)

        self.assertEqual(matches[0]["detectedPitchClassSequence"], "C D E F G")
        self.assertEqual(matches[0]["matchedNoteRun"], 5)
        self.assertEqual(len(matches), 1)

    def test_candidate_micro_transcription_is_withheld_until_audio_match(self):
        inventory = {
            "youtube": [
                {
                    "id": "exercise521",
                    "title": "5-21-26",
                    "url": "https://www.youtube.com/watch?v=exercise521",
                    "publishedAt": "2026-05-21T09:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                }
            ]
        }
        names = ["E5", "F#5", "G5", "A5", "B5", "C6", "D6", "B5"]
        notes = [
            note(
                name,
                index * 0.16,
                index * 0.16 + 0.12,
                0.91,
                audioAgreement=True,
                agreementSources=["spectral_onset"],
                detectorSource="onset_segmented_pyin",
            )
            for index, name in enumerate(names)
        ]
        transcriptions = [
            {
                "transcriptionId": "micro",
                "sampleId": "exercise521",
                "sourceUrl": "https://www.youtube.com/watch?v=exercise521",
                "sourceTitle": "5-21-26",
                "sourceWindow": "*100-130",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 120,
                "noteCount": len(notes),
                "quality": {
                    "audioAgreementEventCount": len(notes),
                    "spectralAgreedEventCount": len(notes),
                },
                "notes": notes,
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "exercise521", "path": "sample.mp4", "window": "*100-130", "containsViolin": True}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-21")
        transcription = record["transcription"]

        self.assertEqual(daily["transcribedRecordCount"], 0)
        self.assertEqual(daily["scoreAudioOnlyRecordCount"], 1)
        self.assertEqual(transcription["status"], "score_audio_only")
        self.assertEqual(transcription["kind"], "score_audio_evidence")
        self.assertEqual(transcription["reliability"], "score_audio_only")
        self.assertFalse(transcription["displayNotation"])
        self.assertFalse(transcription["transcriptionReady"])
        self.assertEqual(transcription["clef"], "treble")
        self.assertEqual(transcription["keySignature"]["label"], "key pending")
        self.assertEqual(transcription["noteCount"], len(notes))
        self.assertEqual(transcription["events"], [])
        self.assertEqual(transcription["notationSystems"], [])
        self.assertEqual(transcription["qualityStatus"], "candidate_micro_transcription")
        self.assertEqual(transcription["candidateMicroNoteCount"], len(notes))
        self.assertIn("withheld", transcription["reliabilityLimit"])
        self.assertEqual(record["materialStatus"], "piece_or_exercise_pending")
        self.assertEqual(record["transcription"]["scoreAlignmentStatus"], "pending_piece_or_exercise_alignment")
        self.assertIn("full-session transcription", record["transcription"]["fullSessionLimit"])
        self.assertEqual(transcription["musicianRead"]["source"], "score-free or unidentified material")
        self.assertEqual(transcription["musicianRead"]["scoreMode"], "piece_or_exercise_pending")
        self.assertEqual(transcription["musicianRead"]["pattern"], "notation pending")

    def test_title_labeled_scale_becomes_calibration_anchor_not_repertoire(self):
        inventory = {
            "youtube": [
                {
                    "id": "gscale521",
                    "title": "5-21-26",
                    "url": "https://www.youtube.com/watch?v=gscale521",
                    "publishedAt": "2026-05-21T09:10:00Z",
                    "durationSeconds": 420,
                    "practiceCandidate": True,
                }
            ]
        }
        names = ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"]
        notes = [
            note(
                name,
                index * 0.2,
                index * 0.2 + 0.16,
                0.92,
                audioAgreement=True,
                agreementSources=["spectral_onset"],
                detectorSource="onset_segmented_pyin",
            )
            for index, name in enumerate(names)
        ]
        transcriptions = [
            {
                "transcriptionId": "gscale",
                "sampleId": "gscale521",
                "sourceUrl": "https://www.youtube.com/watch?v=gscale521",
                "sourceTitle": "G major scale violin calibration",
                "sourceWindow": "*60-90",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 92,
                "quality": {
                    "audioAgreementEventCount": len(notes),
                    "spectralAgreedEventCount": len(notes),
                },
                "notes": notes,
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "gscale521", "path": "gscale.mp4", "window": "*60-90", "containsViolin": True}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = daily["records"][0]
        transcription = record["transcription"]

        self.assertEqual(record["pieces"], [])
        self.assertEqual(transcription["keySignature"]["label"], "G major / 1 sharp")
        self.assertEqual(transcription["musicianRead"]["source"], "explicit title label")
        self.assertEqual(transcription["musicianRead"]["pieceTitle"], "G major scale")
        self.assertEqual(transcription["musicianRead"]["materialType"], "calibration_scale")
        self.assertEqual(transcription["musicianRead"]["scoreMode"], "title_labeled_calibration")

    def test_lead_transcription_uses_accepted_audio_match_not_unreviewed_micro_records(self):
        inventory = {
            "youtube": [
                {
                    "id": "wDfVpTU4I_I",
                    "title": "5-1-26",
                    "url": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                    "publishedAt": "2026-05-02T09:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                },
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "publishedAt": "2026-05-04T09:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                },
                {
                    "id": "newer_unverified",
                    "title": "5-6-26",
                    "url": "https://www.youtube.com/watch?v=newer_unverified",
                    "publishedAt": "2026-05-07T09:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                },
            ]
        }
        haydn_names = ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"]
        scherzo_names = ["E5", "F#5", "G5", "A5", "B5", "C6", "D6", "E6", "F#6", "G6", "A6", "B6"]
        transcriptions = [
            {
                "transcriptionId": "haydn",
                "sampleId": "wDfVpTU4I_I-13800",
                "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                "sourceTitle": "5-1-26",
                "sourceWindow": "*13800-13830",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 120,
                "quality": {"audioAgreementEventCount": len(haydn_names), "spectralAgreedEventCount": len(haydn_names)},
                "notes": [
                    note(
                        name,
                        index * 0.16,
                        index * 0.16 + 0.12,
                        0.91,
                        audioAgreement=True,
                        agreementSources=["spectral_onset"],
                        detectorSource="onset_segmented_pyin",
                    )
                    for index, name in enumerate(haydn_names)
                ],
            },
            {
                "transcriptionId": "scherzo",
                "sampleId": "Njh8_zq9_DM-26813",
                "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*26813-26843",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 132,
                "quality": {"audioAgreementEventCount": len(scherzo_names), "spectralAgreedEventCount": len(scherzo_names)},
                "notes": [
                    note(
                        name,
                        index * 0.13,
                        index * 0.13 + 0.1,
                        0.93,
                        audioAgreement=True,
                        agreementSources=["spectral_onset"],
                        detectorSource="onset_segmented_pyin",
                    )
                    for index, name in enumerate(scherzo_names)
                ],
            },
            {
                "transcriptionId": "unverified",
                "sampleId": "newer_unverified",
                "sourceUrl": "https://www.youtube.com/watch?v=newer_unverified",
                "sourceTitle": "5-6-26",
                "sourceWindow": "*100-130",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 120,
                "quality": {"audioAgreementEventCount": 0, "spectralAgreedEventCount": 0},
                "notes": [note("D4", index * 0.1, index * 0.1 + 0.08, 0.92, audioAgreement=False) for index in range(24)],
            },
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {"id": "wDfVpTU4I_I-13800", "path": "haydn.mp4", "window": "*13800-13830", "containsViolin": True},
                {"id": "Njh8_zq9_DM-26813", "path": "scherzo.mp4", "window": "*26813-26843", "containsViolin": True},
                {"id": "Njh8_zq9_DM-10545", "path": "scherzo-d4.webm", "window": "*10545-10635", "containsViolin": True},
                {"id": "Njh8_zq9_DM-10815", "path": "scherzo-a4.webm", "window": "*10815-10905", "containsViolin": True},
                {"id": "newer_unverified", "path": "newer.mp4", "window": "*100-130", "containsViolin": True},
            ],
            transcriptions=transcriptions,
            sections=[],
        )

        self.assertEqual(daily["leadTranscriptionPracticeDay"], "2026-05-03")
        self.assertEqual(daily["transcribedRecordCount"], 1)
        self.assertEqual(daily["scoreAudioOnlyRecordCount"], 2)
        scherzo = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-03")
        self.assertEqual(scherzo["transcription"]["status"], "audio_matched_fragment")
        self.assertEqual(scherzo["transcription"]["renderedNoteCount"], 2)
        self.assertEqual(scherzo["transcription"]["events"][0]["note"], "D4")
        self.assertEqual(scherzo["transcription"]["events"][1]["note"], "A4")
        self.assertEqual(scherzo["clips"][0]["sampleId"], "Njh8_zq9_DM-10545")
        self.assertEqual(scherzo["clips"][1]["sampleId"], "Njh8_zq9_DM-10815")
        self.assertEqual(scherzo["transcription"]["musicianRead"]["source"], "Alan-confirmed source label")
        self.assertEqual(scherzo["transcription"]["musicianRead"]["scoreMode"], "source_confirmed_score_target")
        self.assertEqual(scherzo["matchingWorkflow"]["status"], "searching_score_match")
        self.assertFalse(scherzo["transcription"]["scoreLinked"])
        self.assertFalse(scherzo["transcription"]["referenceLinked"])
        self.assertEqual(len(scherzo["matchGroups"]), 0)
        self.assertEqual(scherzo["transcription"]["scoreSequenceMatchCount"], 0)
        self.assertGreaterEqual(scherzo["transcription"]["detectedSeriesCount"], 1)

    def test_audio_matched_single_note_fragment_renders_with_exact_clip_window(self):
        inventory = {
            "youtube": [
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "publishedAt": "2026-05-04T09:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "scherzo",
                "sampleId": "Njh8_zq9_DM-10545",
                "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*10545-10635",
                "status": "failed_pitch_collapse",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 120,
                "noteCount": 30,
                "quality": {"failed": True, "failureMode": "repeated_pitch_collapse"},
                "notes": [note("D5", index * 0.1, index * 0.1 + 0.08, 0.92) for index in range(30)],
                "matchedFragments": [
                    {
                        "status": "audio_matched",
                        "kind": "stable_single_note",
                        "startSeconds": 3.866,
                        "endSeconds": 4.458,
                        "durationSeconds": 0.592,
                        "midi": midi_for_note("D4"),
                        "note": "D4",
                        "confidence": 0.961,
                        "pitchStdCents": 7.0,
                        "medianPitchOffsetCents": 0.0,
                        "voicedFrameCount": 48,
                        "detectors": ["pyin", "yin"],
                    }
                ],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {
                    "id": "Njh8_zq9_DM-10545",
                    "path": "scherzo.webm",
                    "window": "*10545-10635",
                    "containsViolin": True,
                }
            ],
            transcriptions=transcriptions,
            sections=[],
        )

        record = daily["records"][0]
        transcription = record["transcription"]

        self.assertEqual(daily["transcribedRecordCount"], 1)
        self.assertEqual(daily["leadTranscriptionPracticeDay"], "2026-05-03")
        self.assertEqual(transcription["status"], "audio_matched_fragment")
        self.assertEqual(transcription["kind"], "audio_matched_fragment_transcription")
        self.assertTrue(transcription["displayNotation"])
        self.assertTrue(transcription["transcriptionReady"])
        self.assertEqual(transcription["renderedNoteCount"], 1)
        self.assertEqual(transcription["events"][0]["note"], "D4")
        self.assertTrue(transcription["events"][0]["strictAudioWindow"])
        self.assertEqual(record["matchingWorkflow"]["status"], "searching_score_match")
        self.assertEqual(record["matchingWorkflow"]["displayMode"], "groups_only")
        self.assertEqual(record["matchingWorkflow"]["matchCriterion"], "pitch_class_sequence")
        self.assertEqual(record["matchingWorkflow"]["minimumMatchedNoteRun"], 1)
        self.assertEqual(record["matchingWorkflow"]["minimumDistinctPitchClasses"], 2)
        self.assertFalse(record["matchingWorkflow"]["rhythmRequired"])
        self.assertEqual(transcription["pdfUrl"], "/api/curtis/daily-records/2026-05-03/transcription.pdf")
        self.assertEqual(record["matchGroups"], [])
        self.assertEqual(transcription["scoreReferenceStatus"], "symbolic_score_sequence_ready")
        self.assertEqual(transcription["scoreSequenceMatchCount"], 0)
        self.assertEqual(len(transcription["notationSystems"]), 1)
        self.assertEqual(transcription["notationSystems"][0]["clip"]["localStartSeconds"], 3.866)
        self.assertEqual(transcription["notationSystems"][0]["clip"]["localEndSeconds"], 4.458)
        self.assertIn("/clip?start=3.866&end=4.458", transcription["notationSystems"][0]["clip"]["audioUrl"])
        self.assertEqual(record["clips"][0]["type"], "audio_matched_fragment")
        self.assertEqual(record["clips"][0]["localStartSeconds"], 3.866)
        self.assertEqual(record["clips"][0]["localEndSeconds"], 4.458)
        self.assertIn("/clip?start=3.866&end=4.458", record["clips"][0]["audioUrl"])

    def test_detected_note_series_can_match_score_pitch_classes_without_rhythm(self):
        transcriptions = [
            {
                "transcriptionId": "detected-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("D4", 0, 0.2),
                    note("A4", 0.2, 0.35),
                    note("B4", 0.35, 0.5),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        matches = score_sequence_matches_for_series(
            series,
            [
                {
                    "title": "Source-backed test piece",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scoreNoteDetectionStatus": "source_confirmed_score_sequence",
                        "scoreBoxes": [{"x": 10, "y": 20, "width": 30, "height": 8, "label": "mm. 1-2"}],
                        "scorePitchClassSequences": [
                            {"label": "mm. 1-2", "values": ["G4", "D5", "A5", "B5", "E6"]},
                        ],
                    },
                }
            ],
        )

        self.assertEqual(series[0]["collapsedPitchClassSeriesLabel"], "D A B")
        self.assertEqual(matches[0]["matchedNoteRun"], 3)
        self.assertEqual(matches[0]["detectedPitchClassSequence"], "D A B")
        self.assertEqual(matches[0]["scorePitchClassSequence"], "D A B")
        self.assertEqual(matches[0]["detectedPitchClassSequenceCompact"], "D A B")
        self.assertEqual([item["note"] for item in matches[0]["displayDetectedNotes"]], ["D4", "A4", "B4"])
        self.assertEqual(matches[0]["minimumDistinctPitchClasses"], 2)
        self.assertEqual(matches[0]["score"]["boxes"], [])
        self.assertEqual(matches[0]["score"]["cropStatus"], "exact_score_location_pending")
        self.assertEqual(matches[0]["scoreSnippetStatus"], "exact_score_location_pending")
        self.assertFalse(matches[0]["rhythmRequired"])

    def test_score_sequence_match_uses_score_boxes_only_when_location_is_exact(self):
        transcriptions = [
            {
                "transcriptionId": "matched-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("D4", 0, 0.2),
                    note("A4", 0.2, 0.35),
                    note("B4", 0.35, 0.5),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        matches = score_sequence_matches_for_series(
            series,
            [
                {
                    "title": "Source-backed test piece",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scoreSequenceLocations": [
                            {
                                "label": "mm. 1-2",
                                "status": "exact_score_location_verified",
                                "referenceStart": 1,
                                "referenceEnd": 4,
                                "boxes": [{"x": 10, "y": 20, "width": 30, "height": 8, "label": "mm. 1-2"}],
                            }
                        ],
                        "scorePitchClassSequences": [
                            {"label": "mm. 1-2", "values": ["G4", "D5", "A5", "B5", "E6"]},
                        ],
                    },
                }
            ],
        )

        self.assertEqual(matches[0]["score"]["boxes"][0]["label"], "mm. 1-2")
        self.assertEqual(matches[0]["score"]["cropStatus"], "exact_score_location_verified")
        self.assertEqual(matches[0]["scoreSnippetStatus"], "exact_score_location_verified")

    def test_verified_score_location_does_not_unlock_unrelated_score_sequences(self):
        transcriptions = [
            {
                "transcriptionId": "unrelated-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("E4", 0, 0.2),
                    note("F4", 0.2, 0.35),
                    note("G4", 0.35, 0.5),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        matches = score_sequence_matches_for_series(
            series,
            [
                {
                    "title": "Source-backed test piece",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scoreSequenceLocations": [
                            {
                                "label": "mm. 1-2",
                                "status": "exact_score_location_verified",
                                "referenceStart": 0,
                                "referenceEnd": 3,
                                "boxes": [{"x": 10, "y": 20, "width": 30, "height": 8, "label": "mm. 1-2"}],
                            }
                        ],
                        "scorePitchClassSequences": [
                            {"label": "mm. 1-2", "values": ["D4", "A4", "B4"]},
                            {"label": "mm. 3-4", "values": ["E4", "F4", "G4"]},
                        ],
                    },
                }
            ],
        )

        self.assertEqual(matches, [])

    def test_repeated_single_pitch_series_does_not_create_score_match_group(self):
        transcriptions = [
            {
                "transcriptionId": "repeated-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [note("D4", index * 0.2, index * 0.2 + 0.1) for index in range(8)],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        matches = score_sequence_matches_for_series(
            series,
            [
                {
                    "title": "Source-backed test piece",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scoreNoteDetectionStatus": "source_confirmed_score_sequence",
                        "scorePitchClassSequences": [
                            {"label": "mm. 1-2", "values": ["D4", "D5", "D5", "D4", "D6"]},
                        ],
                    },
                }
            ],
        )

        self.assertEqual(matches, [])

    def test_collapsed_score_match_maps_back_to_compact_source_notes(self):
        transcriptions = [
            {
                "transcriptionId": "collapsed-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("D4", 0.0, 0.2),
                    note("D4", 0.2, 0.4),
                    note("D4", 0.4, 0.6),
                    note("A#4", 0.6, 0.8),
                    note("A#4", 0.8, 1.0),
                    note("G4", 1.0, 1.2),
                    note("D4", 1.2, 1.4),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        matches = score_sequence_matches_for_series(
            series,
            [
                {
                    "title": "Source-backed test piece",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scoreNoteDetectionStatus": "source_confirmed_score_sequence",
                        "scorePitchClassSequences": [
                            {"label": "mm. 1-2", "values": ["D4", "A#4", "G4", "D4"]},
                        ],
                    },
                }
            ],
        )

        self.assertEqual(matches[0]["detectedPitchClassSequence"], "D A# G D")
        self.assertEqual([item["note"] for item in matches[0]["displayDetectedNotes"]], ["D4", "A#4", "G4", "D4"])

    def test_scanned_pdf_score_sequences_are_ignored_until_note_source_is_proven(self):
        transcriptions = [
            {
                "transcriptionId": "scanned-score-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("D4", 0, 0.2),
                    note("A4", 0.2, 0.35),
                    note("B4", 0.35, 0.5),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        score_target = {
            "scoreAssetId": "scanned-score",
            "scoreNoteDetectionStatus": "not_available_for_scanned_pdf",
            "scorePitchClassSequences": [
                {"label": "bad ocr guess", "values": ["D4", "A4", "B4"]},
            ],
        }

        matches = score_sequence_matches_for_series(series, [{"title": "Scanned PDF", "score": score_target}])

        self.assertEqual(matches, [])

    def test_single_pitch_anchor_records_obvious_note_overlap_without_score_location(self):
        transcriptions = [
            {
                "transcriptionId": "anchor-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("A4", 0.25, 0.45),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        anchors = pitch_anchor_matches_for_series(
            series,
            [
                {
                    "title": "Source-backed test piece",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scorePitchClassAnchors": [
                            {
                                "pitchClass": "A",
                                "status": "source_confirmed_pitch_anchor",
                                "source": "IMSLP public-domain source score",
                                "sourceUrl": "https://imslp.org/wiki/test",
                                "pdfUrl": "https://imslp.org/test.pdf",
                                "sourcePage": 3,
                                "snippetImageUrl": "/assets/score/test-a.png",
                                "snippetStatus": "source_score_pitch_anchor",
                                "noteLocation": "highlighted A4",
                                "visualNoteVerified": True,
                                "exactNoteVerified": True,
                            },
                        ],
                    },
                }
            ],
        )

        self.assertEqual(anchors[0]["status"], "pitch_anchor_match")
        self.assertEqual(anchors[0]["detectedPitchClassSequence"], "A")
        self.assertEqual(anchors[0]["minimumDistinctPitchClasses"], 1)
        self.assertEqual(anchors[0]["scoreAnchorNotes"][0]["note"], "A4")
        self.assertEqual(anchors[0]["scoreAnchorNotes"][0]["pitchClass"], "A")
        self.assertEqual(anchors[0]["scoreAnchorSnippet"]["imageUrl"], "/assets/score/test-a.png")
        self.assertEqual(anchors[0]["scoreAnchorSnippet"]["note"], "A4")
        self.assertEqual(anchors[0]["scoreAnchorSnippet"]["pitchClass"], "A")
        self.assertEqual(anchors[0]["scoreAnchorSnippet"]["status"], "source_score_pitch_anchor")
        self.assertTrue(anchors[0]["scoreAnchorSnippet"]["visualNoteVerified"])
        self.assertTrue(anchors[0]["scoreAnchorSnippet"]["exactNoteVerified"])
        self.assertTrue(anchors[0]["scoreAnchorSnippet"]["visibleScoreNoteSequenceVerified"])
        self.assertEqual(anchors[0]["score"]["imageUrl"], "/assets/score/test-a.png")
        self.assertEqual(anchors[0]["score"]["boxes"], [])
        self.assertFalse(anchors[0]["scoreLocationVerified"])

    def test_unverified_pitch_anchor_is_not_accepted_as_score_match(self):
        transcriptions = [
            {
                "transcriptionId": "anchor-run",
                "sampleId": "sample-1",
                "sourceTitle": "test",
                "sourceUrl": "https://www.youtube.com/watch?v=test",
                "sourceWindow": "*10-20",
                "status": "transcribed",
                "notes": [
                    note("A4", 0.25, 0.45),
                ],
            }
        ]
        series = detected_note_series(transcriptions, max_series=None)
        anchors = pitch_anchor_matches_for_series(
            series,
            [
                {
                    "title": "Unverified score crop",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scorePitchClassAnchors": [
                            {
                                "pitchClass": "A",
                                "displayNote": "A4",
                                "snippetImageUrl": "/assets/score/bad-a.png",
                                "snippetStatus": "source_score_pitch_anchor",
                            },
                        ],
                    },
                }
            ],
        )

        self.assertEqual(anchors, [])

    def test_visual_pitch_anchor_without_exact_note_review_is_not_renderable(self):
        series = detected_note_series(
            [
                {
                    "transcriptionId": "anchor-run",
                    "sampleId": "sample-1",
                    "sourceTitle": "test",
                    "sourceUrl": "https://www.youtube.com/watch?v=test",
                    "sourceWindow": "*10-20",
                    "status": "transcribed",
                    "notes": [note("A4", 0.25, 0.45)],
                }
            ],
            max_series=None,
        )
        anchors = pitch_anchor_matches_for_series(
            series,
            [
                {
                    "title": "Visual-only score crop",
                    "score": {
                        "scoreAssetId": "test-score",
                        "scorePitchClassAnchors": [
                            {
                                "pitchClass": "A",
                                "displayNote": "A4",
                                "snippetImageUrl": "/assets/score/a-crop.png",
                                "snippetStatus": "source_score_pitch_anchor",
                                "visualNoteVerified": True,
                            },
                        ],
                    },
                }
            ],
        )

        self.assertEqual(anchors, [])

    def test_exact_verified_score_anchor_does_not_accept_same_pitch_class_different_octave(self):
        target = {
            "scorePitchClassAnchors": [
                {
                    "pitchClass": "A",
                    "displayNote": "A4",
                    "snippetImageUrl": "/assets/score/test-a4.png",
                    "visualNoteVerified": True,
                    "exactNoteVerified": True,
                }
            ]
        }

        a4_series = [{"transcriptionId": "a4", "notes": [note("A4", 0, 1)]}]
        a5_series = [{"transcriptionId": "a5", "notes": [note("A5", 0, 1)]}]

        self.assertEqual(
            pitch_anchor_matches_for_series(a4_series, [{"title": "Score", "score": target}])[0]["matchedDetectedNotes"][0]["note"],
            "A4",
        )
        self.assertEqual(pitch_anchor_matches_for_series(a5_series, [{"title": "Score", "score": target}]), [])

    def test_wieniawski_score_note_anchor_and_rejected_phrase_are_withheld(self):
        target = wieniawski_reference_target()
        audit = score_reference_audit_for_pieces([{"score": target}])
        rejected_by_note = {}
        for anchor in target["rejectedScorePitchClassAnchors"]:
            rejected_by_note.setdefault(anchor["displayNote"], []).append(anchor)

        self.assertEqual(target["scoreNoteCropStatus"], "actual_source_phrase_review_pending")
        self.assertEqual(audit["sourcePdfLocalReadyCount"], 1)
        self.assertEqual(audit["symbolicScoreNoteCount"], 9)
        self.assertEqual(audit["symbolicScoreSourceSnippetCount"], 0)
        self.assertGreaterEqual(audit["scoreMapCandidateGlyphCount"], 1)
        self.assertGreaterEqual(audit["scoreMapCandidateStaffCount"], 1)
        self.assertGreaterEqual(audit["scoreMapNoteHypothesisCount"], 1)
        self.assertGreaterEqual(audit["scoreMapNoteHypothesisStaffCount"], 1)
        self.assertGreaterEqual(audit["scoreMapReviewPacketCount"], 1)
        self.assertTrue(
            target["symbolicScore"]["candidateMapPath"].endswith(
                "wieniawski-scherzo-tarantelle-page2-score-map-candidates.json"
            )
        )
        self.assertEqual(target["scorePitchClassAnchors"], [])
        accepted_source = target["symbolicScore"]["sourceSnippets"][1]
        self.assertEqual(accepted_source["status"], "source_score_phrase_review_rejected")
        self.assertEqual(accepted_source["visibleScoreExactNoteSequence"], ["Bb4", "D5", "C5", "Bb4", "D5"])
        self.assertFalse(accepted_source["visibleScoreExactNoteSequenceVerified"])
        self.assertFalse(accepted_source["scoreBoxCenterAgreement"])
        corrected_source = target["symbolicScore"]["sourceSnippets"][2]
        self.assertEqual(corrected_source["status"], "source_score_phrase_review_rejected")
        self.assertEqual(corrected_source["visibleScoreExactNoteSequence"], ["Bb4", "D5", "C5", "Bb4", "D5"])
        self.assertFalse(corrected_source["visibleScoreExactNoteSequenceVerified"])
        self.assertFalse(corrected_source["scoreBoxCenterAgreement"])
        self.assertFalse(corrected_source["truthEvidenceAccepted"])
        self.assertEqual(target["symbolicScoreStatus"], "source_symbolic_opening_phrase_review_pending")
        self.assertTrue(
            any(
                item.get("pitchClassSequence") == ["A#", "D", "C", "A#", "D"]
                and item.get("status") == "alan_rejected_2026_05_15"
                for item in target["rejectedScorePhraseSequences"]
            )
        )
        self.assertTrue(
            any(
                anchor.get("snippetImageUrl") == "/assets/score/wieniawski-scherzo-tarantelle-a4-source-verified.png"
                and anchor.get("status") == "rejected_visual_note_review"
                for anchor in rejected_by_note["A4"]
            )
        )
        self.assertTrue(any(anchor.get("displayNote") == "A5" for anchor in target["rejectedScorePitchClassAnchors"]))

        a4_series = [{"transcriptionId": "a4", "notes": [note("A4", 0, 1)]}]
        a5_series = [{"transcriptionId": "a5", "notes": [note("A5", 0, 1)]}]
        self.assertEqual(pitch_anchor_matches_for_series(a4_series, [{"title": "Scherzo", "score": target}]), [])
        self.assertEqual(pitch_anchor_matches_for_series(a5_series, [{"title": "Scherzo", "score": target}]), [])

    def test_daily_score_anchor_requires_audio_accepted_fragment_not_raw_detector_note(self):
        inventory = {
            "youtube": [
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "publishedAt": "2026-05-03T10:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "raw-a4-only",
                "sampleId": "Njh8_zq9_DM-999",
                "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*999-1089",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "notes": [note("A4", 4.133, 4.191, 0.784)],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {
                    "id": "Njh8_zq9_DM-999",
                    "path": "raw-a4.webm",
                    "window": "*999-1089",
                    "containsViolin": True,
                }
            ],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-03")

        self.assertEqual(record["pitchAnchorGroups"], [])

    def test_daily_score_anchor_withholds_audio_a4_when_score_crop_is_rejected(self):
        inventory = {
            "youtube": [
                {
                    "id": "Njh8_zq9_DM",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                    "publishedAt": "2026-05-03T10:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "accepted-a4",
                "sampleId": "Njh8_zq9_DM-8925",
                "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*8925-9015",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "notes": [note("A4", 7.198, 7.605, 0.891)],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {
                    "id": "Njh8_zq9_DM-8925",
                    "path": "accepted-a4.webm",
                    "window": "*8925-9015",
                    "containsViolin": True,
                }
            ],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-03")

        self.assertEqual(record["pitchAnchorGroups"], [])

    def test_unaccepted_audio_matched_fragment_stays_hidden(self):
        inventory = {
            "youtube": [
                {
                    "id": "unaccepted_526",
                    "title": "5-26-26",
                    "url": "https://www.youtube.com/watch?v=unaccepted_526",
                    "publishedAt": "2026-05-26T09:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "unaccepted-fragment",
                "sampleId": "unaccepted_526-120",
                "sourceUrl": "https://www.youtube.com/watch?v=unaccepted_526",
                "sourceTitle": "5-26-26",
                "sourceWindow": "*120-210",
                "status": "failed_pitch_collapse",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 120,
                "noteCount": 30,
                "quality": {"failed": True, "failureMode": "repeated_pitch_collapse"},
                "notes": [note("D5", index * 0.1, index * 0.1 + 0.08, 0.92) for index in range(30)],
                "matchedFragments": [
                    {
                        "status": "audio_matched",
                        "kind": "stable_single_note",
                        "startSeconds": 17.891,
                        "endSeconds": 18.541,
                        "durationSeconds": 0.65,
                        "midi": midi_for_note("E6"),
                        "note": "E6",
                        "confidence": 0.985,
                        "pitchStdCents": 6.0,
                        "medianPitchOffsetCents": 0.0,
                        "voicedFrameCount": 55,
                        "detectors": ["pyin", "yin"],
                    }
                ],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {
                    "id": "unaccepted_526-120",
                    "path": "unaccepted.webm",
                    "window": "*120-210",
                    "containsViolin": True,
                }
            ],
            transcriptions=transcriptions,
            sections=[],
        )

        record = daily["records"][0]
        self.assertEqual(daily["transcribedRecordCount"], 0)
        self.assertEqual(daily["leadTranscriptionPracticeDay"], "")
        self.assertEqual(record["transcription"]["status"], "score_audio_only")
        self.assertFalse(record["transcription"]["displayNotation"])
        self.assertFalse(any(clip.get("type") == "audio_matched_fragment" for clip in record["clips"]))

    def test_micro_transcription_rejects_repeated_unagreed_note_stream(self):
        inventory = {
            "youtube": [
                {
                    "id": "repeat521",
                    "title": "5-21-26",
                    "url": "https://www.youtube.com/watch?v=repeat521",
                    "publishedAt": "2026-05-21T10:10:00Z",
                    "durationSeconds": 900,
                    "practiceCandidate": True,
                }
            ]
        }
        notes = [
            note(
                "D4",
                index * 0.08,
                index * 0.08 + 0.06,
                0.92,
                audioAgreement=False,
                agreementSources=[],
                detectorSource="pitch_hysteresis",
            )
            for index in range(20)
        ]
        transcriptions = [
            {
                "transcriptionId": "repeat",
                "sampleId": "repeat521",
                "sourceUrl": "https://www.youtube.com/watch?v=repeat521",
                "sourceTitle": "5-21-26",
                "sourceWindow": "*200-230",
                "status": "transcribed",
                "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                "tempoBpm": 120,
                "noteCount": len(notes),
                "quality": {"audioAgreementEventCount": 0, "spectralAgreedEventCount": 0},
                "notes": notes,
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "repeat521", "path": "sample.mp4", "window": "*200-230", "containsViolin": True}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-21")

        self.assertEqual(daily["transcribedRecordCount"], 0)
        self.assertEqual(record["transcription"]["status"], "score_audio_only")
        self.assertFalse(record["transcription"]["displayNotation"])
        self.assertEqual(record["transcription"]["failureMode"], "unverified_machine_pitch")

    def test_stale_pipeline_transcriptions_do_not_surface_as_current_clips(self):
        inventory = {
            "youtube": [
                {
                    "id": "wDfVpTU4I_I",
                    "title": "5-1-26",
                    "url": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
                    "publishedAt": "2026-05-03T10:20:47Z",
                    "durationSeconds": 300,
                    "practiceCandidate": True,
                }
            ]
        }
        old_item = {
            "transcriptionId": "old",
            "sampleId": "wDfVpTU4I_I-old",
            "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
            "sourceTitle": "5-1-26",
            "sourceWindow": "*10-30",
            "status": "transcribed",
            "pipelineVersion": "violin_pyin_onset_v3",
            "noteCount": 24,
            "notes": [note("D4", index * 0.1, index * 0.1 + 0.08) for index in range(24)],
        }
        current_item = {
            "transcriptionId": "current",
            "sampleId": "wDfVpTU4I_I-current",
            "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
            "sourceTitle": "5-1-26",
            "sourceWindow": "*40-70",
            "status": "transcribed",
            "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
            "noteCount": 24,
            "notes": [note("G4", index * 0.1, index * 0.1 + 0.08) for index in range(24)],
        }

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {"id": "wDfVpTU4I_I-old", "path": "old.mp4", "window": "*10-30", "containsViolin": True},
                {"id": "wDfVpTU4I_I-current", "path": "current.mp4", "window": "*40-70", "containsViolin": True},
            ],
            transcriptions=[old_item, current_item],
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-01")

        self.assertEqual(record["clips"][0]["pipelineVersion"], TRANSCRIPTION_PIPELINE_VERSION)
        self.assertEqual(record["clips"][0]["sampleId"], "wDfVpTU4I_I-current")
        self.assertNotIn("violin_pyin_onset_v3", [clip.get("pipelineVersion") for clip in record["clips"]])
        self.assertEqual(record["transcription"]["noteCount"], 24)

    def test_repeated_pitch_collapse_is_reported_as_matching_evidence(self):
        inventory = {
            "youtube": [
                {
                    "id": "collapse",
                    "title": "5-3-26",
                    "url": "https://www.youtube.com/watch?v=collapse",
                    "publishedAt": "2026-05-04T09:10:00Z",
                    "durationSeconds": 300,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "collapse-1",
                "sampleId": "collapse",
                "sourceUrl": "https://www.youtube.com/watch?v=collapse",
                "sourceTitle": "5-3-26",
                "sourceWindow": "*0-60",
                "status": "failed_pitch_collapse",
                "durationSeconds": 42,
                "tempoBpm": 108,
                "noteCount": 24,
                "notes": [note("D4", index * 0.05, index * 0.05 + 0.04) for index in range(24)],
                "quality": {
                    "failed": True,
                    "failureMode": "repeated_pitch_collapse",
                    "failureLimit": "Machine pitch extraction was rejected because the note stream collapsed into repeated D4 events.",
                    "pitchCollapseDominantNote": "D4",
                    "pitchCollapseEventCount": 24,
                    "pitchCollapseDetectedOnsetCount": 28,
                    "windowMode": "detected_active_sections",
                },
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "collapse", "path": "sample.mp4", "window": "*0-60", "containsViolin": True}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = daily["records"][0]

        self.assertEqual(daily["failedTranscriptionRecordCount"], 0)
        self.assertEqual(daily["scoreAudioOnlyRecordCount"], 1)
        self.assertEqual(record["transcription"]["status"], "score_audio_only")
        self.assertEqual(record["transcription"]["qualityStatus"], "score_audio_only")
        self.assertEqual(record["transcription"]["reliability"], "score_audio_only")
        self.assertEqual(record["transcription"]["failureMode"], "repeated_pitch_collapse")
        self.assertFalse(record["transcription"]["displayNotation"])
        self.assertEqual(record["transcription"]["qualityLabel"], "matching")
        self.assertIn("Only audio-checked note evidence", record["transcription"]["reliabilityLimit"])
        self.assertIn("score", record["mainCurtisBlocker"])
        self.assertIn("Only audio-checked note evidence", record["clips"][0]["reason"])

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
        self.assertEqual(repertoire["entries"][0]["heatMap"]["status"], "pending_transcription")
        self.assertEqual(repertoire["entries"][0]["heatMap"]["fragments"], [])
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
            media_samples=[
                {"id": "K38CgZhvF3Q", "path": "sample.mp4", "window": "*10-100", "containsViolin": True},
                {"id": "K38CgZhvF3Q-empty", "path": "empty.mp4", "window": "*100-190", "containsViolin": True},
            ],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-02")

        self.assertEqual(record["transcription"]["windowSeconds"], 12)
        self.assertEqual(record["transcription"]["segmentCount"], 1)
        self.assertEqual(record["transcription"]["coverageStatus"], "active_sections_only")
        self.assertIn("active-audio evidence", record["transcription"]["coverageLimit"])
        self.assertEqual(record["activeViolinSeconds"], 57)
        self.assertEqual(record["clips"][0]["activeTranscribedSeconds"], 12.4)
        self.assertIn("active audio", record["clips"][0]["reason"])
        self.assertEqual(record["clips"][1]["activeTranscribedSeconds"], 44.2)
        self.assertIn("no reliable accepted transcription", record["clips"][1]["reason"])

    def test_unverified_media_samples_are_withheld_from_audio_and_transcription(self):
        inventory = {
            "youtube": [
                {
                    "id": "e8a0hrb4IzY",
                    "title": "5-6-26",
                    "url": "https://www.youtube.com/watch?v=e8a0hrb4IzY",
                    "publishedAt": "2026-05-07T09:10:00Z",
                    "durationSeconds": 600,
                    "practiceCandidate": True,
                }
            ]
        }
        transcriptions = [
            {
                "transcriptionId": "bad-room-window",
                "sampleId": "e8a0hrb4IzY-600",
                "sourceUrl": "https://www.youtube.com/watch?v=e8a0hrb4IzY",
                "sourceTitle": "5-6-26",
                "sourceWindow": "*600-690",
                "status": "transcribed",
                "tempoBpm": 100,
                "noteCount": 24,
                "notes": [note("D4", index * 0.1, index * 0.1 + 0.08) for index in range(24)],
            }
        ]

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[
                {
                    "id": "e8a0hrb4IzY-600",
                    "path": "room.mp4",
                    "window": "*600-690",
                    "violinPresence": "unverified",
                }
            ],
            transcriptions=transcriptions,
            sections=[
                {
                    "sampleId": "e8a0hrb4IzY-600",
                    "url": "https://www.youtube.com/watch?v=e8a0hrb4IzY",
                    "startSeconds": 600,
                    "endSeconds": 640,
                    "status": "candidate_playing_section",
                }
            ],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-06")

        self.assertEqual(daily["audioEvidenceRecordCount"], 0)
        self.assertEqual(daily["scoreAudioOnlyRecordCount"], 0)
        self.assertEqual(daily["withheldNonViolinSampleCount"], 1)
        self.assertEqual(daily["violinPositiveSampleCount"], 0)
        self.assertEqual(record["activeViolinSeconds"], 0)
        self.assertEqual(record["status"], "pending_media")
        self.assertEqual(record["transcription"]["kind"], "pending")
        self.assertFalse(record["transcription"]["notationSystems"])
        self.assertNotIn("/api/curtis/media/sample", str(record["clips"]))

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

        daily = build_daily_records(
            inventory=inventory,
            state={},
            media_samples=[{"id": "wDfVpTU4I_I", "path": "sample.mp4", "window": "*100-180", "containsViolin": True}],
            transcriptions=transcriptions,
            sections=[],
        )
        record = next(item for item in daily["records"] if item["practiceDay"] == "2026-05-01")
        transcription = record["transcription"]

        self.assertEqual(transcription["keySignature"]["label"], "G major / 1 sharp")
        self.assertEqual(transcription["events"], [])
        self.assertFalse(transcription["notationSystems"])
        self.assertEqual(transcription["eventCount"], 0)
        self.assertEqual(transcription["renderedEventCount"], 0)
        self.assertFalse(transcription["displayNotation"])
        self.assertEqual(transcription["status"], "score_audio_only")
        self.assertEqual(transcription["qualityStatus"], "score_audio_only")
        self.assertEqual(transcription["reliability"], "score_audio_only")
        self.assertEqual(transcription["failureMode"], "unverified_machine_pitch")
        self.assertEqual(transcription["hiddenPitchEventCount"], len(notes))
        self.assertIn("hidden from notation", transcription["displayLimit"])


if __name__ == "__main__":
    unittest.main()
