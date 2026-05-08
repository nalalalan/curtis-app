from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .state import utc_now


FIVE_ONE_KEY = "youtube:wDfVpTU4I_I"
FIVE_ONE_REJECTED_TITLES = [
    "Paganini",
    "Paganini Violin Concerto No. 1",
    "Paganini Violin Concerto No. 1 in D major, Op. 6",
    "Paganini Caprice No. 5",
    "Paganini Caprice No. 24",
    "Bruch",
    "Max Bruch",
    "Bruch Violin Concerto No. 1",
    "Bruch Violin Concerto No. 1 in G minor, Op. 26",
    "Max Bruch Violin Concerto No. 1 in G minor, Op. 26",
    "Mendelssohn",
    "Felix Mendelssohn",
    "Mendelssohn Violin Concerto",
    "Mendelssohn Violin Concerto in E minor, Op. 64",
    "Felix Mendelssohn Violin Concerto in E minor, Op. 64",
    "Brahms",
    "Johannes Brahms",
    "Brahms Hungarian Dance No. 5",
    "Brahms Hungarian Dance No. 5 (arranged for violin)",
    "Hungarian Dance No. 5",
    "Sibelius",
    "Jean Sibelius",
    "Sibelius Violin Concerto",
    "Sibelius Violin Concerto in D minor, Op. 47",
    "Sibelius Violin Concerto in D minor, Op. 47, 3rd movement",
    "Jean Sibelius Violin Concerto in D minor, Op. 47, 3rd movement",
    "Tchaikovsky",
    "Pyotr Ilyich Tchaikovsky",
    "Tchaikovsky Violin Concerto",
    "Tchaikovsky Violin Concerto in D major, Op. 35",
    "Tchaikovsky Violin Concerto in D major, Op. 35, 3rd movement",
    "Pyotr Ilyich Tchaikovsky Violin Concerto in D major, Op. 35, 3rd movement",
    "Wieniawski",
    "Wieniawski Violin Concerto No. 2",
    "Wieniawski Polonaise Brillante No. 1 in D major, Op. 4",
    "Wieniawski Scherzo-Tarantelle, Op. 16",
    "Saint-Saens",
    "Saint-Saens Introduction and Rondo Capriccioso, Op. 28",
    "Ravel",
    "Ravel Tzigane",
    "Tzigane",
    "Bazzini",
    "Bazzini La Ronde des Lutins, Op. 25",
    "La Ronde des Lutins",
    "Ernst",
    "Ernst Last Rose of Summer Variations",
    "The Last Rose of Summer",
    "Ernst Grand Caprice on Schubert's Erlkonig",
    "Erlkonig",
    "Pablo de Sarasate Carmen Fantasy, Op. 25",
    "Sarasate Carmen Fantasy",
    "Carmen Fantasy",
    "Pablo de Sarasate Zigeunerweisen, Op. 20",
    "Sarasate Zigeunerweisen",
    "Zigeunerweisen",
    "J.S. Bach Partita No. 3 in E major, BWV 1006, Preludio",
    "Bach Partita No. 3 Preludio",
    "Kreisler Praeludium and Allegro",
    "Fritz Kreisler Praeludium and Allegro",
    "Praeludium and Allegro",
    "Praeludium and Allegro in the Style of Pugnani",
    "Sarasate Zapateado",
    "Sarasate Zapateado Op. 23 No. 2",
    "Pablo de Sarasate Zapateado, Op. 23 No. 2",
    "Zapateado",
    "Ysaye Sonata No. 3 Ballade",
    "Ysaÿe Sonata No. 3 Ballade",
    "Eugene Ysaye Sonata No. 3 Ballade",
    "Eugène Ysaÿe Sonata No. 3 Ballade",
    "Ysaÿe Solo Violin Sonata No. 3, Op. 27 No. 3, Ballade",
    "Ysaye Solo Violin Sonata No. 3, Op. 27 No. 3, Ballade",
    "Mozart",
    "Wolfgang Amadeus Mozart",
    "Mozart K. 216",
    "Mozart Violin Concerto No. 3",
    "Mozart Violin Concerto No. 3 in G major, K. 216",
    "Mozart Violin Concerto No. 3 in G major, K. 216, 3rd movement",
    "Wolfgang Amadeus Mozart Violin Concerto No. 3 in G major, K. 216",
]
SOURCE_ACCEPTANCE_REJECT_COUNT = 3


