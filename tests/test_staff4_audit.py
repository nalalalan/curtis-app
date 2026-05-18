import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import backend.app.staff4_audit as staff4_audit
from backend.app.staff4_audit import (
    attach_staff4_audit_decision,
    ensure_staff4_phrase_audit_packet,
    latest_staff4_phrase_audit_packet,
    latest_staff4_phrase_audit_packet_for_completion,
    media_sample_for_id,
    packet_id_for_current,
    source_media_path,
)


def current_best():
    return {
        "status": "blocked_audio_mismatch",
        "practiceDay": "2026-05-03",
        "pieceTitle": "Wieniawski Scherzo-Tarantelle, Op. 16",
        "targetReferenceStart": 9,
        "targetReferenceEnd": 16,
        "targetSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5",
        "targetMidiSequence": [75, 75, 72, 75, 75, 75, 72],
        "bestAudioSequence": "D#5 D#5 C5 D#5 D#5 D5 D#5",
        "bestAudioMidiSequence": [75, 75, 72, 75, 75, 74, 75],
        "expectedNextScoreNote": "Eb5",
        "expectedNextScoreMidi": 75,
        "observedNextAudioNote": "D5",
        "observedNextAudioMidi": 74,
        "sampleId": "sample-staff4",
        "sourceWindow": "*8835-8925",
        "audioRunSource": "ranked_match_group",
        "audioLocalStartSeconds": 0.5,
        "audioLocalEndSeconds": 1.34,
        "sourceImageUrl": "/assets/score/staff4.png",
        "limit": "Adjacent audio notes do not match the verified source MIDI sequence.",
        "bestAudioNotes": [
            {"note": "D#5", "midi": 75, "startSeconds": 0.50, "endSeconds": 0.62, "audioAgreement": True},
            {"note": "D#5", "midi": 75, "startSeconds": 0.62, "endSeconds": 0.74, "audioAgreement": True},
            {"note": "C5", "midi": 72, "startSeconds": 0.74, "endSeconds": 0.86, "audioAgreement": True},
            {"note": "D#5", "midi": 75, "startSeconds": 0.86, "endSeconds": 0.98, "audioAgreement": True},
            {"note": "D#5", "midi": 75, "startSeconds": 0.98, "endSeconds": 1.10, "audioAgreement": True},
            {"note": "D5", "midi": 74, "startSeconds": 1.10, "endSeconds": 1.22, "audioAgreement": True},
            {"note": "D#5", "midi": 75, "startSeconds": 1.22, "endSeconds": 1.34, "audioAgreement": True},
        ],
    }


def current_best_right1():
    value = dict(current_best())
    value.update(
        {
            "targetReferenceEnd": 15,
            "targetSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5",
            "targetMidiSequence": [75, 75, 72, 75, 75, 75],
            "bestAudioSequence": "D#5 D#5 C5 D#5 D#5 D5",
            "bestAudioMidiSequence": [75, 75, 72, 75, 75, 74],
            "bestAudioNotes": value["bestAudioNotes"][:6],
        }
    )
    return value


def current_best_right1_exact():
    value = current_best_right1()
    value.update(
        {
            "status": "blocked_source_crop_required",
            "bestAudioSequence": "D#5 D#5 C5 D#5 D#5 D#5",
            "bestAudioMidiSequence": [75, 75, 72, 75, 75, 75],
            "expectedNextScoreNote": "",
            "expectedNextScoreMidi": None,
            "observedNextAudioNote": "",
            "observedNextAudioMidi": None,
            "limit": "Exact audio MIDI exists, but the source crop has not been verified.",
            "bestAudioNotes": [
                {"note": "D#5", "midi": 75, "startSeconds": 0.50, "endSeconds": 0.62, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 0.62, "endSeconds": 0.74, "audioAgreement": True},
                {"note": "C5", "midi": 72, "startSeconds": 0.74, "endSeconds": 0.86, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 0.86, "endSeconds": 0.98, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 0.98, "endSeconds": 1.10, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 1.10, "endSeconds": 1.22, "audioAgreement": True},
            ],
        }
    )
    return value


