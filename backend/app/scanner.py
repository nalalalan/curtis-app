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
    item_stale_after_source_correction,
    source_requires_confirmed_acceptance,
    title_rejected_for_item,
    youtube_video_id,
)
from .platforms import credential_state, fetch_instagram_inventory, fetch_youtube_inventory
from .settings import (
    OPENAI_AUDIO_MODEL,
    OPENAI_MODEL,
    OPENAI_PIECE_VERIFY_MODEL,
    OPENAI_REASONING_EFFORT,
    OPENAI_VISION_MODEL,
    SERVICE_NAME,
)
from .state import append_run, load_state, save_state, utc_now

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


def correction_matches_sample(correction: dict[str, Any], sample: dict[str, Any]) -> bool:
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
                "tip": "Haydn finale: light bow, even rhythm.",
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
                        "tip": "Haydn finale: light bow, even rhythm.",
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


def merge_enriched_pieces(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for piece in pieces:
        key = str(piece.get("title") or "Piece being identified").lower()
        current = merged.get(key)
        if current is None:
            merged[key] = piece
            continue
        current["sectionCount"] = int(current.get("sectionCount") or 0) + int(piece.get("sectionCount") or 0)
        current["completionPercent"] = max(int(current.get("completionPercent") or 0), int(piece.get("completionPercent") or 0))
        current["todayCompletionPercent"] = max(
            int(current.get("todayCompletionPercent") or 0),
            int(piece.get("todayCompletionPercent") or 0),
        )
        current["tip"] = better_tip(str(current.get("tip") or ""), str(piece.get("tip") or ""))
        current["todayTip"] = better_tip(str(current.get("todayTip") or ""), str(piece.get("todayTip") or ""))
        evidence = " ".join(
            part
            for part in [str(current.get("evidence") or "").strip(), str(piece.get("evidence") or "").strip()]
            if part
        )
        current["evidence"] = evidence[:220]
        if str(piece.get("latestAt") or "") > str(current.get("latestAt") or ""):
            current["latestAt"] = piece.get("latestAt")
            current["todayLatestAt"] = piece.get("todayLatestAt") or current.get("todayLatestAt")
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
                if piece.get(source_key) not in {None, ""}:
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
        current_piece_id_version = str(piece.get("reviewVersion") or "") == CONFIRMED_PIECE_ID_VERSION
        if (
            str(piece.get("confidence") or "unknown").lower() != "clear"
            or rejected_repertoire_title(piece.get("title"), piece)
            or (
                not human_verified_source_label
                and (
                    not has_source_window
                    or not verified_piece_id
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


def derive_review(
    inventory: dict[str, list[dict[str, Any]]],
    existing: dict[str, Any] | None = None,
    media_samples: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = existing or {}
    today = today_local_day()
    sections = existing.get("notableSections") if isinstance(existing.get("notableSections"), list) else []
    findings = sanitized_findings(existing.get("skillFindings") if isinstance(existing.get("skillFindings"), list) else [])
    raw_pieces = existing.get("pieces") if isinstance(existing.get("pieces"), list) else []
    source_label_pieces = accepted_source_pieces(state or {}, inventory, media_samples)
    pieces = enriched_pieces([*source_label_pieces, *raw_pieces], today, media_samples)
    today_pieces = [piece for piece in pieces if piece.get("isActiveToday")]
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
            "sampleCount": len(media_samples),
            "sampleIndex": sample_index,
            "samples": media_samples[:5],
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
