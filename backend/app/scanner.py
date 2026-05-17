from __future__ import annotations

import os
import re
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .analyzer import parse_window_start
from .auth import youtube_auth_status
from .corrections import (
    accepted_source_corrections,
    compact_text,
    item_stale_after_source_correction,
    source_requires_confirmed_acceptance,
    source_key_from_item,
    title_rejected_for_item,
    wieniawski_reference_target,
    youtube_video_id,
)
from .platforms import (
    credential_state,
    fetch_instagram_inventory,
    fetch_youtube_inventory,
    fetch_youtube_public_references,
)
from .reference_corpus import (
    PUBLIC_REFERENCE_SEEDS,
    calibration_anchor_for_item,
    public_reference_training_state,
)
from .settings import (
    OPENAI_AUDIO_MODEL,
    OPENAI_MODEL,
    OPENAI_PIECE_VERIFY_MODEL,
    OPENAI_REASONING_EFFORT,
    OPENAI_VISION_MODEL,
    PUBLIC_REFERENCE_REFRESH_SECONDS,
    RUNTIME_DIR,
    REQUIRE_SOURCE_CONFIRMED_PIECE_TITLES,
    SERVICE_NAME,
)
from .staff4_audit import (
    latest_staff4_phrase_audit_packet_for_completion,
    run_ffmpeg_extract_audio,
    source_media_path,
)
from .state import append_run, load_state, save_state, utc_now
from .daily_records import (
    build_daily_records,
    build_repertoire_evidence,
    exact_score_location_ready,
    note_midi_value,
    notes_have_score_match_audio_agreement,
)
from .evidence_ledger import build_active_practice_coverage, build_evidence_progress, build_truth_progress
from .gold_truth import load_long_phrase_truth, verify_long_phrase_truth_manifest
from .gold_review import build_gold_review_loop
from .long_phrase_truth import exact_midi_phrase_gate
from .study_packets import build_practice_study, build_practice_totals
from .transcription import (
    TRANSCRIPTION_PIPELINE_VERSION,
    midi_from_hz,
    note_name,
    spectral_pitch_for_segment,
    transcribe_audio_array,
)
from .symbolic_scores import (
    longest_common_contiguous_run,
    normalize_pitch_class,
    score_map_candidate_audit,
    symbolic_score_from_target,
)

DEFAULT_YOUTUBE_SOURCE = "https://www.youtube.com/@nalalan"
STAFF4_SOURCE_AUDIO_RESCAN_VERSION = "staff4_source_audio_rescan_v6"
STAFF4_SOURCE_AUDIO_RESCAN_DIR = RUNTIME_DIR / "staff4-source-rescan"
STAFF4_SOURCE_AUDIO_RESCAN_PAD_BEFORE_SECONDS = 4.0
STAFF4_SOURCE_AUDIO_RESCAN_PAD_AFTER_SECONDS = 10.0
STAFF4_SOURCE_AUDIO_RESCAN_MAX_SECONDS = 18.0
STAFF4_SOURCE_AUDIO_RESCAN_STEP_SECONDS = 14.0
STAFF4_SOURCE_AUDIO_RESCAN_MAX_WINDOWS = 5
STAFF4_ACCEPTED_ANCHOR_MIDI = [75, 75, 72, 75, 75]
STAFF4_ANCHOR_GUIDED_PAD_SECONDS = 0.03
STAFF4_ANCHOR_GUIDED_MIN_EXACT_VOTES = 2
STAFF4_ADJACENT_GUIDED_MAX_TARGET_NOTES = 7
STAFF4_ADJACENT_GUIDED_SWEEP_OFFSETS_SECONDS = (0.0, -0.06, 0.06, -0.12, 0.12, -0.18, 0.18, -0.24, 0.24)
MEDIA_REVIEW_PENDING_BLOCKERS = {"youtube_data_api_returns_metadata_not_video_media"}
WEAK_EVIDENCE_TERMS = (
    "background noise",
    "no clear",
    "not audible",
    "no discernible",
    "not heard",
    "obscured",
    "masked",
    "dominates",
)
REPERTOIRE_NAME_TERMS = (
    "bach",
    "beethoven",
    "brahms",
    "bruch",
    "dont",
    "fiorillo",
    "haydn",
    "kreisler",
    "kreutzer",
    "lalo",
    "mendelssohn",
    "mozart",
    "paganini",
    "prokofiev",
    "rode",
    "saint-saens",
    "saint-saëns",
    "sarasate",
    "sibelius",
    "tchaikovsky",
    "vieuxtemps",
    "wieniawski",
    "ysaye",
    "ysaÿe",
)
REJECTED_REPERTOIRE_TITLES: tuple[str, ...] = ()
FIVE_ONE_REJECTED_REPERTOIRE_TITLES = (
    "paganini",
    "wieniawski",
    "saint saens",
    "saint saens introduction and rondo capriccioso",
    "ravel",
    "tzigane",
    "bazzini",
    "la ronde des lutins",
    "ernst",
    "last rose of summer",
    "erlkonig",
    "sarasate",
    "sarasate introduction and tarantella",
    "sarasate caprice basque",
    "carmen fantasy",
    "sarasate zigeunerweisen",
    "zigeunerweisen",
    "bach",
    "bach partita",
    "bach partita no 2",
    "bach partita no 2 in d minor bwv 1004",
    "bach partita no 3",
    "bach partita no 3 in e major bwv 1006",
    "bach preludio",
    "kreisler praeludium and allegro",
    "praeludium and allegro",
    "sarasate zapateado",
    "zapateado",
    "ysaye sonata no 3 ballade",
    "ysa e sonata no 3 ballade",
    "ysaye solo violin sonata no 3",
    "ysa e solo violin sonata no 3",
    "mozart",
    "mozart k 216",
    "mozart violin concerto no 3",
    "mozart violin concerto no 3 in g major k 216",
    "glinka ruslan and lyudmila overture",
    "ruslan and lyudmila overture",
    "till eulenspiegel",
    "strauss don juan",
    "bartered bride overture",
    "prokofiev classical symphony",
    "dvorak carnival overture",
    "shostakovich symphony no 5",
    "ravel bolero",
    "bolero",
    "beethoven symphony no 9 scherzo",
    "beethoven symphony no 7 fourth movement",
    "beethoven leonore overture no 3",
    "schumann symphony no 2 scherzo",
    "schubert symphony no 9 fourth movement",
    "rossini william tell overture",
    "rossini semiramide overture",
    "rossini la gazza ladra overture",
    "weber der freischutz overture",
    "weber oberon overture",
    "berlioz roman carnival overture",
    "berlioz symphonie fantastique fifth movement",
    "wagner tannhauser overture",
    "wagner die meistersinger von nurnberg overture",
    "wagner rienzi overture",
    "verdi la forza del destino overture",
    "verdi nabucco overture",
    "smetana the moldau",
    "rimsky korsakov scheherazade",
    "rimsky korsakov capriccio espagnol",
    "borodin polovtsian dances",
    "bizet l arlesienne suite no 2 farandole",
    "mahler symphony no 1 fourth movement",
    "mahler symphony no 5 scherzo",
    "mahler symphony no 9 first movement",
    "prokofiev romeo and juliet",
    "prokofiev lieutenant kije suite",
    "dvorak symphony no 9 scherzo",
    "dvorak slavonic dances",
    "shostakovich symphony no 10 scherzo",
    "shostakovich festive overture",
    "nielsen maskarade overture",
    "elgar cockaigne overture",
    "stravinsky firebird suite",
    "stravinsky petrushka",
    "stravinsky the rite of spring",
    "bartok concerto for orchestra",
    "kodaly dances of galanta",
    "khachaturian sabre dance",
    "holst the planets mercury",
    "rossini the barber of seville overture",
    "rossini l italiana in algeri overture",
    "rossini la scala di seta overture",
    "beethoven symphony no 5 scherzo or finale",
    "beethoven symphony no 3 scherzo",
    "beethoven egmont overture",
    "weber euryanthe overture",
    "auber fra diavolo overture",
    "suppe poet and peasant overture",
    "suppe light cavalry overture",
    "offenbach orpheus in the underworld overture",
    "johann strauss ii die fledermaus overture",
    "johann strauss ii tritsch tratsch polka",
    "johann strauss ii perpetuum mobile",
    "johann strauss ii thunder and lightning polka",
    "josef strauss feuerfest polka",
    "glinka kamarinskaya",
    "rimsky korsakov russian easter overture",
    "rimsky korsakov the tsar s bride overture",
    "borodin symphony no 2",
    "mussorgsky night on bald mountain",
    "grieg holberg suite praeludium",
    "grieg peer gynt in the hall of the mountain king",
    "copland rodeo hoe down",
    "copland el salon mexico",
    "bernstein candide overture",
    "bernstein west side story mambo",
    "bernstein west side story america",
    "arturo marquez danzon no 2",
    "moncayo huapango",
    "ginastera estancia malambo",
    "revueltas sensemaya",
    "gershwin cuban overture",
    "gershwin an american in paris",
    "john adams short ride in a fast machine",
    "john williams star wars main title",
    "john williams raiders march",
)
LONG_SESSION_PRACTICE_FLOOR_SECONDS = int(os.getenv("CURTIS_LONG_SESSION_PRACTICE_FLOOR_SECONDS", str(2 * 60 * 60)))
LONG_SESSION_LATE_SAMPLE_COUNT = int(os.getenv("CURTIS_LONG_SESSION_LATE_SAMPLE_COUNT", "3"))
LONG_SESSION_SPAN_SECONDS = int(os.getenv("CURTIS_LONG_SESSION_SPAN_SECONDS", str(90 * 60)))
CONFIRMED_PIECE_ID_VERSION = os.getenv("CURTIS_CONFIRMED_PIECE_ID_VERSION", "audio_piece_id_v8")


def local_timezone() -> ZoneInfo | timezone:
    try:
        return ZoneInfo(os.getenv("CURTIS_LOCAL_TIMEZONE", "America/New_York"))
    except ZoneInfoNotFoundError:
        return timezone.utc


def local_day(value: Any) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(local_timezone()).date().isoformat()


def today_local_day() -> str:
    return datetime.now(timezone.utc).astimezone(local_timezone()).date().isoformat()


def practice_day_from_title(value: Any) -> str:
    match = re.search(r"\b(\d{1,2})[-_/](\d{1,2})[-_/](\d{2,4})\b", str(value or ""))
    if not match:
        return ""
    month, day, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def sample_window_start(sample: dict[str, Any]) -> int:
    return parse_window_start(str(sample.get("window") or sample.get("id") or ""))


def prefer_late_practice_windows(samples: list[dict[str, Any]]) -> bool:
    starts = [sample_window_start(sample) for sample in samples]
    starts = [start for start in starts if start >= 0]
    if len(starts) < LONG_SESSION_LATE_SAMPLE_COUNT + 1:
        return False
    late = [start for start in starts if start >= LONG_SESSION_PRACTICE_FLOOR_SECONDS]
    if max(starts) - min(starts) < LONG_SESSION_SPAN_SECONDS:
        return False
    return len(late) >= LONG_SESSION_LATE_SAMPLE_COUNT or bool(late)


def untrusted_long_session_source(piece: dict[str, Any], media_samples: list[dict[str, Any]] | None) -> bool:
    if not media_samples:
        return False
    url = str(piece.get("sourceUrl") or "")
    if not url:
        return False
    group = [sample for sample in media_samples if str(sample.get("url") or "") == url]
    if not group or not prefer_late_practice_windows(group):
        return False
    return int(piece.get("sourceStartSeconds") or 0) < LONG_SESSION_PRACTICE_FLOOR_SECONDS


