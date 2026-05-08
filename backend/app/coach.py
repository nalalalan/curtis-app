from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .analyzer import parse_window_start
from .settings import MODEL_REVIEW_FRAME_COUNT, MODEL_REVIEW_SAMPLE_SECONDS, OPENAI_AUDIO_MODEL, OPENAI_VISION_MODEL
from .state import load_state, save_state, utc_now


DIMENSIONS = {
    "intonation",
    "time",
    "tone",
    "articulation",
    "shifts",
    "musicality",
    "auditionDelivery",
}
JUDGMENTS = {"Strong signal", "Needs work", "Unjudged"}
WEAK_EVIDENCE_TERMS = {
    "background noise",
    "no clear",
    "not audible",
    "no discernible",
    "not heard",
    "obscured",
    "masked",
    "dominates",
}
UNKNOWN_PIECE_TITLES = {
    "",
    "unknown",
    "unknown piece",
    "n/a",
    "none",
    "piece being identified",
}
GENERIC_PIECE_TERMS = {
    "possible",
    "likely",
    "virtuosic",
    "solo work",
    "solo piece",
    "etude or caprice",
    "practice passage",
    "technical passage",
    "spiccato section",
    "fast passage",
    "scale",
    "exercise",
    "warmup",
    "warm-up",
    "piece",
    "section",
    "excerpt",
}
REJECTED_PIECE_TITLES: set[str] = set()
COMPOSER_MARKERS = {
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
    "sarasate",
    "sibelius",
    "tchaikovsky",
    "vieuxtemps",
    "vitali",
    "vivaldi",
    "wieniawski",
    "ysaye",
}
WORK_MARKERS = {
    "bwv",
    "caprice",
    "chaconne",
    "concerto",
    "czardas",
    "etude",
    "major",
    "minor",
    "movement",
    "no.",
    "no ",
    "op.",
    "opus",
    "partita",
    "sonata",
}
REVIEW_VERSION = "audio_video_piece_v2"


def local_timezone() -> ZoneInfo | timezone:
    try:
        return ZoneInfo(os.getenv("CURTIS_LOCAL_TIMEZONE", "America/New_York"))
    except ZoneInfoNotFoundError:
        return timezone.utc


def local_day(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value or utc_now()).replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(local_timezone()).date().isoformat()


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


def merge_daily_piece_state(piece: dict[str, Any], item: dict[str, Any], completion: int) -> None:
    day = practice_day_from_title(item.get("sourceTitle") or item.get("title")) or local_day(item.get("createdAt"))
    existing = piece.get("daily") if isinstance(piece.get("daily"), dict) else {}
    daily = {str(key): value for key, value in existing.items() if isinstance(value, dict)}
    current = dict(daily.get(day, {}))
    prior_count = int(current.get("sectionCount") or 0)
    prior_completion = int(current.get("completionPercent") or completion)
    count = prior_count + 1
    current["completionPercent"] = round(((prior_completion * prior_count) + completion) / count)
    current["sectionCount"] = count
    current["tip"] = str(item.get("immediateTip") or piece.get("tip") or "Capture one clearer excerpt.").strip()[:180]
    current["evidence"] = str(item.get("evidence") or piece.get("evidence") or "Evidence accumulating.").strip()[:220]
    current["latestAt"] = item.get("createdAt") or utc_now()
    for key in (
        "sampleId",
        "sectionId",
        "sourceTitle",
        "sourceUrl",
        "sourceWindow",
        "sourceStartSeconds",
        "sourceEndSeconds",
    ):
        if item.get(key) not in {None, ""}:
            current[key] = item.get(key)
    daily[day] = current
    piece["daily"] = {key: daily[key] for key in sorted(daily)[-21:]}


def run_process(args: list[str], timeout: int = 120) -> tuple[int, str]:
    completed = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout


def sample_for_section(section: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    sample_id = section.get("sampleId")
    for sample in samples:
        if sample.get("id") == sample_id:
            return sample
    return None


def extract_review_wav(sample: dict[str, Any], section: dict[str, Any], target: Path) -> tuple[bool, str]:
    source = Path(str(sample.get("path") or ""))
    if not source.exists():
        return False, "media_sample_missing"
    base_start = parse_window_start(str(sample.get("window") or ""))
    section_start = int(section.get("startSeconds") or base_start)
    relative_start = max(0, section_start - base_start)
    duration = max(4, min(MODEL_REVIEW_SAMPLE_SECONDS, int(section.get("endSeconds") or section_start + 8) - section_start))
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(relative_start),
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-t",
            str(duration),
            "-f",
            "wav",
            str(target),
        ],
        timeout=180,
    )
    return code == 0 and target.exists() and target.stat().st_size > 44, output


