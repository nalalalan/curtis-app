from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .corrections import accepted_source_corrections, compact_text, source_key_from_item, youtube_video_id
from .score_assets import score_page_url


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


def local_day(value: Any) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.date().isoformat()


def parse_window_bounds(value: Any) -> tuple[int, int]:
    match = re.search(r"\*(\d+)-(\d+)", str(value or ""))
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def source_matches(correction: dict[str, Any], item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    source_key = str(correction.get("sourceKey") or "")
    item_key = str(item.get("sourceKey") or source_key_from_item(item) or "")
    if source_key and item_key == source_key:
        return True
    source_url = str(correction.get("sourceUrl") or "")
    item_url = str(item.get("sourceUrl") or item.get("url") or "")
    if source_url and item_url == source_url:
        return True
    video_id = youtube_video_id(source_url or source_key)
    signal = " ".join(
        str(item.get(key) or "")
        for key in ("id", "sampleId", "sourceUrl", "url", "sourceTitle", "title", "sourceKey")
    )
    if video_id and video_id.lower() in signal.lower():
        return True
    source_title = compact_text(correction.get("sourceTitle"))
    item_title = compact_text(item.get("sourceTitle") or item.get("title"))
    return bool(source_title and item_title and (source_title == item_title or source_title in item_title or item_title in source_title))


def source_record(
    correction: dict[str, Any],
    inventory_items: list[dict[str, Any]],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    matching_samples = [sample for sample in samples if source_matches(correction, sample)]
    matching_inventory = [item for item in inventory_items if source_matches(correction, item)]
    sample = matching_samples[0] if matching_samples else {}
    inventory = matching_inventory[0] if matching_inventory else {}
    source_title = str(correction.get("sourceTitle") or sample.get("sourceTitle") or sample.get("title") or inventory.get("title") or "").strip()
    source_url = str(correction.get("sourceUrl") or sample.get("sourceUrl") or sample.get("url") or inventory.get("url") or "").strip()
    source_window = str(sample.get("sourceWindow") or sample.get("window") or "").strip()
    start, end = parse_window_bounds(source_window)
    if not end and start:
        end = start + 45
    return {
        "sourceTitle": source_title,
        "sourceUrl": source_url,
        "sourceWindow": source_window,
        "sourceStartSeconds": start,
        "sourceEndSeconds": end,
        "practiceDay": practice_day_from_title(source_title) or local_day(inventory.get("publishedAt")),
        "sampleCount": len(matching_samples),
        "inventory": inventory,
        "sample": sample,
    }


def first_notes(item: dict[str, Any], limit: int = 28) -> list[str]:
    notes = item.get("notes") if isinstance(item.get("notes"), list) else []
    values = [str(note.get("note") or "").strip() for note in notes if isinstance(note, dict) and str(note.get("note") or "").strip()]
    if values:
        return values[:limit]
    fingerprint = item.get("fingerprint") if isinstance(item.get("fingerprint"), dict) else {}
    return [str(note).strip() for note in fingerprint.get("firstNotes", []) if str(note).strip()][:limit]


def duration_label(beats: float) -> str:
    if beats <= 0.38:
        return "16th"
    if beats <= 0.75:
        return "8th"
    if beats <= 1.45:
        return "quarter"
    if beats <= 2.6:
        return "half"
    return f"{beats:.1f}b"


def clean_transcription_text(item: dict[str, Any]) -> str:
    notes = item.get("notes") if isinstance(item.get("notes"), list) else []
    tempo = float(item.get("tempoBpm") or 0.0)
    beat_seconds = 60.0 / tempo if tempo > 0 else 0.5
    tokens: list[str] = []
    for event in notes[:48]:
        if not isinstance(event, dict):
            continue
        note = str(event.get("note") or "").strip()
        if not note:
            continue
        beats = max(0.25, float(event.get("durationSeconds") or 0.0) / beat_seconds)
        tokens.append(f"{note}/{duration_label(beats)}")
    if tokens:
        return " ".join(tokens)
    compact_notes = first_notes(item, 36)
    return " ".join(compact_notes)


def score_boxes(target: dict[str, Any]) -> list[dict[str, Any]]:
    boxes = target.get("scoreBoxes") if isinstance(target.get("scoreBoxes"), list) else []
    clean: list[dict[str, Any]] = []
    for box in boxes:
        if not isinstance(box, dict):
            continue
        clean.append(
            {
                "x": max(0, min(100, float(box.get("x") or 0))),
                "y": max(0, min(100, float(box.get("y") or 0))),
                "width": max(1, min(100, float(box.get("width") or 1))),
                "height": max(1, min(100, float(box.get("height") or 1))),
                "label": str(box.get("label") or "practice area").strip(),
            }
        )
    return clean[:3]


def snippet_feedback(title: str, source_tip: str, transcription: dict[str, Any] | None) -> str:
    if source_tip:
        return source_tip
    signal = compact_text(title)
    if "wieniawski" in signal or "scherzo tarantelle" in signal:
        return "Small bow, rhythm first. Repetitions must stay narrow before tempo goes up."
    if "haydn" in signal or "symphony no 94" in signal:
        return "Light bow. Repeated notes need equal spacing; keep it orchestral, not concerto-heavy."
    if transcription and int(transcription.get("noteCount") or 0) > 0:
        return "Use the boxed passage and the clip together; confirm pitch/rhythm before judging polish."
    return "Score target ready. Transcription needed before section-specific coaching."


def readiness_text(transcription: dict[str, Any] | None, score_image_url: str) -> str:
    if transcription and transcription.get("status") == "transcribed" and score_image_url:
        return "Pitch/rhythm extracted. Score match pending exact measure proof."
    if transcription and transcription.get("status") == "transcribed":
        return "Pitch/rhythm extracted. Score page pending."
    if score_image_url:
        return "Score page ready. Transcription pending."
    return "Source confirmed. Score render pending."


def transcription_packet(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "status": "pending",
            "noteCount": 0,
            "tempoBpm": 0,
            "firstNotes": [],
            "cleanText": "",
            "limit": "No machine transcription stored for this day yet.",
        }
    clean_text = clean_transcription_text(item)
    return {
        "status": item.get("status") or "pending",
        "noteCount": int(item.get("noteCount") or 0),
        "tempoBpm": float(item.get("tempoBpm") or 0.0),
        "firstNotes": first_notes(item, 24),
        "cleanText": clean_text[:520],
        "sourceWindow": item.get("sourceWindow") or "",
        "limit": "Machine transcription; use as alignment evidence, not final notation.",
    }


def build_snippet(
    correction: dict[str, Any],
    source: dict[str, Any],
    transcription: dict[str, Any] | None,
    index: int,
) -> dict[str, Any]:
    target = correction.get("referenceTarget") if isinstance(correction.get("referenceTarget"), dict) else {}
    page = int(target.get("scorePage") or 1)
    asset_id = str(target.get("scoreAssetId") or "")
    score_image_url = score_page_url(asset_id, page) if asset_id else ""
    source_window = str(transcription.get("sourceWindow") if transcription else source.get("sourceWindow") or "")
    start, end = parse_window_bounds(source_window)
    if not start:
        start = int(source.get("sourceStartSeconds") or 0)
    if not end:
        end = int(source.get("sourceEndSeconds") or 0) or (start + 45 if start else 0)
    passage = ""
    vocabulary = target.get("passageVocabulary") if isinstance(target.get("passageVocabulary"), list) else []
    if vocabulary:
        passage = str(vocabulary[min(index, len(vocabulary) - 1)] or "").strip()
    packet = transcription_packet(transcription)
    return {
        "id": f"{correction.get('sourceKey') or 'source'}:{index}",
        "title": passage or "practice passage",
        "pieceTitle": correction.get("acceptedTitle") or "",
        "practiceDay": source.get("practiceDay") or "",
        "status": "transcribed" if packet["status"] == "transcribed" else "score_target_ready",
        "score": {
            "source": target.get("scoreSource") or "",
            "sourceUrl": target.get("scoreUrl") or "",
            "pdfUrl": target.get("scorePdfUrl") or "",
            "assetId": asset_id,
            "page": page,
            "imageUrl": score_image_url,
            "boxes": score_boxes(target),
            "part": target.get("part") or "",
            "movement": target.get("movement") or "",
        },
        "audio": {
            "url": source.get("sourceUrl") or "",
            "startSeconds": start,
            "endSeconds": end,
            "window": source_window,
            "label": f"{start}-{end}" if start and end else "clip pending",
        },
        "transcription": packet,
        "feedback": snippet_feedback(str(correction.get("acceptedTitle") or ""), str(correction.get("sourceTip") or ""), transcription),
        "readiness": readiness_text(transcription, score_image_url),
    }


def build_practice_study(
    state: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
    pieces: list[dict[str, Any]],
) -> dict[str, Any]:
    inventory_items = [item for items in inventory.values() for item in items if isinstance(item, dict)]
    transcriptions = [
        item
        for item in state.get("transcriptions", {}).get("items", [])
        if isinstance(item, dict)
    ]
    day_packets: list[dict[str, Any]] = []
    for correction in accepted_source_corrections(state):
        title = str(correction.get("acceptedTitle") or "").strip()
        if not title:
            continue
        source = source_record(correction, inventory_items, media_samples)
        matching_transcriptions = [item for item in transcriptions if source_matches(correction, item)]
        matching_transcriptions.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        matching_pieces = [piece for piece in pieces if compact_text(piece.get("title")) == compact_text(title)]
        daily_entries = [
            entry
            for piece in matching_pieces
            for entry in (piece.get("daily") or {}).values()
            if isinstance(entry, dict) and source_matches(correction, entry)
        ]
        latest_daily = daily_entries[0] if daily_entries else {}
        snippet_sources = matching_transcriptions[:3] or [None]
        snippets = [
            build_snippet(correction, source, transcription, index)
            for index, transcription in enumerate(snippet_sources)
        ]
        latest_transcription = matching_transcriptions[0] if matching_transcriptions else None
        day_packets.append(
            {
                "id": correction.get("sourceKey") or title,
                "practiceDay": source.get("practiceDay") or "",
                "sourceTitle": source.get("sourceTitle") or "",
                "sourceUrl": source.get("sourceUrl") or "",
                "pieceTitle": title,
                "status": "transcribed" if latest_transcription else "score_target_ready",
                "completionPercent": int(latest_daily.get("completionPercent") or 0),
                "tip": str(latest_daily.get("tip") or correction.get("sourceTip") or snippets[0].get("feedback") or "").strip(),
                "transcription": transcription_packet(latest_transcription),
                "snippetCount": len(snippets),
                "snippets": snippets,
            }
        )
    day_packets = sorted(
        day_packets,
        key=lambda item: (str(item.get("practiceDay") or ""), str(item.get("sourceTitle") or "")),
        reverse=True,
    )
    return {
        "status": "ready" if day_packets else "pending",
        "dayCount": len(day_packets),
        "snippetCount": sum(int(item.get("snippetCount") or 0) for item in day_packets),
        "transcribedDayCount": sum(1 for item in day_packets if item.get("status") == "transcribed"),
        "days": day_packets[:21],
        "method": "source-confirmed practice days, machine transcription, cached public-domain score pages, boxed target passages, and timed practice clips",
        "limit": "Exact measure proof requires aligning extracted notes/rhythm to the score; source-confirmed labels are not a musical readiness score.",
    }