def sanitized_findings(findings: list[Any]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        item = dict(finding)
        evidence = str(item.get("evidence") or "").lower()
        if any(term in evidence for term in WEAK_EVIDENCE_TERMS):
            item["judgment"] = "Unjudged"
        clean.append(item)
    return clean


def major_piece_tip(piece: dict[str, Any], tip: str) -> str:
    clean_tip = str(tip or "Capture one clearer excerpt.").strip()
    signal = f"{piece.get('title') or ''} {piece.get('evidence') or ''} {piece.get('candidateEvidence') or ''}".lower()
    if re.match(r"^capture one clear(er)? excerpt\.?$", clean_tip, flags=re.IGNORECASE):
        if piece.get("confidence") != "clear" or piece.get("title") == "Piece being identified":
            return "Record one clean 60-second excerpt with the full violin, bow arm, left hand, and music stand visible."
        if any(term in signal for term in ("bariolage", "string crossing", "arpeggio", "arpeggiated")):
            return "Keep the E-major pattern even: small string crossings, steady left-hand frame, no rush after shifts."
        if "etude" in signal or "caprice" in signal:
            return "Isolate one small technical cell and record a slower clean take."
    return clean_tip


def unclear_piece_evidence(value: Any) -> str:
    evidence = str(value or "Exact piece not identified from current excerpt.").strip()
    lowered = evidence.lower()
    if any(term in lowered for term in REPERTOIRE_NAME_TERMS):
        return "Exact piece not identified from current excerpt."
    return evidence[:220]


def piece_matches_five_one(piece: dict[str, Any] | None) -> bool:
    piece = piece or {}
    source = " ".join(
        str(piece.get(key) or "")
        for key in ("sourceTitle", "sourceUrl", "sourceWindow", "sampleId", "sectionId")
    ).lower()
    return "5-1" in source or "5/1" in source or "5 1 26" in source or "wdfvptu4i_i" in source


def rejected_repertoire_title(value: Any, piece: dict[str, Any] | None = None) -> bool:
    compact = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    state = load_state()
    if (
        item_stale_after_source_correction(state, piece)
        or source_requires_confirmed_acceptance(state, piece)
        or title_rejected_for_item(value, state, piece)
    ):
        return True
    rejected_titles = list(REJECTED_REPERTOIRE_TITLES)
    if piece_matches_five_one(piece):
        rejected_titles.extend(FIVE_ONE_REJECTED_REPERTOIRE_TITLES)
    return any(rejected in compact or compact in rejected for rejected in rejected_titles)


def canonical_piece_title(value: Any) -> str:
    title = str(value or "").strip()
    compact = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if "bach" in compact and "partita" in compact and "1006" in compact and (
        "preludio" in compact or "prelude" in compact
    ):
        return "J.S. Bach Partita No. 3 in E major, BWV 1006, Preludio"
    return title


def parse_window_bounds(value: Any) -> tuple[int, int]:
    match = re.search(r"\*(\d+)-(\d+)", str(value or ""))
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def correction_matches_source_key(correction: dict[str, Any], item: dict[str, Any]) -> bool:
    key = str(correction.get("sourceKey") or "").strip()
    return bool(key and source_key_from_item(item) == key)


def correction_matches_sample(correction: dict[str, Any], sample: dict[str, Any]) -> bool:
    if correction_matches_source_key(correction, sample):
        return True
    source_url = str(correction.get("sourceUrl") or "")
    sample_url = str(sample.get("url") or "")
    if source_url and sample_url == source_url:
        return True
    source_video_id = youtube_video_id(source_url or correction.get("sourceKey"))
    sample_signal = " ".join(
        str(sample.get(key) or "")
        for key in ("id", "url", "title")
    )
    return bool(source_video_id and source_video_id.lower() in sample_signal.lower())


def correction_matches_inventory(correction: dict[str, Any], item: dict[str, Any]) -> bool:
    if correction_matches_source_key(correction, item):
        return True
    source_url = str(correction.get("sourceUrl") or "")
    item_url = str(item.get("url") or "")
    if source_url and item_url == source_url:
        return True
    source_video_id = youtube_video_id(source_url or correction.get("sourceKey"))
    item_signal = " ".join(
        str(item.get(key) or "")
        for key in ("id", "url", "title")
    )
    return bool(source_video_id and source_video_id.lower() in item_signal.lower())


def accepted_source_pieces(
    state: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    for correction in accepted_source_corrections(state):
        title = str(correction.get("acceptedTitle") or "").strip()
        if not title:
            continue
        matching_samples = [
            sample
            for sample in media_samples
            if isinstance(sample, dict) and correction_matches_sample(correction, sample)
        ]
        matching_samples.sort(key=lambda sample: parse_window_start(str(sample.get("window") or "")))
        sample = matching_samples[0] if matching_samples else {}
        inventory_items = [
            item
            for items in inventory.values()
            for item in items
            if isinstance(item, dict) and correction_matches_inventory(correction, item)
        ]
        inventory_item = inventory_items[0] if inventory_items else {}
        source_title = str(correction.get("sourceTitle") or sample.get("title") or inventory_item.get("title") or "").strip()
        source_url = str(correction.get("sourceUrl") or sample.get("url") or inventory_item.get("url") or "").strip()
        window = str(sample.get("window") or "").strip()
        start_seconds, end_seconds = parse_window_bounds(window)
        if not end_seconds and start_seconds:
            end_seconds = start_seconds + 45
        practice_day = practice_day_from_title(source_title)
        updated_at = str(correction.get("acceptedAt") or correction.get("updatedAt") or sample.get("createdAt") or utc_now())
        source_tip = str(correction.get("sourceTip") or "Record one clean source take for scoring.").strip()
        pieces.append(
            {
                "title": title,
                "confidence": "clear",
                "confidenceScore": 100,
                "completionPercent": 0,
                "todayCompletionPercent": 0,
                "readinessStatus": "identified_not_scored",
                "evidenceQuality": "human_verified_source_label",
                "evidence": "Alan-confirmed source label. Scoring pending judged playing evidence.",
                "candidateEvidence": "Alan-confirmed source label. Scoring pending judged playing evidence.",
                "tip": source_tip,
                "sampleId": sample.get("id") or "",
                "sourceTitle": source_title,
                "sourceUrl": source_url,
                "sourceWindow": window,
                "sourceStartSeconds": start_seconds,
                "sourceEndSeconds": end_seconds,
                "latestAt": updated_at,
                "createdAt": updated_at,
                "reviewVersion": "human_source_label_v1",
                "sectionCount": max(1, len(matching_samples)),
                "daily": {
                    practice_day: {
                        "completionPercent": 0,
                        "sectionCount": max(1, len(matching_samples)),
                        "tip": source_tip,
                        "evidence": "Alan-confirmed source label. Scoring pending judged playing evidence.",
                        "latestAt": updated_at,
                        "sampleId": sample.get("id") or "",
                        "sourceTitle": source_title,
                        "sourceUrl": source_url,
                        "sourceWindow": window,
                        "sourceStartSeconds": start_seconds,
                        "sourceEndSeconds": end_seconds,
                    }
                } if practice_day else {},
            }
        )
    return pieces


def correction_video_id(correction: dict[str, Any]) -> str:
    video_id = youtube_video_id(correction.get("sourceUrl")) or youtube_video_id(correction.get("sourceKey"))
    if video_id:
        return video_id
    key = str(correction.get("sourceKey") or "")
    if key.startswith("youtube:"):
        return key.split(":", 1)[1]
    return ""


def title_matches(left: Any, right: Any) -> bool:
    left_compact = compact_text(left)
    right_compact = compact_text(right)
    if not left_compact or not right_compact:
        return False
    return left_compact == right_compact or left_compact in right_compact or right_compact in left_compact


def correction_matches_result(correction: dict[str, Any], result: dict[str, Any]) -> bool:
    if correction_matches_source_key(correction, result):
        return True
    source_url = str(correction.get("sourceUrl") or "")
    result_url = str(result.get("sourceUrl") or result.get("url") or "")
    if source_url and result_url == source_url:
        return True
    video_id = correction_video_id(correction)
    result_signal = " ".join(
        str(result.get(key) or "")
        for key in (
            "id",
            "sampleId",
            "url",
            "sourceUrl",
            "title",
            "sourceTitle",
            "sampleTitle",
            "sourceWindow",
        )
    )
    return bool(video_id and video_id.lower() in result_signal.lower())


def review_piece_results(state: dict[str, Any], existing: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_sources = [
        existing.get("pieceIdentifications"),
        state.get("review", {}).get("pieceIdentifications") if isinstance(state.get("review"), dict) else None,
        state.get("lastPieceIdRun", {}).get("results") if isinstance(state.get("lastPieceIdRun"), dict) else None,
    ]
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for source in candidate_sources:
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("sampleId") or item.get("id") or ""),
                str(item.get("sourceUrl") or item.get("url") or ""),
                str(item.get("title") or item.get("proposedTitle") or ""),
                str(item.get("evidenceQuality") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
    return results


def result_is_blind_audio_match(correction: dict[str, Any], result: dict[str, Any]) -> bool:
    if not correction_matches_result(correction, result):
        return False
    accepted_title = str(correction.get("acceptedTitle") or "").strip()
    if not accepted_title:
        return False
    if result.get("modelMatchedAcceptedTitle") is True:
        return True
    if (
        result.get("status") == "piece_identified"
        and str(result.get("evidenceQuality") or "") == "verified_piece_id"
    ):
        return any(
            title_matches(title, accepted_title)
            for title in (
                result.get("title"),
                result.get("proposedTitle"),
                result.get("candidateTitle"),
                result.get("verificationTitle"),
            )
        )
    return False


def result_is_score_aligned(correction: dict[str, Any], result: dict[str, Any]) -> bool:
    if not correction_matches_result(correction, result):
        return False
    alignment = result.get("scoreAlignment")
    if not isinstance(alignment, dict):
        return False
    if alignment.get("possible") is not True:
        return False
    return bool(str(alignment.get("matchedSection") or alignment.get("matchedMeasures") or "").strip())


def transcription_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    items = state.get("transcriptions", {}).get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def transcription_ready(item: dict[str, Any]) -> bool:
    return item.get("status") == "transcribed" and int(item.get("noteCount") or 0) >= 4


def source_training_state(
    state: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
    piece_results: list[dict[str, Any]],
) -> dict[str, Any]:
    anchors: list[dict[str, Any]] = []
    transcriptions = transcription_items(state)
    for correction in accepted_source_corrections(state):
        title = str(correction.get("acceptedTitle") or "").strip()
        if not title:
            continue
        samples = [
            sample
            for sample in media_samples
            if isinstance(sample, dict) and correction_matches_sample(correction, sample)
        ]
        samples.sort(key=lambda sample: parse_window_start(str(sample.get("window") or "")))
        inventory_items = [
            item
            for items in inventory.values()
            for item in items
            if isinstance(item, dict) and correction_matches_inventory(correction, item)
        ]
        source_title = str(
            correction.get("sourceTitle")
            or (samples[0].get("title") if samples else "")
            or (inventory_items[0].get("title") if inventory_items else "")
            or ""
        ).strip()
        source_url = str(
            correction.get("sourceUrl")
            or (samples[0].get("url") if samples else "")
            or (inventory_items[0].get("url") if inventory_items else "")
            or ""
        ).strip()
        reference_target = correction.get("referenceTarget") if isinstance(correction.get("referenceTarget"), dict) else {}
        blind_match_count = sum(1 for result in piece_results if result_is_blind_audio_match(correction, result))
        score_aligned_count = sum(1 for result in piece_results if result_is_score_aligned(correction, result))
        pitch_rhythm_items = [
            item
            for item in transcriptions
            if correction_matches_result(correction, item) and transcription_ready(item)
        ]
        status = "score_alignment_started" if score_aligned_count else "blind_audio_title_match" if blind_match_count else "source_label_only"
        if pitch_rhythm_items and not score_aligned_count and not blind_match_count:
            status = "pitch_rhythm_extracted"
        if not samples:
            status = "pitch_rhythm_extracted" if pitch_rhythm_items else "audio_window_needed"
        latest_transcription = pitch_rhythm_items[0] if pitch_rhythm_items else {}
        anchors.append(
            {
                "sourceKey": correction.get("sourceKey") or "",
                "title": title,
                "sourceTitle": source_title,
                "sourceUrl": source_url,
                "practiceDay": practice_day_from_title(source_title),
                "sourceConfirmed": True,
                "sampleCount": len(samples),
                "sampleWindows": stable_unique([str(sample.get("window") or "") for sample in samples])[:4],
                "blindAudioMatchCount": blind_match_count,
                "scoreAlignedWindowCount": score_aligned_count,
                "pitchRhythmWindowCount": len(pitch_rhythm_items),
                "referenceTargetStatus": reference_target.get("status") or "needed",
                "scoreAlignment": {
                    "status": "score_match_proven" if score_aligned_count else "pitch_rhythm_extracted" if pitch_rhythm_items else "not_configured",
                    "matchedSection": "",
                    "matchedMeasures": "",
                    "pitchRhythmExtracted": bool(pitch_rhythm_items),
                    "latestTranscription": {
                        "sourceTitle": latest_transcription.get("sourceTitle") or "",
                        "sourceWindow": latest_transcription.get("sourceWindow") or "",
                        "noteCount": latest_transcription.get("noteCount") or 0,
                        "tempoBpm": latest_transcription.get("tempoBpm") or 0,
                        "firstNotes": latest_transcription.get("fingerprint", {}).get("firstNotes", [])[:16]
                        if isinstance(latest_transcription.get("fingerprint"), dict)
                        else [],
                    },
                    "referenceScore": "target_ready" if reference_target else "needed",
                    "referenceAudio": reference_target.get("referenceAudio") or "needed",
                    "referenceTarget": {
                        "composer": reference_target.get("composer") or "",
                        "work": reference_target.get("work") or "",
                        "movement": reference_target.get("movement") or "",
                        "part": reference_target.get("part") or "",
                        "scoreSource": reference_target.get("scoreSource") or "",
                        "scoreUrl": reference_target.get("scoreUrl") or "",
                        "alignmentGoal": reference_target.get("alignmentGoal") or "",
                        "passageVocabulary": [
                            str(item).strip()
                            for item in reference_target.get("passageVocabulary", [])
                            if str(item).strip()
                        ][:8],
                    },
                },
                "status": status,
                "note": (
                    "score passage alignment started"
                    if score_aligned_count
                    else "pitch/rhythm transcription extracted; score alignment not yet proven"
                    if pitch_rhythm_items
                    else "audio title match proven before source correction"
                    if blind_match_count
                    else "source label confirmed; score alignment not proven"
                ),
            }
        )
    calibration_anchors: list[dict[str, Any]] = []
    for item in transcriptions:
        if not isinstance(item, dict) or not transcription_ready(item):
            continue
        calibration = calibration_anchor_for_item(item)
        if not calibration:
            continue
        calibration_anchors.append(
            {
                "sourceKey": item.get("sourceKey") or "",
                "title": calibration.get("title") or "",
                "sourceTitle": calibration.get("sourceTitle") or item.get("sourceTitle") or "",
                "sourceUrl": calibration.get("sourceUrl") or item.get("sourceUrl") or "",
                "sourceConfirmed": False,
                "sourceConfidence": calibration.get("sourceConfidence") or "explicit_title_label",
                "materialType": calibration.get("materialType") or "calibration",
                "referenceKind": calibration.get("referenceKind") or "title_labeled_calibration",
                "pitchRhythmWindowCount": 1,
                "status": "calibration_pitch_rhythm_extracted",
                "note": "title-labeled calibration anchor; not promoted to repertoire",
            }
        )
    confirmed_count = len(anchors)
    calibration_count = len(calibration_anchors)
    captured_count = sum(int(anchor.get("sampleCount") or 0) for anchor in anchors)
    blind_count = sum(int(anchor.get("blindAudioMatchCount") or 0) for anchor in anchors)
    score_count = sum(int(anchor.get("scoreAlignedWindowCount") or 0) for anchor in anchors)
    pitch_rhythm_count = sum(int(anchor.get("pitchRhythmWindowCount") or 0) for anchor in anchors)
    calibration_pitch_count = sum(int(anchor.get("pitchRhythmWindowCount") or 0) for anchor in calibration_anchors)
    reference_count = sum(1 for anchor in anchors if anchor.get("referenceTargetStatus") == "reference_target_ready")
    public_reference = public_reference_training_state(state)
    status = "no_anchors"
    if confirmed_count and score_count:
        status = "score_alignment_started"
    elif confirmed_count and (pitch_rhythm_count or calibration_pitch_count):
        status = "pitch_rhythm_extracted"
    elif confirmed_count and blind_count >= confirmed_count:
        status = "audio_title_match_ready"
    elif calibration_count:
        status = "calibration_anchored"
    elif confirmed_count:
        status = "source_anchored"
    public_seed_count = int(public_reference.get("seedQueryCount") or 0)
    public_item_count = int(public_reference.get("storedItemCount") or 0)
    return {
        "status": status,
        "label": (
            f"{calibration_count} cal / {calibration_pitch_count} pitch windows"
            if calibration_count and not confirmed_count
            else f"{reference_count} refs / {score_count} score alignments"
            if not pitch_rhythm_count and not calibration_pitch_count
            else f"{reference_count} refs / {pitch_rhythm_count + calibration_pitch_count} pitch windows"
        ),
        "confirmedSourceCount": confirmed_count,
        "calibrationAnchorCount": calibration_count,
        "referenceTargetCount": reference_count,
        "publicReferenceSeedCount": public_seed_count,
        "publicReferenceItemCount": public_item_count,
        "capturedAnchorWindowCount": captured_count,
        "blindAudioMatchCount": blind_count,
        "pitchRhythmWindowCount": pitch_rhythm_count + calibration_pitch_count,
        "scoreAlignedWindowCount": score_count,
        "anchors": anchors,
        "calibrationAnchors": calibration_anchors,
        "publicReference": public_reference,
        "method": "source-confirmed labels, title-labeled calibration videos, public labeled reference seeds, pitch/rhythm extraction, score alignment, and reference-audio comparison",
        "limit": "Confirmed labels and explicit calibration titles train source memory. Public YouTube labels seed reference targets; audio proof still requires permitted media and score or pattern alignment.",
    }


def better_tip(current: str, incoming: str) -> str:
    current_clean = str(current or "").strip()
    incoming_clean = str(incoming or "").strip()
    if re.match(r"^capture one clear(er)? excerpt\.?$", current_clean, flags=re.IGNORECASE) and incoming_clean:
        return incoming_clean
    return current_clean or incoming_clean


def normalize_piece_daily(piece: dict[str, Any], daily: dict[str, Any], practice_day: str) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for day, entry in daily.items():
        if not isinstance(entry, dict):
            continue
        target_day = practice_day_from_title(entry.get("sourceTitle")) or practice_day or str(day)
        current = dict(normalized.get(target_day, {}))
        prior_count = int(current.get("sectionCount") or 0)
        incoming_count = max(1, int(entry.get("sectionCount") or 1))
        prior_completion = int(current.get("completionPercent") or 0)
        incoming_completion = int(entry.get("completionPercent") or 0)
        total_count = prior_count + incoming_count
        if total_count:
            current["completionPercent"] = round(
                ((prior_completion * prior_count) + (incoming_completion * incoming_count)) / total_count
            )
        current["sectionCount"] = total_count
        current["tip"] = better_tip(str(current.get("tip") or ""), str(entry.get("tip") or piece.get("tip") or ""))
        current["evidence"] = str(entry.get("evidence") or current.get("evidence") or piece.get("evidence") or "").strip()[:220]
        if str(entry.get("latestAt") or "") > str(current.get("latestAt") or ""):
            current["latestAt"] = entry.get("latestAt")
        for key in (
            "sampleId",
            "sectionId",
            "sourceTitle",
            "sourceUrl",
            "sourceWindow",
            "sourceStartSeconds",
            "sourceEndSeconds",
        ):
            if entry.get(key) not in {None, ""}:
                current[key] = entry.get(key)
            elif current.get(key) in {None, ""} and piece.get(key) not in {None, ""}:
                current[key] = piece.get(key)
        normalized[target_day] = current
    if not normalized and practice_day:
        normalized[practice_day] = {
            "completionPercent": int(piece.get("completionPercent") or 0),
            "sectionCount": int(piece.get("sectionCount") or 1),
            "tip": str(piece.get("tip") or piece.get("immediateTip") or "Evidence recorded.").strip()[:180],
            "evidence": str(piece.get("evidence") or "Evidence recorded.").strip()[:220],
            "latestAt": piece.get("latestAt") or piece.get("createdAt"),
            "sampleId": piece.get("sampleId"),
            "sectionId": piece.get("sectionId"),
            "sourceTitle": piece.get("sourceTitle"),
            "sourceUrl": piece.get("sourceUrl"),
            "sourceWindow": piece.get("sourceWindow"),
            "sourceStartSeconds": piece.get("sourceStartSeconds"),
            "sourceEndSeconds": piece.get("sourceEndSeconds"),
        }
    return {key: normalized[key] for key in sorted(normalized)[-21:]}


def merge_daily_maps(current: dict[str, Any], incoming: dict[str, Any]) -> None:
    current_daily = current.get("daily") if isinstance(current.get("daily"), dict) else {}
    incoming_daily = incoming.get("daily") if isinstance(incoming.get("daily"), dict) else {}
    merged = {str(day): dict(entry) for day, entry in current_daily.items() if isinstance(entry, dict)}
    for day, entry in incoming_daily.items():
        if not isinstance(entry, dict):
            continue
        day_key = str(day)
        if day_key not in merged:
            merged[day_key] = dict(entry)
            continue
        existing = merged[day_key]
        existing_count = max(1, int(existing.get("sectionCount") or 1))
        incoming_count = max(1, int(entry.get("sectionCount") or 1))
        total_count = existing_count + incoming_count
        existing_completion = int(existing.get("completionPercent") or 0)
        incoming_completion = int(entry.get("completionPercent") or 0)
        existing["completionPercent"] = round(
            ((existing_completion * existing_count) + (incoming_completion * incoming_count)) / total_count
        )
        existing["sectionCount"] = total_count
        existing["tip"] = better_tip(str(existing.get("tip") or ""), str(entry.get("tip") or incoming.get("tip") or ""))
        existing["evidence"] = str(entry.get("evidence") or existing.get("evidence") or incoming.get("evidence") or "")[:220]
        if str(entry.get("latestAt") or "") >= str(existing.get("latestAt") or ""):
            existing["latestAt"] = entry.get("latestAt") or existing.get("latestAt")
            for source_key in (
                "sampleId",
                "sectionId",
                "sourceTitle",
                "sourceUrl",
                "sourceWindow",
                "sourceStartSeconds",
                "sourceEndSeconds",
            ):
                if entry.get(source_key) not in {None, ""}:
                    existing[source_key] = entry.get(source_key)
        merged[day_key] = existing
    current["daily"] = {key: merged[key] for key in sorted(merged)[-21:]}


def merge_enriched_pieces(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for piece in pieces:
        key = str(piece.get("title") or "Piece being identified").lower()
        current = merged.get(key)
        if current is None:
            merged[key] = piece
            continue
        merge_daily_maps(current, piece)
        current["sectionCount"] = int(current.get("sectionCount") or 0) + int(piece.get("sectionCount") or 0)
        current["completionPercent"] = max(int(current.get("completionPercent") or 0), int(piece.get("completionPercent") or 0))
        current["todayCompletionPercent"] = max(
            int(current.get("todayCompletionPercent") or 0),
            int(piece.get("todayCompletionPercent") or 0),
        )
        current["tip"] = better_tip(str(current.get("tip") or ""), str(piece.get("tip") or ""))
        current["todayTip"] = better_tip(str(current.get("todayTip") or ""), str(piece.get("todayTip") or ""))
        evidence = " ".join(
            stable_unique(
                [
                    str(current.get("evidence") or "").strip(),
                    str(piece.get("evidence") or "").strip(),
                ]
            )
        )
        current["evidence"] = evidence[:220]
        incoming_latest = str(piece.get("latestAt") or "")
        current_latest = str(current.get("latestAt") or "")
        incoming_day = str(piece.get("practiceDay") or "")
        current_day = str(current.get("practiceDay") or "")
        if incoming_latest > current_latest or (incoming_latest == current_latest and incoming_day > current_day):
            current["latestAt"] = piece.get("latestAt")
            current["todayLatestAt"] = piece.get("todayLatestAt") or current.get("todayLatestAt")
            if str(piece.get("tip") or "").strip():
                current["tip"] = piece.get("tip")
            for source_key in (
                "sampleId",
                "sectionId",
                "sourceTitle",
                "sourceUrl",
                "sourceWindow",
                "sourceStartSeconds",
                "sourceEndSeconds",
                "practiceDay",
            ):
                if piece.get(source_key) not in {None, ""} or source_key in {"sampleId", "sectionId", "sourceUrl", "sourceWindow"}:
                    current[source_key] = piece.get(source_key)
        else:
            for source_key in (
                "sampleId",
                "sectionId",
                "sourceTitle",
                "sourceUrl",
                "sourceWindow",
                "sourceStartSeconds",
                "sourceEndSeconds",
                "practiceDay",
            ):
                if current.get(source_key) in {None, ""} and piece.get(source_key) not in {None, ""}:
                    current[source_key] = piece.get(source_key)
        current["isActiveToday"] = bool(current.get("isActiveToday") or piece.get("isActiveToday"))
    return sorted(
        merged.values(),
        key=lambda piece: (
            1 if piece.get("isActiveToday") else 0,
            str(piece.get("practiceDay") or local_day(piece.get("latestAt"))),
            int(piece.get("confidenceScore") or 0),
            int(piece.get("todayCompletionPercent") or 0),
            int(piece.get("completionPercent") or 0),
            str(piece.get("latestAt") or ""),
        ),
        reverse=True,
    )[:12]


def enriched_pieces(pieces: list[Any], today: str, media_samples: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in pieces:
        if not isinstance(item, dict):
            continue
        piece = dict(item)
        has_source_window = bool(
            piece.get("sampleId")
            and piece.get("sourceUrl")
            and piece.get("sourceStartSeconds") is not None
        )
        verified_piece_id = str(piece.get("evidenceQuality") or "") == "verified_piece_id"
        human_verified_source_label = str(piece.get("evidenceQuality") or "") == "human_verified_source_label"
        source_confirmed = human_verified_source_label or (
            verified_piece_id and not REQUIRE_SOURCE_CONFIRMED_PIECE_TITLES
        )
        current_piece_id_version = str(piece.get("reviewVersion") or "") == CONFIRMED_PIECE_ID_VERSION
        if (
            str(piece.get("confidence") or "unknown").lower() != "clear"
            or rejected_repertoire_title(piece.get("title"), piece)
            or not source_confirmed
            or (
                not human_verified_source_label
                and (
                    not has_source_window
                    or not current_piece_id_version
                    or untrusted_long_session_source(piece, media_samples)
                )
            )
        ):
            piece["title"] = "Piece being identified"
            piece["confidence"] = "unknown"
            piece["confidenceScore"] = 1
            piece["completionPercent"] = 0
            piece["evidenceQuality"] = "weak"
            piece["candidateTitle"] = ""
            piece["evidence"] = unclear_piece_evidence(piece.get("evidence"))
            piece["candidateEvidence"] = unclear_piece_evidence(piece.get("candidateEvidence") or piece.get("evidence"))
            daily = piece.get("daily") if isinstance(piece.get("daily"), dict) else {}
            piece["daily"] = {
                str(day): {
                    **entry,
                    "completionPercent": 0,
                    "tip": "Piece identification pending verified source evidence.",
                }
                for day, entry in daily.items()
                if isinstance(entry, dict)
            }
        else:
            piece["title"] = canonical_piece_title(piece.get("title"))
        practice_day = practice_day_from_title(piece.get("sourceTitle"))
        daily = normalize_piece_daily(
            piece,
            piece.get("daily") if isinstance(piece.get("daily"), dict) else {},
            practice_day,
        )
        piece["daily"] = daily
        today_entry = daily.get(today) if isinstance(daily.get(today), dict) else None
        latest_day = practice_day or (max(daily) if daily else "") or local_day(piece.get("latestAt"))
        if today_entry:
            today_percent = int(today_entry.get("completionPercent") or 0)
            today_tip = str(today_entry.get("tip") or piece.get("tip") or "Capture one clearer excerpt.").strip()
            today_latest = today_entry.get("latestAt") or piece.get("latestAt")
        elif latest_day == today and not daily:
            today_percent = int(piece.get("completionPercent") or 0)
            today_tip = str(piece.get("tip") or "Capture one clearer excerpt.").strip()
            today_latest = piece.get("latestAt")
        else:
            today_percent = 0
            today_tip = "Awaiting today's practice sample."
            today_latest = ""
        if piece.get("confidence") != "clear":
            today_percent = 0
            today_tip = "Record one clean 60-second excerpt with the full violin, bow arm, left hand, and music stand visible."
        piece["today"] = today
        piece["todayCompletionPercent"] = max(0, min(100, today_percent))
        piece["todayTip"] = major_piece_tip(piece, today_tip)[:180]
        piece["todayLatestAt"] = today_latest
        piece["practiceDay"] = latest_day
        piece["isActiveToday"] = bool(today_entry or (latest_day == today and not daily))
        enriched.append(piece)
    return merge_enriched_pieces(enriched)


def inventory_blockers(blockers: list[str]) -> list[str]:
    return [blocker for blocker in blockers if blocker not in MEDIA_REVIEW_PENDING_BLOCKERS]


def effective_sources(state: dict[str, Any]) -> dict[str, Any]:
    sources = dict(state.get("sources", {}))
    stored_youtube = str(sources.get("youtube") or "").strip()
    env_youtube = os.getenv("CURTIS_YOUTUBE_SOURCE", "").strip()
    if stored_youtube:
        sources["youtube"] = stored_youtube
    elif env_youtube:
        sources["youtube"] = env_youtube
    elif youtube_auth_status().get("connected"):
        sources["youtube"] = "mine"
    else:
        sources["youtube"] = DEFAULT_YOUTUBE_SOURCE
    sources["instagram"] = sources.get("instagram") or os.getenv("CURTIS_INSTAGRAM_SOURCE", "")
    return sources


def public_reference_corpus_is_stale(state: dict[str, Any]) -> bool:
    corpus = state.get("referenceCorpus") if isinstance(state.get("referenceCorpus"), dict) else {}
    stored = corpus.get("publicYouTubeItems") if isinstance(corpus.get("publicYouTubeItems"), list) else []
    indexed_at = str(corpus.get("publicYouTubeIndexedAt") or "")
    if not stored or not indexed_at:
        return True
    try:
        parsed = datetime.fromisoformat(indexed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - parsed).total_seconds() >= PUBLIC_REFERENCE_REFRESH_SECONDS


async def refresh_public_reference_corpus(state: dict[str, Any]) -> None:
    corpus = state.setdefault("referenceCorpus", {})
    if not public_reference_corpus_is_stale(state):
        return
    try:
        result = await fetch_youtube_public_references(PUBLIC_REFERENCE_SEEDS)
        if result.items:
            corpus["publicYouTubeItems"] = result.items
            corpus["publicYouTubeIndexedAt"] = utc_now()
        corpus["sourceType"] = result.source_type
        corpus["blockers"] = result.blockers
    except httpx.HTTPStatusError as exc:
        corpus["blockers"] = ["youtube_public_reference_search_error"]
        corpus["lastError"] = exc.response.text[:500]
    except Exception as exc:  # pragma: no cover - defensive service boundary
        corpus["blockers"] = ["youtube_public_reference_search_failed"]
        corpus["lastError"] = str(exc)[:500]


def score_sequence_match_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
        total += int(
            transcription.get("scoreSequenceCandidateCount")
            or transcription.get("scoreSequenceMatchCount")
            or 0
        )
    return total


def candidate_match_groups_for_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int, int, str]] = set()
    for key in ("candidateMatchGroups", "matchGroups"):
        raw_groups = record.get(key) if isinstance(record.get(key), list) else []
        for group in raw_groups:
            if not isinstance(group, dict):
                continue
            transcription = group.get("transcription") if isinstance(group.get("transcription"), dict) else {}
            detected = group.get("detectedSeries") if isinstance(group.get("detectedSeries"), dict) else {}
            score = group.get("score") if isinstance(group.get("score"), dict) else {}
            identity = (
                str(group.get("status") or ""),
                str(transcription.get("sampleId") or detected.get("sampleId") or ""),
                str(score.get("assetId") or group.get("pieceTitle") or ""),
                int(group.get("referenceStart") or 0),
                int(group.get("referenceEnd") or 0),
                match_detected_pitch_sequence(group),
            )
            if identity in seen:
                continue
            seen.add(identity)
            groups.append(group)
    return groups


def score_location_verified_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        groups = candidate_match_groups_for_record(record)
        total += sum(
            1
            for group in groups
            if isinstance(group, dict)
            and group.get("scoreLocationVerified")
            and actual_source_score_snippet_ready(group)
        )
    return total


def score_visual_agreement_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        groups = candidate_match_groups_for_record(record)
        total += sum(1 for group in groups if isinstance(group, dict) and actual_source_score_snippet_ready(group))
    return total


def actual_source_score_snippet_ready(match: dict[str, Any]) -> bool:
    if not isinstance(match, dict):
        return False
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    image_url = str(score.get("imageUrl") or "").strip()
    if not image_url or image_url.startswith("data:"):
        return False
    status_text = " ".join(
        str(value or "")
        for value in (
            match.get("status"),
            match.get("scoreLocationStatus"),
            match.get("scoreSnippetStatus"),
            score.get("status"),
            score.get("cropStatus"),
        )
    ).lower()
    if any(token in status_text for token in ("rejected", "failed", "mismatch")):
        return False
    if score.get("actualSourceSnippetDisplayed") is not True and match.get("scoreActualPieceAgreement") is not True:
        return False
    if score.get("visualRangeAgreement") is not True or match.get("scoreVisualRangeAgreement") is not True:
        return False
    if score.get("visibleScoreNoteSequenceVerified") is not True or match.get("scoreVisibleNoteSequenceVerified") is not True:
        return False
    if (
        score.get("visibleScoreExactNoteSequenceVerified") is not True
        or match.get("scoreVisibleExactNoteSequenceVerified") is not True
    ):
        return False
    if score.get("scoreSpellingAgreement") is not True or match.get("scoreSpellingAgreement") is not True:
        return False
    if score.get("scoreBoxCenterAgreement") is not True and match.get("scoreBoxCenterAgreement") is not True:
        return False
    if score.get("audioTranscriptionAgreement") is not True and match.get("audioTranscriptionAgreement") is not True:
        return False
    if score.get("transcriptionScoreAgreement") is not True and match.get("transcriptionScoreAgreement") is not True:
        return False
    if score.get("truthEvidenceAccepted") is not True and match.get("truthEvidenceAccepted") is not True:
        return False
    return bool(match.get("scoreVisualAgreement") is True)


def actual_source_score_snippet_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        groups = candidate_match_groups_for_record(record)
        total += sum(1 for group in groups if actual_source_score_snippet_ready(group))
    return total


def match_has_local_media(match: dict[str, Any]) -> bool:
    clip = match.get("clip") if isinstance(match.get("clip"), dict) else {}
    if any(str(clip.get(key) or "").strip() for key in ("mediaUrl", "audioUrl", "videoUrl", "localVideoUrl", "localAudioUrl")):
        return True
    transcription = match.get("transcription") if isinstance(match.get("transcription"), dict) else {}
    return bool(str(transcription.get("sampleId") or "").strip())


def match_detected_pitch_sequence(match: dict[str, Any]) -> str:
    full = str(match.get("detectedPitchClassSequence") or "").strip()
    compact = str(match.get("detectedPitchClassSequenceCompact") or "").strip()
    return max((full, compact), key=lambda value: len(value.split()))


def match_detected_note_events(match: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("matchedDetectedNotes", "displayDetectedNotes"):
        notes = match.get(key)
        if isinstance(notes, list) and notes and all(isinstance(note, dict) for note in notes):
            return [note for note in notes if isinstance(note, dict)]
    detected = match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}
    notes = detected.get("notes") if isinstance(detected.get("notes"), list) else []
    return [note for note in notes if isinstance(note, dict)]


def match_detected_exact_sequence(match: dict[str, Any]) -> str:
    return " ".join(str(note.get("note") or "").strip() for note in match_detected_note_events(match) if str(note.get("note") or "").strip())


def match_detected_midi_values(match: dict[str, Any]) -> list[int]:
    values: list[int] = []
    for note in match_detected_note_events(match):
        midi = note_midi_value(note)
        if midi is None:
            return []
        values.append(midi)
    return values


def match_distinct_pitch_class_count(match: dict[str, Any]) -> int:
    sequence = match_detected_pitch_sequence(match)
    return len({value for value in sequence.split() if value})


def reference_phrase_candidate_match(match: dict[str, Any]) -> bool:
    if not isinstance(match, dict):
        return False
    if match.get("scoreLocationVerified"):
        return False
    status = str(match.get("status") or "").strip().lower()
    if status not in {"reference_sequence_match", "score_sequence_match"}:
        return False
    if int(match.get("matchedNoteRun") or 0) < 5:
        return False
    if match_distinct_pitch_class_count(match) < 3:
        return False
    return match_has_local_media(match)


def reference_phrase_candidate_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    candidates: set[tuple[str, str, str, int, int, str]] = set()
    for record in records:
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = candidate_match_groups_for_record(record)
        for match in groups:
            if not reference_phrase_candidate_match(match):
                continue
            score = match.get("score") if isinstance(match.get("score"), dict) else {}
            transcription = match.get("transcription") if isinstance(match.get("transcription"), dict) else {}
            detected = match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}
            candidates.add(
                (
                    practice_day,
                    str(transcription.get("sampleId") or detected.get("sampleId") or ""),
                    str(score.get("assetId") or match.get("pieceTitle") or ""),
                    int(match.get("referenceStart") or 0),
                    int(match.get("referenceEnd") or 0),
                    match_detected_pitch_sequence(match),
                )
            )
    return len(candidates)


def reference_phrase_candidate_top(daily_records: dict[str, Any]) -> dict[str, Any]:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    candidates: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = candidate_match_groups_for_record(record)
        for match in groups:
            if not reference_phrase_candidate_match(match):
                continue
            sequence = match_detected_pitch_sequence(match)
            if not sequence:
                continue
            sequence_note_count = len(sequence.split())
            candidates.append(
                {
                    "practiceDay": practice_day,
                    "sequence": sequence,
                    "sequenceNoteCount": sequence_note_count,
                    "matchedNoteRun": int(match.get("matchedNoteRun") or 0),
                    "distinctPitchClasses": match_distinct_pitch_class_count(match),
                    "pieceTitle": str(match.get("pieceTitle") or ""),
                    "scoreSequenceLabel": str(match.get("scoreSequenceLabel") or ""),
                    "status": str(match.get("status") or ""),
                }
            )
    if not candidates:
        return {}
    return sorted(
        candidates,
        key=lambda item: (
            -int(item.get("sequenceNoteCount") or 0),
            -int(item.get("matchedNoteRun") or 0),
            -int(item.get("distinctPitchClasses") or 0),
            str(item.get("practiceDay") or ""),
            str(item.get("sequence") or ""),
        ),
    )[0]


def source_verification_target_match(match: dict[str, Any]) -> bool:
    if not isinstance(match, dict):
        return False
    if match.get("scoreLocationVerified"):
        return False
    status = str(match.get("status") or "").strip().lower()
    if status not in {"reference_sequence_match", "score_sequence_match"}:
        return False
    if not match_has_local_media(match):
        return False
    if int(match.get("matchedNoteRun") or 0) < 4:
        return False
    if match_distinct_pitch_class_count(match) < 3:
        return False
    sequence = match_detected_pitch_sequence(match)
    return len(sequence.split()) >= 4


def source_reference_target_for_match(match: dict[str, Any]) -> dict[str, Any]:
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    score_asset_id = str(score.get("assetId") or score.get("scoreAssetId") or "").strip()
    piece_title = str(match.get("pieceTitle") or "").strip().lower()
    if score_asset_id == "wieniawski-scherzo-tarantelle-vln" or (
        "wieniawski" in piece_title and "scherzo" in piece_title and "tarantelle" in piece_title
    ):
        return wieniawski_reference_target()
    return {}


def source_target_score_check(match: dict[str, Any], sequence: str) -> dict[str, Any]:
    target = source_reference_target_for_match(match)
    score = symbolic_score_from_target(target) if target else {}
    candidate_audit = score_map_candidate_audit(target) if target else {}
    notes = score.get("notes") if isinstance(score.get("notes"), list) else []
    source_pitch_values = [normalize_pitch_class(note.get("pitchClass")) for note in notes if isinstance(note, dict)]
    source_pitch_values = [value for value in source_pitch_values if value]
    source_exact_values = [str(note.get("note") or "").strip() for note in notes if isinstance(note, dict) and str(note.get("note") or "").strip()]
    source_midi_values = [note_midi_value(note) for note in notes if isinstance(note, dict)]
    source_midi_values = [value for value in source_midi_values if value is not None]
    query_values = [normalize_pitch_class(value) for value in str(sequence or "").split()]
    query_values = [value for value in query_values if value]
    query_notes = match_detected_note_events(match)
    query_exact_values = [str(note.get("note") or "").strip() for note in query_notes if str(note.get("note") or "").strip()]
    query_midi_values = match_detected_midi_values(match)
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    if not query_values:
        return {
            "sourceScoreChecked": False,
            "sourceScoreVerified": False,
            "sourceScoreCheckStatus": "source_score_sequence_missing",
            "sourceScoreBestOverlap": 0,
            "sourceScoreExactMidiChecked": False,
            "sourceScoreMatchCriterion": "exact_midi_sequence",
            "sourceScoreLimit": "No detected sequence is available to verify against the score.",
        }
    if not source_midi_values:
        return {
            "sourceScoreChecked": False,
            "sourceScoreVerified": False,
            "sourceScoreCheckStatus": "source_score_map_missing",
            "sourceScoreBestOverlap": 0,
            "sourceScoreExactMidiChecked": False,
            "sourceScoreMatchCriterion": "exact_midi_sequence",
            "sourceScoreLimit": "No verified symbolic score map is available for this source target.",
        }
    pitch_overlap = longest_common_contiguous_run(query_values, source_pitch_values)
    pitch_overlap_length = int(pitch_overlap.get("length") or 0)
    if not query_notes or not query_midi_values or len(query_midi_values) != len(query_values):
        return {
            "sourceScoreChecked": True,
            "sourceScoreVerified": False,
            "sourceScoreCheckStatus": "source_score_exact_midi_missing",
            "sourceScoreBestOverlap": 0,
            "sourceScoreQueryLength": len(query_values),
            "sourceScoreReferenceLength": len(source_midi_values),
            "sourceScoreExactMidiChecked": False,
            "sourceScoreMatchCriterion": "exact_midi_sequence",
            "sourceScoreQueryPitchClassSequence": " ".join(query_values),
            "sourceScoreQueryExactSequence": " ".join(query_exact_values),
            "sourceScoreQueryMidiSequence": " ".join(str(value) for value in query_midi_values),
            "sourceScoreReferencePitchClassSequence": " ".join(source_pitch_values),
            "sourceScoreReferenceSequence": " ".join(source_exact_values),
            "sourceScoreReferenceMidiSequence": " ".join(str(value) for value in source_midi_values),
            "sourceScorePitchClassBestOverlap": pitch_overlap_length,
            "sourceScorePitchClassBestOverlapSequence": " ".join(
                source_pitch_values[
                    int(pitch_overlap.get("referenceStart") or 0) :
                    int(pitch_overlap.get("referenceStart") or 0) + pitch_overlap_length
                ]
            ),
            "sourceScoreSourceId": str(score.get("sourceId") or score_config.get("sourceId") or ""),
            "sourceScoreTitle": str(score.get("title") or target.get("work") or ""),
            "sourceScoreCandidateGlyphCount": int(candidate_audit.get("scoreMapCandidateGlyphCount") or 0),
            "sourceScoreCandidateStaffCount": int(candidate_audit.get("scoreMapCandidateStaffCount") or 0),
            "sourceScoreNoteHypothesisCount": int(candidate_audit.get("scoreMapNoteHypothesisCount") or 0),
            "sourceScoreNoteHypothesisStaffCount": int(candidate_audit.get("scoreMapNoteHypothesisStaffCount") or 0),
            "sourceScoreReviewPacketCount": int(candidate_audit.get("scoreMapReviewPacketCount") or 0),
            "sourceScoreCandidateStatus": str(candidate_audit.get("status") or ""),
            "sourceScoreLimit": "Detected pitch letters are not enough; this source target needs exact detected MIDI values before it can be checked against MusicXML.",
        }
    candidate_only = bool((match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}).get("candidateOnly"))
    audio_agreed = notes_have_score_match_audio_agreement(query_notes, candidate_only=candidate_only)
    phrase_gate = exact_midi_phrase_gate(
        query_notes,
        notes,
        audio_agreed=audio_agreed,
        min_exact_notes=5,
        require_full_query=True,
    )
    overlap_length = int(phrase_gate.get("bestOverlap") or 0)
    verified = bool(phrase_gate.get("accepted"))
    reference_start = int(phrase_gate.get("referenceStart") or 0)
    reference_end = int(phrase_gate.get("referenceEnd") or reference_start + overlap_length)
    check_status = str(phrase_gate.get("status") or "source_score_exact_midi_sequence_not_found")
    return {
        "sourceScoreChecked": True,
        "sourceScoreVerified": verified,
        "sourceScoreCheckStatus": check_status,
        "sourceScoreBestOverlap": overlap_length,
        "sourceScoreQueryLength": len(query_midi_values),
        "sourceScoreReferenceLength": len(source_midi_values),
        "sourceScoreExactMidiChecked": True,
        "sourceScoreAudioAgreed": audio_agreed,
        "sourceScoreMatchCriterion": "exact_midi_sequence",
        "sourceScoreExactMidiMinimumNotes": int(phrase_gate.get("minimumExactNotes") or 5),
        "sourceScoreExactMidiFullQueryRequired": bool(phrase_gate.get("requireFullQuery")),
        "sourceScoreOrderedOverlap": int(phrase_gate.get("orderedOverlap") or 0),
        "sourceScoreSourceId": str(score.get("sourceId") or score_config.get("sourceId") or ""),
        "sourceScoreTitle": str(score.get("title") or target.get("work") or ""),
        "sourceScoreCandidateGlyphCount": int(candidate_audit.get("scoreMapCandidateGlyphCount") or 0),
        "sourceScoreCandidateStaffCount": int(candidate_audit.get("scoreMapCandidateStaffCount") or 0),
        "sourceScoreNoteHypothesisCount": int(candidate_audit.get("scoreMapNoteHypothesisCount") or 0),
        "sourceScoreNoteHypothesisStaffCount": int(candidate_audit.get("scoreMapNoteHypothesisStaffCount") or 0),
        "sourceScoreReviewPacketCount": int(candidate_audit.get("scoreMapReviewPacketCount") or 0),
        "sourceScoreCandidateStatus": str(candidate_audit.get("status") or ""),
        "sourceScoreQueryPitchClassSequence": " ".join(query_values),
        "sourceScoreQueryExactSequence": " ".join(query_exact_values),
        "sourceScoreQueryMidiSequence": " ".join(str(value) for value in query_midi_values),
        "sourceScoreReferencePitchClassSequence": " ".join(source_pitch_values),
        "sourceScoreReferenceSequence": " ".join(source_exact_values),
        "sourceScoreReferenceMidiSequence": " ".join(str(value) for value in source_midi_values),
        "sourceScoreBestOverlapSequence": " ".join(source_exact_values[reference_start:reference_end]),
        "sourceScoreBestOverlapMidiSequence": " ".join(str(value) for value in source_midi_values[reference_start:reference_end]),
        "sourceScorePitchClassBestOverlap": pitch_overlap_length,
        "sourceScorePitchClassBestOverlapSequence": " ".join(
            source_pitch_values[
                int(pitch_overlap.get("referenceStart") or 0) :
                int(pitch_overlap.get("referenceStart") or 0) + pitch_overlap_length
            ]
        ),
        "sourceScoreLimit": (
            "Exact detected MIDI sequence exists in the verified symbolic score map; crop coordinates still need review before accepted display."
            if verified
            else "Checked against the current verified symbolic score map by exact MIDI; this sequence is not present, so it remains reference-audio only and not accepted score evidence until the source MusicXML is extended or the transcription changes."
            if audio_agreed
            else "Detected notes did not all pass the audio-agreement gate, so this remains search data and not accepted score evidence."
        ),
    }


def source_verification_targets(daily_records: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    candidates: dict[tuple[str, str, str, int, int, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = candidate_match_groups_for_record(record)
        for match in groups:
            if not source_verification_target_match(match):
                continue
            score = match.get("score") if isinstance(match.get("score"), dict) else {}
            transcription = match.get("transcription") if isinstance(match.get("transcription"), dict) else {}
            detected = match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}
            clip = match.get("clip") if isinstance(match.get("clip"), dict) else {}
            sequence = match_detected_pitch_sequence(match)
            score_asset_id = str(score.get("assetId") or score.get("scoreAssetId") or "")
            score_check = source_target_score_check(match, sequence)
            key = (
                practice_day,
                str(transcription.get("sampleId") or detected.get("sampleId") or ""),
                score_asset_id or str(match.get("pieceTitle") or ""),
                int(match.get("referenceStart") or 0),
                int(match.get("referenceEnd") or 0),
                sequence,
            )
            candidates[key] = {
                "practiceDay": practice_day,
                "sequence": sequence,
                "exactSequence": match_detected_exact_sequence(match),
                "midiSequence": " ".join(str(value) for value in match_detected_midi_values(match)),
                "sequenceNoteCount": len(sequence.split()),
                "matchedNoteRun": int(match.get("matchedNoteRun") or 0),
                "distinctPitchClasses": match_distinct_pitch_class_count(match),
                "pieceTitle": str(match.get("pieceTitle") or ""),
                "scoreSequenceLabel": str(match.get("scoreSequenceLabel") or ""),
                "scoreAssetId": score_asset_id,
                "clipSampleId": str(transcription.get("sampleId") or detected.get("sampleId") or ""),
                "clipStartSeconds": clip.get("startSeconds"),
                "clipEndSeconds": clip.get("endSeconds"),
                "referenceStart": int(match.get("referenceStart") or 0),
                "referenceEnd": int(match.get("referenceEnd") or 0),
                "status": "source_verification_required",
                "limit": score_check.get("sourceScoreLimit")
                or "Reference-audio phrase target only; not accepted score evidence until local score notes and coordinates are verified.",
                **score_check,
            }
    sorted_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            -int(item.get("sequenceNoteCount") or 0),
            -int(item.get("matchedNoteRun") or 0),
            -int(item.get("distinctPitchClasses") or 0),
            str(item.get("practiceDay") or ""),
            str(item.get("sequence") or ""),
        ),
    )
    return sorted_candidates[: max(0, int(limit))]


def source_verification_target_count(daily_records: dict[str, Any]) -> int:
    return len(source_verification_targets(daily_records, limit=1000))


def source_verification_target_top(daily_records: dict[str, Any]) -> dict[str, Any]:
    targets = source_verification_targets(daily_records, limit=1)
    return targets[0] if targets else {}


def note_midi_values(notes: list[dict[str, Any]]) -> list[int]:
    values: list[int] = []
    for note in notes:
        value = note_midi_value(note)
        if value is None:
            return []
        values.append(value)
    return values


def note_exact_label(notes: list[dict[str, Any]]) -> str:
    return " ".join(str(note.get("note") or "").strip() for note in notes if str(note.get("note") or "").strip())


def source_snippet_for_range(target: dict[str, Any], reference_start: int, reference_end: int) -> dict[str, Any]:
    score = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    snippets = score.get("sourceSnippets") if isinstance(score.get("sourceSnippets"), list) else []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        if int(snippet.get("referenceStart") or -1) == reference_start and int(snippet.get("referenceEnd") or -1) == reference_end:
            return snippet
    return {}


def exact_source_range_visually_verified(snippet: dict[str, Any]) -> bool:
    return bool(
        isinstance(snippet, dict)
        and str(snippet.get("imageUrl") or "").strip()
        and snippet.get("visualRangeAgreement") is True
        and snippet.get("visibleScoreNoteSequenceVerified") is True
        and snippet.get("visibleScoreExactNoteSequenceVerified") is True
        and snippet.get("scoreBoxCenterAgreement") is True
    )


def expansion_audio_run_identity(run: dict[str, Any]) -> tuple[str, str, float, float, tuple[int, ...]]:
    notes = run.get("notes") if isinstance(run.get("notes"), list) else []
    midi = tuple(note_midi_values([note for note in notes if isinstance(note, dict)]))
    return (
        str(run.get("practiceDay") or ""),
        str(run.get("sampleId") or ""),
        float(run.get("localStartSeconds") or run.get("startSeconds") or 0),
        float(run.get("localEndSeconds") or run.get("endSeconds") or 0),
        midi,
    )


def expansion_audio_run_from_notes(
    *,
    practice_day: str,
    sample_id: str,
    source_window: str,
    source_title: str,
    notes: list[dict[str, Any]],
    candidate_only: bool = False,
    run_source: str,
) -> dict[str, Any]:
    clean_notes = [note for note in notes if isinstance(note, dict) and note_midi_value(note) is not None]
    clean_notes = sorted(clean_notes, key=lambda note: (float(note.get("startSeconds") or 0), float(note.get("endSeconds") or 0)))
    midi = note_midi_values(clean_notes)
    start = float(clean_notes[0].get("startSeconds") or 0) if clean_notes else 0.0
    end = float(clean_notes[-1].get("endSeconds") or start) if clean_notes else start
    return {
        "practiceDay": practice_day,
        "sampleId": sample_id,
        "sourceWindow": source_window,
        "sourceTitle": source_title,
        "candidateOnly": candidate_only,
        "runSource": run_source,
        "notes": clean_notes,
        "midiSequence": midi,
        "exactSequence": note_exact_label(clean_notes),
        "startSeconds": round(start, 3),
        "endSeconds": round(end, 3),
        "localStartSeconds": round(start, 3),
        "localEndSeconds": round(end, 3),
    }


def media_sample_for_id(media_samples: list[dict[str, Any]], sample_id: str) -> dict[str, Any]:
    for sample in media_samples:
        if isinstance(sample, dict) and str(sample.get("id") or "") == str(sample_id or ""):
            return sample
    return {}


def seconds_pair_from_url(value: str) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    start_match = re.search(r"(?:[?&#]|^)start=([0-9]+(?:\.[0-9]+)?)", value)
    end_match = re.search(r"(?:[?&#]|^)end=([0-9]+(?:\.[0-9]+)?)", value)
    try:
        start = float(start_match.group(1)) if start_match else None
    except (TypeError, ValueError):
        start = None
    try:
        end = float(end_match.group(1)) if end_match else None
    except (TypeError, ValueError):
        end = None
    return start, end


def staff4_anchor_audio_bounds(match: dict[str, Any]) -> tuple[float, float]:
    clip = match.get("clip") if isinstance(match.get("clip"), dict) else {}
    for key in ("audioUrl", "videoUrl", "mediaUrl", "localAudioUrl", "localVideoUrl"):
        start, end = seconds_pair_from_url(str(clip.get(key) or ""))
        if start is not None and end is not None and end > start:
            return start, end
    start = clip.get("localStartSeconds")
    end = clip.get("localEndSeconds")
    try:
        if start is not None and end is not None and float(end) > float(start):
            return float(start), float(end)
    except (TypeError, ValueError):
        pass
    notes = match_detected_note_events(match)
    starts = [float(note.get("startSeconds") or 0.0) for note in notes if isinstance(note, dict)]
    ends = [
        float(note.get("endSeconds") or note.get("startSeconds") or 0.0)
        for note in notes
        if isinstance(note, dict)
    ]
    if starts and ends:
        return min(starts), max(ends)
    return 0.0, 2.0


def staff4_truth_anchor_source() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    target = wieniawski_reference_target()
    score = symbolic_score_from_target(target)
    source_notes = score.get("notes") if isinstance(score.get("notes"), list) else []
    return target, score, source_notes


def staff4_anchor_audio_window_from_runs(
    daily_records: dict[str, Any],
    *,
    sample_id: str,
    source_window: str,
    midi_sequence: list[int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not sample_id or not midi_sequence:
        return {}, []
    for run in detected_audio_runs_for_expansion(daily_records):
        if str(run.get("sampleId") or "") != sample_id:
            continue
        if source_window and str(run.get("sourceWindow") or "") != source_window:
            continue
        notes = run.get("notes") if isinstance(run.get("notes"), list) else []
        run_midi = note_midi_values([note for note in notes if isinstance(note, dict)])
        if len(run_midi) < len(midi_sequence):
            continue
        for start in range(0, len(run_midi) - len(midi_sequence) + 1):
            end = start + len(midi_sequence)
            if run_midi[start:end] == midi_sequence:
                return run, notes[start:end]
    return {}, []


def staff4_truth_anchor_matches(daily_records: dict[str, Any]) -> list[dict[str, Any]]:
    truth = load_long_phrase_truth()
    phrases = truth.get("positiveSourcePhrases") if isinstance(truth.get("positiveSourcePhrases"), list) else []
    sources = truth.get("sources") if isinstance(truth.get("sources"), list) else []
    sources_by_id = {str(item.get("id") or ""): item for item in sources if isinstance(item, dict)}
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    record_days = {
        str(record.get("practiceDay") or record.get("date") or "")
        for record in records
        if isinstance(record, dict)
    }
    target, score, source_notes = staff4_truth_anchor_source()
    anchors: list[dict[str, Any]] = []
    for phrase in phrases:
        if not isinstance(phrase, dict):
            continue
        if phrase.get("liveAccepted") is not True and str(phrase.get("status") or "") != "accepted_truth":
            continue
        midi_sequence = [int(value) for value in phrase.get("midiSequence") or [] if isinstance(value, int)]
        if midi_sequence != STAFF4_ACCEPTED_ANCHOR_MIDI:
            continue
        source = sources_by_id.get(str(phrase.get("sourceId") or ""))
        if not isinstance(source, dict):
            continue
        practice_day = str(phrase.get("practiceDay") or "")
        if record_days and practice_day and practice_day not in record_days:
            continue
        reference_start = int(source.get("referenceStart") or 0)
        reference_end = int(source.get("referenceEnd") or reference_start)
        anchor_slice = source_notes[reference_start:reference_end] if source_notes else []
        if note_midi_values(anchor_slice) != STAFF4_ACCEPTED_ANCHOR_MIDI:
            continue
        sample_id = str(phrase.get("sampleId") or "")
        source_window = str(phrase.get("sourceWindow") or "")
        run, window_notes = staff4_anchor_audio_window_from_runs(
            daily_records,
            sample_id=sample_id,
            source_window=source_window,
            midi_sequence=STAFF4_ACCEPTED_ANCHOR_MIDI,
        )
        local_start = phrase.get("localStartSeconds")
        local_end = phrase.get("localEndSeconds")
        if window_notes:
            local_start = window_notes[0].get("startSeconds")
            local_end = window_notes[-1].get("endSeconds") or window_notes[-1].get("startSeconds")
        try:
            local_start = float(local_start) if local_start is not None else 0.0
        except (TypeError, ValueError):
            local_start = 0.0
        try:
            local_end = float(local_end) if local_end is not None and float(local_end) > local_start else local_start + 2.0
        except (TypeError, ValueError):
            local_end = local_start + 2.0
        match = {
            "status": "truth_manifest_staff4_anchor",
            "pieceTitle": str(source.get("pieceTitle") or phrase.get("pieceTitle") or score.get("title") or ""),
            "referenceStart": reference_start,
            "referenceEnd": reference_end,
            "detectedSeries": {
                "sampleId": sample_id,
                "sourceWindow": source_window,
                "notes": window_notes,
            },
            "clip": {
                "sampleId": sample_id,
                "sourceWindow": source_window,
                "localStartSeconds": round(local_start, 3),
                "localEndSeconds": round(local_end, 3),
            },
        }
        anchors.append(
            {
                "practiceDay": practice_day,
                "pieceTitle": str(source.get("pieceTitle") or phrase.get("pieceTitle") or score.get("title") or ""),
                "match": match,
                "target": target,
                "score": score,
                "sourceNotes": source_notes,
                "referenceStart": reference_start,
                "referenceEnd": reference_end,
                "anchorSequence": note_exact_label(anchor_slice),
                "anchorMidiSequence": STAFF4_ACCEPTED_ANCHOR_MIDI,
                "sampleId": sample_id,
                "sourceWindow": source_window,
                "anchorLocalStartSeconds": round(local_start, 3),
                "anchorLocalEndSeconds": round(local_end, 3),
                "anchorSource": "truth_manifest",
                "audioRunSource": str(run.get("runSource") or "") if run else "",
            }
        )
    return anchors


def staff4_anchor_matches(daily_records: dict[str, Any]) -> list[dict[str, Any]]:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    anchors: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
        for match in groups:
            if not accepted_long_phrase_match(match):
                continue
            target = source_reference_target_for_match(match)
            score = symbolic_score_from_target(target) if target else {}
            source_notes = score.get("notes") if isinstance(score.get("notes"), list) else []
            if not source_notes:
                continue
            piece_title = str(match.get("pieceTitle") or score.get("title") or "")
            if "wieniawski" not in piece_title.lower():
                continue
            reference_start = int(match.get("referenceStart") or 0)
            reference_end = int(match.get("referenceEnd") or reference_start)
            anchor_slice = source_notes[reference_start:reference_end]
            anchor_midi = note_midi_values(anchor_slice)
            if anchor_midi != STAFF4_ACCEPTED_ANCHOR_MIDI:
                continue
            detected = match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}
            clip = match.get("clip") if isinstance(match.get("clip"), dict) else {}
            local_start, local_end = staff4_anchor_audio_bounds(match)
            anchors.append(
                {
                    "practiceDay": practice_day,
                    "pieceTitle": piece_title,
                    "match": match,
                    "target": target,
                    "score": score,
                    "sourceNotes": source_notes,
                    "referenceStart": reference_start,
                    "referenceEnd": reference_end,
                    "anchorSequence": note_exact_label(anchor_slice),
                    "anchorMidiSequence": anchor_midi,
                    "sampleId": str(detected.get("sampleId") or clip.get("sampleId") or ""),
                    "sourceWindow": str(detected.get("sourceWindow") or clip.get("sourceWindow") or ""),
                    "anchorLocalStartSeconds": round(local_start, 3),
                    "anchorLocalEndSeconds": round(local_end, 3),
                }
            )
    seen = {
        (
            str(anchor.get("practiceDay") or ""),
            str(anchor.get("sampleId") or ""),
            str(anchor.get("sourceWindow") or ""),
            int(anchor.get("referenceStart") or 0),
            int(anchor.get("referenceEnd") or 0),
            tuple(anchor.get("anchorMidiSequence") or []),
        )
        for anchor in anchors
    }
    source_seen = {
        (
            str(anchor.get("practiceDay") or ""),
            int(anchor.get("referenceStart") or 0),
            int(anchor.get("referenceEnd") or 0),
            tuple(anchor.get("anchorMidiSequence") or []),
        )
        for anchor in anchors
    }
    for anchor in staff4_truth_anchor_matches(daily_records):
        identity = (
            str(anchor.get("practiceDay") or ""),
            str(anchor.get("sampleId") or ""),
            str(anchor.get("sourceWindow") or ""),
            int(anchor.get("referenceStart") or 0),
            int(anchor.get("referenceEnd") or 0),
            tuple(anchor.get("anchorMidiSequence") or []),
        )
        source_identity = (
            str(anchor.get("practiceDay") or ""),
            int(anchor.get("referenceStart") or 0),
            int(anchor.get("referenceEnd") or 0),
            tuple(anchor.get("anchorMidiSequence") or []),
        )
        if identity in seen or source_identity in source_seen:
            continue
        seen.add(identity)
        source_seen.add(source_identity)
        anchors.append(anchor)
    return anchors


def staff4_rescan_id(sample_id: str, source_path: Path, scan_start: float, scan_end: float, scan_label: str = "") -> str:
    try:
        stat = source_path.stat()
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = "missing"
    raw = "|".join(
        [
            STAFF4_SOURCE_AUDIO_RESCAN_VERSION,
            sample_id,
            scan_label,
            str(source_path),
            f"{scan_start:.3f}",
            f"{scan_end:.3f}",
            stamp,
            TRANSCRIPTION_PIPELINE_VERSION,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def shifted_rescan_notes(notes: list[dict[str, Any]], scan_start: float, *, detector_source: str) -> list[dict[str, Any]]:
    shifted: list[dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict) or note_midi_value(note) is None:
            continue
        item = dict(note)
        local_start = float(item.get("startSeconds") or 0.0)
        local_end = float(item.get("endSeconds") or local_start)
        item["startSeconds"] = round(scan_start + local_start, 3)
        item["endSeconds"] = round(scan_start + local_end, 3)
        item["durationSeconds"] = round(max(0.0, local_end - local_start), 3)
        item["detectorSource"] = str(item.get("detectorSource") or detector_source)
        item["sourceAudioRescan"] = True
        shifted.append(item)
    return shifted


def staff4_anchor_seed_note_windows(anchor: dict[str, Any]) -> list[dict[str, Any]]:
    anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
    if not anchor_midi:
        return []
    match = anchor.get("match") if isinstance(anchor.get("match"), dict) else {}
    notes = [note for note in match_detected_note_events(match) if isinstance(note, dict) and note_midi_value(note) is not None]
    if len(notes) < len(anchor_midi):
        return []
    midi_values = note_midi_values(notes)
    if not midi_values:
        return []
    anchor_start = float(anchor.get("anchorLocalStartSeconds") or 0.0)
    best: tuple[float, list[dict[str, Any]]] | None = None
    for index in range(0, len(midi_values) - len(anchor_midi) + 1):
        end = index + len(anchor_midi)
        if midi_values[index:end] != anchor_midi:
            continue
        window = notes[index:end]
        distance = abs(float(window[0].get("startSeconds") or 0.0) - anchor_start)
        if best is None or distance < best[0]:
            best = (distance, window)
    return [dict(note) for note in best[1]] if best else []


def staff4_detector_votes_for_segment(segment: Any, expected_midi: int, sr: int, librosa: Any, numpy: Any) -> list[dict[str, Any]]:
    votes: list[dict[str, Any]] = []
    if getattr(segment, "size", 0) <= 0:
        return votes
    try:
        f0, voiced_flag, voiced_prob = librosa.pyin(
            segment,
            fmin=librosa.midi_to_hz(55),
            fmax=librosa.midi_to_hz(108),
            sr=sr,
            frame_length=1024,
            hop_length=128,
        )
        midi_values: list[int] = []
        probabilities: list[float] = []
        for frequency, voiced, probability in zip(f0, voiced_flag, voiced_prob):
            try:
                probability_value = float(probability)
                frequency_value = float(frequency)
            except (TypeError, ValueError):
                continue
            if not voiced or probability_value < 0.15 or frequency_value <= 0 or numpy.isnan(frequency_value):
                continue
            midi_values.append(midi_from_hz(frequency_value))
            probabilities.append(probability_value)
        if midi_values:
            midi = int(round(float(numpy.median(numpy.array(midi_values)))))
            votes.append(
                {
                    "detector": "pyin",
                    "midi": midi,
                    "note": note_name(midi),
                    "confidence": round(sum(probabilities) / max(1, len(probabilities)), 3),
                    "exact": midi == expected_midi,
                    "frameCount": len(midi_values),
                }
            )
    except Exception:
        pass
    try:
        yin = librosa.yin(
            segment,
            fmin=librosa.midi_to_hz(55),
            fmax=librosa.midi_to_hz(108),
            sr=sr,
            frame_length=1024,
            hop_length=128,
        )
        midi_values = []
        for frequency in yin:
            try:
                frequency_value = float(frequency)
            except (TypeError, ValueError):
                continue
            if frequency_value <= 0 or numpy.isnan(frequency_value):
                continue
            midi = midi_from_hz(frequency_value)
            if 55 <= midi <= 108:
                midi_values.append(midi)
        if midi_values:
            midi = int(round(float(numpy.median(numpy.array(midi_values)))))
            votes.append(
                {
                    "detector": "yin",
                    "midi": midi,
                    "note": note_name(midi),
                    "confidence": 1.0,
                    "exact": midi == expected_midi,
                    "frameCount": len(midi_values),
                }
            )
    except Exception:
        pass
    try:
        spectral = spectral_pitch_for_segment(segment, sr, librosa, numpy)
    except Exception:
        spectral = None
    if isinstance(spectral, dict):
        midi = int(spectral.get("midi") or -1)
        if 55 <= midi <= 108:
            votes.append(
                {
                    "detector": "spectral_onset",
                    "midi": midi,
                    "note": note_name(midi),
                    "confidence": round(float(spectral.get("confidence") or 0.0), 3),
                    "spectralRelativeScore": spectral.get("spectralRelativeScore"),
                    "exact": midi == expected_midi,
                    "frameCount": 1,
                }
            )
    return votes


def staff4_anchor_guided_reproduction_notes(
    anchor: dict[str, Any],
    y: Any,
    sr: int,
    scan_start: float,
    scan_end: float,
    librosa: Any,
    numpy: Any,
) -> list[dict[str, Any]]:
    seed_windows = staff4_anchor_seed_note_windows(anchor)
    anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
    if not seed_windows or len(seed_windows) != len(anchor_midi):
        return []
    notes: list[dict[str, Any]] = []
    for seed, expected_midi in zip(seed_windows, anchor_midi):
        start = float(seed.get("startSeconds") or 0.0)
        end = float(seed.get("endSeconds") or start)
        if end <= start or start < scan_start or end > scan_end:
            return []
        padded_start = max(scan_start, start - STAFF4_ANCHOR_GUIDED_PAD_SECONDS)
        padded_end = min(scan_end, end + STAFF4_ANCHOR_GUIDED_PAD_SECONDS)
        start_sample = max(0, int(round((padded_start - scan_start) * sr)))
        end_sample = min(len(y), int(round((padded_end - scan_start) * sr)))
        if end_sample <= start_sample:
            return []
        segment = y[start_sample:end_sample]
        votes = staff4_detector_votes_for_segment(segment, expected_midi, sr, librosa, numpy)
        exact_votes = [vote for vote in votes if vote.get("exact")]
        exact_sources = [str(vote.get("detector") or "") for vote in exact_votes if str(vote.get("detector") or "")]
        if len(exact_sources) < STAFF4_ANCHOR_GUIDED_MIN_EXACT_VOTES or "spectral_onset" not in exact_sources:
            return []
        confidence = max([float(vote.get("confidence") or 0.0) for vote in exact_votes] + [0.86])
        notes.append(
            {
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
                "durationSeconds": round(max(0.0, end - start), 3),
                "midi": expected_midi,
                "note": note_name(expected_midi),
                "confidence": round(min(0.99, confidence), 3),
                "audioAgreement": True,
                "agreementSources": sorted(set(exact_sources)),
                "agreementSourceCount": len(set(exact_sources)),
                "detectorSource": "staff4_anchor_guided_current_detector",
                "verification": "current_audio_pyin_yin_spectral_exact_midi_anchor_reproduction",
                "sourceAudioRescan": True,
                "anchorGuidedReproduction": True,
                "detectorVotes": votes,
            }
        )
    return notes


def staff4_adjacent_source_targets(anchor: dict[str, Any]) -> list[dict[str, Any]]:
    source_notes = anchor.get("sourceNotes") if isinstance(anchor.get("sourceNotes"), list) else []
    if not source_notes:
        return []
    reference_start = int(anchor.get("referenceStart") or 0)
    reference_end = int(anchor.get("referenceEnd") or reference_start)
    anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
    anchor_slice = source_notes[reference_start:reference_end]
    if not anchor_midi:
        anchor_midi = note_midi_values(anchor_slice)
    if anchor_midi != STAFF4_ACCEPTED_ANCHOR_MIDI:
        return []
    targets: list[dict[str, Any]] = []
    max_end = min(len(source_notes), reference_start + STAFF4_ADJACENT_GUIDED_MAX_TARGET_NOTES)
    if reference_end < max_end:
        targets.append({"direction": "right-1", "start": reference_start, "end": reference_end + 1})
    if reference_end + 1 < max_end:
        targets.append({"direction": "right-2", "start": reference_start, "end": reference_end + 2})
    for target in targets:
        source_slice = source_notes[int(target["start"]) : int(target["end"])]
        target["sourceSlice"] = source_slice
        target["targetMidiSequence"] = note_midi_values(source_slice)
        target["targetSequence"] = note_exact_label(source_slice)
        target["anchorMidiSequence"] = anchor_midi
    return [target for target in targets if target.get("targetMidiSequence")]


def median_float(values: list[float], fallback: float) -> float:
    cleaned = sorted(value for value in values if value > 0)
    if not cleaned:
        return fallback
    middle = len(cleaned) // 2
    if len(cleaned) % 2:
        return cleaned[middle]
    return (cleaned[middle - 1] + cleaned[middle]) / 2.0


def staff4_adjacent_guided_note_windows(anchor: dict[str, Any], target_midi: list[int]) -> list[dict[str, Any]]:
    seed_windows = staff4_anchor_seed_note_windows(anchor)
    anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
    if not seed_windows or not anchor_midi or target_midi[: len(anchor_midi)] != anchor_midi:
        return []
    if len(target_midi) < len(anchor_midi):
        return []
    durations = [
        float(seed.get("endSeconds") or seed.get("startSeconds") or 0.0) - float(seed.get("startSeconds") or 0.0)
        for seed in seed_windows
    ]
    starts = [float(seed.get("startSeconds") or 0.0) for seed in seed_windows]
    onset_deltas = [starts[index + 1] - starts[index] for index in range(0, len(starts) - 1)]
    duration = min(0.45, max(0.06, median_float(durations, 0.12)))
    onset_delta = min(0.75, max(duration * 0.75, median_float(onset_deltas, duration)))
    windows = [dict(seed) for seed in seed_windows]
    last_start = starts[-1]
    last_end = float(seed_windows[-1].get("endSeconds") or last_start + duration)
    for index in range(len(seed_windows), len(target_midi)):
        next_start = last_start + onset_delta
        if next_start <= last_end:
            next_start = last_end + max(0.01, onset_delta - duration)
        next_end = next_start + duration
        windows.append(
            {
                "startSeconds": round(next_start, 3),
                "endSeconds": round(next_end, 3),
                "durationSeconds": round(duration, 3),
                "inferredAdjacentWindow": True,
                "timingSource": "accepted_staff4_anchor_median_onset_delta",
            }
        )
        last_start = next_start
        last_end = next_end
    return windows


def staff4_guided_detector_note_from_window(
    *,
    y: Any,
    sr: int,
    scan_start: float,
    scan_end: float,
    librosa: Any,
    numpy: Any,
    window: dict[str, Any],
    expected_midi: int,
    note_index: int,
    allow_sweep: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_start = float(window.get("startSeconds") or 0.0)
    base_end = float(window.get("endSeconds") or base_start)
    if base_end <= base_start:
        return {}, {
            "noteIndex": note_index,
            "expectedMidi": expected_midi,
            "expectedNote": note_name(expected_midi),
            "reason": "empty_seed_window",
        }
    duration = base_end - base_start
    offsets = STAFF4_ADJACENT_GUIDED_SWEEP_OFFSETS_SECONDS if allow_sweep else (0.0,)
    attempts: list[dict[str, Any]] = []
    for offset in offsets:
        start = base_start + float(offset)
        end = start + duration
        if start < scan_start or end > scan_end:
            attempts.append(
                {
                    "offsetSeconds": round(float(offset), 3),
                    "startSeconds": round(start, 3),
                    "endSeconds": round(end, 3),
                    "reason": "outside_scan",
                }
            )
            continue
        padded_start = max(scan_start, start - STAFF4_ANCHOR_GUIDED_PAD_SECONDS)
        padded_end = min(scan_end, end + STAFF4_ANCHOR_GUIDED_PAD_SECONDS)
        start_sample = max(0, int(round((padded_start - scan_start) * sr)))
        end_sample = min(len(y), int(round((padded_end - scan_start) * sr)))
        if end_sample <= start_sample:
            attempts.append(
                {
                    "offsetSeconds": round(float(offset), 3),
                    "startSeconds": round(start, 3),
                    "endSeconds": round(end, 3),
                    "reason": "empty_seed_audio",
                }
            )
            continue
        segment = y[start_sample:end_sample]
        votes = staff4_detector_votes_for_segment(segment, expected_midi, sr, librosa, numpy)
        exact_votes = [vote for vote in votes if vote.get("exact")]
        exact_sources = [str(vote.get("detector") or "") for vote in exact_votes if str(vote.get("detector") or "")]
        attempts.append(
            {
                "offsetSeconds": round(float(offset), 3),
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
                "exactSourceCount": len(set(exact_sources)),
                "exactSources": sorted(set(exact_sources)),
                "detectorVotes": votes,
            }
        )
        if len(exact_sources) < STAFF4_ANCHOR_GUIDED_MIN_EXACT_VOTES or "spectral_onset" not in exact_sources:
            continue
        confidence = max([float(vote.get("confidence") or 0.0) for vote in exact_votes] + [0.86])
        return {
            "startSeconds": round(start, 3),
            "endSeconds": round(end, 3),
            "durationSeconds": round(max(0.0, end - start), 3),
            "midi": expected_midi,
            "note": note_name(expected_midi),
            "confidence": round(min(0.99, confidence), 3),
            "audioAgreement": True,
            "agreementSources": sorted(set(exact_sources)),
            "agreementSourceCount": len(set(exact_sources)),
            "detectorSource": "staff4_adjacent_guided_current_detector",
            "verification": "current_audio_pyin_yin_spectral_exact_midi_adjacent_reproduction",
            "sourceAudioRescan": True,
            "adjacentGuidedReproduction": True,
            "timingOffsetSeconds": round(float(offset), 3),
            "timingSweepUsed": bool(allow_sweep and abs(float(offset)) > 0.0001),
            "detectorVotes": votes,
            "detectorAttempts": attempts,
        }, {}
    best_attempt = max(
        attempts,
        key=lambda item: (int(item.get("exactSourceCount") or 0), -abs(float(item.get("offsetSeconds") or 0.0))),
        default={},
    )
    return {}, {
        "noteIndex": note_index,
        "expectedMidi": expected_midi,
        "expectedNote": note_name(expected_midi),
        "reason": "current_detectors_did_not_reproduce_exact_midi",
        "detectorAttempts": attempts,
        "bestAttempt": best_attempt,
    }


def staff4_adjacent_guided_reproduction_targets(
    anchor: dict[str, Any],
    y: Any,
    sr: int,
    scan_start: float,
    scan_end: float,
    librosa: Any,
    numpy: Any,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target in staff4_adjacent_source_targets(anchor):
        target_midi = [int(value) for value in target.get("targetMidiSequence") or [] if isinstance(value, int)]
        windows = staff4_adjacent_guided_note_windows(anchor, target_midi)
        notes: list[dict[str, Any]] = []
        failed: dict[str, Any] = {}
        for note_index, (window, expected_midi) in enumerate(zip(windows, target_midi)):
            note_result, failure = staff4_guided_detector_note_from_window(
                y=y,
                sr=sr,
                scan_start=scan_start,
                scan_end=scan_end,
                librosa=librosa,
                numpy=numpy,
                window=window,
                expected_midi=expected_midi,
                note_index=note_index,
                allow_sweep=bool(window.get("inferredAdjacentWindow")),
            )
            if failure:
                failed = failure
                break
            note_result["targetDirection"] = str(target.get("direction") or "")
            notes.append(note_result)
        status = "reproduced" if len(notes) == len(target_midi) and not failed else "not_reproduced"
        results.append(
            {
                "status": status,
                "direction": str(target.get("direction") or ""),
                "targetReferenceStart": int(target.get("start") or 0),
                "targetReferenceEnd": int(target.get("end") or 0),
                "targetSequence": str(target.get("targetSequence") or ""),
                "targetMidiSequence": target_midi,
                "targetNoteCount": len(target_midi),
                "reproducedNoteCount": len(notes),
                "notes": notes if status == "reproduced" else [],
                "failedAt": failed,
                "seedWindows": [
                    {
                        "startSeconds": round(float(window.get("startSeconds") or 0.0), 3),
                        "endSeconds": round(float(window.get("endSeconds") or 0.0), 3),
                        "inferredAdjacentWindow": bool(window.get("inferredAdjacentWindow")),
                    }
                    for window in windows
                ],
            }
        )
    return results


def compact_staff4_adjacent_failure(target: dict[str, Any]) -> dict[str, Any]:
    failed = target.get("failedAt") if isinstance(target.get("failedAt"), dict) else {}
    if not failed:
        return {}
    best_attempt = failed.get("bestAttempt") if isinstance(failed.get("bestAttempt"), dict) else {}
    detector_attempts = failed.get("detectorAttempts") if isinstance(failed.get("detectorAttempts"), list) else []
    best_votes = best_attempt.get("detectorVotes") if isinstance(best_attempt.get("detectorVotes"), list) else []
    expected_midi = int(failed.get("expectedMidi") or 0)
    observed_midi_values = [
        int(vote.get("midi"))
        for vote in best_votes
        if isinstance(vote, dict) and isinstance(vote.get("midi"), int)
    ]
    observed_notes = [
        str(vote.get("note") or note_name(int(vote.get("midi"))))
        for vote in best_votes
        if isinstance(vote, dict) and isinstance(vote.get("midi"), int)
    ]
    observed_counts = {
        midi: observed_midi_values.count(midi)
        for midi in sorted(set(observed_midi_values))
    }
    observed_consensus_midi = (
        max(observed_counts, key=lambda midi: (observed_counts[midi], -abs(midi - expected_midi)))
        if observed_counts
        else 0
    )
    exact_source_count = int(best_attempt.get("exactSourceCount") or 0)
    if not best_votes:
        failure_kind = str(best_attempt.get("reason") or "no_detector_votes")
    elif observed_consensus_midi and observed_consensus_midi != expected_midi:
        failure_kind = "wrong_midi_detected"
    elif exact_source_count:
        failure_kind = "partial_detector_agreement"
    else:
        failure_kind = "detectors_uncertain"
    return {
        "direction": str(target.get("direction") or ""),
        "targetReferenceStart": int(target.get("targetReferenceStart") or 0),
        "targetReferenceEnd": int(target.get("targetReferenceEnd") or 0),
        "targetSequence": str(target.get("targetSequence") or ""),
        "targetMidiSequence": [
            int(value) for value in target.get("targetMidiSequence") or [] if isinstance(value, int)
        ],
        "targetNoteCount": int(target.get("targetNoteCount") or 0),
        "reproducedNoteCount": int(target.get("reproducedNoteCount") or 0),
        "failedNoteIndex": int(failed.get("noteIndex") or 0),
        "expectedMidi": expected_midi,
        "expectedNote": str(failed.get("expectedNote") or ""),
        "reason": str(failed.get("reason") or ""),
        "failureKind": failure_kind,
        "attemptCount": len(detector_attempts),
        "bestAttemptOffsetSeconds": best_attempt.get("offsetSeconds"),
        "bestAttemptStartSeconds": best_attempt.get("startSeconds"),
        "bestAttemptEndSeconds": best_attempt.get("endSeconds"),
        "bestAttemptExactSourceCount": int(best_attempt.get("exactSourceCount") or 0),
        "bestAttemptExactSources": [
            str(source) for source in best_attempt.get("exactSources") or [] if str(source or "")
        ],
        "bestAttemptObservedMidi": observed_midi_values,
        "bestAttemptObservedNotes": observed_notes,
        "bestAttemptObservedConsensusMidi": observed_consensus_midi,
        "bestAttemptObservedConsensusNote": note_name(observed_consensus_midi) if observed_consensus_midi else "",
        "bestAttemptDetectorVotes": best_votes,
    }


def staff4_first_adjacent_failure(targets: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [
        target
        for target in targets
        if isinstance(target, dict)
        and target.get("status") != "reproduced"
        and isinstance(target.get("failedAt"), dict)
    ]
    if not failures:
        return {}

    def failure_key(target: dict[str, Any]) -> tuple[int, int, int, str]:
        failed = target.get("failedAt") if isinstance(target.get("failedAt"), dict) else {}
        direction = str(target.get("direction") or "")
        direction_rank = 0 if direction == "right-1" else 1 if direction == "right-2" else 2
        return (
            direction_rank,
            int(failed.get("noteIndex") or 999),
            int(target.get("targetNoteCount") or 999),
            direction,
        )

    return compact_staff4_adjacent_failure(sorted(failures, key=failure_key)[0])


def audio_agreed_midi_sequence_exists_in_runs(runs: list[dict[str, Any]], target_midi: list[int]) -> bool:
    if not target_midi:
        return False
    for run in runs:
        notes = run.get("notes") if isinstance(run.get("notes"), list) else []
        midi_values = note_midi_values([note for note in notes if isinstance(note, dict)])
        if len(midi_values) < len(target_midi):
            continue
        for index in range(0, len(midi_values) - len(target_midi) + 1):
            if midi_values[index : index + len(target_midi)] != target_midi:
                continue
            window_notes = [note for note in notes[index : index + len(target_midi)] if isinstance(note, dict)]
            if notes_have_score_match_audio_agreement(window_notes, candidate_only=bool(run.get("candidateOnly"))):
                return True
    return False


def staff4_source_audio_rescan_windows(anchor: dict[str, Any], sample: dict[str, Any]) -> list[dict[str, Any]]:
    anchor_start = float(anchor.get("anchorLocalStartSeconds") or 0.0)
    anchor_end = max(anchor_start + 0.25, float(anchor.get("anchorLocalEndSeconds") or anchor_start + 2.0))
    source_window = str(anchor.get("sourceWindow") or sample.get("window") or "")
    source_window_start, source_window_end = parse_window_bounds(source_window)
    source_duration = float(source_window_end - source_window_start) if source_window_end > source_window_start else 0.0
    window_seconds = float(STAFF4_SOURCE_AUDIO_RESCAN_MAX_SECONDS)
    step_seconds = float(STAFF4_SOURCE_AUDIO_RESCAN_STEP_SECONDS)
    max_windows = max(1, int(STAFF4_SOURCE_AUDIO_RESCAN_MAX_WINDOWS))
    windows: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()

    def add_window(label: str, start: float, end: float) -> bool:
        if source_duration:
            start = min(max(0.0, start), source_duration)
            end = min(max(0.0, end), source_duration)
        else:
            start = max(0.0, start)
            end = max(0.0, end)
        if end - start < 1.0:
            return False
        identity = (round(start, 3), round(end, 3))
        if identity in seen:
            return False
        seen.add(identity)
        windows.append(
            {
                "label": label,
                "scanLocalStartSeconds": round(start, 3),
                "scanLocalEndSeconds": round(end, 3),
                "scanDurationSeconds": round(end - start, 3),
            }
        )
        return True

    core_start = max(0.0, anchor_start - STAFF4_SOURCE_AUDIO_RESCAN_PAD_BEFORE_SECONDS)
    core_end = max(anchor_end + STAFF4_SOURCE_AUDIO_RESCAN_PAD_AFTER_SECONDS, core_start + 2.0)
    if core_end - core_start > window_seconds:
        core_end = core_start + window_seconds
    add_window("anchor_core", core_start, core_end)

    next_start = core_start + step_seconds
    while len(windows) < max_windows:
        if source_duration and next_start >= source_duration - 1.0:
            break
        start = next_start
        if source_duration and start + window_seconds > source_duration:
            start = max(0.0, source_duration - window_seconds)
        if not add_window(f"right_{len(windows)}", start, start + window_seconds):
            break
        if source_duration and windows[-1]["scanLocalEndSeconds"] >= source_duration:
            break
        next_start += step_seconds

    return windows


def staff4_source_audio_rescan_record(
    *,
    anchor: dict[str, Any],
    sample: dict[str, Any],
    source_path: Path,
    scan_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sample_id = str(anchor.get("sampleId") or sample.get("id") or "")
    anchor_start = float(anchor.get("anchorLocalStartSeconds") or 0.0)
    anchor_end = max(anchor_start + 0.25, float(anchor.get("anchorLocalEndSeconds") or anchor_start + 2.0))
    scan_window = scan_window if isinstance(scan_window, dict) else {}
    scan_label = str(scan_window.get("label") or "anchor_core")
    scan_start = float(scan_window.get("scanLocalStartSeconds") or max(0.0, anchor_start - STAFF4_SOURCE_AUDIO_RESCAN_PAD_BEFORE_SECONDS))
    scan_end = float(scan_window.get("scanLocalEndSeconds") or max(anchor_end + STAFF4_SOURCE_AUDIO_RESCAN_PAD_AFTER_SECONDS, scan_start + 2.0))
    if scan_end - scan_start > STAFF4_SOURCE_AUDIO_RESCAN_MAX_SECONDS:
        scan_end = scan_start + STAFF4_SOURCE_AUDIO_RESCAN_MAX_SECONDS
    rescan_id = staff4_rescan_id(sample_id, source_path, scan_start, scan_end, scan_label)
    rescan_dir = STAFF4_SOURCE_AUDIO_RESCAN_DIR / rescan_id
    result_path = rescan_dir / "rescan.json"
    audio_path = rescan_dir / "source-window.wav"
    if result_path.exists():
        try:
            cached = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached.get("version") == STAFF4_SOURCE_AUDIO_RESCAN_VERSION:
                cached["cacheHit"] = True
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    rescan_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "version": STAFF4_SOURCE_AUDIO_RESCAN_VERSION,
        "status": "started",
        "cacheHit": False,
        "practiceDay": anchor.get("practiceDay") or "",
        "pieceTitle": anchor.get("pieceTitle") or "",
        "sampleId": sample_id,
        "sourceWindow": anchor.get("sourceWindow") or sample.get("window") or "",
        "scanLabel": scan_label,
        "anchorSequence": anchor.get("anchorSequence") or "",
        "anchorMidiSequence": anchor.get("anchorMidiSequence") or [],
        "anchorLocalStartSeconds": round(anchor_start, 3),
        "anchorLocalEndSeconds": round(anchor_end, 3),
        "scanLocalStartSeconds": round(scan_start, 3),
        "scanLocalEndSeconds": round(scan_end, 3),
        "scanDurationSeconds": round(scan_end - scan_start, 3),
        "scanWindow": {
            "label": scan_label,
            "scanLocalStartSeconds": round(scan_start, 3),
            "scanLocalEndSeconds": round(scan_end, 3),
            "scanDurationSeconds": round(scan_end - scan_start, 3),
        },
        "runs": [],
        "eventCount": 0,
        "candidateEventCount": 0,
        "audioAgreementEventCount": 0,
        "quality": {},
    }
    ok, output = run_ffmpeg_extract_audio(source_path, audio_path, scan_start, scan_end)
    if not ok:
        result["status"] = "blocked_audio_extract_failed"
        result["limit"] = output[-240:]
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    try:
        import librosa  # type: ignore
        import numpy  # type: ignore
    except Exception as exc:  # pragma: no cover - environment boundary
        result["status"] = "blocked_dependency"
        result["limit"] = str(exc)[:180]
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    try:
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    except Exception as exc:
        result["status"] = "blocked_audio_load"
        result["limit"] = str(exc)[:180]
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result
    if y.size == 0:
        result["status"] = "blocked_empty_audio"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    transcription = transcribe_audio_array(y, sr, librosa, numpy)
    primary_notes = shifted_rescan_notes(
        transcription.get("events") if isinstance(transcription.get("events"), list) else [],
        scan_start,
        detector_source="staff4_source_audio_rescan",
    )
    candidate_notes = shifted_rescan_notes(
        transcription.get("scoreMatchCandidateNotes")
        if isinstance(transcription.get("scoreMatchCandidateNotes"), list)
        else [],
        scan_start,
        detector_source="staff4_source_audio_rescan_candidate",
    )
    runs: list[dict[str, Any]] = []
    guided_notes = staff4_anchor_guided_reproduction_notes(
        anchor,
        y,
        sr,
        scan_start,
        scan_end,
        librosa,
        numpy,
    )
    adjacent_guided_targets = staff4_adjacent_guided_reproduction_targets(
        anchor,
        y,
        sr,
        scan_start,
        scan_end,
        librosa,
        numpy,
    )
    reproduced_adjacent_targets = [
        item
        for item in adjacent_guided_targets
        if isinstance(item, dict) and item.get("status") == "reproduced" and isinstance(item.get("notes"), list)
    ]
    adjacent_first_failure = staff4_first_adjacent_failure(
        [item for item in adjacent_guided_targets if isinstance(item, dict)]
    )
    best_adjacent_target = max(
        reproduced_adjacent_targets,
        key=lambda item: int(item.get("targetNoteCount") or 0),
        default={},
    )
    guided_adjacent_notes = (
        best_adjacent_target.get("notes")
        if isinstance(best_adjacent_target.get("notes"), list)
        else []
    )
    guided_adjacent_midi = [
        int(value)
        for value in best_adjacent_target.get("targetMidiSequence") or []
        if isinstance(value, int)
    ]
    if primary_notes:
        runs.append(
            expansion_audio_run_from_notes(
                practice_day=str(anchor.get("practiceDay") or ""),
                sample_id=sample_id,
                source_window=str(anchor.get("sourceWindow") or sample.get("window") or ""),
                source_title=str(sample.get("title") or anchor.get("pieceTitle") or ""),
                notes=primary_notes,
                candidate_only=False,
                run_source="staff4_source_audio_rescan",
            )
        )
    if candidate_notes:
        runs.append(
            expansion_audio_run_from_notes(
                practice_day=str(anchor.get("practiceDay") or ""),
                sample_id=sample_id,
                source_window=str(anchor.get("sourceWindow") or sample.get("window") or ""),
                source_title=str(sample.get("title") or anchor.get("pieceTitle") or ""),
                notes=candidate_notes,
                candidate_only=True,
                run_source="staff4_source_audio_rescan_candidate",
            )
        )
    if guided_notes and not audio_agreed_midi_sequence_exists_in_runs(runs, [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]):
        runs.append(
            expansion_audio_run_from_notes(
                practice_day=str(anchor.get("practiceDay") or ""),
                sample_id=sample_id,
                source_window=str(anchor.get("sourceWindow") or sample.get("window") or ""),
                source_title=str(sample.get("title") or anchor.get("pieceTitle") or ""),
                notes=guided_notes,
                candidate_only=False,
                run_source="staff4_anchor_guided_current_detector",
            )
        )
    if guided_adjacent_notes and not audio_agreed_midi_sequence_exists_in_runs(runs, guided_adjacent_midi):
        runs.append(
            expansion_audio_run_from_notes(
                practice_day=str(anchor.get("practiceDay") or ""),
                sample_id=sample_id,
                source_window=str(anchor.get("sourceWindow") or sample.get("window") or ""),
                source_title=str(sample.get("title") or anchor.get("pieceTitle") or ""),
                notes=guided_adjacent_notes,
                candidate_only=False,
                run_source="staff4_adjacent_guided_current_detector",
            )
        )
    quality = transcription.get("quality") if isinstance(transcription.get("quality"), dict) else {}
    result.update(
        {
            "status": "rescanned" if runs else "no_notes_detected",
            "eventCount": len(primary_notes),
            "candidateEventCount": len(candidate_notes),
            "guidedAnchorEventCount": len(guided_notes),
            "guidedAdjacentEventCount": len(guided_adjacent_notes),
            "guidedAdjacentTargetCount": len(adjacent_guided_targets),
            "guidedAdjacentReproducedCount": len(reproduced_adjacent_targets),
            "guidedAdjacentStatus": "reproduced" if reproduced_adjacent_targets else "not_reproduced" if adjacent_guided_targets else "not_checked",
            "guidedAdjacentFirstFailure": adjacent_first_failure,
            "guidedAdjacentTargets": [
                {
                    key: value
                    for key, value in item.items()
                    if key != "notes" or item.get("status") == "reproduced"
                }
                for item in adjacent_guided_targets
                if isinstance(item, dict)
            ],
            "audioAgreementEventCount": sum(
                1
                for note in [*primary_notes, *candidate_notes, *guided_notes, *guided_adjacent_notes]
                if note.get("audioAgreement") is True
            ),
            "quality": {
                "segmentationSource": quality.get("segmentationSource") or "",
                "pitchEventCount": int(quality.get("pitchEventCount") or 0),
                "onsetEventCount": int(quality.get("onsetEventCount") or 0),
                "spectralEventCount": int(quality.get("spectralEventCount") or 0),
                "transitionTraceEventCount": int(quality.get("transitionTraceEventCount") or 0),
                "audioAgreementEventCount": int(quality.get("audioAgreementEventCount") or 0),
                "guidedAnchorEventCount": len(guided_notes),
                "guidedAnchorStatus": "reproduced" if guided_notes else "not_reproduced",
                "guidedAdjacentEventCount": len(guided_adjacent_notes),
                "guidedAdjacentStatus": "reproduced" if reproduced_adjacent_targets else "not_reproduced" if adjacent_guided_targets else "not_checked",
                "guidedAdjacentFirstFailureExpectedNote": adjacent_first_failure.get("expectedNote") or "",
            },
            "runs": runs,
        }
    )
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def staff4_source_audio_rescan(daily_records: dict[str, Any], media_samples: list[dict[str, Any]], limit: int = 2) -> dict[str, Any]:
    anchors = staff4_anchor_matches(daily_records)
    if not anchors:
        return {
            "version": STAFF4_SOURCE_AUDIO_RESCAN_VERSION,
            "status": "no_staff4_anchor",
            "anchorCount": 0,
            "records": [],
            "runs": [],
            "nextAction": "Create one accepted Staff 4 source/audio anchor before source-audio rescanning.",
        }
    records: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    anchor_reproduction_targets: list[dict[str, Any]] = []
    blocked = 0
    for anchor in anchors[: max(0, int(limit))]:
        sample_id = str(anchor.get("sampleId") or "")
        sample = media_sample_for_id(media_samples, sample_id)
        source_path = source_media_path(sample) if sample else None
        if not source_path:
            blocked += 1
            records.append(
                {
                    "status": "blocked_media_missing",
                    "practiceDay": anchor.get("practiceDay") or "",
                    "sampleId": sample_id,
                    "anchorSequence": anchor.get("anchorSequence") or "",
                    "limit": "The Staff 4 source sample is not present locally, so Curtis cannot rescan beyond stored note windows.",
                    "runs": [],
                }
            )
            continue
        for scan_window in staff4_source_audio_rescan_windows(anchor, sample):
            record = staff4_source_audio_rescan_record(
                anchor=anchor,
                sample=sample,
                source_path=source_path,
                scan_window=scan_window,
            )
            records.append(record)
            for run in record.get("runs") if isinstance(record.get("runs"), list) else []:
                if isinstance(run, dict):
                    runs.append(run)
        anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
        if anchor_midi:
            anchor_absolute_start = parse_window_start(str(anchor.get("sourceWindow") or "")) + float(anchor.get("anchorLocalStartSeconds") or 0.0)
            reproduction = audio_window_search_for_exact_midi(
                runs,
                anchor_midi,
                practice_day=str(anchor.get("practiceDay") or ""),
                anchor_sample_id=sample_id,
                anchor_absolute_start=anchor_absolute_start,
            )
            exact_candidates = reproduction.get("exactCandidates") if isinstance(reproduction.get("exactCandidates"), list) else []
            exact_audio_candidates = [
                item
                for item in exact_candidates
                if isinstance(item, dict) and item.get("audioAgreed") and item.get("sameSampleAsAnchor")
            ]
            nearest = reproduction.get("nearestWindow") if isinstance(reproduction.get("nearestWindow"), dict) else {}
            anchor_reproduction_targets.append(
                {
                    "practiceDay": str(anchor.get("practiceDay") or ""),
                    "sampleId": sample_id,
                    "sourceWindow": str(anchor.get("sourceWindow") or ""),
                    "anchorSequence": str(anchor.get("anchorSequence") or ""),
                    "anchorMidiSequence": anchor_midi,
                    "searchedWindowCount": int(reproduction.get("searchedWindowCount") or 0),
                    "exactCandidateCount": len(exact_candidates),
                    "exactAudioCandidateCount": len(exact_audio_candidates),
                    "status": "reproduced" if exact_audio_candidates else "not_reproduced",
                    "nearestWindow": nearest,
                }
            )
    status = "rescanned" if runs else "blocked_media_missing" if blocked == len(records) else "no_notes_detected"
    anchor_reproduced_count = sum(1 for item in anchor_reproduction_targets if item.get("status") == "reproduced")
    anchor_reproduction_status = (
        "not_checked"
        if not anchor_reproduction_targets
        else "reproduced"
        if anchor_reproduced_count == len(anchor_reproduction_targets)
        else "not_reproduced"
    )
    adjacent_targets = [
        target
        for record in records
        if isinstance(record, dict)
        for target in (record.get("guidedAdjacentTargets") if isinstance(record.get("guidedAdjacentTargets"), list) else [])
        if isinstance(target, dict)
    ]
    adjacent_reproduced_count = sum(1 for target in adjacent_targets if target.get("status") == "reproduced")
    adjacent_reproduction_status = (
        "not_checked"
        if not adjacent_targets
        else "reproduced"
        if adjacent_reproduced_count
        else "not_reproduced"
    )
    adjacent_first_failure = staff4_first_adjacent_failure(adjacent_targets)
    adjacent_failure_label = str(adjacent_first_failure.get("expectedNote") or "")
    adjacent_failure_offset = adjacent_first_failure.get("bestAttemptOffsetSeconds")
    adjacent_failure_action = (
        "Improve note-window segmentation for the next Staff 4 source note "
        f"{adjacent_failure_label or 'unknown'}; the best swept offset "
        f"{adjacent_failure_offset}s heard "
        f"{adjacent_first_failure.get('bestAttemptObservedConsensusNote') or 'no stable MIDI'}."
    )
    return {
        "version": STAFF4_SOURCE_AUDIO_RESCAN_VERSION,
        "status": status,
        "anchorCount": len(anchors),
        "anchorReproductionStatus": anchor_reproduction_status,
        "anchorReproducedCount": anchor_reproduced_count,
        "anchorReproductionTargetCount": len(anchor_reproduction_targets),
        "anchorReproductionTargets": anchor_reproduction_targets,
        "recordCount": len(records),
        "scanWindowCount": len(records),
        "scanWindowLabels": [
            str(record.get("scanLabel") or "")
            for record in records
            if isinstance(record, dict) and str(record.get("scanLabel") or "")
        ],
        "runCount": len(runs),
        "eventCount": sum(int(record.get("eventCount") or 0) for record in records if isinstance(record, dict)),
        "candidateEventCount": sum(int(record.get("candidateEventCount") or 0) for record in records if isinstance(record, dict)),
        "guidedAnchorEventCount": sum(int(record.get("guidedAnchorEventCount") or 0) for record in records if isinstance(record, dict)),
        "guidedAdjacentEventCount": sum(int(record.get("guidedAdjacentEventCount") or 0) for record in records if isinstance(record, dict)),
        "guidedAdjacentTargetCount": len(adjacent_targets),
        "guidedAdjacentReproducedCount": adjacent_reproduced_count,
        "guidedAdjacentStatus": adjacent_reproduction_status,
        "guidedAdjacentFirstFailure": adjacent_first_failure,
        "guidedAdjacentTargets": adjacent_targets,
        "audioAgreementEventCount": sum(int(record.get("audioAgreementEventCount") or 0) for record in records if isinstance(record, dict)),
        "cacheHitCount": sum(1 for record in records if isinstance(record, dict) and record.get("cacheHit")),
        "records": records,
        "runs": runs,
        "nextAction": (
            "Fix current-detector anchor reproduction before expanding the Staff 4 phrase."
            if anchor_reproduction_targets and not anchor_reproduced_count
            else "Audit the adjacent-guided Staff 4 phrase reproduced by current audio detectors."
            if adjacent_reproduced_count
            else adjacent_failure_action
            if adjacent_first_failure
            else "Improve note-window segmentation for the next Staff 4 source notes; adjacent-guided current detectors did not reproduce the exact source phrase."
            if adjacent_targets
            else "Search exact Staff 4 MIDI phrase windows inside the rescanned source-audio runs."
            if runs
            else "Make the Staff 4 source media available, then rescan the source audio around the accepted anchor."
        ),
    }


def detected_audio_runs_for_expansion(
    daily_records: dict[str, Any],
    extra_audio_runs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    runs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float, float, tuple[int, ...]]] = set()

    def add_run(run: dict[str, Any]) -> None:
        notes = run.get("notes") if isinstance(run.get("notes"), list) else []
        if not notes:
            return
        identity = expansion_audio_run_identity(run)
        if not identity[-1] or identity in seen:
            return
        seen.add(identity)
        runs.append(run)

    for record in records:
        if not isinstance(record, dict):
            continue
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        for group in candidate_match_groups_for_record(record):
            detected = group.get("detectedSeries") if isinstance(group.get("detectedSeries"), dict) else {}
            clip = group.get("clip") if isinstance(group.get("clip"), dict) else {}
            notes = detected.get("notes") if isinstance(detected.get("notes"), list) else []
            if not notes:
                notes = match_detected_note_events(group)
            notes = [note for note in notes if isinstance(note, dict) and note_midi_value(note) is not None]
            if not notes:
                continue
            run = expansion_audio_run_from_notes(
                practice_day=practice_day,
                sample_id=str(detected.get("sampleId") or clip.get("sampleId") or ""),
                source_window=str(detected.get("sourceWindow") or ""),
                source_title=str(detected.get("sourceTitle") or clip.get("sourceTitle") or ""),
                notes=notes,
                candidate_only=bool(detected.get("candidateOnly")),
                run_source="ranked_match_group",
            )
            if clip.get("startSeconds") is not None:
                run["startSeconds"] = clip.get("startSeconds")
            if clip.get("endSeconds") is not None:
                run["endSeconds"] = clip.get("endSeconds")
            add_run(run)
        transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
        raw_series = transcription.get("detectedSeries") if isinstance(transcription.get("detectedSeries"), list) else []
        for series in raw_series:
            if not isinstance(series, dict):
                continue
            notes = series.get("notes") if isinstance(series.get("notes"), list) else []
            run = expansion_audio_run_from_notes(
                practice_day=practice_day,
                sample_id=str(series.get("sampleId") or ""),
                source_window=str(series.get("sourceWindow") or ""),
                source_title=str(series.get("sourceTitle") or ""),
                notes=[note for note in notes if isinstance(note, dict)],
                candidate_only=bool(series.get("candidateOnly")),
                run_source="raw_detected_series",
            )
            if not run.get("notes"):
                continue
            run["startSeconds"] = series.get("startSeconds") or run.get("startSeconds")
            run["endSeconds"] = series.get("endSeconds") or run.get("endSeconds")
            run["localStartSeconds"] = series.get("localStartSeconds") or run.get("localStartSeconds")
            run["localEndSeconds"] = series.get("localEndSeconds") or run.get("localEndSeconds")
            add_run(run)
    for run in extra_audio_runs or []:
        if isinstance(run, dict):
            add_run(run)
    return runs


def best_audio_window_for_source_range(
    runs: list[dict[str, Any]],
    source_slice: list[dict[str, Any]],
    *,
    anchor_midi: list[int],
    anchor_offset: int,
) -> dict[str, Any]:
    source_midi = note_midi_values(source_slice)
    if not source_midi:
        return {}
    best: dict[str, Any] = {}
    target_length = len(source_midi)
    for run in runs:
        notes = run.get("notes") if isinstance(run.get("notes"), list) else []
        run_midi = note_midi_values([note for note in notes if isinstance(note, dict)])
        if len(run_midi) < target_length:
            continue
        for start in range(0, len(run_midi) - target_length + 1):
            window_midi = run_midi[start : start + target_length]
            window_notes = notes[start : start + target_length]
            anchor_end = anchor_offset + len(anchor_midi)
            if anchor_midi and window_midi[anchor_offset:anchor_end] != anchor_midi:
                continue
            exact_count = sum(1 for observed, expected in zip(window_midi, source_midi) if observed == expected)
            prefix_count = 0
            for observed, expected in zip(window_midi, source_midi):
                if observed != expected:
                    break
                prefix_count += 1
            mismatch_index = next(
                (index for index, (observed, expected) in enumerate(zip(window_midi, source_midi)) if observed != expected),
                -1,
            )
            candidate_only = bool(run.get("candidateOnly"))
            audio_agreed = notes_have_score_match_audio_agreement(window_notes, candidate_only=candidate_only)
            current = {
                "run": run,
                "windowStart": start,
                "windowEnd": start + target_length,
                "windowNotes": window_notes,
                "windowMidiSequence": window_midi,
                "windowExactSequence": note_exact_label(window_notes),
                "exactCount": exact_count,
                "prefixCount": prefix_count,
                "mismatchIndex": mismatch_index,
                "audioAgreed": audio_agreed,
                "candidateOnly": candidate_only,
            }
            current_key = (
                1 if audio_agreed else 0,
                exact_count,
                prefix_count,
                1 if run.get("sampleId") else 0,
                -start,
            )
            best_key = (
                1 if best.get("audioAgreed") else 0,
                int(best.get("exactCount") or 0),
                int(best.get("prefixCount") or 0),
                1 if (best.get("run") or {}).get("sampleId") else 0,
                -int(best.get("windowStart") or 0),
            )
            if not best or current_key > best_key:
                best = current
    return best


def audio_window_search_for_exact_midi(
    runs: list[dict[str, Any]],
    target_midi: list[int],
    *,
    practice_day: str = "",
    anchor_sample_id: str = "",
    anchor_absolute_start: float | None = None,
) -> dict[str, Any]:
    if not target_midi:
        return {
            "searchedWindowCount": 0,
            "exactCandidates": [],
            "nearestWindow": {},
        }
    searched = 0
    exact_candidates: list[dict[str, Any]] = []
    nearest: dict[str, Any] = {}
    target_length = len(target_midi)

    for run in runs:
        if practice_day and str(run.get("practiceDay") or "") != practice_day:
            continue
        notes = run.get("notes") if isinstance(run.get("notes"), list) else []
        run_midi = note_midi_values([note for note in notes if isinstance(note, dict)])
        if len(run_midi) < target_length:
            continue
        source_window_start = parse_window_start(str(run.get("sourceWindow") or ""))
        for start in range(0, len(run_midi) - target_length + 1):
            searched += 1
            window_midi = run_midi[start : start + target_length]
            window_notes = notes[start : start + target_length]
            exact_count = sum(1 for observed, expected in zip(window_midi, target_midi) if observed == expected)
            prefix_count = 0
            for observed, expected in zip(window_midi, target_midi):
                if observed != expected:
                    break
                prefix_count += 1
            mismatch_index = next(
                (index for index, (observed, expected) in enumerate(zip(window_midi, target_midi)) if observed != expected),
                -1,
            )
            candidate_only = bool(run.get("candidateOnly"))
            audio_agreed = notes_have_score_match_audio_agreement(window_notes, candidate_only=candidate_only)
            local_start = float(window_notes[0].get("startSeconds") or 0.0) if window_notes else 0.0
            local_end = float(window_notes[-1].get("endSeconds") or local_start) if window_notes else local_start
            absolute_start = source_window_start + local_start
            distance = (
                abs(absolute_start - anchor_absolute_start)
                if anchor_absolute_start is not None
                else 999999.0
            )
            item = {
                "practiceDay": str(run.get("practiceDay") or ""),
                "sampleId": str(run.get("sampleId") or ""),
                "sourceWindow": str(run.get("sourceWindow") or ""),
                "sourceTitle": str(run.get("sourceTitle") or ""),
                "audioRunSource": str(run.get("runSource") or ""),
                "sameSampleAsAnchor": bool(anchor_sample_id and str(run.get("sampleId") or "") == anchor_sample_id),
                "windowStartIndex": start,
                "windowEndIndex": start + target_length,
                "localStartSeconds": round(local_start, 3),
                "localEndSeconds": round(local_end, 3),
                "absoluteStartSeconds": round(absolute_start, 3),
                "absoluteEndSeconds": round(source_window_start + local_end, 3),
                "neighborDistanceSeconds": round(distance, 3),
                "windowSequence": note_exact_label(window_notes),
                "windowMidiSequence": window_midi,
                "exactCount": exact_count,
                "prefixCount": prefix_count,
                "mismatchIndex": mismatch_index,
                "audioAgreed": audio_agreed,
                "candidateOnly": candidate_only,
                "windowNotes": expansion_window_note_summary(window_notes),
            }
            if window_midi == target_midi:
                exact_candidates.append(item)
            nearest_key = (
                exact_count,
                prefix_count,
                1 if audio_agreed else 0,
                1 if item["sameSampleAsAnchor"] else 0,
                -distance,
            )
            current_key = (
                int(nearest.get("exactCount") or 0),
                int(nearest.get("prefixCount") or 0),
                1 if nearest.get("audioAgreed") else 0,
                1 if nearest.get("sameSampleAsAnchor") else 0,
                -float(nearest.get("neighborDistanceSeconds") or 999999.0),
            )
            if not nearest or nearest_key > current_key:
                nearest = item

    exact_candidates = sorted(
        exact_candidates,
        key=lambda item: (
            1 if item.get("audioAgreed") else 0,
            1 if item.get("sameSampleAsAnchor") else 0,
            -float(item.get("neighborDistanceSeconds") or 999999.0),
            -float(item.get("absoluteStartSeconds") or 0.0),
        ),
        reverse=True,
    )
    return {
        "searchedWindowCount": searched,
        "exactCandidates": exact_candidates,
        "nearestWindow": nearest,
    }


def staff4_adjacent_phrase_mining(
    daily_records: dict[str, Any],
    extra_audio_runs: list[dict[str, Any]] | None = None,
    source_audio_rescan: dict[str, Any] | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    audio_runs = detected_audio_runs_for_expansion(daily_records, extra_audio_runs)
    source_audio_rescan = source_audio_rescan if isinstance(source_audio_rescan, dict) else {}
    target_results: list[dict[str, Any]] = []
    anchor_count = 0
    total_searched = 0
    total_exact = 0
    best_candidate: dict[str, Any] = {}
    best_nearest: dict[str, Any] = {}

    for anchor in staff4_anchor_matches(daily_records):
        practice_day = str(anchor.get("practiceDay") or "")
        source_notes = anchor.get("sourceNotes") if isinstance(anchor.get("sourceNotes"), list) else []
        if not source_notes:
            continue
        piece_title = str(anchor.get("pieceTitle") or "")
        if "wieniawski" not in piece_title.lower():
            continue
        reference_start = int(anchor.get("referenceStart") or 0)
        reference_end = int(anchor.get("referenceEnd") or reference_start)
        anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
        if anchor_midi != STAFF4_ACCEPTED_ANCHOR_MIDI:
            continue
        anchor_count += 1
        anchor_sample_id = str(anchor.get("sampleId") or "")
        anchor_source_window = str(anchor.get("sourceWindow") or "")
        anchor_absolute_start = parse_window_start(anchor_source_window) + float(anchor.get("anchorLocalStartSeconds") or 0.0)
        targets: list[tuple[str, int, int]] = []
        if reference_end < len(source_notes):
            targets.append(("right-1", reference_start, reference_end + 1))
        if reference_end + 1 < len(source_notes):
            targets.append(("right-2", reference_start, reference_end + 2))
        for direction, start, end in targets:
            source_slice = source_notes[start:end]
            target_midi = note_midi_values(source_slice)
            search = audio_window_search_for_exact_midi(
                audio_runs,
                target_midi,
                practice_day=practice_day,
                anchor_sample_id=anchor_sample_id,
                anchor_absolute_start=anchor_absolute_start,
            )
            exact_candidates = search["exactCandidates"][: max(0, int(limit))]
            nearest = search["nearestWindow"]
            total_searched += int(search.get("searchedWindowCount") or 0)
            total_exact += len(search["exactCandidates"])
            status = "exact_audio_candidate" if any(item.get("audioAgreed") for item in search["exactCandidates"]) else "exact_midi_audio_unconfirmed" if search["exactCandidates"] else "not_found"
            if exact_candidates and (not best_candidate or len(target_midi) > int(best_candidate.get("targetNoteCount") or 0)):
                candidate = dict(exact_candidates[0])
                candidate["targetDirection"] = direction
                candidate["targetSequence"] = note_exact_label(source_slice)
                candidate["targetMidiSequence"] = target_midi
                candidate["targetNoteCount"] = len(target_midi)
                best_candidate = candidate
            if nearest:
                nearest_with_target = dict(nearest)
                nearest_with_target["targetDirection"] = direction
                nearest_with_target["targetSequence"] = note_exact_label(source_slice)
                nearest_with_target["targetMidiSequence"] = target_midi
                nearest_key = (
                    int(nearest_with_target.get("exactCount") or 0),
                    int(nearest_with_target.get("prefixCount") or 0),
                    len(target_midi),
                )
                best_nearest_key = (
                    int(best_nearest.get("exactCount") or 0),
                    int(best_nearest.get("prefixCount") or 0),
                    len(best_nearest.get("targetMidiSequence") or []),
                )
                if not best_nearest or nearest_key > best_nearest_key:
                    best_nearest = nearest_with_target
            target_results.append(
                {
                    "direction": direction,
                    "practiceDay": practice_day,
                    "pieceTitle": piece_title,
                    "targetReferenceStart": start,
                    "targetReferenceEnd": end,
                    "targetSequence": note_exact_label(source_slice),
                    "targetMidiSequence": target_midi,
                    "targetNoteCount": len(target_midi),
                    "status": status,
                    "searchedWindowCount": int(search.get("searchedWindowCount") or 0),
                    "exactCandidateCount": len(search["exactCandidates"]),
                    "exactAudioCandidateCount": sum(1 for item in search["exactCandidates"] if item.get("audioAgreed")),
                    "exactCandidates": exact_candidates,
                    "nearestWindow": nearest,
                }
            )

    status = (
        "exact_audio_candidate"
        if best_candidate and best_candidate.get("audioAgreed")
        else "exact_midi_audio_unconfirmed"
        if best_candidate
        else "not_found"
        if anchor_count
        else "no_staff4_anchor"
    )
    if status == "exact_audio_candidate":
        next_action = "Audit the exact Staff 4 adjacent audio candidate before accepting it into the visible phrase lane."
    elif status == "exact_midi_audio_unconfirmed":
        next_action = "Run second-pass audio agreement on the exact Staff 4 MIDI candidate before review."
    elif anchor_count:
        adjacent_failure = (
            source_audio_rescan.get("guidedAdjacentFirstFailure")
            if isinstance(source_audio_rescan.get("guidedAdjacentFirstFailure"), dict)
            else {}
        )
        if (
            int(source_audio_rescan.get("guidedAdjacentTargetCount") or 0)
            and str(source_audio_rescan.get("guidedAdjacentStatus") or "") == "not_reproduced"
        ):
            expected_note = str(adjacent_failure.get("expectedNote") or "the next source note")
            best_offset = adjacent_failure.get("bestAttemptOffsetSeconds")
            next_action = (
                "Adjacent-guided Staff 4 source-note windows were tested, but current detectors did not reproduce exact MIDI; "
                f"calibrate the failed {expected_note} window at best offset {best_offset}s."
            )
        elif int(source_audio_rescan.get("runCount") or 0):
            next_action = "No exact adjacent Staff 4 MIDI window was found after source-audio rescanning; widen the source window or improve note segmentation."
        else:
            next_action = "No exact adjacent Staff 4 MIDI window is in the stored May 3 detected runs yet; rescan the source audio around the accepted anchor."
    else:
        next_action = "Create one accepted Staff 4 source/audio anchor before adjacent mining."
    return {
        "status": status,
        "anchorCount": anchor_count,
        "audioRunCount": len(audio_runs),
        "sourceAudioRescanStatus": source_audio_rescan.get("status") or "",
        "sourceAudioRescanRunCount": int(source_audio_rescan.get("runCount") or 0),
        "sourceAudioRescanEventCount": int(source_audio_rescan.get("eventCount") or 0)
        + int(source_audio_rescan.get("candidateEventCount") or 0)
        + int(source_audio_rescan.get("guidedAnchorEventCount") or 0)
        + int(source_audio_rescan.get("guidedAdjacentEventCount") or 0),
        "sourceAudioRescanGuidedAdjacentStatus": str(source_audio_rescan.get("guidedAdjacentStatus") or ""),
        "sourceAudioRescanGuidedAdjacentTargetCount": int(source_audio_rescan.get("guidedAdjacentTargetCount") or 0),
        "sourceAudioRescanGuidedAdjacentReproducedCount": int(source_audio_rescan.get("guidedAdjacentReproducedCount") or 0),
        "sourceAudioRescanGuidedAdjacentFirstFailure": (
            source_audio_rescan.get("guidedAdjacentFirstFailure")
            if isinstance(source_audio_rescan.get("guidedAdjacentFirstFailure"), dict)
            else {}
        ),
        "searchedWindowCount": total_searched,
        "exactCandidateCount": total_exact,
        "bestCandidate": best_candidate,
        "nearestWindow": best_nearest,
        "targets": target_results,
        "nextAction": next_action,
    }


def expansion_status_for_window(
    *,
    source_slice: list[dict[str, Any]],
    source_snippet: dict[str, Any],
    best_window: dict[str, Any],
) -> tuple[str, str]:
    source_midi = note_midi_values(source_slice)
    snippet_ready = exact_source_range_visually_verified(source_snippet)
    truth_ready = bool(source_snippet.get("truthEvidenceAccepted"))
    if not best_window:
        return "blocked_no_audio_candidate", "No audio-note run currently covers this adjacent source range."
    exact_count = int(best_window.get("exactCount") or 0)
    audio_agreed = bool(best_window.get("audioAgreed"))
    if exact_count == len(source_midi) and audio_agreed and snippet_ready and truth_ready:
        return "accepted_source_audio_expansion", "Exact source MIDI, paired audio, source crop, and truth gate all pass."
    if exact_count == len(source_midi) and audio_agreed and snippet_ready:
        return "ready_for_truth_review", "Audio and source MIDI agree; the source crop still needs accepted truth evidence before display."
    if exact_count == len(source_midi) and audio_agreed:
        return "blocked_source_crop_required", "Audio and source MIDI agree, but an accepted actual-score crop is still required."
    if not audio_agreed:
        return "blocked_audio_agreement", "Candidate notes do not all pass the paired-audio agreement gate."
    return "blocked_audio_mismatch", "Adjacent audio notes do not match the verified source MIDI sequence."


def expansion_window_note_summary(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        midi = note_midi_value(note)
        summary.append(
            {
                "note": str(note.get("note") or ""),
                "midi": midi,
                "startSeconds": round(float(note.get("startSeconds") or 0.0), 3),
                "endSeconds": round(float(note.get("endSeconds") or note.get("startSeconds") or 0.0), 3),
                "durationSeconds": round(float(note.get("durationSeconds") or 0.0), 3),
                "confidence": round(float(note.get("confidence") or 0.0), 3),
                "audioAgreement": bool(note.get("audioAgreement")),
                "agreementSourceCount": int(note.get("agreementSourceCount") or 0),
                "agreementSources": note.get("agreementSources") if isinstance(note.get("agreementSources"), list) else [],
                "detectorSource": str(note.get("detectorSource") or ""),
            }
        )
    return summary


def rejected_staff4_expansion_cases() -> list[dict[str, Any]]:
    manifest = load_long_phrase_truth()
    rejected = manifest.get("rejectedRegressionPhrases") if isinstance(manifest.get("rejectedRegressionPhrases"), list) else []
    cases: list[dict[str, Any]] = []
    for item in rejected:
        if not isinstance(item, dict):
            continue
        if str(item.get("rejectionKind") or "") != "staff4_expansion_audio_mismatch":
            continue
        cases.append(item)
    return cases


def int_sequence(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            return []
    return out


def rejected_staff4_case_for_candidate(
    cases: list[dict[str, Any]],
    *,
    direction: str,
    start: int,
    end: int,
    source_midi: list[int],
    best_window: dict[str, Any],
) -> dict[str, Any]:
    if not best_window:
        return {}
    run = best_window.get("run") if isinstance(best_window.get("run"), dict) else {}
    observed_midi = int_sequence(best_window.get("windowMidiSequence"))
    for case in cases:
        if str(case.get("direction") or "") != direction:
            continue
        if int(case.get("targetReferenceStart") or -1) != start:
            continue
        if int(case.get("targetReferenceEnd") or -1) != end:
            continue
        if str(case.get("sampleId") or "") and str(case.get("sampleId") or "") != str(run.get("sampleId") or ""):
            continue
        if str(case.get("sourceWindow") or "") and str(case.get("sourceWindow") or "") != str(run.get("sourceWindow") or ""):
            continue
        expected_source = int_sequence(case.get("expectedSourceMidiSequence"))
        if expected_source and expected_source != source_midi:
            continue
        rejected_observed = int_sequence(case.get("midiSequence"))
        if rejected_observed and rejected_observed != observed_midi:
            continue
        return case
    return {}


def source_phrase_expansion_harness(
    daily_records: dict[str, Any],
    extra_audio_runs: list[dict[str, Any]] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    audio_runs = detected_audio_runs_for_expansion(daily_records, extra_audio_runs)
    rejected_cases = rejected_staff4_expansion_cases()
    items: list[dict[str, Any]] = []
    anchor_count = 0
    for anchor in staff4_anchor_matches(daily_records):
        practice_day = str(anchor.get("practiceDay") or "")
        target = anchor.get("target") if isinstance(anchor.get("target"), dict) else {}
        score = anchor.get("score") if isinstance(anchor.get("score"), dict) else {}
        source_notes = anchor.get("sourceNotes") if isinstance(anchor.get("sourceNotes"), list) else []
        if not source_notes:
            continue
        reference_start = int(anchor.get("referenceStart") or 0)
        reference_end = int(anchor.get("referenceEnd") or reference_start)
        if reference_end <= reference_start:
            continue
        anchor_slice = source_notes[reference_start:reference_end]
        anchor_midi = [int(value) for value in anchor.get("anchorMidiSequence") or [] if isinstance(value, int)]
        if not anchor_midi:
            anchor_midi = note_midi_values(anchor_slice)
        if not anchor_midi:
            continue
        anchor_count += 1
        candidates: list[tuple[str, int, int]] = []
        if reference_start > 0:
            candidates.append(("left-1", reference_start - 1, reference_end))
        if reference_end < len(source_notes):
            candidates.append(("right-1", reference_start, reference_end + 1))
        if reference_end + 1 < len(source_notes):
            candidates.append(("right-2", reference_start, reference_end + 2))
        for direction, start, end in candidates:
            source_slice = source_notes[start:end]
            source_midi = note_midi_values(source_slice)
            if not source_midi:
                continue
            anchor_offset = reference_start - start
            source_snippet = source_snippet_for_range(target, start, end)
            best_window = best_audio_window_for_source_range(
                audio_runs,
                source_slice,
                anchor_midi=anchor_midi,
                anchor_offset=anchor_offset,
            )
            status, limit_text = expansion_status_for_window(
                source_slice=source_slice,
                source_snippet=source_snippet,
                best_window=best_window,
            )
            rejected_case = rejected_staff4_case_for_candidate(
                rejected_cases,
                direction=direction,
                start=start,
                end=end,
                source_midi=source_midi,
                best_window=best_window,
            )
            if rejected_case:
                status = "rejected_regression"
                limit_text = str(
                    rejected_case.get("basis")
                    or "Rejected by the Staff 4 audit packet; this exact source/audio expansion must not be retried as accepted evidence."
                )
            mismatch_index = int(best_window.get("mismatchIndex") if best_window else -1)
            expected_note = ""
            observed_note = ""
            expected_midi = None
            observed_midi = None
            if mismatch_index >= 0 and mismatch_index < len(source_slice):
                expected_note = str(source_slice[mismatch_index].get("note") or "")
                expected_midi = note_midi_value(source_slice[mismatch_index])
                window_notes = best_window.get("windowNotes") if isinstance(best_window.get("windowNotes"), list) else []
                if mismatch_index < len(window_notes):
                    observed_note = str(window_notes[mismatch_index].get("note") or "")
                    observed_midi = note_midi_value(window_notes[mismatch_index])
            elif isinstance(source_snippet.get("extensionCheck"), dict):
                check = source_snippet["extensionCheck"]
                expected_note = str(check.get("expectedNextScoreNote") or "")
                expected_midi = check.get("expectedNextScoreMidi")
                observed_note = str(check.get("observedNextAudioNote") or "")
                observed_midi = check.get("observedNextAudioMidi")
                if not best_window and observed_note:
                    status = "blocked_audio_mismatch"
                    limit_text = "Source-lane extension is verified, but the stored adjacent audio check disagrees."
            run = best_window.get("run") if isinstance(best_window.get("run"), dict) else {}
            window_notes = best_window.get("windowNotes") if isinstance(best_window.get("windowNotes"), list) else []
            audio_local_start = None
            audio_local_end = None
            if window_notes:
                audio_local_start = round(float(window_notes[0].get("startSeconds") or 0.0), 3)
                audio_local_end = round(float(window_notes[-1].get("endSeconds") or window_notes[-1].get("startSeconds") or 0.0), 3)
            source_window_start = parse_window_start(str(run.get("sourceWindow") or ""))
            items.append(
                {
                    "status": status,
                    "direction": direction,
                    "practiceDay": practice_day,
                    "pieceTitle": str(anchor.get("pieceTitle") or score.get("title") or ""),
                    "anchorSource": str(anchor.get("anchorSource") or "match_group"),
                    "anchorReferenceStart": reference_start,
                    "anchorReferenceEnd": reference_end,
                    "targetReferenceStart": start,
                    "targetReferenceEnd": end,
                    "sourceNoteCount": len(source_slice),
                    "anchorSequence": note_exact_label(anchor_slice),
                    "targetSequence": note_exact_label(source_slice),
                    "targetMidiSequence": source_midi,
                    "bestAudioSequence": str(best_window.get("windowExactSequence") or ""),
                    "bestAudioMidiSequence": best_window.get("windowMidiSequence") or [],
                    "bestExactCount": int(best_window.get("exactCount") or 0),
                    "bestPrefixCount": int(best_window.get("prefixCount") or 0),
                    "expectedNextScoreNote": expected_note,
                    "expectedNextScoreMidi": expected_midi,
                    "observedNextAudioNote": observed_note,
                    "observedNextAudioMidi": observed_midi,
                    "audioAgreed": bool(best_window.get("audioAgreed")) if best_window else False,
                    "sourceCropReady": exact_source_range_visually_verified(source_snippet),
                    "truthEvidenceAccepted": bool(source_snippet.get("truthEvidenceAccepted")) if source_snippet else False,
                    "sourceImageUrl": str(source_snippet.get("imageUrl") or ""),
                    "sampleId": str(run.get("sampleId") or ""),
                    "sourceWindow": str(run.get("sourceWindow") or ""),
                    "audioLocalStartSeconds": audio_local_start,
                    "audioLocalEndSeconds": audio_local_end,
                    "audioAbsoluteStartSeconds": round(source_window_start + audio_local_start, 3)
                    if audio_local_start is not None
                    else None,
                    "audioAbsoluteEndSeconds": round(source_window_start + audio_local_end, 3)
                    if audio_local_end is not None
                    else None,
                    "audioRunSource": str(run.get("runSource") or ""),
                    "bestAudioNotes": expansion_window_note_summary(window_notes),
                    "rejectedRegressionId": str(rejected_case.get("id") or "") if rejected_case else "",
                    "limit": limit_text,
                }
            )
    items = sorted(
        items,
        key=lambda item: (
            0 if item.get("status") == "rejected_regression" else 1,
            1 if item.get("status") == "accepted_source_audio_expansion" else 0,
            1 if item.get("status") == "ready_for_truth_review" else 0,
            int(item.get("bestExactCount") or 0),
            int(item.get("bestPrefixCount") or 0),
            int(item.get("sourceNoteCount") or 0),
        ),
        reverse=True,
    )
    accepted_count = sum(1 for item in items if item.get("status") == "accepted_source_audio_expansion")
    ready_count = sum(1 for item in items if item.get("status") == "ready_for_truth_review")
    rejected_count = sum(1 for item in items if item.get("status") == "rejected_regression")
    blocked_count = sum(1 for item in items if str(item.get("status") or "").startswith("blocked") or item.get("status") == "rejected_regression")
    current = items[0] if items else {}
    return {
        "status": "accepted" if accepted_count else "ready" if items else "empty",
        "anchorCount": anchor_count,
        "audioRunCount": len(audio_runs),
        "rawDetectedAudioRunCount": sum(1 for run in audio_runs if run.get("runSource") == "raw_detected_series"),
        "rankedAudioRunCount": sum(1 for run in audio_runs if run.get("runSource") == "ranked_match_group"),
        "sourceAudioRescanRunCount": sum(1 for run in audio_runs if str(run.get("runSource") or "").startswith("staff4_source_audio_rescan")),
        "targetCount": len(items),
        "acceptedExpansionCount": accepted_count,
        "readyForReviewCount": ready_count,
        "blockedExpansionCount": blocked_count,
        "rejectedRegressionCount": rejected_count,
        "currentBest": current,
        "items": items[: max(0, int(limit))],
        "nextAction": (
            "Promote the accepted expansion into the visible score/audio lane."
            if accepted_count
            else "Keep the accepted Staff 4 anchor fixed and search adjacent audio candidates until the next source note agrees."
            if items
            else "Create one accepted source/audio anchor before running expansion."
        ),
    }


def build_truth_workbench(
    state: dict[str, Any],
    daily_records: dict[str, Any],
    evidence_progress: dict[str, Any],
    limit: int = 12,
) -> dict[str, Any]:
    truth_progress = build_truth_progress(state)
    long_phrase_truth = verify_long_phrase_truth_manifest()
    source_targets = source_verification_targets(daily_records, limit=limit)
    benchmarks = (
        evidence_progress.get("recentBenchmarks")
        if isinstance(evidence_progress.get("recentBenchmarks"), list)
        else []
    )
    corrections = (
        evidence_progress.get("recentCorrections")
        if isinstance(evidence_progress.get("recentCorrections"), list)
        else []
    )
    rejected_score_corrections = [
        item
        for item in corrections
        if isinstance(item, dict)
        and item.get("status") == "rejected"
        and item.get("type") in {"score", "score_note", "score_match", "match"}
    ]
    queued_items: list[dict[str, Any]] = []
    for target in source_targets:
        queued_items.append(
            {
                "kind": "source_target",
                "status": "pending_review",
                "practiceDay": target.get("practiceDay") or "",
                "pieceTitle": target.get("pieceTitle") or target.get("sourceScoreTitle") or "",
                "sequence": target.get("sequence") or "",
                "scoreStatus": target.get("sourceScoreCheckStatus") or "pending",
                "scoreOverlap": target.get("sourceScoreBestOverlap") or 0,
                "noteCount": target.get("sequenceNoteCount") or 0,
                "sampleId": target.get("clipSampleId") or "",
                "limit": target.get("limit") or "",
            }
        )
    for item in truth_progress.get("recentTruthItems", []):
        if not isinstance(item, dict):
            continue
        gate_state = item.get("gateState") if isinstance(item.get("gateState"), dict) else {}
        queued_items.append(
            {
                "kind": "truth_item",
                "status": item.get("status") or "",
                "practiceDay": item.get("practiceDay") or "",
                "pieceTitle": item.get("pieceTitle") or "",
                "sequence": item.get("acceptedPitchClassSequence") or item.get("detectedPitchClassSequence") or "",
                "scoreStatus": "accepted" if gate_state.get("acceptedEvidenceReady") else "pending",
                "scoreOverlap": len(str(item.get("scorePitchClassSequence") or "").split()),
                "noteCount": len(str(item.get("acceptedPitchClassSequence") or item.get("detectedPitchClassSequence") or "").split()),
                "sampleId": item.get("sampleId") or "",
                "limit": item.get("limit") or "",
            }
        )
    return {
        "status": "ready" if source_targets or benchmarks or truth_progress.get("truthItemCount") or long_phrase_truth.get("truthManifestItemCount") else "empty",
        "version": truth_progress.get("version") or "truth_workbench_v1",
        "truthItemCount": int(truth_progress.get("truthItemCount") or 0),
        "acceptedTruthCount": int(truth_progress.get("acceptedTruthCount") or 0),
        "pendingTruthCount": int(truth_progress.get("pendingTruthCount") or 0),
        "rejectedTruthCount": int(truth_progress.get("rejectedTruthCount") or 0),
        "acceptedEvidenceReadyCount": int(truth_progress.get("acceptedEvidenceReadyCount") or 0),
        "scoreReadyTruthCount": int(truth_progress.get("scoreReadyTruthCount") or 0),
        "sourceTargetQueueCount": len(source_targets),
        "wrongScoreRegressionCount": int(evidence_progress.get("wrongScoreNoteRegressionCount") or 0),
        "benchmarkCount": int(evidence_progress.get("benchmarkCount") or len(benchmarks) or 0),
        "rejectedScoreCorrectionCount": len(rejected_score_corrections),
        "longPhraseTruth": long_phrase_truth,
        "truthManifestStatus": str(long_phrase_truth.get("status") or ""),
        "truthManifestItemCount": int(long_phrase_truth.get("truthManifestItemCount") or 0),
        "truthManifestSourceCount": int(long_phrase_truth.get("sourceCount") or 0),
        "truthManifestSourceVerifiedCount": int(long_phrase_truth.get("sourceVerifiedCount") or 0),
        "truthManifestPositiveSourcePhraseCount": int(long_phrase_truth.get("positiveSourcePhraseCount") or 0),
        "truthManifestPositiveSourcePhraseVerifiedCount": int(long_phrase_truth.get("positiveSourcePhraseVerifiedCount") or 0),
        "truthManifestRejectedRegressionPhraseCount": int(long_phrase_truth.get("rejectedRegressionPhraseCount") or 0),
        "truthManifestRejectedRegressionBlockedCount": int(long_phrase_truth.get("rejectedRegressionBlockedCount") or 0),
        "truthManifestLiveAcceptedPhraseCount": int(long_phrase_truth.get("liveAcceptedPhraseCount") or 0),
        "queuedItems": queued_items[: max(0, int(limit))],
        "acceptanceRule": str(long_phrase_truth.get("minimumAcceptedEvidenceRule") or "")
        or "Accepted score evidence needs local media, accepted audio notes, verified source-score notes, exact note-and-octave agreement, and verified score coordinates.",
        "nextAction": (
            "Convert queued score-note hypotheses into verified MusicXML, then store accepted or rejected truth items for each audio-score phrase."
            if source_targets
            else "Add accepted or rejected truth items from local clips before promoting score matches."
        ),
    }


def accepted_long_phrase_match(match: dict[str, Any]) -> bool:
    if not isinstance(match, dict):
        return False
    if not actual_source_score_snippet_ready(match):
        return False
    if not match.get("scoreLocationVerified"):
        return False
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    if not any(
        exact_score_location_ready(value)
        for value in (
            match.get("scoreLocationStatus"),
            match.get("scoreSnippetStatus"),
            score.get("cropStatus"),
            match.get("status"),
        )
    ):
        return False
    matched_note_run = int(match.get("matchedNoteRun") or 0)
    minimum_note_run = max(5, int(match.get("minimumMatchedNoteRun") or 0))
    if matched_note_run < minimum_note_run:
        return False
    if not match_has_local_media(match):
        return False
    status = str(match.get("status") or "").strip().lower()
    if "pitch_anchor" in status:
        return False
    return True


def accepted_measure_match(match: dict[str, Any]) -> bool:
    if not isinstance(match, dict):
        return False
    if not actual_source_score_snippet_ready(match):
        return False
    if not match.get("scoreLocationVerified"):
        return False
    status = str(match.get("status") or "").strip().lower()
    if status != "symbolic_score_phrase_match":
        return False
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    if not any(
        exact_score_location_ready(value)
        for value in (
            match.get("scoreLocationStatus"),
            match.get("scoreSnippetStatus"),
            score.get("cropStatus"),
        )
    ):
        return False
    matched_note_run = int(match.get("matchedNoteRun") or 0)
    minimum_note_run = max(4, int(match.get("minimumMatchedNoteRun") or 0))
    if matched_note_run < minimum_note_run:
        return False
    detected = str(match.get("detectedPitchClassSequenceCompact") or match.get("detectedPitchClassSequence") or "")
    minimum_distinct = max(2, int(match.get("minimumDistinctPitchClasses") or 3))
    if len({value for value in detected.split() if value}) < minimum_distinct:
        return False
    return match_has_local_media(match)


def accepted_measure_match_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    accepted: set[tuple[str, str, str, str, int, int]] = set()
    for record in records:
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
        for match in groups:
            if not accepted_measure_match(match):
                continue
            score = match.get("score") if isinstance(match.get("score"), dict) else {}
            transcription = match.get("transcription") if isinstance(match.get("transcription"), dict) else {}
            detected = match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}
            accepted.add(
                (
                    practice_day,
                    str(transcription.get("sampleId") or detected.get("sampleId") or ""),
                    str(score.get("assetId") or match.get("pieceTitle") or ""),
                    str(match.get("scoreSequenceLabel") or score.get("measureLabel") or ""),
                    int(match.get("referenceStart") or 0),
                    int(match.get("referenceEnd") or 0),
                )
            )
    return len(accepted)


def accepted_long_phrase_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    accepted: set[tuple[str, str, str, str, int, int]] = set()
    for record in records:
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
        for match in groups:
            if not accepted_long_phrase_match(match):
                continue
            score = match.get("score") if isinstance(match.get("score"), dict) else {}
            transcription = match.get("transcription") if isinstance(match.get("transcription"), dict) else {}
            detected = match.get("detectedSeries") if isinstance(match.get("detectedSeries"), dict) else {}
            accepted.add(
                (
                    practice_day,
                    str(transcription.get("sampleId") or detected.get("sampleId") or ""),
                    str(score.get("assetId") or match.get("pieceTitle") or ""),
                    str(match.get("scoreSequenceLabel") or score.get("measureLabel") or ""),
                    int(match.get("referenceStart") or 0),
                    int(match.get("referenceEnd") or 0),
                )
            )
    return len(accepted)


def score_heatmap_fragment_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    accepted: set[tuple[str, str, str]] = set()
    for record in records:
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        heat_map = record.get("heatMap") if isinstance(record.get("heatMap"), dict) else {}
        fragments = heat_map.get("fragments") if isinstance(heat_map.get("fragments"), list) else []
        for fragment in fragments:
            if not isinstance(fragment, dict) or fragment.get("status") != "score_location_verified":
                continue
            label = str(fragment.get("label") or "").strip()
            score_image = str(fragment.get("scoreImageUrl") or "").strip()
            if not label or not score_image:
                continue
            accepted.add((practice_day, label, score_image))
    return len(accepted)


def score_reference_audit_totals(daily_records: dict[str, Any]) -> dict[str, int]:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    local_source_assets: set[str] = set()
    symbolic_notes_by_source: dict[str, int] = {}
    source_snippets_by_source: dict[str, int] = {}
    score_map_candidates_by_source: dict[str, int] = {}
    score_map_candidate_staves_by_source: dict[str, int] = {}
    score_map_note_hypotheses_by_source: dict[str, int] = {}
    score_map_note_hypothesis_staves_by_source: dict[str, int] = {}
    score_map_review_packets_by_source: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
        audit = transcription.get("scoreReferenceAudit") if isinstance(transcription.get("scoreReferenceAudit"), dict) else {}
        targets = audit.get("targets") if isinstance(audit.get("targets"), list) else []
        if not targets and int(audit.get("symbolicScoreNoteCount") or 0):
            source_id = str(audit.get("symbolicScoreSourceId") or f"record:{record.get('practiceDay') or len(symbolic_notes_by_source)}").strip()
            symbolic_notes_by_source[source_id] = max(
                symbolic_notes_by_source.get(source_id, 0),
                int(audit.get("symbolicScoreNoteCount") or 0),
            )
            source_snippets_by_source[source_id] = max(
                source_snippets_by_source.get(source_id, 0),
                int(audit.get("symbolicScoreSourceSnippetCount") or 0),
            )
            score_map_candidates_by_source[source_id] = max(
                score_map_candidates_by_source.get(source_id, 0),
                int(audit.get("scoreMapCandidateGlyphCount") or 0),
            )
            score_map_candidate_staves_by_source[source_id] = max(
                score_map_candidate_staves_by_source.get(source_id, 0),
                int(audit.get("scoreMapCandidateStaffCount") or 0),
            )
            score_map_note_hypotheses_by_source[source_id] = max(
                score_map_note_hypotheses_by_source.get(source_id, 0),
                int(audit.get("scoreMapNoteHypothesisCount") or 0),
            )
            score_map_note_hypothesis_staves_by_source[source_id] = max(
                score_map_note_hypothesis_staves_by_source.get(source_id, 0),
                int(audit.get("scoreMapNoteHypothesisStaffCount") or 0),
            )
            score_map_review_packets_by_source[source_id] = max(
                score_map_review_packets_by_source.get(source_id, 0),
                int(audit.get("scoreMapReviewPacketCount") or 0),
            )
        for target in targets:
            if not isinstance(target, dict):
                continue
            asset_id = str(target.get("scoreAssetId") or "").strip()
            source_id = str(target.get("symbolicScoreSourceId") or asset_id or target.get("symbolicScoreTitle") or "").strip()
            if source_id:
                symbolic_notes_by_source[source_id] = max(
                    symbolic_notes_by_source.get(source_id, 0),
                    int(target.get("symbolicScoreNoteCount") or 0),
                )
                source_snippets_by_source[source_id] = max(
                    source_snippets_by_source.get(source_id, 0),
                    int(target.get("symbolicScoreSourceSnippetCount") or 0),
                )
                score_map_candidates_by_source[source_id] = max(
                    score_map_candidates_by_source.get(source_id, 0),
                    int(target.get("scoreMapCandidateGlyphCount") or 0),
                )
                score_map_candidate_staves_by_source[source_id] = max(
                    score_map_candidate_staves_by_source.get(source_id, 0),
                    int(target.get("scoreMapCandidateStaffCount") or 0),
                )
                score_map_note_hypotheses_by_source[source_id] = max(
                    score_map_note_hypotheses_by_source.get(source_id, 0),
                    int(target.get("scoreMapNoteHypothesisCount") or 0),
                )
                score_map_note_hypothesis_staves_by_source[source_id] = max(
                    score_map_note_hypothesis_staves_by_source.get(source_id, 0),
                    int(target.get("scoreMapNoteHypothesisStaffCount") or 0),
                )
                score_map_review_packets_by_source[source_id] = max(
                    score_map_review_packets_by_source.get(source_id, 0),
                    int(target.get("scoreMapReviewPacketCount") or 0),
                )
            if asset_id and target.get("sourcePdfLocalReady"):
                local_source_assets.add(asset_id)
    return {
        "sourcePdfLocalReadyCount": len(local_source_assets),
        "symbolicScoreNoteCount": sum(symbolic_notes_by_source.values()),
        "symbolicScoreSourceSnippetCount": sum(source_snippets_by_source.values()),
        "scoreMapCandidateGlyphCount": sum(score_map_candidates_by_source.values()),
        "scoreMapCandidateStaffCount": sum(score_map_candidate_staves_by_source.values()),
        "scoreMapNoteHypothesisCount": sum(score_map_note_hypotheses_by_source.values()),
        "scoreMapNoteHypothesisStaffCount": sum(score_map_note_hypothesis_staves_by_source.values()),
        "scoreMapReviewPacketCount": sum(score_map_review_packets_by_source.values()),
    }


def roadmap_gate(
    gate_id: str,
    label: str,
    weight: float,
    points: float,
    evidence: str,
    done: str,
    remaining: str,
) -> dict[str, Any]:
    bounded_points = max(0.0, min(float(weight), float(points)))
    display_points = round(bounded_points, 2)
    status = "complete" if bounded_points >= weight else "partial" if bounded_points > 0 else "pending"
    return {
        "id": gate_id,
        "label": label,
        "weight": weight,
        "points": display_points,
        "precisePoints": round(bounded_points, 4),
        "status": status,
        "evidence": evidence,
        "done": done,
        "remaining": remaining,
    }


def build_transcription_completion(
    training: dict[str, Any],
    daily_records: dict[str, Any],
    repertoire_evidence: dict[str, Any],
    active_practice_coverage: dict[str, Any],
    evidence_progress: dict[str, Any],
    media_samples: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    truth_workbench: dict[str, Any] | None = None,
    gold_review: dict[str, Any] | None = None,
    staff4_phrase_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    truth_workbench = truth_workbench or {}
    gold_review = gold_review or {}
    staff4_audit = staff4_phrase_audit if isinstance(staff4_phrase_audit, dict) else {}
    active_scan = (
        active_practice_coverage.get("activePracticeScan")
        if isinstance(active_practice_coverage.get("activePracticeScan"), dict)
        else {}
    )
    uploaded_seconds = int(active_practice_coverage.get("uploadedVideoSeconds") or 0)
    checked_seconds = int(active_practice_coverage.get("checkedVideoSeconds") or 0)
    coverage_ratio = min(1.0, checked_seconds / uploaded_seconds) if uploaded_seconds else 0.0
    record_count = int(daily_records.get("recordCount") or 0)
    ledger_video_count = int(active_practice_coverage.get("ledgerVideoCount") or 0)
    sample_result_count = int(active_scan.get("sampleResultCount") or 0)
    active_interval_count = int(active_scan.get("activeIntervalCount") or 0)
    pending_window_count = int(active_scan.get("pendingWindowCount") or 0)
    active_sample_count = int(active_scan.get("activeViolinSampleCount") or 0)
    checked_no_violin_count = int(active_scan.get("checkedNoViolinSampleCount") or 0)
    audio_record_count = int(daily_records.get("audioEvidenceRecordCount") or 0)
    transcribed_record_count = int(daily_records.get("transcribedRecordCount") or 0)
    score_sequence_count = score_sequence_match_count(daily_records)
    score_verified_count = score_location_verified_count(daily_records)
    score_visual_lock_count = score_visual_agreement_count(daily_records)
    actual_source_score_snippet_lock_count = actual_source_score_snippet_count(daily_records)
    score_audit_totals = score_reference_audit_totals(daily_records)
    local_score_source_count = int(score_audit_totals.get("sourcePdfLocalReadyCount") or 0)
    symbolic_score_note_count = int(score_audit_totals.get("symbolicScoreNoteCount") or 0)
    symbolic_score_source_snippet_count = int(score_audit_totals.get("symbolicScoreSourceSnippetCount") or 0)
    score_map_candidate_glyph_count = int(score_audit_totals.get("scoreMapCandidateGlyphCount") or 0)
    score_map_candidate_staff_count = int(score_audit_totals.get("scoreMapCandidateStaffCount") or 0)
    score_map_note_hypothesis_count = int(score_audit_totals.get("scoreMapNoteHypothesisCount") or 0)
    score_map_note_hypothesis_staff_count = int(score_audit_totals.get("scoreMapNoteHypothesisStaffCount") or 0)
    score_map_review_packet_count = int(score_audit_totals.get("scoreMapReviewPacketCount") or 0)
    benchmark_count = int(evidence_progress.get("benchmarkCount") or 0)
    rejected_score_count = int(evidence_progress.get("wrongScoreNoteRegressionCount") or 0)
    truth_item_count = int(truth_workbench.get("truthItemCount") or 0)
    truth_ready_count = int(truth_workbench.get("acceptedEvidenceReadyCount") or 0)
    score_truth_ready_count = int(truth_workbench.get("scoreReadyTruthCount") or 0)
    truth_queue_count = int(truth_workbench.get("sourceTargetQueueCount") or 0) + int(truth_workbench.get("pendingTruthCount") or 0)
    truth_manifest_status = str(truth_workbench.get("truthManifestStatus") or "")
    truth_manifest_item_count = int(truth_workbench.get("truthManifestItemCount") or 0)
    truth_manifest_source_verified_count = int(truth_workbench.get("truthManifestSourceVerifiedCount") or 0)
    truth_manifest_positive_count = int(truth_workbench.get("truthManifestPositiveSourcePhraseCount") or 0)
    truth_manifest_positive_verified_count = int(truth_workbench.get("truthManifestPositiveSourcePhraseVerifiedCount") or 0)
    truth_manifest_rejected_count = int(truth_workbench.get("truthManifestRejectedRegressionPhraseCount") or 0)
    truth_manifest_rejected_blocked_count = int(truth_workbench.get("truthManifestRejectedRegressionBlockedCount") or 0)
    truth_manifest_live_phrase_count = int(truth_workbench.get("truthManifestLiveAcceptedPhraseCount") or 0)
    truth_manifest_ready = truth_manifest_status == "verified"
    truth_route_ready = str(truth_workbench.get("version") or "") == "truth_workbench_v1"
    gold_label_count = int(gold_review.get("labelCount") or 0)
    gold_accepted_count = int(gold_review.get("acceptedCount") or 0)
    gold_rejected_count = int(gold_review.get("rejectedCount") or 0)
    gold_queue_count = int(gold_review.get("queueCount") or 0)
    gold_accepted_audio_phrase_count = int(gold_review.get("acceptedAudioPhraseCount") or 0)
    gold_accepted_score_phrase_count = int(gold_review.get("acceptedScorePhraseCount") or 0)
    transition_trace_count = sum(
        int((item.get("quality") if isinstance(item.get("quality"), dict) else {}).get("transitionTraceSelectedEventCount") or 0)
        for item in transcriptions
        if isinstance(item, dict)
    )
    repertoire_entries = repertoire_evidence.get("entries") if isinstance(repertoire_evidence.get("entries"), list) else []
    score_target_count = int(
        training.get("scoreReferenceTargetCount")
        or training.get("sourceConfirmedScoreTargetCount")
        or training.get("referenceTargetCount")
        or 0
    )
    long_phrase_count = accepted_long_phrase_count(daily_records)
    measure_match_count = accepted_measure_match_count(daily_records)
    score_heatmap_count = score_heatmap_fragment_count(daily_records)
    phrase_candidate_count = reference_phrase_candidate_count(daily_records)
    phrase_candidate_top = reference_phrase_candidate_top(daily_records)
    phrase_candidate_sequence = str(phrase_candidate_top.get("sequence") or "")
    source_target_count = source_verification_target_count(daily_records)
    source_targets = source_verification_targets(daily_records)
    source_target_top = source_targets[0] if source_targets else {}
    source_target_sequence = str(source_target_top.get("sequence") or "")
    source_target_note_count = int(source_target_top.get("sequenceNoteCount") or 0)
    source_target_checked = sum(1 for target in source_targets if target.get("sourceScoreChecked"))
    source_target_verified = sum(1 for target in source_targets if target.get("sourceScoreVerified"))
    source_target_best_overlap = int(source_target_top.get("sourceScoreBestOverlap") or 0)
    source_target_check_status = str(source_target_top.get("sourceScoreCheckStatus") or "")
    staff4_source_rescan = staff4_source_audio_rescan(daily_records, media_samples)
    staff4_source_rescan_runs = (
        staff4_source_rescan.get("runs")
        if isinstance(staff4_source_rescan.get("runs"), list)
        else []
    )
    phrase_expansion = source_phrase_expansion_harness(daily_records, staff4_source_rescan_runs)
    staff4_mining = staff4_adjacent_phrase_mining(daily_records, staff4_source_rescan_runs, staff4_source_rescan)
    phrase_expansion_target_count = int(phrase_expansion.get("targetCount") or 0)
    phrase_expansion_accepted_count = int(phrase_expansion.get("acceptedExpansionCount") or 0)
    phrase_expansion_ready_count = int(phrase_expansion.get("readyForReviewCount") or 0)
    phrase_expansion_blocked_count = int(phrase_expansion.get("blockedExpansionCount") or 0)
    phrase_expansion_rejected_count = int(phrase_expansion.get("rejectedRegressionCount") or 0)
    phrase_expansion_audio_run_count = int(phrase_expansion.get("audioRunCount") or 0)
    phrase_expansion_raw_audio_run_count = int(phrase_expansion.get("rawDetectedAudioRunCount") or 0)
    phrase_expansion_source_rescan_run_count = int(phrase_expansion.get("sourceAudioRescanRunCount") or 0)
    staff4_source_rescan_status = str(staff4_source_rescan.get("status") or "")
    staff4_source_rescan_run_count = int(staff4_source_rescan.get("runCount") or 0)
    staff4_source_rescan_event_count = (
        int(staff4_source_rescan.get("eventCount") or 0)
        + int(staff4_source_rescan.get("candidateEventCount") or 0)
        + int(staff4_source_rescan.get("guidedAnchorEventCount") or 0)
        + int(staff4_source_rescan.get("guidedAdjacentEventCount") or 0)
    )
    staff4_source_rescan_anchor_status = str(staff4_source_rescan.get("anchorReproductionStatus") or "")
    staff4_source_rescan_anchor_count = int(staff4_source_rescan.get("anchorReproducedCount") or 0)
    staff4_source_rescan_anchor_target_count = int(staff4_source_rescan.get("anchorReproductionTargetCount") or 0)
    staff4_source_rescan_adjacent_status = str(staff4_source_rescan.get("guidedAdjacentStatus") or "")
    staff4_source_rescan_adjacent_count = int(staff4_source_rescan.get("guidedAdjacentReproducedCount") or 0)
    staff4_source_rescan_adjacent_target_count = int(staff4_source_rescan.get("guidedAdjacentTargetCount") or 0)
    staff4_source_rescan_adjacent_first_failure = (
        staff4_source_rescan.get("guidedAdjacentFirstFailure")
        if isinstance(staff4_source_rescan.get("guidedAdjacentFirstFailure"), dict)
        else {}
    )
    staff4_source_rescan_adjacent_failure_note = str(
        staff4_source_rescan_adjacent_first_failure.get("expectedNote") or ""
    )
    staff4_source_rescan_adjacent_failure_offset = staff4_source_rescan_adjacent_first_failure.get(
        "bestAttemptOffsetSeconds"
    )
    staff4_mining_status = str(staff4_mining.get("status") or "")
    staff4_mining_searched_count = int(staff4_mining.get("searchedWindowCount") or 0)
    staff4_mining_exact_count = int(staff4_mining.get("exactCandidateCount") or 0)
    staff4_mining_nearest = staff4_mining.get("nearestWindow") if isinstance(staff4_mining.get("nearestWindow"), dict) else {}
    phrase_expansion_current = (
        phrase_expansion.get("currentBest")
        if isinstance(phrase_expansion.get("currentBest"), dict)
        else {}
    )
    staff4_audit_status = str(staff4_audit.get("status") or "")
    staff4_audit_ready = staff4_audit_status not in {"", "not_generated", "blocked_no_staff4_expansion"}
    phrase_expansion_detail = (
        f"{phrase_expansion_accepted_count} accepted / {phrase_expansion_blocked_count} blocked"
        + (f" / {phrase_expansion_rejected_count} rejected" if phrase_expansion_rejected_count else "")
        if phrase_expansion_target_count
        else "pending anchor"
    )
    staff4_mining_detail = (
        f"{staff4_mining_exact_count} exact / {staff4_mining_searched_count} windows"
        + (f" / {staff4_source_rescan_run_count} source runs" if staff4_source_rescan_run_count else "")
        if staff4_mining_searched_count
        else "pending stored runs"
    )
    phrase_candidate_detail = (
        f"pending: {phrase_candidate_sequence}"
        if phrase_candidate_sequence
        else "pending source-score verification"
    )
    source_target_detail = (
        source_target_sequence
        if source_target_sequence
        else "none"
    )

    gates = [
        roadmap_gate(
            "source-ledger",
            "Source ledger and daily grouping",
            5,
            5 if ledger_video_count and record_count else 0,
            f"{ledger_video_count} strict-ledger videos / {record_count} practice days",
            "Practice videos are indexed from the strict ledger and grouped by day.",
            "Keep new uploads entering the same ledger without changing historical dates.",
        ),
        roadmap_gate(
            "paper-tracker",
            "Paper tracker",
            5,
            5,
            "Curtis paper PDF is the progress record.",
            "The paper contains the long-phrase transcription roadmap and live progress entries.",
            "Update this PDF on every material transcription, score, practice-time, or evidence-gate change.",
        ),
        roadmap_gate(
            "active-scan-route",
            "Active-practice scan route",
            8,
            8 if active_interval_count or sample_result_count or pending_window_count else 0,
            f"{active_interval_count} active intervals / {sample_result_count} scan results / {pending_window_count} queued windows",
            "Active violin-playing time is separated from uploaded video duration.",
            "Continue converting queued windows into checked source coverage.",
        ),
        roadmap_gate(
            "full-archive-coverage",
            "Full archive practice-time coverage",
            12,
            12 * coverage_ratio,
            f"{active_practice_coverage.get('checkedVideoLabel') or '0s'} checked of {active_practice_coverage.get('uploadedVideoLabel') or 'unknown'}",
            "Checked windows count playing and non-playing intervals separately.",
            "Every strict-ledger video still needs chronological playing/non-playing coverage.",
        ),
        roadmap_gate(
            "local-media-evidence",
            "Local audio/video evidence",
            6,
            (2 if media_samples else 0) + (2 if audio_record_count else 0),
            f"{len(media_samples)} media samples / {audio_record_count} audio-evidence daily records",
            "Accepted snippets can use local media evidence instead of YouTube embeds.",
            "Every accepted transcription and future phrase match needs stable local audio/video.",
        ),
        roadmap_gate(
            "correction-benchmarks",
            "Truth, correction, and benchmark loop",
            6,
            (1.5 if benchmark_count else 0)
            + (0.5 if rejected_score_count else 0)
            + (1.0 if truth_route_ready else 0)
            + (0.75 if truth_manifest_ready else 0)
            + min(0.75, truth_manifest_positive_verified_count * 0.35)
            + min(0.75, truth_manifest_rejected_blocked_count * 0.2)
            + (0.75 if gold_queue_count else 0)
            + min(1.5, gold_accepted_count * 0.5)
            + min(1.0, truth_queue_count * 0.25)
            + min(1.0, truth_ready_count * 0.5)
            + (0.75 if score_visual_lock_count else 0)
            + (0.75 if actual_source_score_snippet_lock_count else 0),
            f"{benchmark_count} benchmark corrections / {rejected_score_count} wrong-score-note regressions / {truth_queue_count} queued truth checks / {truth_ready_count} accepted truth items / {gold_queue_count} gold review clips / {gold_accepted_count} accepted gold labels / {truth_manifest_positive_verified_count} source-positive exact-MIDI phrases / {truth_manifest_rejected_blocked_count} rejected exact-MIDI regressions / {score_visual_lock_count} score-visual locks / {actual_source_score_snippet_lock_count} actual-source score locks",
            "Gold review now turns queued clips into accepted or rejected labels, rejected score-note mistakes can be stored as regression evidence, and source-only exact-MIDI phrases can be checked against MusicXML.",
            "Review queued clips into accepted audio phrases, rejected mismatches, or score phrases with exact notes and score location.",
        ),
        roadmap_gate(
            "score-truth",
            "Verified score library and note coordinates",
            15,
            (1.5 if score_target_count else 0)
            + (1.5 if local_score_source_count else 0)
            + (2 if symbolic_score_note_count else 0)
            + (1 if symbolic_score_source_snippet_count else 0)
            + (1 if score_map_candidate_glyph_count else 0)
            + (1.5 if score_map_note_hypothesis_count else 0)
            + (2.5 if score_map_review_packet_count else 0)
            + (1 if source_target_checked else 0)
            + (4 if score_verified_count else 0),
            f"{score_target_count} score targets / {local_score_source_count} local PDFs / {symbolic_score_note_count} verified symbolic notes / {score_map_candidate_glyph_count} unaccepted score glyph candidates / {score_map_note_hypothesis_count} unaccepted note hypotheses / {score_map_review_packet_count} review packets / {source_target_checked} source checks / {score_verified_count} exact locations",
            "Source-confirmed pieces can seed score targets, pending source targets are checked before promotion, and local score glyphs now produce staff-level review packets for faster MusicXML review.",
            "Scherzo-Tarantelle review packets still need source review into verified MusicXML notes and rendered score coordinates.",
        ),
        roadmap_gate(
            "single-note-anchor",
            "Verified score/audio anchor",
            5,
            5 if score_verified_count else 0,
            f"{score_verified_count} verified score locations",
            "At least one displayed score/audio group has an exact symbolic score location.",
            "Extend verified anchors into longer contiguous score phrases.",
        ),
        roadmap_gate(
            "note-rhythm-engine",
            "Accurate note and rhythm extraction",
            18,
            (1 if transcriptions else 0)
            + (1 if transcribed_record_count else 0)
            + (1 if audio_record_count else 0)
            + (1 if transition_trace_count else 0)
            + min(2, long_phrase_count * 2),
            f"{len(transcriptions)} transcription records / {transition_trace_count} hidden fast-note candidates / {transcribed_record_count} notation-ready daily records / {audio_record_count} audio-evidence records",
            "Short audio-checked fragments exist; failed broad transcription stays hidden, and fast-transition candidates now need second-pass spectral/onset audio agreement before score search.",
            "Fast runs, arpeggios, repeated notes, rests, rhythm, and full active windows remain unsolved.",
        ),
        roadmap_gate(
            "notation-rendering",
            "Professional notation rendering",
            6,
            (1 if transcribed_record_count else 0) + (1.5 if long_phrase_count else 0),
            f"{transcribed_record_count} notation-ready daily records",
            "Notation is gated so failed transcription is not displayed as accepted evidence.",
            "Replace fragile hand-built notation with publication-quality rendering for accepted phrases.",
        ),
        roadmap_gate(
            "score-pattern-alignment",
            "Score or exercise-pattern alignment",
            8,
            (1.5 if score_sequence_match_count(daily_records) else 0)
            + min(2.5, phrase_candidate_count * 0.5)
            + min(0.5, phrase_expansion_target_count * 0.25)
            + (0.25 if phrase_expansion_raw_audio_run_count else 0)
            + (0.4 if phrase_expansion_source_rescan_run_count else 0)
            + (0.25 if staff4_mining_searched_count else 0)
            + (0.5 if staff4_audit_ready else 0)
            + (1 if source_target_note_count >= 7 else 0)
            + (2 if score_verified_count else 0)
            + (1 if measure_match_count else 0)
            + min(2, long_phrase_count * 2),
            f"{score_sequence_count} pitch-sequence groups / {phrase_candidate_count} phrase candidates / {source_target_count} source targets / {phrase_expansion_target_count} anchored expansions / {phrase_expansion_audio_run_count} audio runs searched / {phrase_expansion_source_rescan_run_count} source-rescan runs / {score_verified_count} exact score locations",
            "Pitch-sequence groups are separated from exact score evidence, accepted anchors now search raw detected note runs, a Staff 4 source-audio rescan, and a dedicated adjacent-mining pass before any outward source-lane expansion is accepted; Staff 4 blockers can generate audit packets.",
            "Promote phrase candidates only after source-score or score-free exercise verification.",
        ),
        roadmap_gate(
            "repeat-heatmap",
            "Repeat grouping and heat maps",
            3,
            (0.5 if score_sequence_count else 0)
            + (1.0 if score_heatmap_count else 0)
            + min(1.5, long_phrase_count * 1.5),
            f"{score_heatmap_count} score-coordinate heat-map fragments / {score_sequence_count} pitch-sequence groups",
            "Verified score matches now become score-coordinate heat-map fragments.",
            "Extend heat maps from one accepted phrase to repeated attempts, problem density, and improvement layers.",
        ),
        roadmap_gate(
            "repertoire-observation",
            "Repertoire and Curtis-level observations",
            3,
            (1 if repertoire_entries else 0) + (0.5 if long_phrase_count else 0),
            f"{len(repertoire_entries)} repertoire entries / {measure_match_count} accepted measures / {long_phrase_count} accepted long phrases",
            "Confirmed source evidence can promote repertoire without fake progress percentages.",
            "Curtis-level blockers need accepted clips, transcription events, and score or pattern locations.",
        ),
    ]

    total_weight = sum(float(item["weight"]) for item in gates)
    completed_points = round(sum(float(item.get("precisePoints", item["points"])) for item in gates), 3)
    completion_exact_percent = round((completed_points / total_weight) * 100, 3) if total_weight else 0
    completion_percent = int(round(completion_exact_percent)) if total_weight else 0
    completion_exact_label = f"{completion_exact_percent:.3f}".rstrip("0").rstrip(".") + "%"
    completed_points_label = (
        f"{completed_points:.3f}".rstrip("0").rstrip(".")
        + f"/{int(total_weight)} weighted points"
    )
    checked_label = active_practice_coverage.get("checkedVideoLabel") or "0s"
    uploaded_label = active_practice_coverage.get("uploadedVideoLabel") or "unknown"
    active_label = active_practice_coverage.get("activePracticeLabel") or "pending"
    estimate_label = active_practice_coverage.get("estimatedTotalPracticeLabel") or "pending"
    implementation_summary = (
        "Practice-time scanning is working. The long-phrase path now has a local source score PDF and still counts only verified score/audio phrase matches."
        if not measure_match_count
        else "Practice-time scanning is working. The long-phrase path now has one accepted source-score/audio phrase; the remaining work is expanding that verified lane into longer phrases and full-session coverage."
        if long_phrase_count
        else "Practice-time scanning is working. The long-phrase path now has a source-backed score/audio measure match and still separates measure progress from solved long phrases."
    )
    implementation_current = [
        {
            "label": "Implementation",
            "value": completion_exact_label,
            "detail": completed_points_label,
        },
        {
            "label": "Checked video",
            "value": checked_label,
            "detail": f"of {uploaded_label}",
        },
        {
            "label": "Practice time",
            "value": active_label,
            "detail": f"{estimate_label} archive estimate",
        },
        {
            "label": "Score windows",
            "value": str(score_verified_count),
            "detail": f"{actual_source_score_snippet_lock_count} source locks",
        },
        {
            "label": "Score map queue",
            "value": str(score_map_candidate_glyph_count),
            "detail": f"{score_map_candidate_staff_count} staves pending",
        },
        {
            "label": "Score note queue",
            "value": str(score_map_note_hypothesis_count),
            "detail": f"{score_map_note_hypothesis_staff_count} staves pending",
        },
        {
            "label": "Score review packets",
            "value": str(score_map_review_packet_count),
            "detail": f"{score_map_note_hypothesis_count} notes queued",
        },
        {
            "label": "Truth set",
            "value": str(truth_ready_count),
            "detail": f"{truth_queue_count} queued / {score_truth_ready_count} score-ready",
        },
        {
            "label": "Exact MIDI truth",
            "value": f"{truth_manifest_positive_verified_count}/{truth_manifest_positive_count}",
            "detail": f"{truth_manifest_rejected_blocked_count}/{truth_manifest_rejected_count} regressions blocked",
        },
        {
            "label": "Gold review",
            "value": f"{gold_accepted_count}/{gold_label_count}",
            "detail": f"{gold_queue_count} queued / {gold_rejected_count} rejected",
        },
        {
            "label": "Long phrases",
            "value": str(long_phrase_count),
            "detail": "accepted",
        },
        {
            "label": "Expansion gate",
            "value": f"{phrase_expansion_accepted_count}/{phrase_expansion_target_count}",
            "detail": (
                f"{phrase_expansion_detail}; {phrase_expansion_raw_audio_run_count} raw / {phrase_expansion_source_rescan_run_count} rescan"
                if phrase_expansion_target_count
                else phrase_expansion_detail
            ),
        },
        {
            "label": "Source rescan",
            "value": staff4_source_rescan_status.replace("_", " ") if staff4_source_rescan_status else "pending",
            "detail": (
                f"{staff4_source_rescan_run_count} runs / {staff4_source_rescan_event_count} events / "
                f"anchor {staff4_source_rescan_anchor_status.replace('_', ' ') or 'unchecked'}"
            ),
        },
        {
            "label": "Staff 4 mining",
            "value": staff4_mining_status.replace("_", " ") if staff4_mining_status else "pending",
            "detail": staff4_mining_detail,
        },
        {
            "label": "Staff 4 audit",
            "value": staff4_audit_status.replace("_", " ") if staff4_audit_status else "not generated",
            "detail": (
                f"{staff4_audit.get('expectedNextScoreNote') or 'score'} vs {staff4_audit.get('observedNextAudioNote') or 'audio'}"
                if staff4_audit_ready
                else "packet pending"
            ),
        },
        {
            "label": "Fast-note trace",
            "value": str(transition_trace_count),
            "detail": "hidden candidates",
        },
        {
            "label": "Measure target",
            "value": f"{min(measure_match_count, 1)}/1",
            "detail": "verified score/audio measure",
        },
        {
            "label": "Score heat map",
            "value": str(score_heatmap_count),
            "detail": "verified fragments",
        },
        {
            "label": "Phrase candidates",
            "value": str(phrase_candidate_count),
            "detail": phrase_candidate_detail,
        },
        {
            "label": "Source target",
            "value": str(source_target_note_count),
            "detail": source_target_detail,
        },
        {
            "label": "Target check",
            "value": f"{source_target_verified}/{source_target_checked}",
            "detail": (
                f"{source_target_best_overlap}/{source_target_note_count} MIDI overlap"
                if source_target_checked and source_target_note_count
                else "pending"
            ),
        },
        {
            "label": "Scan queue",
            "value": str(pending_window_count),
            "detail": f"{active_interval_count} active intervals",
        },
    ]
    done_summary = [
        "Strict-ledger videos are grouped by practice day.",
        "Uploaded video time is separated from active violin-playing time.",
        "Violin-positive local audio/video evidence can be stored and replayed.",
        "Failed broad transcription is withheld from notation.",
        "Fast YIN transition traces are hidden from notation but available to the strict score matcher.",
        "Fast-transition phrase candidates now fail closed unless every matched note has second-pass spectral/onset audio agreement.",
        "Local score-glyph candidates are queued for verification without being accepted as score evidence.",
        "Likely score noteheads now receive unaccepted staff-position pitch hypotheses before MusicXML review.",
        "Staff-level source review packets now map queued hypotheses back to the scanned score.",
        "A source-only exact-MIDI truth manifest now verifies the current Wieniawski MusicXML excerpt and blocks known false phrase maps.",
        "A gold review loop now queues clip-level candidates for accepted/rejected labels before they can train the transcription gate.",
        "Score panels require visible score noteheads, range, spelling, exact note-and-octave agreement, and an actual source-score crop before display.",
        "The rejected five-note Scherzo phrase is blocked from accepted score evidence.",
        "A truth workbench now separates queued, accepted, and rejected audio-score-transcription evidence before anything can become visible score evidence.",
        "Accepted source/audio anchors now feed an outward expansion gate before Curtis tries a new random match.",
        "Expansion search now includes raw detected note series, not only already-ranked score candidate cards.",
        "Staff 4 source-audio rescanning now extracts a fresh window around the accepted source/audio anchor and adds its events to the exact-MIDI search pool.",
        "Staff 4 adjacent mining now searches stored May 3 audio-note windows for the exact right-1 and right-2 MIDI sequences before accepting another expansion.",
        "A Staff 4 audit packet generator now creates audio/video, pitch-trace, and spectrogram evidence for the exact Eb5-versus-D5 expansion blocker.",
    ]
    if phrase_expansion_rejected_count:
        done_summary.append(f"{phrase_expansion_rejected_count} Staff 4 audited expansion is now locked as a rejected regression case.")
    if staff4_audit_ready:
        done_summary.append(f"Latest Staff 4 audit status: {staff4_audit_status.replace('_', ' ')}.")
    remaining_summary = [
        "Finish chronological active-practice coverage across the full archive.",
        "Build benchmark clips for known notes, fast runs, arpeggios, rhythm, and score boxes.",
        "Promote local clips into accepted truth items only after audio notes, score notes, octave/register, and score coordinates agree.",
        "Use review packets to convert queued score-note hypotheses into verified MusicXML notes before promoting source targets from reference-audio candidates to accepted score evidence.",
        "Replace short fragments with accurate phrase-level note and rhythm extraction.",
        "Build longer phrase candidates that survive the second-pass audio gate instead of relying on loose transition traces or reference-audio coincidences.",
        "Keep extending the accepted Staff 4 anchor only when each adjacent source note agrees with paired audio.",
        "Use the source-audio rescan and raw detected-series expansion pool to find a real adjacent Staff 4 audio run before accepting a longer phrase.",
        "Audit the next adjacent Staff 4 phrase window before accepting, rejecting, or expanding it.",
        "Align accepted phrases to score locations or score-free repeated exercise patterns.",
        "Generate heat maps and Curtis-level observations only from accepted evidence.",
    ]
    implementation_plan = [
        {
            "phase": "1",
            "label": "Full practice-time coverage",
            "status": "partial",
            "evidence": f"{checked_label} checked / {uploaded_label} video / {pending_window_count} queued windows",
            "target": "Every strict-ledger window classified as playing or non-playing.",
        },
        {
            "phase": "2",
            "label": "Truth, benchmark, and correction set",
            "status": "pending" if not (benchmark_count or rejected_score_count or score_visual_lock_count) else "partial",
            "evidence": f"{benchmark_count} benchmark corrections / {rejected_score_count} wrong-score-note regressions / {truth_item_count} stored truth items / {gold_label_count} gold labels / {gold_queue_count} queued gold clips / {truth_manifest_item_count} manifest truth checks / {truth_queue_count} queued truth checks / {score_visual_lock_count} score-visual locks / {actual_source_score_snippet_lock_count} actual-source score locks",
            "target": "Accepted truth clips for exact notes, registers, fast runs, arpeggios, repeats, rests, and score boxes.",
        },
        {
            "phase": "3",
            "label": "Verified score truth",
            "status": "partial" if local_score_source_count or symbolic_score_note_count or score_verified_count else "pending",
            "evidence": f"{score_target_count} score targets / {local_score_source_count} local PDFs / {symbolic_score_note_count} verified symbolic notes / {symbolic_score_source_snippet_count} source snippets / {score_map_candidate_glyph_count} candidate glyphs / {score_map_note_hypothesis_count} note hypotheses / {score_map_review_packet_count} review packets / {source_target_checked} source checks / {score_verified_count} exact score locations",
            "target": "Parsed score notes plus coordinates; candidate glyphs stay unaccepted until source verification converts them into MusicXML.",
        },
        {
            "phase": "4",
            "label": "One-measure acceleration gate",
            "status": "complete" if measure_match_count else "blocked",
            "evidence": f"{measure_match_count} accepted measures / {long_phrase_count} accepted long phrases / {phrase_expansion_target_count} anchored expansions / {phrase_expansion_source_rescan_run_count} source-rescan runs / {score_verified_count} exact score locations",
            "target": "First accepted measure plus outward expansion from the same verified source lane.",
        },
        {
            "phase": "5",
            "label": "Accurate phrase transcription",
            "status": "partial" if transcriptions else "pending",
            "evidence": f"{len(transcriptions)} transcription records / {transition_trace_count} hidden fast-note candidates / {long_phrase_count} accepted long phrases",
            "target": "10-30 second passages with notes, rests, rhythm, repeats, and audio agreement.",
        },
        {
            "phase": "6",
            "label": "Publication-quality notation",
            "status": "partial" if transcribed_record_count else "pending",
            "evidence": f"{transcribed_record_count} notation-ready daily records",
            "target": "Treble-clef score rendering from accepted notes only, not hand-positioned approximations.",
        },
        {
            "phase": "7",
            "label": "Score and exercise alignment",
            "status": "partial" if score_sequence_count or phrase_candidate_count else "pending",
            "evidence": f"{score_sequence_count} pitch-sequence groups / {phrase_candidate_count} phrase candidates / {source_target_count} source targets / {phrase_expansion_target_count} anchored expansions / {phrase_expansion_source_rescan_run_count} source-rescan runs / {score_verified_count} exact score locations",
            "target": "Accepted phrase groups paired with original score snippets or repeated exercise patterns.",
        },
        {
            "phase": "8",
            "label": "Heat maps and observations",
            "status": "partial" if score_heatmap_count else "blocked" if not score_verified_count else "partial",
            "evidence": f"{score_heatmap_count} score-coordinate heat-map fragments",
            "target": "Practice density, repetition density, problem density, and improvement layers.",
        },
        {
            "phase": "9",
            "label": "Regression lock",
            "status": "partial" if rejected_score_count or benchmark_count or score_visual_lock_count else "pending",
            "evidence": f"Current tests block wrong-note score evidence, broad score crops, visually unverified source crops, generated-score score panels, and non-playing practice credit; {actual_source_score_snippet_lock_count} actual-source score locks active.",
            "target": "Tests fail on mismatched audio/notation, wrong score boxes, missing media, and fake practice time.",
        },
    ]
    if phrase_expansion_current and phrase_expansion_accepted_count == 0 and phrase_expansion_ready_count:
        next_action = (
            "Review the ready Staff 4 expansion from the raw detected-series search; exact MIDI and audio agree, "
            "but accepted truth evidence is still required before display."
        )
    elif staff4_mining_status == "exact_audio_candidate":
        candidate = staff4_mining.get("bestCandidate") if isinstance(staff4_mining.get("bestCandidate"), dict) else {}
        next_action = (
            f"Audit the exact Staff 4 {candidate.get('targetDirection') or 'adjacent'} mining candidate "
            f"{candidate.get('targetSequence') or ''} before accepting it."
        )
    elif phrase_expansion_current and phrase_expansion_accepted_count == 0:
        current_direction = str(phrase_expansion_current.get("direction") or "")
        if staff4_audit_status == "blocked_audio_mismatch_confirmed" and current_direction == "right-2":
            next_action = "Record the Staff 4 right-2 expansion as rejected from the audit packet, then test the next adjacent phrase window."
        elif phrase_expansion_rejected_count:
            next_action = (
                f"Audit the current Staff 4 {current_direction or 'adjacent'} window; it is blocked at "
                f"{phrase_expansion_current.get('expectedNextScoreNote') or 'the next source note'} vs "
                f"{phrase_expansion_current.get('observedNextAudioNote') or 'current audio'} after the previous right-2 audit was locked as rejected."
            )
            if staff4_mining_status == "not_found":
                if staff4_source_rescan_anchor_status == "not_reproduced":
                    next_action = (
                        "Fix current-detector reproduction of the accepted Staff 4 anchor before widening again; "
                        "the fresh source-audio rescan did not recover the accepted "
                        f"{phrase_expansion_current.get('anchorSequence') or 'anchor'} window, and adjacent mining found no exact "
                        f"{phrase_expansion_current.get('targetSequence') or 'adjacent'} window after "
                        f"{staff4_mining_searched_count} stored/rescanned windows."
                    )
                elif staff4_source_rescan_adjacent_target_count and staff4_source_rescan_adjacent_status == "not_reproduced":
                    next_action = (
                        "Calibrate the Staff 4 adjacent note-window segmentation; source-audio rescan reproduces the anchor, "
                        f"but the first failed adjacent note is {staff4_source_rescan_adjacent_failure_note or 'unknown'} "
                        f"at best swept offset {staff4_source_rescan_adjacent_failure_offset}s; detectors heard "
                        f"{staff4_source_rescan_adjacent_first_failure.get('bestAttemptObservedConsensusNote') or 'no stable MIDI'}."
                    )
                elif staff4_source_rescan_run_count:
                    next_action = (
                        "Widen the Staff 4 source-audio rescan or improve note segmentation; exact MIDI search found no "
                        f"{phrase_expansion_current.get('targetSequence') or 'adjacent'} window after "
                        f"{staff4_mining_searched_count} stored/rescanned windows."
                    )
                else:
                    next_action = (
                        "Rescan the Staff 4 source audio around the accepted anchor; stored mining found no exact "
                        f"{phrase_expansion_current.get('targetSequence') or 'adjacent'} MIDI window yet."
                    )
        else:
            if staff4_mining_status == "not_found" and staff4_source_rescan_run_count:
                if staff4_source_rescan_anchor_status == "not_reproduced":
                    next_action = (
                        "Fix current-detector reproduction of the accepted Staff 4 anchor before widening again; "
                        "the fresh source-audio rescan did not recover the accepted "
                        f"{phrase_expansion_current.get('anchorSequence') or 'anchor'} window, and adjacent mining found no exact "
                        f"{phrase_expansion_current.get('targetSequence') or 'adjacent'} window after "
                        f"{staff4_mining_searched_count} stored/rescanned windows."
                    )
                elif staff4_source_rescan_adjacent_target_count and staff4_source_rescan_adjacent_status == "not_reproduced":
                    next_action = (
                        "Calibrate the Staff 4 adjacent note-window segmentation; source-audio rescan reproduces the anchor, "
                        f"but the first failed adjacent note is {staff4_source_rescan_adjacent_failure_note or 'unknown'} "
                        f"at best swept offset {staff4_source_rescan_adjacent_failure_offset}s; detectors heard "
                        f"{staff4_source_rescan_adjacent_first_failure.get('bestAttemptObservedConsensusNote') or 'no stable MIDI'}."
                    )
                else:
                    next_action = (
                        "Widen the Staff 4 source-audio rescan or improve note segmentation; exact MIDI search found no "
                        f"{phrase_expansion_current.get('targetSequence') or 'adjacent'} window after "
                        f"{staff4_mining_searched_count} stored/rescanned windows."
                    )
            else:
                next_action = (
                    "Keep the accepted Staff 4 source lane fixed; expansion is blocked at "
                    f"{phrase_expansion_current.get('expectedNextScoreNote') or 'the next source note'} vs "
                    f"{phrase_expansion_current.get('observedNextAudioNote') or 'current audio'} after searching "
                    f"{phrase_expansion_audio_run_count} audio-note runs."
                )
    elif not measure_match_count:
        next_action = "Convert one local source-score measure into verified symbolic notes, then run the existing phrase matcher over hidden detected series."
    elif not long_phrase_count:
        next_action = "Extend the accepted source-backed measure into longer phrases and score-coordinate heat maps."
    elif source_target_sequence and source_target_checked and not source_target_verified:
        next_action = (
            "Use IMSLP staff review packets to verify score-note hypotheses into MusicXML before promoting "
            f"{source_target_sequence}; current exact-MIDI source overlap is {source_target_best_overlap}/{source_target_note_count}."
        )
    elif source_target_sequence:
        next_action = (
            f"Verify the {source_target_note_count}-note source target {source_target_sequence} against the local IMSLP score, "
            "then promote only if the score notes and crop match."
        )
    else:
        next_action = "Extend the accepted score-coordinate phrase into longer passages, repeated attempts, and problem-density layers."
    return {
        "status": "partial" if completed_points else "pending",
        "completionPercent": completion_percent,
        "completionLabel": f"{completion_percent}%",
        "completionExactPercent": completion_exact_percent,
        "completionExactLabel": completion_exact_label,
        "completedPoints": completed_points,
        "completedPointsLabel": completed_points_label,
        "totalPoints": total_weight,
        "basis": "100-point implementation gate checklist for solved long-phrase transcription; not a playing-readiness score.",
        "implementationSummary": implementation_summary,
        "implementationCurrent": implementation_current,
        "doneSummary": done_summary,
        "remainingSummary": remaining_summary,
        "implementationPlan": implementation_plan,
        "longPhraseAcceptedCount": long_phrase_count,
        "acceptedMeasureMatchCount": measure_match_count,
        "scoreHeatmapFragmentCount": score_heatmap_count,
        "referencePhraseCandidateCount": phrase_candidate_count,
        "phraseExpansionHarness": phrase_expansion,
        "phraseExpansionTargetCount": phrase_expansion_target_count,
        "phraseExpansionAcceptedCount": phrase_expansion_accepted_count,
        "phraseExpansionReadyForReviewCount": phrase_expansion_ready_count,
        "phraseExpansionBlockedCount": phrase_expansion_blocked_count,
        "phraseExpansionRejectedRegressionCount": phrase_expansion_rejected_count,
        "phraseExpansionAudioRunCount": phrase_expansion_audio_run_count,
        "phraseExpansionRawAudioRunCount": phrase_expansion_raw_audio_run_count,
        "phraseExpansionSourceAudioRescanRunCount": phrase_expansion_source_rescan_run_count,
        "phraseExpansionCurrentStatus": str(phrase_expansion_current.get("status") or ""),
        "staff4SourceAudioRescan": staff4_source_rescan,
        "staff4SourceAudioRescanStatus": staff4_source_rescan_status,
        "staff4SourceAudioRescanRunCount": staff4_source_rescan_run_count,
        "staff4SourceAudioRescanEventCount": staff4_source_rescan_event_count,
        "staff4SourceAudioRescanAnchorStatus": staff4_source_rescan_anchor_status,
        "staff4SourceAudioRescanAnchorReproducedCount": staff4_source_rescan_anchor_count,
        "staff4SourceAudioRescanAnchorTargetCount": staff4_source_rescan_anchor_target_count,
        "staff4SourceAudioRescanAdjacentStatus": staff4_source_rescan_adjacent_status,
        "staff4SourceAudioRescanAdjacentReproducedCount": staff4_source_rescan_adjacent_count,
        "staff4SourceAudioRescanAdjacentTargetCount": staff4_source_rescan_adjacent_target_count,
        "staff4SourceAudioRescanAdjacentFirstFailure": staff4_source_rescan_adjacent_first_failure,
        "staff4AdjacentMining": staff4_mining,
        "staff4AdjacentMiningStatus": staff4_mining_status,
        "staff4AdjacentMiningSearchedWindowCount": staff4_mining_searched_count,
        "staff4AdjacentMiningExactCandidateCount": staff4_mining_exact_count,
        "staff4AdjacentMiningNearestSequence": str(staff4_mining_nearest.get("windowSequence") or ""),
        "staff4PhraseAudit": staff4_audit,
        "staff4PhraseAuditStatus": staff4_audit_status,
        "staff4PhraseAuditPacketId": staff4_audit.get("packetId") or "",
        "sourceVerificationTargetCount": source_target_count,
        "sourceVerificationTargets": source_targets,
        "sourceVerificationTargetTop": source_target_top,
        "sourceVerificationTargetTopSequence": source_target_sequence,
        "sourceVerificationTargetCheckedCount": source_target_checked,
        "sourceVerificationTargetVerifiedCount": source_target_verified,
        "sourceVerificationTargetTopChecked": bool(source_target_top.get("sourceScoreChecked")),
        "sourceVerificationTargetTopVerified": bool(source_target_top.get("sourceScoreVerified")),
        "sourceVerificationTargetTopStatus": source_target_check_status,
        "sourceVerificationTargetTopBestSourceOverlap": source_target_best_overlap,
        "exactScoreAlignedWindowCount": score_verified_count,
        "referencePhraseCandidateTop": phrase_candidate_top,
        "referencePhraseCandidateTopSequence": phrase_candidate_sequence,
        "localScoreSourceCount": local_score_source_count,
        "symbolicScoreNoteCount": symbolic_score_note_count,
        "symbolicScoreSourceSnippetCount": symbolic_score_source_snippet_count,
        "scoreMapCandidateGlyphCount": score_map_candidate_glyph_count,
        "scoreMapCandidateStaffCount": score_map_candidate_staff_count,
        "scoreMapNoteHypothesisCount": score_map_note_hypothesis_count,
        "scoreMapNoteHypothesisStaffCount": score_map_note_hypothesis_staff_count,
        "scoreMapReviewPacketCount": score_map_review_packet_count,
        "scoreVisualAgreementCount": score_visual_lock_count,
        "actualSourceScoreSnippetCount": actual_source_score_snippet_lock_count,
        "truthWorkbench": truth_workbench,
        "truthItemCount": truth_item_count,
        "acceptedTruthItemCount": truth_ready_count,
        "scoreReadyTruthItemCount": score_truth_ready_count,
        "truthQueueCount": truth_queue_count,
        "truthManifestStatus": truth_manifest_status,
        "truthManifestItemCount": truth_manifest_item_count,
        "truthManifestSourceVerifiedCount": truth_manifest_source_verified_count,
        "truthManifestPositiveSourcePhraseCount": truth_manifest_positive_count,
        "truthManifestPositiveSourcePhraseVerifiedCount": truth_manifest_positive_verified_count,
        "truthManifestRejectedRegressionPhraseCount": truth_manifest_rejected_count,
        "truthManifestRejectedRegressionBlockedCount": truth_manifest_rejected_blocked_count,
        "truthManifestLiveAcceptedPhraseCount": truth_manifest_live_phrase_count,
        "goldReviewLabelCount": gold_label_count,
        "goldReviewAcceptedCount": gold_accepted_count,
        "goldReviewRejectedCount": gold_rejected_count,
        "goldReviewQueueCount": gold_queue_count,
        "goldReviewAcceptedAudioPhraseCount": gold_accepted_audio_phrase_count,
        "goldReviewAcceptedScorePhraseCount": gold_accepted_score_phrase_count,
        "transitionTraceCandidateCount": transition_trace_count,
        "pitchSequenceGroupCount": score_sequence_count,
        "checkedVideoLabel": checked_label if checked_label != "0s" else "",
        "uploadedVideoLabel": uploaded_label if uploaded_label != "unknown" else "",
        "activePracticeLabel": active_label if active_label != "pending" else "",
        "estimatedTotalPracticeLabel": estimate_label if estimate_label != "pending" else "",
        "activeIntervalCount": active_interval_count,
        "sampleResultCount": sample_result_count,
        "activeViolinSampleCount": active_sample_count,
        "checkedNoViolinSampleCount": checked_no_violin_count,
        "pendingWindowCount": pending_window_count,
        "doneItems": [item["done"] for item in gates if item["points"] > 0],
        "remainingItems": [item["remaining"] for item in gates if item["points"] < item["weight"]],
        "gates": gates,
        "nextAction": next_action,
    }


def derive_review(
    inventory: dict[str, list[dict[str, Any]]],
    existing: dict[str, Any] | None = None,
    media_samples: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = existing or {}
    state = state or {}
    media_samples = media_samples or []
    today = today_local_day()
    sections = existing.get("notableSections") if isinstance(existing.get("notableSections"), list) else []
    findings = sanitized_findings(existing.get("skillFindings") if isinstance(existing.get("skillFindings"), list) else [])
    raw_pieces = existing.get("pieces") if isinstance(existing.get("pieces"), list) else []
    source_label_pieces = accepted_source_pieces(state, inventory, media_samples)
    pieces = enriched_pieces([*source_label_pieces, *raw_pieces], today, media_samples)
    today_pieces = [piece for piece in pieces if piece.get("isActiveToday")]
    piece_results = review_piece_results(state, existing)
    training = source_training_state(state, inventory, media_samples, piece_results)
    practice_totals = build_practice_totals(inventory)
    practice_study = build_practice_study(state, inventory, media_samples, pieces, practice_totals)
    transcriptions = transcription_items(state)
    active_practice_coverage = build_active_practice_coverage(
        inventory,
        media_samples,
        transcriptions,
        sections,
        state.get("activePracticeScan") if isinstance(state.get("activePracticeScan"), dict) else {},
    )
    daily_records = build_daily_records(
        state,
        inventory,
        media_samples,
        transcriptions,
        sections,
        active_practice_coverage=active_practice_coverage,
    )
    repertoire_evidence = build_repertoire_evidence(daily_records)
    evidence_progress = build_evidence_progress(state)
    truth_workbench = build_truth_workbench(state, daily_records, evidence_progress)
    gold_review = build_gold_review_loop(state, daily_records)
    staff4_phrase_audit = (
        state.get("staff4PhraseAuditLatest")
        if isinstance(state.get("staff4PhraseAuditLatest"), dict)
        else {}
    )
    transcription_completion = build_transcription_completion(
        training,
        daily_records,
        repertoire_evidence,
        active_practice_coverage,
        evidence_progress,
        media_samples,
        transcriptions,
        truth_workbench,
        gold_review,
        staff4_phrase_audit,
    )
    current_staff4_phrase_audit = latest_staff4_phrase_audit_packet_for_completion(state, transcription_completion)
    if current_staff4_phrase_audit != staff4_phrase_audit:
        staff4_phrase_audit = current_staff4_phrase_audit
        transcription_completion = build_transcription_completion(
            training,
            daily_records,
            repertoire_evidence,
            active_practice_coverage,
            evidence_progress,
            media_samples,
            transcriptions,
            truth_workbench,
            gold_review,
            staff4_phrase_audit,
        )
    progress_plan = existing.get("progressPlan") if isinstance(existing.get("progressPlan"), dict) else None
    youtube_items = inventory.get("youtube", [])
    practice_candidates = [
        item
        for item in youtube_items
        if isinstance(item, dict) and item.get("practiceCandidate")
    ]
    long_form_candidates = [
        item
        for item in practice_candidates
        if isinstance(item.get("durationSeconds"), int) and item["durationSeconds"] >= 20 * 60
    ]
    reviewed_urls = {
        section.get("url")
        for section in sections
        if isinstance(section, dict) and section.get("url")
    }
    current_work = "No processed video sections."
    if practice_candidates and not sections:
        current_work = "Practice corpus indexed. Section listening pending."
    elif sections:
        current_work = existing.get("currentWork") or "Section evidence recorded."
    if pieces and str(pieces[0].get("confidence") or "") == "clear":
        current_work = f"Piece identified: {pieces[0]['title']}"
    media_access = existing.get("mediaAccess")
    if media_access not in {"blocked", "sample_ready"}:
        media_access = "metadata_only"
    return {
        "reviewedVideoCount": len(reviewed_urls),
        "notableSections": sections,
        "skillFindings": findings,
        "pieces": pieces,
        "today": today,
        "todayPiece": today_pieces[0] if today_pieces else None,
        "todayPieceCount": len(today_pieces),
        "training": training,
        "practiceTotals": practice_totals,
        "practiceStudy": practice_study,
        "dailyRecords": daily_records,
        "activePracticeCoverage": active_practice_coverage,
        "evidenceProgress": evidence_progress,
        "truthWorkbench": truth_workbench,
        "goldReview": gold_review,
        "staff4PhraseAudit": staff4_phrase_audit,
        "transcriptionCompletion": transcription_completion,
        "repertoireEvidence": repertoire_evidence,
        "progressPlan": progress_plan,
        "currentWork": current_work,
        "strongestSignal": "Unjudged",
        "weakestRecurringSignal": "Unjudged",
        "inventoryCount": sum(len(items) for items in inventory.values()),
        "practiceCandidateCount": len(practice_candidates),
        "longFormCandidateCount": len(long_form_candidates),
        "latestPracticeCandidate": practice_candidates[0] if practice_candidates else None,
        "mediaAccess": media_access,
    }


def base_ops(state: dict[str, Any], extra_blockers: list[str] | None = None) -> dict[str, Any]:
    credentials = credential_state()
    sources = effective_sources(state)
    blockers = list(extra_blockers or [])
    has_any_source = bool(sources.get("youtube") or sources.get("instagram"))
    if not credentials["openai"]:
        blockers.append("missing_openai_api_key")
    if not has_any_source and not sources.get("youtube"):
        blockers.append("missing_youtube_source")
    if not has_any_source and not sources.get("instagram"):
        blockers.append("missing_instagram_source")

    inventory = state.get("inventory", {"youtube": [], "instagram": []})
    media_samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    transcriptions = transcription_items(state)
    review = derive_review(inventory, state.get("review"), media_samples, state)
    hard_blockers = inventory_blockers(blockers)
    status = "blocked" if hard_blockers else "ready"
    if not hard_blockers and review.get("inventoryCount"):
        status = "inventory_ready"

    sample_index = [
        {
            "id": sample.get("id"),
            "url": sample.get("url"),
            "title": sample.get("title"),
            "window": sample.get("window"),
            "createdAt": sample.get("createdAt"),
            "source": sample.get("source"),
            "sizeBytes": sample.get("sizeBytes"),
            "violinPresence": sample.get("violinPresence"),
            "practiceEvidenceStatus": sample.get("practiceEvidenceStatus"),
            "containsViolin": sample.get("containsViolin"),
            "violinSamplerScore": sample.get("violinSamplerScore"),
            "violinSamplerVersion": sample.get("violinSamplerVersion"),
        }
        for sample in media_samples
        if sample.get("id")
    ]

    return {
        "service": SERVICE_NAME,
        "status": status,
        "checkedAt": utc_now(),
        "model": {
            "id": OPENAI_MODEL,
            "audioId": OPENAI_AUDIO_MODEL,
            "pieceVerifyId": OPENAI_PIECE_VERIFY_MODEL,
            "visionId": OPENAI_VISION_MODEL,
            "reasoningEffort": OPENAI_REASONING_EFFORT,
        },
        "credentials": credentials,
        "auth": {
            "youtube": youtube_auth_status(),
        },
        "sources": sources,
        "inventory": inventory,
        "review": review,
        "media": {
            "lastMediaRun": state.get("lastMediaRun"),
            "lastTranscriptionRun": state.get("lastTranscriptionRun"),
            "sampleCount": len(media_samples),
            "sampleIndex": sample_index,
            "samples": media_samples[:5],
            "transcriptionCount": len(transcriptions),
            "transcriptions": [
                {
                    "transcriptionId": item.get("transcriptionId"),
                    "sampleId": item.get("sampleId"),
                    "sourceTitle": item.get("sourceTitle"),
                    "sourceWindow": item.get("sourceWindow"),
                    "status": item.get("status"),
                    "noteCount": item.get("noteCount"),
                    "tempoBpm": item.get("tempoBpm"),
                    "acceptedTitle": item.get("acceptedTitle"),
                    "referenceMatches": item.get("referenceMatches", [])[:3]
                    if isinstance(item.get("referenceMatches"), list)
                    else [],
                    "firstNotes": item.get("fingerprint", {}).get("firstNotes", [])[:16]
                    if isinstance(item.get("fingerprint"), dict)
                    else [],
                }
                for item in transcriptions[:5]
            ],
        },
        "analysis": state.get("lastAnalysisRun"),
        "coach": state.get("lastCoachRun"),
        "pieceId": state.get("lastPieceIdRun"),
        "lastScan": state.get("lastScan"),
        "blockers": stable_unique(blockers),
    }


async def run_scan(incoming_sources: dict[str, Any] | None = None) -> dict[str, Any]:
    state = load_state()
    if incoming_sources:
        state["sources"] = {
            **state.get("sources", {}),
            **{key: value for key, value in incoming_sources.items() if value is not None},
        }

    sources = effective_sources(state)
    blockers: list[str] = []
    errors: list[dict[str, str]] = []
    inventory = {"youtube": [], "instagram": []}
    has_any_source = bool(sources.get("youtube") or sources.get("instagram"))

    if sources.get("youtube"):
        try:
            youtube_result = await fetch_youtube_inventory(str(sources.get("youtube", "")))
            inventory["youtube"] = youtube_result.items
            blockers.extend(youtube_result.blockers)
        except httpx.HTTPStatusError as exc:
            blockers.append("youtube_api_error")
            errors.append({"platform": "youtube", "detail": exc.response.text[:500]})
        except Exception as exc:  # pragma: no cover - defensive service boundary
            blockers.append("youtube_scan_failed")
            errors.append({"platform": "youtube", "detail": str(exc)[:500]})

    if sources.get("instagram"):
        try:
            instagram_result = await fetch_instagram_inventory(str(sources.get("instagram", "")))
            inventory["instagram"] = instagram_result.items
            blockers.extend(instagram_result.blockers)
        except httpx.HTTPStatusError as exc:
            blockers.append("instagram_api_error")
            errors.append({"platform": "instagram", "detail": exc.response.text[:500]})
        except Exception as exc:  # pragma: no cover - defensive service boundary
            blockers.append("instagram_scan_failed")
            errors.append({"platform": "instagram", "detail": str(exc)[:500]})

    if not has_any_source:
        blockers.extend(["missing_youtube_source", "missing_instagram_source"])

    await refresh_public_reference_corpus(state)
    state["inventory"] = inventory
    media_samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    state["review"] = derive_review(inventory, state.get("review"), media_samples, state)

    run = {
        "startedAt": utc_now(),
        "status": "blocked" if inventory_blockers(blockers) else "inventory_ready",
        "inventoryCount": sum(len(items) for items in inventory.values()),
        "blockers": stable_unique(blockers),
        "errors": errors,
    }
    append_run(state, run)
    save_state(state)
    return base_ops(state, blockers)