def current_best_seven_exact_pending_source():
    value = dict(current_best())
    value.update(
        {
            "status": "ready_for_truth_review",
            "bestAudioSequence": "D#5 D#5 C5 D#5 D#5 D#5 C5",
            "bestAudioMidiSequence": [75, 75, 72, 75, 75, 75, 72],
            "expectedNextScoreNote": "",
            "expectedNextScoreMidi": None,
            "observedNextAudioNote": "",
            "observedNextAudioMidi": None,
            "audioAgreed": True,
            "audioRunSource": "staff4_adjacent_guided_current_detector",
            "audioLocalStartSeconds": 20.225,
            "audioLocalEndSeconds": 23.280,
            "audioAbsoluteStartSeconds": 8855.225,
            "audioAbsoluteEndSeconds": 8858.280,
            "sourceCropReady": True,
            "truthEvidenceAccepted": False,
            "limit": "Audio and source MIDI agree; the source crop still needs accepted truth evidence before display.",
            "bestAudioNotes": [
                {"note": "D#5", "midi": 75, "startSeconds": 20.225, "endSeconds": 20.422, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 20.550, "endSeconds": 20.689, "audioAgreement": True},
                {"note": "C5", "midi": 72, "startSeconds": 20.817, "endSeconds": 20.898, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 21.629, "endSeconds": 21.792, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 22.361, "endSeconds": 22.535, "audioAgreement": True},
                {"note": "D#5", "midi": 75, "startSeconds": 22.829, "endSeconds": 22.992, "audioAgreement": True},
                {"note": "C5", "midi": 72, "startSeconds": 23.117, "endSeconds": 23.280, "audioAgreement": True},
            ],
        }
    )
    return value


def staff4_first_failure(**overrides):
    failure = {
        "direction": "right-1",
        "targetReferenceStart": 9,
        "targetReferenceEnd": 15,
        "targetSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5",
        "targetMidiSequence": [75, 75, 72, 75, 75, 75],
        "targetNoteCount": 6,
        "reproducedNoteCount": 0,
        "failedNoteIndex": 0,
        "expectedMidi": 75,
        "expectedNote": "D#5",
        "reason": "current_detectors_did_not_reproduce_exact_midi",
        "failureKind": "outside_scan",
        "attemptCount": 1,
        "bestAttemptStartSeconds": 0.50,
        "bestAttemptEndSeconds": 0.62,
        "bestAttemptObservedMidi": [],
        "bestAttemptObservedNotes": [],
        "bestAttemptObservedConsensusMidi": 0,
        "bestAttemptObservedConsensusNote": "",
        "bestAttemptDetectorVotes": [],
    }
    failure.update(overrides)
    return failure


def completion_state():
    return {
        "phraseExpansionHarness": {
            "currentBest": current_best(),
        }
    }


def completion_state_without_stored_audio_run():
    current = dict(current_best())
    current.update(
        {
            "bestAudioSequence": "",
            "bestAudioMidiSequence": [],
            "bestAudioNotes": [],
            "bestExactCount": 0,
            "bestPrefixCount": 0,
            "anchorSequence": "Eb5 Eb5 C5 Eb5 Eb5",
            "audioLocalStartSeconds": None,
            "audioLocalEndSeconds": None,
        }
    )
    return {
        "phraseExpansionHarness": {
            "currentBest": current,
        }
    }


def first_failure_completion_state(failure=None):
    return {
        "phraseExpansionHarness": {
            "currentBest": current_best_right1(),
        },
        "staff4SourceAudioRescanAdjacentFirstFailure": failure or staff4_first_failure(),
    }