def section_relative_window(sample: dict[str, Any], section: dict[str, Any]) -> tuple[int, int]:
    base_start = parse_window_start(str(sample.get("window") or ""))
    section_start = int(section.get("startSeconds") or base_start)
    section_end = int(section.get("endSeconds") or section_start + MODEL_REVIEW_SAMPLE_SECONDS)
    relative_start = max(0, section_start - base_start)
    duration = max(4, min(MODEL_REVIEW_SAMPLE_SECONDS, section_end - section_start))
    return relative_start, duration


def extract_review_frames(sample: dict[str, Any], section: dict[str, Any], target_dir: Path) -> tuple[list[Path], str]:
    source = Path(str(sample.get("path") or ""))
    if not source.exists():
        return [], "media_sample_missing"
    relative_start, duration = section_relative_window(sample, section)
    frame_count = max(1, min(6, MODEL_REVIEW_FRAME_COUNT))
    offsets = [relative_start]
    if frame_count > 1:
        step = duration / frame_count
        offsets = [relative_start + int(step * index) for index in range(frame_count)]

    frames: list[Path] = []
    output = ""
    for index, offset in enumerate(offsets, start=1):
        target = target_dir / f"frame-{index:02d}.jpg"
        code, output = run_process(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(max(0, offset)),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=640:-2",
                "-q:v",
                "3",
                str(target),
            ],
            timeout=120,
        )
        if code == 0 and target.exists() and target.stat().st_size:
            frames.append(target)
    return frames, output


def decode_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def piece_title_is_identified(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(title or "").strip()).lower()
    compact = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    if any(rejected in compact or compact in rejected for rejected in REJECTED_PIECE_TITLES):
        return False
    if normalized in UNKNOWN_PIECE_TITLES:
        return False
    if normalized.startswith(("possible ", "likely ", "unknown ")):
        return False
    has_catalog_or_composer = (
        any(marker in normalized for marker in COMPOSER_MARKERS)
        or any(marker in normalized for marker in {"bwv", "k.", "kv", "no.", "no ", "op.", "opus"})
        or any(char.isdigit() for char in normalized)
    )
    has_work_form = any(marker in normalized for marker in WORK_MARKERS)
    generic_hit = any(term in normalized for term in GENERIC_PIECE_TERMS)
    if " or " in normalized and not has_catalog_or_composer:
        return False
    if generic_hit and not has_catalog_or_composer:
        return False
    return has_catalog_or_composer or (has_work_form and len(normalized.split()) >= 2)


