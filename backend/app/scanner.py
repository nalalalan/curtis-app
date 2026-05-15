from __future__ import annotations

import os
import re
from datetime import datetime, timezone
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
    REQUIRE_SOURCE_CONFIRMED_PIECE_TITLES,
    SERVICE_NAME,
)
from .state import append_run, load_state, save_state, utc_now
from .daily_records import build_daily_records, build_repertoire_evidence, exact_score_location_ready
from .evidence_ledger import build_active_practice_coverage, build_evidence_progress, build_truth_progress
from .study_packets import build_practice_study, build_practice_totals
from .symbolic_scores import (
    longest_common_contiguous_run,
    normalize_pitch_class,
    score_map_candidate_audit,
    symbolic_score_from_target,
)

DEFAULT_YOUTUBE_SOURCE = "https://www.youtube.com/@nalalan"
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
        total += int(transcription.get("scoreSequenceMatchCount") or 0)
    return total


def score_location_verified_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
        total += int(transcription.get("scoreLocationVerifiedCount") or 0)
    return total


def score_visual_agreement_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
        total += sum(1 for group in groups if isinstance(group, dict) and actual_source_score_snippet_ready(group))
    return total


def actual_source_score_snippet_ready(match: dict[str, Any]) -> bool:
    if not isinstance(match, dict):
        return False
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    image_url = str(score.get("imageUrl") or "").strip()
    if not image_url or image_url.startswith("data:"):
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
    return bool(match.get("scoreVisualAgreement") is True)


def actual_source_score_snippet_count(daily_records: dict[str, Any]) -> int:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    total = 0
    for record in records:
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
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
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
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
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
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
    source_values = [normalize_pitch_class(note.get("pitchClass")) for note in notes if isinstance(note, dict)]
    source_values = [value for value in source_values if value]
    query_values = [normalize_pitch_class(value) for value in str(sequence or "").split()]
    query_values = [value for value in query_values if value]
    score_config = target.get("symbolicScore") if isinstance(target.get("symbolicScore"), dict) else {}
    if not query_values:
        return {
            "sourceScoreChecked": False,
            "sourceScoreVerified": False,
            "sourceScoreCheckStatus": "source_score_sequence_missing",
            "sourceScoreBestOverlap": 0,
            "sourceScoreLimit": "No detected pitch-class sequence is available to verify against the score.",
        }
    if not source_values:
        return {
            "sourceScoreChecked": False,
            "sourceScoreVerified": False,
            "sourceScoreCheckStatus": "source_score_map_missing",
            "sourceScoreBestOverlap": 0,
            "sourceScoreLimit": "No verified symbolic score map is available for this source target.",
        }
    overlap = longest_common_contiguous_run(query_values, source_values)
    overlap_length = int(overlap.get("length") or 0)
    verified = overlap_length >= len(query_values)
    reference_start = int(overlap.get("referenceStart") or 0)
    reference_end = reference_start + overlap_length
    return {
        "sourceScoreChecked": True,
        "sourceScoreVerified": verified,
        "sourceScoreCheckStatus": "source_score_sequence_verified" if verified else "source_score_sequence_not_found",
        "sourceScoreBestOverlap": overlap_length,
        "sourceScoreQueryLength": len(query_values),
        "sourceScoreReferenceLength": len(source_values),
        "sourceScoreSourceId": str(score.get("sourceId") or score_config.get("sourceId") or ""),
        "sourceScoreTitle": str(score.get("title") or target.get("work") or ""),
        "sourceScoreCandidateGlyphCount": int(candidate_audit.get("scoreMapCandidateGlyphCount") or 0),
        "sourceScoreCandidateStaffCount": int(candidate_audit.get("scoreMapCandidateStaffCount") or 0),
        "sourceScoreNoteHypothesisCount": int(candidate_audit.get("scoreMapNoteHypothesisCount") or 0),
        "sourceScoreNoteHypothesisStaffCount": int(candidate_audit.get("scoreMapNoteHypothesisStaffCount") or 0),
        "sourceScoreReviewPacketCount": int(candidate_audit.get("scoreMapReviewPacketCount") or 0),
        "sourceScoreCandidateStatus": str(candidate_audit.get("status") or ""),
        "sourceScoreReferenceSequence": " ".join(source_values),
        "sourceScoreBestOverlapSequence": " ".join(source_values[reference_start:reference_end]),
        "sourceScoreLimit": (
            "Exact detected sequence exists in the verified symbolic score map; crop coordinates still need review before accepted display."
            if verified
            else "Checked against the current verified symbolic score map; this sequence is not present, so it remains reference-audio only and not accepted score evidence until the score map is extended."
        ),
    }


