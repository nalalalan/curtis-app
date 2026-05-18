import tempfile
import unittest
import json
from pathlib import Path

import backend.app.staff4_audit as staff4_audit
from backend.app.staff4_audit import (
    ensure_staff4_phrase_audit_packet,
    latest_staff4_phrase_audit_packet,
    latest_staff4_phrase_audit_packet_for_completion,
    packet_id_for_current,
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
            "currentBest": current_best_right1_exact(),
        },
        "staff4SourceAudioRescanAdjacentFirstFailure": failure or staff4_first_failure(),
    }


class Staff4AuditTests(unittest.TestCase):
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

    def test_no_current_expansion_is_not_generated(self):
        state = {}

        packet = ensure_staff4_phrase_audit_packet(state, {"phraseExpansionHarness": {}}, force=True)

        self.assertEqual(packet["status"], "blocked_no_staff4_expansion")
        self.assertEqual(latest_staff4_phrase_audit_packet(state)["status"], "blocked_no_staff4_expansion")

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

            self.assertEqual(packet["packetId"], right1_packet_id)
            self.assertEqual(packet["targetReferenceEnd"], 15)
            self.assertEqual(state["staff4PhraseAuditLatest"]["packetId"], right1_packet_id)
        finally:
            staff4_audit.AUDIT_DIR = old_audit_dir


if __name__ == "__main__":
    unittest.main()
