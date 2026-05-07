from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .auth import youtube_auth_status
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
REJECTED_REPERTOIRE_TITLES = (
    "paganini caprice no 5",
    "niccolo paganini caprice no 5",
    "pablo de sarasate zigeunerweisen op 20",
    "sarasate zigeunerweisen",
    "zigeunerweisen",
)


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


def stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


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


def rejected_repertoire_title(value: Any) -> bool:
    compact = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return any(rejected in compact or compact in rejected for rejected in REJECTED_REPERTOIRE_TITLES)


def canonical_piece_title(value: Any) -> str:
    title = str(value or "").strip()
    compact = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if "bach" in compact and "partita" in compact and "1006" in compact and (
        "preludio" in compact or "prelude" in compact
    ):
        return "J.S. Bach Partita No. 3 in E major, BWV 1006, Preludio"
    return title


def better_tip(current: str, incoming: str) -> str:
    current_clean = str(current or "").strip()
    incoming_clean = str(incoming or "").strip()
    if re.match(r"^capture one clear(er)? excerpt\.?$", current_clean, flags=re.IGNORECASE) and incoming_clean:
        return incoming_clean
    return current_clean or incoming_clean


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
            ):
                if current.get(source_key) in {None, ""} and piece.get(source_key) not in {None, ""}:
                    current[source_key] = piece.get(source_key)
    return sorted(
        merged.values(),
        key=lambda piece: (
            int(piece.get("confidenceScore") or 0),
            int(piece.get("todayCompletionPercent") or 0),
            int(piece.get("completionPercent") or 0),
            str(piece.get("latestAt") or ""),
        ),
        reverse=True,
    )[:12]


def enriched_pieces(pieces: list[Any], today: str) -> list[dict[str, Any]]:
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
        if (
            str(piece.get("confidence") or "unknown").lower() != "clear"
            or rejected_repertoire_title(piece.get("title"))
            or not has_source_window
            or not verified_piece_id
        ):
            piece["title"] = "Piece being identified"
            piece["confidence"] = "unknown"
            piece["confidenceScore"] = 1
            piece["completionPercent"] = 0
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
        daily = piece.get("daily") if isinstance(piece.get("daily"), dict) else {}
        today_entry = daily.get(today) if isinstance(daily.get(today), dict) else None
        latest_day = local_day(piece.get("latestAt"))
        if today_entry:
            today_percent = int(today_entry.get("completionPercent") or 0)
            today_tip = str(today_entry.get("tip") or piece.get("tip") or "Capture one clearer excerpt.").strip()
            today_latest = today_entry.get("latestAt") or piece.get("latestAt")
        elif latest_day == today:
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
        piece["isActiveToday"] = bool(today_entry or latest_day == today)
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


def derive_review(inventory: dict[str, list[dict[str, Any]]], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    today = today_local_day()
    sections = existing.get("notableSections") if isinstance(existing.get("notableSections"), list) else []
    findings = sanitized_findings(existing.get("skillFindings") if isinstance(existing.get("skillFindings"), list) else [])
    pieces = enriched_pieces(existing.get("pieces") if isinstance(existing.get("pieces"), list) else [], today)
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
    media_access = existing.get("mediaAccess")
    if media_access not in {"blocked", "sample_ready"}:
        media_access = "metadata_only"
    return {
        "reviewedVideoCount": len(reviewed_urls),
        "notableSections": sections,
        "skillFindings": findings,
        "pieces": pieces,
        "today": today,
        "todayPiece": today_pieces[0] if today_pieces else pieces[0] if pieces else None,
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
    review = derive_review(inventory, state.get("review"))
    hard_blockers = inventory_blockers(blockers)
    status = "blocked" if hard_blockers else "ready"
    if not hard_blockers and review.get("inventoryCount"):
        status = "inventory_ready"

    media_samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
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
    state["review"] = derive_review(inventory, state.get("review"))

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
