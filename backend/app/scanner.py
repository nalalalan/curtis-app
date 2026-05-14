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
from .daily_records import build_daily_records, build_repertoire_evidence
from .evidence_ledger import build_active_practice_coverage, build_evidence_progress
from .study_packets import build_practice_study, build_practice_totals

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
) -> dict[str, Any]:
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
    benchmark_count = int(evidence_progress.get("benchmarkCount") or 0)
    rejected_score_count = int(evidence_progress.get("wrongScoreNoteRegressionCount") or 0)
    repertoire_entries = repertoire_evidence.get("entries") if isinstance(repertoire_evidence.get("entries"), list) else []
    score_target_count = int(training.get("scoreReferenceTargetCount") or training.get("sourceConfirmedScoreTargetCount") or 0)
    long_phrase_count = 0

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
            "Correction and benchmark loop",
            6,
            (1.5 if benchmark_count else 0) + (0.5 if rejected_score_count else 0),
            f"{benchmark_count} benchmark corrections / {rejected_score_count} wrong-score-note regressions",
            "Rejected score-note mistakes can be stored as regression evidence.",
            "Build a larger benchmark suite for notes, rhythm, score boxes, and full phrases.",
        ),
        roadmap_gate(
            "score-truth",
            "Verified score library and note coordinates",
            15,
            (1.5 if score_target_count else 0) + (4 if score_verified_count else 0),
            f"{score_target_count} score targets / {score_verified_count} score-location-verified notes",
            "Source-confirmed pieces can seed score targets.",
            "Scherzo-Tarantelle needs verified symbolic notes plus rendered score coordinates.",
        ),
        roadmap_gate(
            "single-note-anchor",
            "Verified single-note score anchor",
            5,
            5 if score_verified_count else 0,
            f"{score_verified_count} verified score locations",
            "No accepted one-note score crop is currently visible.",
            "A displayed A from audio must be matched to an actual score-side A.",
        ),
        roadmap_gate(
            "note-rhythm-engine",
            "Accurate note and rhythm extraction",
            18,
            (1 if transcriptions else 0) + (1 if transcribed_record_count else 0) + (1 if audio_record_count else 0),
            f"{len(transcriptions)} transcription records / {transcribed_record_count} notation-ready daily records / {audio_record_count} audio-evidence records",
            "Short audio-checked fragments exist; failed broad transcription stays hidden.",
            "Fast runs, arpeggios, repeated notes, rests, rhythm, and full active windows remain unsolved.",
        ),
        roadmap_gate(
            "notation-rendering",
            "Professional notation rendering",
            6,
            1 if transcribed_record_count else 0,
            f"{transcribed_record_count} notation-ready daily records",
            "Notation is gated so failed transcription is not displayed as accepted evidence.",
            "Replace fragile hand-built notation with publication-quality rendering for accepted phrases.",
        ),
        roadmap_gate(
            "score-pattern-alignment",
            "Score or exercise-pattern alignment",
            8,
            1.5 if score_sequence_match_count(daily_records) else 0,
            f"{score_sequence_count} pitch-sequence groups / {score_verified_count} exact score locations",
            "Pitch-sequence groups are separated from exact score evidence.",
            "Exact score locations and score-free exercise grouping remain open.",
        ),
        roadmap_gate(
            "repeat-heatmap",
            "Repeat grouping and heat maps",
            3,
            0.5 if score_sequence_count else 0,
            "Heat-map scaffolds exist, but score-coordinate heat maps are not accepted.",
            "Display density, repetition, problem, and improvement layers on verified score or pattern coordinates.",
            "Score-coordinate heat maps require accepted phrase locations first.",
        ),
        roadmap_gate(
            "repertoire-observation",
            "Repertoire and Curtis-level observations",
            3,
            1 if repertoire_entries else 0,
            f"{len(repertoire_entries)} repertoire entries / {long_phrase_count} accepted long phrases",
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
        "Practice-time scanning is working. Long-phrase transcription, verified score alignment, and score-coordinate heat maps are still open."
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
            "detail": "exact locations accepted",
        },
        {
            "label": "Long phrases",
            "value": str(long_phrase_count),
            "detail": "accepted",
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
    ]
    remaining_summary = [
        "Finish chronological active-practice coverage across the full archive.",
        "Build benchmark clips for known notes, fast runs, arpeggios, rhythm, and score boxes.",
        "Verify symbolic score notes and score coordinates before any score crop can render.",
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
            "label": "Benchmark and correction set",
            "status": "pending" if not benchmark_count else "partial",
            "evidence": f"{benchmark_count} benchmark corrections / {rejected_score_count} wrong-score-note regressions",
            "target": "Gold clips for A/D anchors, fast runs, arpeggios, repeats, rests, and score boxes.",
        },
        {
            "phase": "3",
            "label": "Verified score truth",
            "status": "pending" if not score_verified_count else "partial",
            "evidence": f"{score_target_count} score targets / {score_verified_count} exact score locations",
            "target": "Parsed score notes plus coordinates; no visual crop unless the boxed note is verified.",
        },
        {
            "phase": "4",
            "label": "Accurate phrase transcription",
            "status": "partial" if transcriptions else "pending",
            "evidence": f"{len(transcriptions)} transcription records / {long_phrase_count} accepted long phrases",
            "target": "10-30 second passages with notes, rests, rhythm, repeats, and audio agreement.",
        },
        {
            "phase": "5",
            "label": "Publication-quality notation",
            "status": "partial" if transcribed_record_count else "pending",
            "evidence": f"{transcribed_record_count} notation-ready daily records",
            "target": "Treble-clef score rendering from accepted notes only, not hand-positioned approximations.",
        },
        {
            "phase": "6",
            "label": "Score and exercise alignment",
            "status": "partial" if score_sequence_count else "pending",
            "evidence": f"{score_sequence_count} pitch-sequence groups / {score_verified_count} exact score locations",
            "target": "Accepted phrase groups paired with original score snippets or repeated exercise patterns.",
        },
        {
            "phase": "7",
            "label": "Heat maps and observations",
            "status": "blocked" if not score_verified_count else "partial",
            "evidence": "Score-coordinate heat maps wait for accepted phrase locations.",
            "target": "Practice density, repetition density, problem density, and improvement layers.",
        },
        {
            "phase": "8",
            "label": "Regression lock",
            "status": "partial" if rejected_score_count or benchmark_count else "pending",
            "evidence": "Current tests block wrong-note score evidence and non-playing practice credit.",
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
        "exactScoreAlignedWindowCount": score_verified_count,
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
            "Queue-only owner sync from the active-scan pending list, then rerun active-practice scan."
            if pending_window_count
            else "Expand accepted phrase transcription only after active coverage and score truth gates advance."
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
    transcription_completion = build_transcription_completion(
        training,
        daily_records,
        repertoire_evidence,
        active_practice_coverage,
        evidence_progress,
        media_samples,
        transcriptions,
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