def source_verification_targets(daily_records: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    records = daily_records.get("records") if isinstance(daily_records.get("records"), list) else []
    candidates: dict[tuple[str, str, str, int, int, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        practice_day = str(record.get("practiceDay") or record.get("date") or "")
        groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
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


def build_truth_workbench(
    state: dict[str, Any],
    daily_records: dict[str, Any],
    evidence_progress: dict[str, Any],
    limit: int = 12,
) -> dict[str, Any]:
    truth_progress = build_truth_progress(state)
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
        "status": "ready" if source_targets or benchmarks or truth_progress.get("truthItemCount") else "empty",
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
        "queuedItems": queued_items[: max(0, int(limit))],
        "acceptanceRule": "Accepted score evidence needs local media, accepted audio notes, verified source-score notes, exact note-and-octave agreement, and verified score coordinates.",
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
    if len({value for value in detected.split() if value}) < 3:
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
) -> dict[str, Any]:
    truth_workbench = truth_workbench or {}
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
    truth_route_ready = str(truth_workbench.get("version") or "") == "truth_workbench_v1"
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
            + min(1.0, truth_queue_count * 0.25)
            + min(1.0, truth_ready_count * 0.5)
            + (0.75 if score_visual_lock_count else 0)
            + (0.75 if actual_source_score_snippet_lock_count else 0),
            f"{benchmark_count} benchmark corrections / {rejected_score_count} wrong-score-note regressions / {truth_queue_count} queued truth checks / {truth_ready_count} accepted truth items / {score_visual_lock_count} score-visual locks / {actual_source_score_snippet_lock_count} actual-source score locks",
            "Rejected score-note mistakes can be stored as regression evidence, and score panels now require verified visible noteheads, range, spelling, an actual source-score crop, and truth-set promotion.",
            "Build accepted truth clips for notes, rhythm, score boxes, and full phrases.",
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
            + min(2, long_phrase_count * 2),
            f"{len(transcriptions)} transcription records / {transcribed_record_count} notation-ready daily records / {audio_record_count} audio-evidence records",
            "Short audio-checked fragments exist; failed broad transcription stays hidden.",
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
            + (1 if source_target_note_count >= 7 else 0)
            + (2 if score_verified_count else 0)
            + (1 if measure_match_count else 0)
            + min(2, long_phrase_count * 2),
            f"{score_sequence_count} pitch-sequence groups / {phrase_candidate_count} phrase candidates / {source_target_count} source targets / {score_verified_count} exact score locations",
            "Pitch-sequence groups are separated from exact score evidence.",
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
        else "Practice-time scanning is working. The long-phrase path has source-verification targets and staff review packets, but accepted score/audio phrase evidence is currently zero after the mismatched score crop was demoted."
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
            "label": "Long phrases",
            "value": str(long_phrase_count),
            "detail": "accepted",
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
                f"{source_target_best_overlap}/{source_target_note_count} source overlap"
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
        "Local score-glyph candidates are queued for verification without being accepted as score evidence.",
        "Likely score noteheads now receive unaccepted staff-position pitch hypotheses before MusicXML review.",
        "Staff-level source review packets now map queued hypotheses back to the scanned score.",
        "Score panels require visible score noteheads, range, spelling, exact note-and-octave agreement, and an actual source-score crop before display.",
        "A truth workbench now separates queued, accepted, and rejected audio-score-transcription evidence before anything can become visible score evidence.",
    ]
    remaining_summary = [
        "Finish chronological active-practice coverage across the full archive.",
        "Build benchmark clips for known notes, fast runs, arpeggios, rhythm, and score boxes.",
        "Promote local clips into accepted truth items only after audio notes, score notes, octave/register, and score coordinates agree.",
        "Use review packets to convert queued score-note hypotheses into verified MusicXML notes before promoting source targets from reference-audio candidates to accepted score evidence.",
        "Replace short fragments with accurate phrase-level note and rhythm extraction.",
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
            "evidence": f"{benchmark_count} benchmark corrections / {rejected_score_count} wrong-score-note regressions / {truth_item_count} stored truth items / {truth_queue_count} queued truth checks / {score_visual_lock_count} score-visual locks / {actual_source_score_snippet_lock_count} actual-source score locks",
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
            "evidence": f"{measure_match_count} accepted measures / {long_phrase_count} accepted long phrases / {score_verified_count} exact score locations",
            "target": "First accepted measure: exact symbolic score notes, local audio/video, and matching transcription.",
        },
        {
            "phase": "5",
            "label": "Accurate phrase transcription",
            "status": "partial" if transcriptions else "pending",
            "evidence": f"{len(transcriptions)} transcription records / {long_phrase_count} accepted long phrases",
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
            "evidence": f"{score_sequence_count} pitch-sequence groups / {phrase_candidate_count} phrase candidates / {source_target_count} source targets / {score_verified_count} exact score locations",
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
        "nextAction": (
            "Convert one local source-score measure into verified symbolic notes, then run the existing phrase matcher over hidden detected series."
            if not measure_match_count
            else "Extend the accepted source-backed measure into longer phrases and score-coordinate heat maps."
            if not long_phrase_count
            else (
                f"Use IMSLP staff review packets to verify score-note hypotheses into MusicXML before promoting {source_target_sequence}; current source overlap is {source_target_best_overlap}/{source_target_note_count}."
                if source_target_checked and not source_target_verified and source_target_sequence
                else f"Verify the {source_target_note_count}-note source target {source_target_sequence} against the local IMSLP score, then promote only if the score notes and crop match."
            )
            if source_target_sequence
            else "Extend the accepted score-coordinate phrase into longer passages, repeated attempts, and problem-density layers."
        ),
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
    daily_records = build_daily_records(state, inventory, media_samples, transcriptions, sections)
    repertoire_evidence = build_repertoire_evidence(daily_records)
    active_practice_coverage = build_active_practice_coverage(
        inventory,
        media_samples,
        transcriptions,
        sections,
        state.get("activePracticeScan") if isinstance(state.get("activePracticeScan"), dict) else {},
    )
    evidence_progress = build_evidence_progress(state)
    truth_workbench = build_truth_workbench(state, daily_records, evidence_progress)
    transcription_completion = build_transcription_completion(
        training,
        daily_records,
        repertoire_evidence,
        active_practice_coverage,
        evidence_progress,
        media_samples,
        transcriptions,
        truth_workbench,
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
