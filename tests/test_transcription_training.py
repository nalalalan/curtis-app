import unittest
from unittest.mock import patch

from backend.app import transcription as transcription_module
from backend.app.scanner import derive_review
from backend.app.study_packets import build_practice_study, build_practice_totals
from backend.app.transcription import (
    TRANSCRIPTION_PIPELINE_VERSION,
    active_windows_for_sample,
    compare_fingerprints,
    choose_transcription_events,
    event_fingerprint,
    f0_to_onset_events,
    f0_to_events,
    mark_audio_agreement,
    normalize_audio_signal,
    onset_frames_for_signal,
    PITCH_HOP_LENGTH,
    pitch_sanity_filter,
    stable_single_note_fragments,
    spectral_onset_events,
    transcribe_audio_array,
    transcription_failure_state,
    reference_matches_for,
    transcription_prior_hint,
    yin_transition_events,
)


def hz_for_midi(midi):
    return 440.0 * (2 ** ((midi - 69) / 12))


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


def note_event(midi, index, confidence=0.9, duration=0.2):
    start = round(index * duration, 3)
    end = round(start + duration, 3)
    return {
        "startSeconds": start,
        "endSeconds": end,
        "durationSeconds": duration,
        "midi": midi,
        "note": str(midi),
        "confidence": confidence,
    }