def canonical_piece_title(title: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    if "bach" in compact and "partita" in compact and "1006" in compact and (
        "preludio" in compact or "prelude" in compact
    ):
        return "J.S. Bach Partita No. 3 in E major, BWV 1006, Preludio"
    return str(title or "").strip()


def clamp_percent(value: Any, *, evidence_quality: str, piece_confidence: str, piece_identified: bool) -> int:
    try:
        percent = int(round(float(value)))
    except (TypeError, ValueError):
        percent = 0
    percent = max(0, min(100, percent))
    if evidence_quality == "weak":
        percent = min(percent, 20)
    if not piece_identified:
        percent = min(percent, 25)
    if piece_confidence == "unknown":
        percent = min(percent, 45)
    if piece_confidence == "possible":
        percent = min(percent, 70)
    return percent


def normalize_piece(raw: dict[str, Any], *, evidence_quality: str, section: dict[str, Any]) -> dict[str, Any]:
    piece = raw.get("piece") if isinstance(raw.get("piece"), dict) else {}
    raw_title = str(piece.get("title") or raw.get("pieceTitle") or "").strip()
    confidence = str(piece.get("confidence") or raw.get("pieceConfidence") or "unknown").strip().lower()
    if confidence not in {"clear", "possible", "unknown"}:
        confidence = "unknown"
    model_candidate_identified = confidence == "clear" and piece_title_is_identified(raw_title)
    candidate_title = canonical_piece_title(raw_title) if model_candidate_identified else ""
    title = "Piece being identified"
    confidence = "unknown"
    completion = clamp_percent(
        0,
        evidence_quality=evidence_quality,
        piece_confidence=confidence,
        piece_identified=False,
    )
    evidence = str(piece.get("evidence") or raw.get("pieceEvidence") or "Evidence accumulating.").strip()[:220]
    return {
        "title": title[:120],
        "confidence": confidence,
        "evidence": evidence,
        "candidateTitle": candidate_title,
        "candidateEvidence": evidence if candidate_title else "",
        "completionPercent": completion,
        "immediateTip": str(raw.get("immediateTip") or raw.get("oneFocus") or "Capture one clearer excerpt.").strip()[:180],
        "sectionId": section.get("id"),
        "sampleId": section.get("sampleId"),
        "sourceTitle": section.get("title"),
        "sourceUrl": section.get("url"),
        "sourceStartSeconds": section.get("startSeconds"),
        "sourceEndSeconds": section.get("endSeconds"),
        "createdAt": utc_now(),
        "evidenceQuality": "coach_candidate",
    }


def normalize_review(raw: dict[str, Any], section: dict[str, Any], *, source: str) -> dict[str, Any]:
    findings = []
    evidence_quality = str(raw.get("evidenceQuality") or "weak").strip()[:40]
    for item in raw.get("findings", []):
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension") or "")
        judgment = str(item.get("judgment") or "Unjudged")
        if dimension not in DIMENSIONS:
            continue
        if judgment not in JUDGMENTS:
            judgment = "Unjudged"
        evidence = str(item.get("evidence") or "No stable evidence.").strip()[:220]
        if evidence_quality == "weak" or any(term in evidence.lower() for term in WEAK_EVIDENCE_TERMS):
            judgment = "Unjudged"
        findings.append(
            {
                "id": f"{section.get('id')}-{dimension}",
                "sectionId": section.get("id"),
                "sampleId": section.get("sampleId"),
                "reviewVersion": REVIEW_VERSION,
                "evidenceSource": source,
                "dimension": dimension,
                "judgment": judgment,
                "evidence": evidence,
                "practiceConstraint": str(item.get("practiceConstraint") or "").strip()[:180],
                "createdAt": utc_now(),
            }
        )

    plan = raw.get("progressPlan") if isinstance(raw.get("progressPlan"), dict) else {}
    session_plan = raw.get("sessionPlan") if isinstance(raw.get("sessionPlan"), list) else []
    piece_review = normalize_piece(raw, evidence_quality=evidence_quality, section=section)
    one_focus = str(raw.get("oneFocus") or plan.get("oneFocus") or "Capture clearer violin sections.").strip()[:180]
    practice_constraint = ""
    for finding in findings:
        if finding.get("practiceConstraint"):
            practice_constraint = str(finding["practiceConstraint"])
            break

    return {
        "sectionId": section.get("id"),
        "sampleId": section.get("sampleId"),
        "status": "model_reviewed",
        "reviewVersion": REVIEW_VERSION,
        "evidenceSource": source,
        "evidenceQuality": evidence_quality,
        "sectionSummary": str(raw.get("sectionSummary") or "Model review completed.").strip()[:260],
        "findings": findings[:5],
        "pieceReview": piece_review,
        "progressPlan": {
            "status": "Curtis-focused review active.",
            "oneFocus": one_focus,
            "practiceConstraint": practice_constraint or "One constraint per session.",
            "sessionPlan": [str(item).strip()[:120] for item in session_plan[:3] if str(item).strip()],
            "boundary": "Curtis admission cannot be predicted from current samples.",
        },
    }


def review_prompt(section: dict[str, Any]) -> str:
    return f"""
Return JSON only. Analyze this audio as an elite classical violin audition reviewer.

Target: Curtis Institute of Music violin admission standard.
Evidence: one short practice-room audio slice from a public YouTube practice video.
Section: {section.get("title") or "untitled"} / {section.get("startSeconds")}s-{section.get("endSeconds")}s.

Required JSON:
{{
  "evidenceQuality": "usable|weak|blocked",
  "sectionSummary": "one factual sentence",
  "piece": {{"title": "piece name or Piece being identified", "confidence": "clear|possible|unknown", "evidence": "short phrase"}},
  "completionPercent": 0,
  "immediateTip": "one immediately useful practice tip",
  "findings": [
    {{
      "dimension": "tone|intonation|time|articulation|shifts|musicality|auditionDelivery",
      "judgment": "Strong signal|Needs work|Unjudged",
      "evidence": "one short evidence phrase",
      "practiceConstraint": "one short constraint"
    }}
  ],
  "oneFocus": "one short focus",
  "sessionPlan": ["block 1", "block 2", "block 3"]
}}

Rules:
- If there is no clear violin playing, set evidenceQuality to "weak" and findings to Unjudged.
- Piece title must be an actual repertoire identifier: composer, work title, movement, etude/caprice number, opus, key, or catalog number.
- Do not use category labels as piece titles: virtuosic solo work, etude or caprice, spiccato passage, technical exercise, fast section, or similar.
- Only name a repertoire work when the exact piece is clear. If the exact piece is not identifiable, set piece.title exactly to "Piece being identified", confidence to "unknown", and do not mention a composer or work title.
- Fast arpeggios, ricochet, spiccato, or caprice-like writing alone are not enough to name Paganini or any other work.
- No admission prediction, no odds, no reassurance, no motivation, no diagnosis language.
- Do not name repertoire unless it is clearly audible.
- Completion percent means Curtis-level readiness for this piece from current evidence. Use 100 only for clearly Curtis-level evidence.
- Use at most three findings.
- Make the plan low-overwhelm: one focus, three short blocks.
""".strip()


def vision_prompt(section: dict[str, Any]) -> str:
    return f"""
Return JSON only. Analyze these sampled video frames as an elite classical violin audition reviewer.

Target: Curtis Institute of Music violin admission standard.
Evidence: still frames from one captured public YouTube practice-video section.
Section: {section.get("title") or "untitled"} / {section.get("startSeconds")}s-{section.get("endSeconds")}s.

Required JSON:
{{
  "evidenceQuality": "usable|weak|blocked",
  "sectionSummary": "one factual sentence",
  "piece": {{"title": "piece name or Piece being identified", "confidence": "clear|possible|unknown", "evidence": "short visual phrase"}},
  "completionPercent": 0,
  "immediateTip": "one immediately useful practice tip",
  "findings": [
    {{
      "dimension": "tone|intonation|time|articulation|shifts|musicality|auditionDelivery",
      "judgment": "Strong signal|Needs work|Unjudged",
      "evidence": "one short visual evidence phrase",
      "practiceConstraint": "one short constraint"
    }}
  ],
  "oneFocus": "one short focus",
  "sessionPlan": ["block 1", "block 2", "block 3"]
}}

Rules:
- Use visual evidence when audio is weak: posture, bow path, contact-point setup, left-hand frame, tension, setup consistency, and audition-room presentation.
- Mark audio-only dimensions Unjudged when frames do not show enough.
- If no violin/person/instrument is visible, evidenceQuality is "weak" and findings are Unjudged.
- Piece title must be an actual repertoire identifier visible in context: score title, overlay title, composer/work clue, movement, etude/caprice number, opus, key, or catalog number.
- Do not use category labels as piece titles: virtuosic solo work, etude or caprice, spiccato passage, technical exercise, fast section, or similar.
- Only name a repertoire work when the exact piece is clear. If the exact piece is not identifiable, set piece.title exactly to "Piece being identified", confidence to "unknown", and do not mention a composer or work title.
- Fast arpeggios, ricochet, spiccato, or caprice-like writing alone are not enough to name Paganini or any other work.
- Completion percent means Curtis-level readiness for this piece from current visual evidence. Use 100 only for clearly Curtis-level evidence.
- No admission prediction, no odds, no reassurance, no motivation, no diagnosis language.
- Use at most three findings.
- Make the plan low-overwhelm: one focus, three short blocks.
""".strip()


def call_audio_model(wav_path: Path, section: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"status": "blocked", "blocker": "missing_openai_api_key"}

    encoded = base64.b64encode(wav_path.read_bytes()).decode("ascii")
    payload = {
        "model": OPENAI_AUDIO_MODEL,
        "modalities": ["text"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": review_prompt(section)},
                    {"type": "input_audio", "input_audio": {"data": encoded, "format": "wav"}},
                ],
            }
        ],
    }
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        return {"status": "blocked", "blocker": "openai_audio_review_failed", "detail": response.text[:500]}
    content = response.json()["choices"][0]["message"].get("content") or "{}"
    try:
        return normalize_review(decode_json(content), section, source="audio")
    except Exception:
        return {"status": "blocked", "blocker": "openai_audio_review_parse_failed", "detail": content[:500]}