class Staff4AuditTests(unittest.TestCase):
    def test_owner_media_sample_fallback_resolves_existing_browser_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            owner_dir = Path(temp_dir) / "owner-media"
            owner_dir.mkdir()
            sample_path = owner_dir / "Njh8_zq9_DM-8835-browser.webm"
            sample_path.write_bytes(b"owner-media")
            state = {"mediaSamples": []}
            with patch("backend.app.staff4_audit.OWNER_MEDIA_DIR", owner_dir):
                sample = media_sample_for_id(state, "Njh8_zq9_DM-8835")
                resolved = source_media_path(sample)

        self.assertEqual(sample["id"], "Njh8_zq9_DM-8835")
        self.assertEqual(sample["source"], "owner_media_fallback")
        self.assertEqual(resolved, sample_path.resolve())

    def test_audit_packet_uses_failure_sample_when_current_source_only_target_has_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            owner_dir = Path(temp_dir) / "owner-media"
            owner_dir.mkdir()
            sample_path = owner_dir / "Njh8_zq9_DM-8835-browser.webm"
            sample_path.write_bytes(b"owner-media")
            completion = first_failure_completion_state(
                staff4_first_failure(
                    targetReferenceEnd=17,
                    targetSequence="Eb5 Eb5 C5 Eb5 Eb5 Eb5 C5 A4",
                    targetMidiSequence=[75, 75, 72, 75, 75, 75, 72, 69],
                    targetNoteCount=8,
                    reproducedNoteCount=7,
                    failedNoteIndex=7,
                    expectedMidi=69,
                    expectedNote="A4",
                    failureKind="wrong_midi_detected",
                    sampleId="Njh8_zq9_DM-8835",
                    sourceWindow="*8835-8925",
                    bestAttemptStartSeconds=23.514,
                    bestAttemptEndSeconds=23.677,
                    bestAttemptObservedMidi=[74, 74, 74],
                    bestAttemptObservedNotes=["D5", "D5", "D5"],
                    bestAttemptObservedConsensusMidi=74,
                    bestAttemptObservedConsensusNote="D5",
                )
            )
            completion["phraseExpansionHarness"]["currentBest"]["sampleId"] = ""
            state = {"mediaSamples": []}
            with patch("backend.app.staff4_audit.AUDIT_DIR", Path(temp_dir) / "staff4-audit"), patch(
                "backend.app.staff4_audit.OWNER_MEDIA_DIR", owner_dir
            ), patch(
                "backend.app.staff4_audit.run_ffmpeg_extract_audio", return_value=(True, "")
            ), patch("backend.app.staff4_audit.run_ffmpeg_extract_video", return_value=(True, "")), patch(
                "backend.app.staff4_audit.analyze_audio_clip",
                return_value={"status": "blocked_audio_mismatch_confirmed"},
            ), patch(
                "backend.app.staff4_audit.write_pitch_trace_svg"
            ), patch(
                "backend.app.staff4_audit.write_spectrogram_svg", return_value=True
            ):
                packet = ensure_staff4_phrase_audit_packet(state, completion, force=True)

        self.assertEqual(packet["sampleId"], "Njh8_zq9_DM-8835")
        self.assertEqual(packet["sourceWindow"], "*8835-8925")
        self.assertEqual(packet["clip"]["mediaUrl"], "/api/curtis/media/sample/Njh8_zq9_DM-8835")
        self.assertEqual(packet["expectedFailedScoreNote"], "A4")
        self.assertEqual(packet["observedFailureAudioNote"], "D5")
        self.assertEqual(packet["status"], "blocked_audio_mismatch_confirmed")
        self.assertEqual(packet["decision"]["status"], "rejected_mismatch")

    def test_missing_runtime_media_still_generates_blocked_packet(self):
        state = {
            "mediaSamples": [
                {
                    "id": "sample-staff4",
                    "path": str(Path(tempfile.gettempdir()) / "curtis-missing-staff4-media.mp4"),
                }
            ]
        }

        packet = ensure_staff4_phrase_audit_packet(state, completion_state(), force=True)

        self.assertEqual(packet["status"], "blocked_media_missing")
        self.assertEqual(packet["truthDecision"], "rejected_mismatch")
        self.assertEqual(packet["expectedNextScoreNote"], "Eb5")
        self.assertEqual(packet["observedNextAudioNote"], "D5")
        self.assertEqual(packet["decision"]["status"], "rejected_mismatch")
        self.assertFalse(packet["canExtendStaff4Lane"])
        self.assertEqual(packet["clip"]["localStartSeconds"], 0.75)
        self.assertEqual(packet["clip"]["noteLocalStartSeconds"], 1.1)
        self.assertEqual(packet["storedAudioNotes"][5]["note"], "D5")
        self.assertIn("packet.json", packet["artifacts"]["packetJsonUrl"])
        self.assertEqual(latest_staff4_phrase_audit_packet(state)["packetId"], packet["packetId"])

    def test_current_mismatch_without_stored_audio_run_still_gets_decision(self):
        state = {
            "mediaSamples": [
                {
                    "id": "sample-staff4",
                    "path": str(Path(tempfile.gettempdir()) / "curtis-missing-staff4-media.mp4"),
                }
            ]
        }

        packet = ensure_staff4_phrase_audit_packet(state, completion_state_without_stored_audio_run(), force=True)

        self.assertEqual(packet["status"], "blocked_media_missing")
        self.assertEqual(packet["auditFocus"], "staff4_first_failed_adjacent_note")
        self.assertEqual(packet["expectedFailedScoreNote"], "Eb5")
        self.assertEqual(packet["observedFailureAudioNote"], "D5")
        self.assertEqual(packet["decision"]["failedNoteIndex"], 5)
        self.assertEqual(packet["decision"]["status"], "rejected_mismatch")
        self.assertEqual(packet["truthDecision"], "rejected_mismatch")
        self.assertFalse(packet["canExtendStaff4Lane"])

    def test_first_failure_packet_uses_source_spelling_and_blocks_extension(self):
        state = {
            "mediaSamples": [
                {
                    "id": "sample-staff4",
                    "path": str(Path(tempfile.gettempdir()) / "curtis-missing-staff4-media.mp4"),
                }
            ]
        }

        packet = ensure_staff4_phrase_audit_packet(state, first_failure_completion_state(), force=True)

        self.assertEqual(packet["status"], "blocked_media_missing")
        self.assertEqual(packet["auditFocus"], "staff4_first_failed_adjacent_note")
        self.assertEqual(packet["expectedFailedScoreNote"], "Eb5")
        self.assertEqual(packet["expectedFailedScoreMidi"], 75)
        self.assertEqual(packet["decision"]["expectedNote"], "Eb5")
        self.assertEqual(packet["decision"]["outcome"], "rescan_window_required")
        self.assertEqual(packet["truthDecision"], "pending_review")
        self.assertFalse(packet["canExtendStaff4Lane"])
        self.assertEqual(packet["goldReviewCandidate"]["expectedNote"], "Eb5")

    def test_first_failure_wrong_midi_locks_rejected_regression_case(self):
        failure = staff4_first_failure(
            failedNoteIndex=5,
            failureKind="wrong_midi_detected",
            bestAttemptObservedMidi=[74, 74],
            bestAttemptObservedNotes=["D5", "D5"],
            bestAttemptObservedConsensusMidi=74,
            bestAttemptObservedConsensusNote="D5",
        )
        state = {
            "mediaSamples": [
                {
                    "id": "sample-staff4",
                    "path": str(Path(tempfile.gettempdir()) / "curtis-missing-staff4-media.mp4"),
                }
            ]
        }

        packet = ensure_staff4_phrase_audit_packet(state, first_failure_completion_state(failure), force=True)

        self.assertEqual(packet["decision"]["status"], "rejected_mismatch")
        self.assertEqual(packet["truthDecision"], "rejected_mismatch")
        self.assertEqual(packet["decision"]["expectedNote"], "Eb5")
        self.assertEqual(packet["decision"]["observedNote"], "D5")
        self.assertFalse(packet["canExtendStaff4Lane"])
        self.assertIn("regressionCase", packet)
        self.assertIn("Eb5-vs-D5", packet["regressionCase"]["regressionId"])

    def test_exact_current_phrase_ignores_stale_first_failure_and_audits_full_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "sample.mp4"
            source_path.write_bytes(b"not-a-real-video")
            state = {
                "mediaSamples": [
                    {
                        "id": "sample-staff4",
                        "path": str(source_path),
                    }
                ]
            }
            completion = {
                "phraseExpansionHarness": {
                    "currentBest": current_best_seven_exact_pending_source(),
                },
                "staff4SourceAudioRescanAdjacentFirstFailure": staff4_first_failure(
                    targetReferenceEnd=16,
                    targetMidiSequence=[75, 75, 72, 75, 75, 75, 72],
                    targetNoteCount=7,
                    bestAttemptStartSeconds=20.225,
                    bestAttemptEndSeconds=20.422,
                ),
            }

            with patch("backend.app.staff4_audit.run_ffmpeg_extract_audio", return_value=(True, "")), patch(
                "backend.app.staff4_audit.run_ffmpeg_extract_video",
                return_value=(True, ""),
            ), patch("backend.app.staff4_audit.analyze_audio_clip", return_value={"status": "needs_manual_audio_review"}), patch(
                "backend.app.staff4_audit.write_pitch_trace_svg"
            ), patch(
                "backend.app.staff4_audit.write_spectrogram_svg", return_value=True
            ):
                packet = ensure_staff4_phrase_audit_packet(state, completion, force=True)

        self.assertEqual(packet["auditFocus"], "staff4_full_exact_phrase")
        self.assertEqual(packet["firstFailure"], {})
        self.assertEqual(packet["status"], "pending_source_lock")
        self.assertEqual(packet["truthDecision"], "pending_review")
        self.assertTrue(packet["fullPhraseCheck"]["exactAudio"])
        self.assertEqual(packet["fullPhraseCheck"]["targetNoteCount"], 7)
        self.assertEqual(packet["clip"]["noteLocalStartSeconds"], 20.225)
        self.assertEqual(packet["clip"]["noteLocalEndSeconds"], 23.28)
        self.assertEqual(packet["goldReviewCandidate"]["kind"], "staff4_full_phrase_audio_score_audit")

    def test_first_failure_exact_audio_and_source_truth_accepts_right1_lane(self):
        packet = {
            "practiceDay": "2026-05-03",
            "sampleId": "Njh8_zq9_DM-8835",
            "targetReferenceStart": 9,
            "targetReferenceEnd": 15,
            "targetSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5",
            "targetMidiSequence": [75, 75, 72, 75, 75, 75],
            "bestAudioMidiSequence": [75, 75, 72, 75, 75, 75],
            "score": {
                "sourceCropReady": True,
                "truthEvidenceAccepted": True,
            },
            "status": "generated",
        }
        failure = staff4_first_failure(
            bestAttemptObservedMidi=[],
            bestAttemptObservedNotes=[],
            bestAttemptObservedConsensusMidi=0,
            bestAttemptObservedConsensusNote="",
        )
        analysis = {
            "mismatchWindow": {
                "detectorVotes": {
                    "expected": 3,
                    "observed": 0,
                    "missing": 0,
                    "other": 0,
                }
            }
        }

        attach_staff4_audit_decision(packet, analysis, failure)

        self.assertEqual(packet["status"], "accepted_truth_candidate")
        self.assertEqual(packet["truthDecision"], "accepted")
        self.assertTrue(packet["canExtendStaff4Lane"])
        self.assertEqual(packet["decision"]["outcome"], "accept_audio_agreed_source_note")
        self.assertEqual(packet["expectedFailedScoreNote"], "Eb5")

    def test_no_current_expansion_is_not_generated(self):
        state = {}

        packet = ensure_staff4_phrase_audit_packet(state, {"phraseExpansionHarness": {}}, force=True)

        self.assertEqual(packet["status"], "blocked_no_staff4_expansion")
        self.assertEqual(latest_staff4_phrase_audit_packet(state)["status"], "blocked_no_staff4_expansion")

    def test_source_extent_exhausted_reports_musicxml_next_step(self):
        state = {}

        packet = ensure_staff4_phrase_audit_packet(
            state,
            {"phraseExpansionHarness": {"status": "source_extent_exhausted", "acceptedAnchorNoteCount": 7}},
            force=True,
        )

        self.assertEqual(packet["status"], "blocked_source_extent_exhausted")
        self.assertEqual(packet["acceptedAnchorNoteCount"], 7)
        self.assertIn("verify more MusicXML/source notes", packet["limit"])

    def test_completion_latest_does_not_return_stale_adjacent_window_packet(self):
        old_audit_dir = staff4_audit.AUDIT_DIR
        temp_dir = Path(tempfile.mkdtemp())
        try:
            staff4_audit.AUDIT_DIR = temp_dir
            right1 = current_best_right1()
            right1_packet_id = packet_id_for_current(right1)
            packet_path = staff4_audit.packet_json_path(right1_packet_id)
            packet_path.parent.mkdir(parents=True, exist_ok=True)
            packet_path.write_text(
                json.dumps(
                    {
                        "version": "staff4_phrase_audit_v1",
                        "packetId": right1_packet_id,
                        "status": "blocked_audio_mismatch_confirmed",
                        "truthDecision": "not_accepted",
                        "targetReferenceStart": 9,
                        "targetReferenceEnd": 15,
                        "targetSequence": "Eb5 Eb5 C5 Eb5 Eb5 Eb5",
                        "bestAudioSequence": "D#5 D#5 C5 D#5 D#5 D5",
                    }
                ),
                encoding="utf-8",
            )
            state = {
                "staff4PhraseAuditLatest": {
                    "version": "staff4_phrase_audit_v1",
                    "packetId": "staff4-2026-05-03-Njh8_zq9_DM-8835-9-16",
                    "status": "blocked_audio_mismatch_confirmed",
                    "targetReferenceEnd": 16,
                }
            }

            packet = latest_staff4_phrase_audit_packet_for_completion(
                state,
                {"phraseExpansionHarness": {"currentBest": right1}},
            )

            self.assertEqual(packet["status"], "not_generated")
            self.assertEqual(packet["currentPacketId"], right1_packet_id)
            self.assertEqual(packet["stalePacketId"], right1_packet_id)
        finally:
            staff4_audit.AUDIT_DIR = old_audit_dir


if __name__ == "__main__":
    unittest.main()