def compact_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def youtube_video_id(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{6,})", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", text.strip()):
        return text.strip()
    return ""


def source_key(*, url: Any = "", title: Any = "", sample_id: Any = "", video_id: Any = "") -> str:
    direct_id = youtube_video_id(video_id) or youtube_video_id(url) or youtube_video_id(sample_id)
    if direct_id:
        return f"youtube:{direct_id}"
    title_key = compact_text(title)
    if "5 1 26" in title_key:
        return FIVE_ONE_KEY
    return f"title:{title_key}" if title_key else ""


def source_key_from_item(item: dict[str, Any] | None) -> str:
    item = item or {}
    return source_key(
        url=item.get("sourceUrl") or item.get("url"),
        title=item.get("sourceTitle") or item.get("sampleTitle") or item.get("title"),
        sample_id=item.get("sampleId") or item.get("id") or item.get("sectionId"),
    )


def builtin_correction(key: str) -> dict[str, Any] | None:
    if key != FIVE_ONE_KEY:
        return None
    return {
        "sourceKey": FIVE_ONE_KEY,
        "sourceTitle": "5-1-26",
        "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
        "rejectedTitles": FIVE_ONE_REJECTED_TITLES,
        "acceptedTitle": "",
        "updatedAt": "2026-05-07T00:00:00+00:00",
        "reason": "Alan-corrected false labels for this source.",
    }


def correction_for_key(state: dict[str, Any], key: str) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "sourceKey": key,
        "rejectedTitles": [],
        "acceptedTitle": "",
        "updatedAt": "",
        "reason": "",
    }
    built_in = builtin_correction(key)
    if built_in:
        merged.update(built_in)
    stored = state.get("sourceCorrections", {}).get(key)
    if isinstance(stored, dict):
        rejected = [
            *merged.get("rejectedTitles", []),
            *[str(item).strip() for item in stored.get("rejectedTitles", []) if str(item).strip()],
        ]
        merged.update(stored)
        merged["rejectedTitles"] = list(dict.fromkeys(rejected))
    return merged


def correction_for_item(state: dict[str, Any], item: dict[str, Any] | None) -> dict[str, Any]:
    key = source_key_from_item(item)
    return correction_for_key(state, key) if key else {"rejectedTitles": [], "acceptedTitle": ""}