def image_content(frame_paths: list[Path]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for frame in frame_paths:
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded}",
                    "detail": "low",
                },
            }
        )
    return content


def call_vision_model(frame_paths: list[Path], section: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"status": "blocked", "blocker": "missing_openai_api_key"}
    if not frame_paths:
        return {"status": "blocked", "blocker": "video_frame_extract_failed"}

    payload = {
        "model": OPENAI_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": vision_prompt(section)}, *image_content(frame_paths)],
            }
        ],
    }
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        return {"status": "blocked", "blocker": "openai_vision_review_failed", "detail": response.text[:500]}
    content = response.json()["choices"][0]["message"].get("content") or "{}"
    try:
        return normalize_review(decode_json(content), section, source="video")
    except Exception:
        return {"status": "blocked", "blocker": "openai_vision_review_parse_failed", "detail": content[:500]}


def merge_review_results(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    by_dimension: dict[str, dict[str, Any]] = {}
    progress_plan: dict[str, Any] | None = None
    piece_reviews: list[dict[str, Any]] = []
    priority = {"Needs work": 3, "Strong signal": 2, "Unjudged": 1}
    for result in results:
        if result.get("status") != "model_reviewed":
            continue
        progress_plan = result.get("progressPlan") or progress_plan
        if isinstance(result.get("pieceReview"), dict):
            piece_reviews.append(result["pieceReview"])
        for finding in result.get("findings", []):
            if not isinstance(finding, dict) or not finding.get("dimension"):
                continue
            dimension = str(finding["dimension"])
            current = by_dimension.get(dimension)
            if current is None or priority.get(str(finding.get("judgment")), 0) > priority.get(str(current.get("judgment")), 0):
                by_dimension[dimension] = finding
    return list(by_dimension.values())[:5], progress_plan, piece_reviews


def aggregate_piece_reviews(existing: list[Any], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pieces: dict[str, dict[str, Any]] = {}
    for item in [*existing, *incoming]:
        if not isinstance(item, dict):
            continue
        raw_title = str(item.get("title") or "Piece being identified").strip()[:120] or "Piece being identified"
        confidence = str(item.get("confidence") or "unknown").strip().lower()
        if confidence not in {"clear", "possible", "unknown"}:
            confidence = "unknown"
        evidence_quality = str(item.get("evidenceQuality") or "usable")
        has_source_window = bool(item.get("sampleId") and item.get("sourceUrl") and item.get("sourceStartSeconds") is not None)
        human_source_label = evidence_quality == "human_verified_source_label" and bool(item.get("sourceUrl"))
        piece_identified = (
            confidence == "clear"
            and ((evidence_quality == "verified_piece_id" and has_source_window) or human_source_label)
            and piece_title_is_identified(raw_title)
        )
        title = canonical_piece_title(raw_title) if piece_identified else "Piece being identified"
        candidate_title = str(item.get("candidateTitle") or "").strip()[:120]
        key = title.lower()
        current = pieces.get(key)
        if not piece_identified:
            confidence = "unknown"
        confidence_score = {"clear": 3, "possible": 2, "unknown": 1}.get(confidence, 1)
        completion = clamp_percent(
            item.get("completionPercent"),
            evidence_quality=evidence_quality,
            piece_confidence=confidence,
            piece_identified=piece_identified,
        )
        if current is None:
            pieces[key] = {
                "title": title,
                "confidence": confidence,
                "confidenceScore": confidence_score,
                "completionPercent": completion,
                "tip": str(item.get("immediateTip") or "Capture one clearer excerpt.").strip()[:180],
                "evidence": str(item.get("evidence") or "Evidence accumulating.").strip()[:220],
                "candidateTitle": candidate_title,
                "candidateEvidence": str(item.get("candidateEvidence") or item.get("evidence") or "").strip()[:220],
                "sampleId": item.get("sampleId"),
                "sectionId": item.get("sectionId"),
                "sourceTitle": item.get("sourceTitle"),
                "sourceUrl": item.get("sourceUrl"),
                "sourceWindow": item.get("sourceWindow"),
                "sourceStartSeconds": item.get("sourceStartSeconds"),
                "sourceEndSeconds": item.get("sourceEndSeconds"),
                "evidenceQuality": evidence_quality,
                "reviewVersion": item.get("reviewVersion"),
                "sectionCount": 1,
                "latestAt": item.get("createdAt") or utc_now(),
            }
            merge_daily_piece_state(pieces[key], item, completion)
            continue
        current["sectionCount"] = int(current.get("sectionCount") or 0) + 1
        current["completionPercent"] = round((int(current["completionPercent"]) + completion) / 2)
        merge_daily_piece_state(current, item, completion)
        if confidence_score >= int(current.get("confidenceScore") or 0):
            current["confidence"] = confidence
            current["confidenceScore"] = confidence_score
            current["tip"] = str(item.get("immediateTip") or current.get("tip") or "").strip()[:180]
            current["evidence"] = str(item.get("evidence") or current.get("evidence") or "").strip()[:220]
            current["candidateTitle"] = candidate_title or current.get("candidateTitle") or ""
            current["candidateEvidence"] = str(
                item.get("candidateEvidence") or item.get("evidence") or current.get("candidateEvidence") or ""
            ).strip()[:220]
            for source_key in (
                "sampleId",
                "sectionId",
                "sourceTitle",
                "sourceUrl",
                "sourceWindow",
                "sourceStartSeconds",
                "sourceEndSeconds",
                "evidenceQuality",
                "reviewVersion",
            ):
                if item.get(source_key) not in {None, ""}:
                    current[source_key] = item.get(source_key)
            current["latestAt"] = item.get("createdAt") or current.get("latestAt")
    return sorted(
        pieces.values(),
        key=lambda item: (int(item.get("confidenceScore") or 0), int(item.get("completionPercent") or 0), str(item.get("latestAt") or "")),
        reverse=True,
    )[:12]


def review_media_sections(limit: int = 4) -> dict[str, Any]:
    state = load_state()
    review = state.setdefault("review", {})
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    sections = [section for section in review.get("notableSections", []) if isinstance(section, dict)]
    findings = [finding for finding in review.get("skillFindings", []) if isinstance(finding, dict)]
    reviewed_sections = {
        finding.get("sectionId")
        for finding in findings
        if finding.get("sectionId") and finding.get("reviewVersion") == REVIEW_VERSION
    }
    selected = [
        section
        for section in sections
        if section.get("status") == "candidate_playing_section" and section.get("id") not in reviewed_sections
    ][:limit]

    results: list[dict[str, Any]] = []
    new_findings: list[dict[str, Any]] = []
    new_piece_reviews: list[dict[str, Any]] = []
    progress_plan: dict[str, Any] | None = None

    for section in selected:
        sample = sample_for_section(section, samples)
        if not sample:
            results.append({"status": "blocked", "blocker": "media_sample_missing", "sectionId": section.get("id")})
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            wav_path = Path(temp.name)
        frame_dir = Path(tempfile.mkdtemp(prefix="curtis-frames-"))
        section_results: list[dict[str, Any]] = []
        try:
            ok, output = extract_review_wav(sample, section, wav_path)
            if ok:
                section_results.append(call_audio_model(wav_path, section))
            else:
                section_results.append({"status": "blocked", "blocker": "audio_extract_failed", "sectionId": section.get("id"), "detail": output[-500:]})
            frames, frame_output = extract_review_frames(sample, section, frame_dir)
            if frames:
                section_results.append(call_vision_model(frames, section))
            else:
                section_results.append({"status": "blocked", "blocker": "video_frame_extract_failed", "sectionId": section.get("id"), "detail": frame_output[-500:]})
        finally:
            wav_path.unlink(missing_ok=True)
            for frame in frame_dir.glob("*.jpg"):
                frame.unlink(missing_ok=True)
            frame_dir.rmdir()
        results.extend(section_results)
        merged_findings, merged_plan, piece_reviews = merge_review_results(section_results)
        if merged_findings:
            new_findings.extend(merged_findings)
            new_piece_reviews.extend(piece_reviews)
            progress_plan = merged_plan or progress_plan

    if new_findings:
        by_id = {finding.get("id"): finding for finding in findings if finding.get("id")}
        for finding in new_findings:
            by_id[finding["id"]] = finding
        review["skillFindings"] = list(by_id.values())[:80]
        review["pieces"] = aggregate_piece_reviews(review.get("pieces", []), new_piece_reviews)
        review["progressPlan"] = progress_plan
        review["currentWork"] = progress_plan.get("oneFocus") if progress_plan else "Curtis-focused review active."

    blockers = [result.get("blocker") for result in results if result.get("status") == "blocked" and result.get("blocker")]
    run = {
        "startedAt": utc_now(),
        "status": "model_reviewed" if new_findings else "blocked" if blockers else "no_new_sections",
        "sectionCount": len(selected),
        "findingCount": len(new_findings),
        "blockers": list(dict.fromkeys(blockers)),
        "results": results,
    }
    state["lastCoachRun"] = run
    save_state(state)
    return run
