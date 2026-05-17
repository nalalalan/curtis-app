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


def completion_state():
    return {
        "phraseExpansionHarness": {
            "currentBest": current_best(),
        }
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
        self.assertEqual(packet["truthDecision"], "not_accepted")
        self.assertEqual(packet["expectedNextScoreNote"], "Eb5")
        self.assertEqual(packet["observedNextAudioNote"], "D5")
        self.assertEqual(packet["clip"]["localStartSeconds"], 0.15)
        self.assertEqual(packet["clip"]["noteLocalStartSeconds"], 0.5)
        self.assertEqual(packet["storedAudioNotes"][5]["note"], "D5")
        self.assertIn("packet.json", packet["artifacts"]["packetJsonUrl"])
        self.assertEqual(latest_staff4_phrase_audit_packet(state)["packetId"], packet["packetId"])

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