class TranscriptionTrainingTests(unittest.TestCase):
    def test_stable_single_note_fragment_requires_pyin_yin_pitch_match(self):
        import numpy
        import librosa

        sr = 22050
        duration = 0.75
        midi = 88
        times = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
        y = 0.2 * numpy.sin(2 * numpy.pi * hz_for_midi(midi) * times)

        fragments = stable_single_note_fragments(y, sr, librosa, numpy)

        self.assertTrue(fragments)
        self.assertEqual(fragments[0]["note"], "E6")
        self.assertEqual(fragments[0]["detectors"], ["pyin", "yin"])
        self.assertLessEqual(fragments[0]["pitchStdCents"], 18.0)

    def test_active_windows_for_sample_uses_detected_playing_sections(self):
        sample = {"id": "sample-1", "window": "*100-190"}
        state = {
            "review": {
                "notableSections": [
                    {
                        "sampleId": "sample-1",
                        "status": "candidate_playing_section",
                        "startSeconds": 110,
                        "endSeconds": 114,
                    },
                    {
                        "sampleId": "sample-1",
                        "status": "candidate_playing_section",
                        "startSeconds": 114,
                        "endSeconds": 118,
                    },
                    {
                        "sampleId": "other",
                        "status": "candidate_playing_section",
                        "startSeconds": 120,
                        "endSeconds": 125,
                    },
                ]
            }
        }

        windows = active_windows_for_sample(sample, state)

        self.assertEqual(len(windows), 1)
        self.assertAlmostEqual(windows[0]["start"], 9.65)
        self.assertAlmostEqual(windows[0]["end"], 18.35)

    def test_f0_to_events_rejects_pitches_below_violin_range(self):
        import numpy

        f0 = numpy.array([hz_for_midi(50), hz_for_midi(50), hz_for_midi(55), hz_for_midi(55), hz_for_midi(55), hz_for_midi(55)])
        voiced = numpy.array([True, True, True, True, True, True])
        probability = numpy.array([0.95, 0.95, 0.95, 0.95, 0.95, 0.95])

        events = f0_to_events(f0, voiced, probability, 22050, 512, numpy)

        self.assertEqual([event["note"] for event in events], ["G3"])

    def test_f0_to_events_absorbs_single_frame_vibrato_noise(self):
        import numpy

        f0 = numpy.array([
            hz_for_midi(69),
            hz_for_midi(69),
            hz_for_midi(70),
            hz_for_midi(69),
            hz_for_midi(69),
            hz_for_midi(69),
        ])
        voiced = numpy.array([True, True, True, True, True, True])
        probability = numpy.array([0.95, 0.95, 0.92, 0.95, 0.95, 0.95])

        events = f0_to_events(f0, voiced, probability, 22050, 512, numpy)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["note"], "A4")

    def test_f0_to_events_requires_sustained_pitch_change(self):
        import numpy

        f0 = numpy.array([
            hz_for_midi(69),
            hz_for_midi(69),
            hz_for_midi(69),
            hz_for_midi(69),
            hz_for_midi(71),
            hz_for_midi(71),
            hz_for_midi(71),
            hz_for_midi(71),
        ])
        voiced = numpy.array([True, True, True, True, True, True, True, True])
        probability = numpy.array([0.96, 0.96, 0.96, 0.96, 0.94, 0.94, 0.94, 0.94])

        events = f0_to_events(f0, voiced, probability, 22050, 512, numpy)

        self.assertEqual([event["note"] for event in events], ["A4", "B4"])

    def test_onset_segmentation_preserves_repeated_same_note_attacks(self):
        import numpy

        f0 = numpy.array([hz_for_midi(69)] * 12)
        voiced = numpy.array([True] * 12)
        probability = numpy.array([0.95] * 12)
        onset_frames = numpy.array([4, 8])

        events = f0_to_onset_events(f0, voiced, probability, onset_frames, 22050, 512, numpy)

        self.assertEqual([event["note"] for event in events], ["A4", "A4", "A4"])

    def test_choose_transcription_events_prefers_richer_onset_segmentation(self):
        pitch_events = [{"note": "A4"}, {"note": "B4"}]
        onset_events = [{"note": value} for value in ("A4", "A4", "B4", "B4", "C5", "D5")]

        events, source = choose_transcription_events(pitch_events, onset_events)

        self.assertEqual(source, "onset_segmented_pyin")
        self.assertEqual(events, onset_events)

    def test_pitch_sanity_filter_adjusts_isolated_octave_flip(self):
        events = [
            note_event(69, 0),
            note_event(81, 1),
            note_event(69, 2),
        ]

        cleaned, quality = pitch_sanity_filter(events)

        self.assertEqual([event["midi"] for event in cleaned], [69, 69, 69])
        self.assertTrue(cleaned[1]["uncertain"])
        self.assertEqual(cleaned[1]["rawMidi"], 81)
        self.assertEqual(quality["sanityOctaveAdjustedCount"], 1)

    def test_pitch_sanity_filter_keeps_real_unresolved_leap(self):
        events = [
            note_event(69, 0),
            note_event(81, 1),
            note_event(84, 2),
        ]

        cleaned, quality = pitch_sanity_filter(events)

        self.assertEqual([event["midi"] for event in cleaned], [69, 81, 84])
        self.assertEqual(quality["sanityOctaveAdjustedCount"], 0)

    def test_pitch_sanity_filter_drops_short_low_confidence_glitch(self):
        events = [
            note_event(69, 0, confidence=0.92, duration=0.2),
            note_event(83, 1, confidence=0.4, duration=0.04),
            note_event(71, 2, confidence=0.9, duration=0.2),
        ]

        cleaned, quality = pitch_sanity_filter(events)

        self.assertEqual([event["midi"] for event in cleaned], [69, 71])
        self.assertEqual(quality["sanityGlitchDroppedCount"], 1)

    def test_transcription_failure_state_rejects_repeated_pitch_collapse(self):
        events = [note_event(62, index, confidence=0.91, duration=0.05) for index in range(24)]

        failure = transcription_failure_state(events, {"detectedOnsetCount": 25})

        self.assertTrue(failure["failed"])
        self.assertEqual(failure["status"], "failed_pitch_collapse")
        self.assertEqual(failure["failureMode"], "repeated_pitch_collapse")
        self.assertEqual(failure["pitchCollapseDominantNote"], "D4")
        self.assertIn("not acceptable sheet-music transcription", failure["pitchCollapseReason"])

    def test_transcription_failure_state_keeps_diverse_fast_arpeggio_trace(self):
        arpeggio = [62, 66, 69, 74, 78, 81] * 4
        events = [note_event(midi, index, confidence=0.88, duration=0.05) for index, midi in enumerate(arpeggio)]

        failure = transcription_failure_state(events, {"detectedOnsetCount": len(arpeggio)})

        self.assertFalse(failure["failed"])
        self.assertFalse(failure["pitchCollapseDetected"])

    def test_choose_transcription_events_rescues_collapsed_pyin_with_spectral_onsets(self):
        collapsed_pyin = [note_event(62, index, confidence=0.91, duration=0.05) for index in range(24)]
        spectral_arpeggio = [
            note_event(midi, index, confidence=0.72, duration=0.05)
            for index, midi in enumerate([62, 66, 69, 73, 76, 81] * 4)
        ]

        events, source = choose_transcription_events(collapsed_pyin, [], spectral_arpeggio)

        self.assertEqual(source, "spectral_onset_rescue")
        self.assertGreaterEqual(len({event["midi"] % 12 for event in events}), 4)

    def test_spectral_onset_events_tracks_fast_arpeggio_pitches(self):
        import librosa  # type: ignore
        import numpy  # type: ignore

        sr = 22050
        hop_length = 256
        pattern = [62, 66, 69, 73, 76, 81] * 2
        duration = 0.085
        chunks = []
        for midi in pattern:
            frequency = hz_for_midi(midi)
            t = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
            envelope = numpy.hanning(t.size)
            chunk = (
                numpy.sin(2 * numpy.pi * frequency * t)
                + 0.32 * numpy.sin(2 * numpy.pi * frequency * 2 * t)
                + 0.18 * numpy.sin(2 * numpy.pi * frequency * 3 * t)
            ) * envelope
            chunks.append(chunk)
        y = numpy.concatenate(chunks)
        onset_frames = [round(index * duration * sr / hop_length) for index in range(1, len(pattern))]

        events = spectral_onset_events(y, onset_frames, sr, hop_length, librosa, numpy)
        failure = transcription_failure_state(events, {"detectedOnsetCount": len(onset_frames)})

        self.assertGreaterEqual(len(events), 8)
        self.assertGreaterEqual(len({event["midi"] % 12 for event in events}), 4)
        self.assertFalse(failure["pitchCollapseDetected"])

    def test_dense_backtracked_onsets_capture_fast_high_attacks(self):
        import librosa  # type: ignore
        import numpy  # type: ignore

        sr = 22050
        pattern = [86, 88, 90, 91, 93, 95, 96, 98, 100, 96, 93, 91]
        duration = 0.045
        chunks = []
        for midi in pattern:
            frequency = hz_for_midi(midi)
            t = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
            envelope = numpy.hanning(t.size)
            chunks.append(
                (
                    0.32 * numpy.sin(2 * numpy.pi * frequency * t)
                    + 0.10 * numpy.sin(2 * numpy.pi * frequency * 2 * t)
                )
                * envelope
            )
        y = normalize_audio_signal(numpy.concatenate(chunks), librosa)

        onset_frames = onset_frames_for_signal(y, sr, PITCH_HOP_LENGTH, librosa, numpy)

        self.assertGreaterEqual(len(onset_frames), len(pattern) - 2)

    def test_transcribe_audio_array_rescues_fast_high_notes_from_lower_octave_noise(self):
        import librosa  # type: ignore
        import numpy  # type: ignore

        sr = 22050
        pattern = [86, 88, 90, 91, 93, 95, 96, 98, 100, 96, 93, 91]
        duration = 0.045
        chunks = []
        for midi in pattern:
            frequency = hz_for_midi(midi)
            lower_frequency = hz_for_midi(midi - 12)
            t = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
            envelope = numpy.hanning(t.size)
            chunks.append(
                (
                    0.32 * numpy.sin(2 * numpy.pi * frequency * t)
                    + 0.11 * numpy.sin(2 * numpy.pi * frequency * 2 * t)
                    + 0.07 * numpy.sin(2 * numpy.pi * frequency * 3 * t)
                )
                * envelope
                + 0.12 * numpy.sin(2 * numpy.pi * lower_frequency * t)
            )
        y = numpy.concatenate(chunks)

        result = transcribe_audio_array(y, sr, librosa, numpy)
        midi_values = [event["midi"] for event in result["events"]]

        self.assertEqual(result["quality"]["segmentationSource"], "spectral_fast_note_rescue")
        self.assertEqual(result["quality"]["spectralStreamSource"], "source")
        self.assertGreaterEqual(len(midi_values), 7)
        self.assertGreaterEqual(len({midi % 12 for midi in midi_values}), 5)
        self.assertTrue(all(midi >= 84 for midi in midi_values))

    def test_transcribe_audio_array_prefers_high_note_when_background_pulls_octave_down(self):
        import librosa  # type: ignore
        import numpy  # type: ignore

        sr = 22050
        duration = 0.3
        t = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
        envelope = numpy.hanning(t.size)
        y = (
            0.22 * numpy.sin(2 * numpy.pi * hz_for_midi(81) * t)
            + 0.08 * numpy.sin(2 * numpy.pi * hz_for_midi(93) * t)
            + 0.20 * numpy.sin(2 * numpy.pi * hz_for_midi(69) * t)
        ) * envelope

        result = transcribe_audio_array(y, sr, librosa, numpy)

        self.assertEqual(result["quality"]["segmentationSource"], "spectral_octave_rescue")
        self.assertTrue(result["events"])
        self.assertTrue(all(event["midi"] == 81 for event in result["events"]))
        self.assertTrue(any(event.get("rawMidi") == 69 for event in result["events"]))

    def test_octave_rescue_does_not_promote_normal_second_harmonic(self):
        import librosa  # type: ignore
        import numpy  # type: ignore

        sr = 22050
        duration = 0.3
        t = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
        envelope = numpy.hanning(t.size)
        y = (
            0.25 * numpy.sin(2 * numpy.pi * hz_for_midi(69) * t)
            + 0.18 * numpy.sin(2 * numpy.pi * hz_for_midi(81) * t)
            + 0.06 * numpy.sin(2 * numpy.pi * hz_for_midi(93) * t)
        ) * envelope

        result = transcribe_audio_array(y, sr, librosa, numpy)

        self.assertTrue(result["events"])
        self.assertTrue(all(event["midi"] == 69 for event in result["events"]))

    def test_yin_transition_events_recovers_fast_note_changes_as_hidden_candidates(self):
        import librosa  # type: ignore
        import numpy  # type: ignore

        sr = 22050
        hop_length = 256
        pattern = [74, 72, 70, 74, 72, 70, 74]
        duration = 0.08
        chunks = []
        for midi in pattern:
            frequency = hz_for_midi(midi)
            t = numpy.linspace(0, duration, int(sr * duration), endpoint=False)
            envelope = numpy.hanning(t.size)
            chunks.append(0.3 * numpy.sin(2 * numpy.pi * frequency * t) * envelope)
        y = numpy.concatenate(chunks)

        events = yin_transition_events(y, sr, hop_length, librosa, numpy)

        self.assertGreaterEqual(len(events), len(pattern) - 1)
        self.assertEqual([event["midi"] for event in events[:5]], pattern[:5])
        self.assertTrue(all(event["candidateOnly"] for event in events[:5]))

    def test_audio_agreement_marks_matching_independent_detector_events(self):
        selected = [
            note_event(76, 0, confidence=0.9, duration=0.12),
            note_event(78, 1, confidence=0.9, duration=0.12),
        ]
        spectral = [
            {**note_event(76, 0, confidence=0.82, duration=0.1), "startSeconds": 0.01, "endSeconds": 0.11},
            {**note_event(78, 1, confidence=0.82, duration=0.1), "startSeconds": 0.21, "endSeconds": 0.31},
        ]

        marked = mark_audio_agreement(
            selected,
            "onset_segmented_pyin",
            [("onset_segmented_pyin", selected), ("spectral_onset", spectral)],
        )

        self.assertTrue(all(event["audioAgreement"] for event in marked))
        self.assertEqual(marked[0]["agreementSources"], ["spectral_onset"])
        self.assertEqual(marked[0]["detectorSource"], "onset_segmented_pyin")

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
            "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
            "noteCount": 12,
            "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
        }
        incoming = {
            "transcriptionId": "5-3",
            "status": "transcribed",
            "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
            "noteCount": 12,
            "fingerprint": fingerprint_for([76, 78, 79, 81, 79, 78, 76, 74, 76, 78, 79, 81]),
        }

        matches = reference_matches_for(incoming, {"transcriptions": {"items": [learned]}})

        self.assertEqual(matches[0]["title"], "Wieniawski Scherzo-Tarantelle, Op. 16")
        self.assertEqual(matches[0]["basis"], "pitch_rhythm_fingerprint")

    def test_transcribe_media_samples_reprocesses_stale_pipeline_output(self):
        sample = {
            "id": "sample-1",
            "path": "C:\\media\\sample.mp4",
            "window": "*0-10",
            "title": "5-3-26",
            "containsViolin": True,
        }
        sample_key = transcription_module.transcription_key(sample)
        state = {
            "mediaSamples": [sample],
            "transcriptions": {
                "items": [
                    {
                        "transcriptionId": sample_key,
                        "pipelineVersion": "old",
                        "status": "transcribed",
                        "noteCount": 300,
                    }
                ]
            },
        }
        saved = []

        with (
            patch.object(transcription_module, "load_state", return_value=state),
            patch.object(transcription_module, "save_state", side_effect=lambda value: saved.append(value)),
            patch.object(
                transcription_module,
                "build_transcription",
                return_value={
                    "transcriptionId": sample_key,
                    "pipelineVersion": TRANSCRIPTION_PIPELINE_VERSION,
                    "status": "transcribed",
                    "noteCount": 12,
                },
            ),
        ):
            run = transcription_module.transcribe_media_samples(limit=1)

        self.assertEqual(run["reprocessedCount"], 1)
        self.assertEqual(saved[0]["transcriptions"]["items"][0]["pipelineVersion"], TRANSCRIPTION_PIPELINE_VERSION)
        self.assertEqual(saved[0]["transcriptions"]["items"][0]["noteCount"], 12)
        self.assertEqual(len(saved[0]["transcriptions"]["items"]), 1)

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
        self.assertEqual(snippet["scoreMatchStatus"], "pending_exact_alignment")
        self.assertEqual(snippet["score"]["matchStatus"], "pending_exact_alignment")
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
        self.assertEqual(snippet["score"]["boxes"], [])
        self.assertEqual(snippet["scoreMatchStatus"], "pending_exact_alignment")
        self.assertEqual(snippet["score"]["matchStatus"], "pending_exact_alignment")
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