def title_rejected_for_item(title: Any, state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    compact = compact_text(title)
    if not compact:
        return False
    correction = correction_for_item(state, item)
    for rejected in correction.get("rejectedTitles", []):
        rejected_compact = compact_text(rejected)
        if rejected_compact and (
            compact == rejected_compact or compact in rejected_compact or rejected_compact in compact
        ):
            return True
    return False


def source_requires_confirmed_acceptance(state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    key = source_key_from_item(item)
    if not key:
        return False
    correction = correction_for_key(state, key)
    if compact_text(correction.get("acceptedTitle")):
        return False
    rejected_titles = {
        compact_text(title)
        for title in correction.get("rejectedTitles", [])
        if compact_text(title)
    }
    return len(rejected_titles) >= SOURCE_ACCEPTANCE_REJECT_COUNT


def parsed_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def item_stale_after_source_correction(state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    item = item or {}
    key = source_key_from_item(item)
    if not key:
        return False
    correction = correction_for_key(state, key)
    if not correction.get("rejectedTitles"):
        return False
    corrected_at = parsed_at(correction.get("updatedAt"))
    if corrected_at is None:
        return False
    item_times = [
        parsed_at(item.get("createdAt")),
        parsed_at(item.get("latestAt")),
        parsed_at(item.get("updatedAt")),
    ]
    item_times = [value for value in item_times if value is not None]
    return not item_times or max(item_times) <= corrected_at


def rejected_title_on_item(state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    item = item or {}
    titles: list[Any] = [
        item.get("title"),
        item.get("proposedTitle"),
        item.get("candidateTitle"),
        item.get("verificationTitle"),
    ]
    verification = item.get("verification")
    if isinstance(verification, dict):
        titles.append(verification.get("title"))
    for candidate in item.get("topCandidates", []):
        if isinstance(candidate, dict):
            titles.append(candidate.get("title"))
    return any(title_rejected_for_item(title, state, item) for title in titles)


def scrubbed_piece_item(item: dict[str, Any]) -> dict[str, Any]:
    current = dict(item)
    rejected_title = str(
        current.get("title")
        or current.get("proposedTitle")
        or current.get("candidateTitle")
        or current.get("verificationTitle")
        or ""
    ).strip()
    if rejected_title and rejected_title != "Piece being identified":
        current["rejectedTitle"] = rejected_title
    current["status"] = "piece_rejected_guess"
    current["title"] = "Piece being identified"
    current["confidence"] = "unknown"
    current["confidenceScore"] = 0
    current["completionPercent"] = 0
    current["todayCompletionPercent"] = 0
    current["readinessStatus"] = "piece_identification_pending"
    current["evidenceQuality"] = "weak"
    current["candidateTitle"] = ""
    current["candidateEvidence"] = "Rejected source-specific false label. Exact piece pending."
    current["evidence"] = "Rejected source-specific false label. Exact piece pending."
    current["rejectedByCorrection"] = True
    daily = current.get("daily")
    if isinstance(daily, dict):
        current["daily"] = {
            str(day): {
                **entry,
                "completionPercent": 0,
                "tip": "Piece identification pending verified source evidence.",
            }
            for day, entry in daily.items()
            if isinstance(entry, dict)
        }
    return current


def scrub_rejected_source(state: dict[str, Any], key: str) -> int:
    changed = 0
    review = state.setdefault("review", {})

    for collection_name in ("pieceIdentifications", "pieces"):
        collection = review.get(collection_name)
        if not isinstance(collection, list):
            continue
        scrubbed: list[Any] = []
        for item in collection:
            if (
                isinstance(item, dict)
                and item_matches_source_key(item, key)
                and (
                    rejected_title_on_item(state, item)
                    or item_stale_after_source_correction(state, item)
                    or source_requires_confirmed_acceptance(state, item)
                )
            ):
                scrubbed.append(scrubbed_piece_item(item))
                changed += 1
            else:
                scrubbed.append(item)
        review[collection_name] = scrubbed

    last_piece_id = state.get("lastPieceIdRun")
    if isinstance(last_piece_id, dict) and isinstance(last_piece_id.get("results"), list):
        scrubbed_results: list[Any] = []
        for item in last_piece_id["results"]:
            if (
                isinstance(item, dict)
                and item_matches_source_key(item, key)
                and (
                    rejected_title_on_item(state, item)
                    or item_stale_after_source_correction(state, item)
                    or source_requires_confirmed_acceptance(state, item)
                )
            ):
                scrubbed_results.append(scrubbed_piece_item(item))
                changed += 1
            else:
                scrubbed_results.append(item)
        last_piece_id["results"] = scrubbed_results
        identified = [
            item
            for item in scrubbed_results
            if isinstance(item, dict) and item.get("status") == "piece_identified"
        ]
        last_piece_id["identifiedCount"] = len(identified)
        if not identified and last_piece_id.get("status") == "piece_identified":
            last_piece_id["status"] = "piece_unidentified"

    current_work = str(review.get("currentWork") or "")
    key_item = {
        "url": key.split(":", 1)[1] if key.startswith("youtube:") else "",
        "sourceTitle": key.split(":", 1)[1] if key.startswith("title:") else "",
    }
    if current_work and (
        title_rejected_for_item(current_work, state, key_item)
        or source_requires_confirmed_acceptance(state, key_item)
    ):
        review["currentWork"] = "Piece identification pending verified source evidence."
        changed += 1

    return changed


def learn_rejection(
    state: dict[str, Any],
    *,
    source_url: str = "",
    source_title: str = "",
    video_id: str = "",
    rejected_title: str = "",
    note: str = "",
) -> dict[str, Any]:
    key = source_key(url=source_url, title=source_title, video_id=video_id)
    if not key:
        raise ValueError("source key required")
    corrections = state.setdefault("sourceCorrections", {})
    current = dict(corrections.get(key) or {})
    rejected = [
        *[str(item).strip() for item in current.get("rejectedTitles", []) if str(item).strip()],
        rejected_title.strip(),
    ]
    current.update(
        {
            "sourceKey": key,
            "sourceUrl": source_url,
            "sourceTitle": source_title,
            "rejectedTitles": list(dict.fromkeys(item for item in rejected if item)),
            "updatedAt": utc_now(),
        }
    )
    if note.strip():
        notes = [str(item).strip() for item in current.get("notes", []) if str(item).strip()]
        current["notes"] = [note.strip(), *notes][:10]
    corrections[key] = current
    return current


def item_matches_source_key(item: dict[str, Any], key: str) -> bool:
    return bool(key) and source_key_from_item(item) == key
