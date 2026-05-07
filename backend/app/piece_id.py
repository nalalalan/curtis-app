from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .analyzer import active_ranges, extract_wav as extract_full_wav, rms_windows
from .coach import aggregate_piece_reviews, decode_json, piece_title_is_identified
from .settings import OPENAI_AUDIO_MODEL, OPENAI_PIECE_VERIFY_MODEL
from .state import load_state, save_state, utc_now


PIECE_ID_VERSION = "audio_piece_id_v2"
PIECE_ID_SECONDS = int(os.getenv("CURTIS_PIECE_ID_SECONDS", "45"))
PIECE_ID_SEGMENTS = int(os.getenv("CURTIS_PIECE_ID_SEGMENTS", "3"))
CLEAR_SCORE = float(os.getenv("CURTIS_PIECE_ID_CLEAR_SCORE", "0.85"))
PIECE_VERIFY_MODEL = OPENAI_PIECE_VERIFY_MODEL
DEFAULT_REJECTED_PIECES = [
    "Paganini Caprice No. 5",
    "Niccolo Paganini Caprice No. 5",
    "Pablo de Sarasate Zigeunerweisen, Op. 20",
    "Sarasate Zigeunerweisen",
    "Zigeunerweisen",
]
WEAK_TITLE_WORDS = {
    "a",
    "an",
    "and",
    "de",
    "for",
    "i",
    "ii",
    "iii",
    "in",
    "j",
    "major",
    "minor",
    "no",
    "number",
    "op",
    "opus",
    "s",
    "solo",
    "the",
    "violin",
}


def run_process(args: list[str], timeout: int = 180) -> tuple[int, str]:
    completed = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout


def extract_piece_id_wav(source: Path, target: Path, *, start_seconds: int = 0) -> tuple[bool, str]:
    code, output = run_process(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(max(0, start_seconds)),
            "-i",
            str(source),
            "-t",
            str(PIECE_ID_SECONDS),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(target),
        ],
        timeout=max(180, PIECE_ID_SECONDS + 90),
    )
    return code == 0 and target.exists() and target.stat().st_size > 44, output


def candidate_segment_starts(source: Path) -> list[int]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        wav_path = Path(temp.name)
    try:
        ok, _ = extract_full_wav(source, wav_path)
        if not ok:
            return [0]
        ranges = active_ranges(rms_windows(wav_path))
    finally:
        wav_path.unlink(missing_ok=True)

    ranked = sorted(
        ranges,
        key=lambda item: (
            float(item.get("end") or 0) - float(item.get("start") or 0),
            float(item.get("peakDbfs") or -120),
        ),
        reverse=True,
    )
    starts = [max(0, int(float(item.get("start") or 0)) - 2) for item in ranked]
    starts.append(0)
    unique = list(dict.fromkeys(starts))
    return unique[: max(1, PIECE_ID_SEGMENTS)]


def piece_id_prompt(sample: dict[str, Any]) -> str:
    rejected = rejected_piece_text(sample)
    return f"""
Return JSON only. Identify the exact classical violin repertoire from this audio excerpt.

Context:
- Public YouTube practice capture: {sample.get("title") or "untitled"}
- Window: {sample.get("window") or "unknown"}
- Rejected false labels for this sample: {rejected}

Rules:
- This is a piece-identification task, not a coaching task.
- Name a piece only when the melody, harmony, rhythm, or quoted material makes the exact work clear.
- Do not infer a piece from generic technique: fast notes, arpeggios, ricochet, spiccato, scales, caprice-like writing, or virtuoso style.
- Fast arpeggios, ricochet, spiccato, or caprice-like writing alone are not enough to name Paganini or any other work.
- Do not return a rejected false label. If one seems plausible from style alone, use title null and confidence "unknown".
- If the excerpt is speech, noise, tuning, setup, or not enough music, use title null and confidence "unknown".
- If the piece is clear, return composer, work title, opus/catalog number, and movement/section when known.
- Include concrete musical clues a violinist can verify by listening.
- Include one major immediate tip for this exact piece/excerpt.
- Completion percent means current-evidence Curtis-level readiness for this named piece. Use 100 only for clearly Curtis-level evidence.

JSON schema:
{{
  "title": "exact piece title or null",
  "confidence": "clear|possible|unknown",
  "confidenceScore": 0.0,
  "completionPercent": 0,
  "immediateTip": "one major immediately useful tip",
  "musicalClues": ["clue"],
  "topCandidates": [
    {{"title": "candidate", "score": 0.0, "reason": "short reason"}}
  ],
  "notes": "short factual note"
}}
""".strip()


def verification_prompt(sample: dict[str, Any], proposed_title: str) -> str:
    rejected = rejected_piece_text(sample)
    return f"""
Return JSON only. Verify whether this exact audio excerpt clearly matches the proposed repertoire title.

Context:
- Public YouTube practice capture: {sample.get("title") or "untitled"}
- Window: {sample.get("window") or "unknown"}
- Proposed title from a separate model: {proposed_title}
- Rejected false labels for this sample: {rejected}

Rules:
- This is a verification task. Do not agree with the proposed title unless the audible material clearly supports the exact work.
- A similar technique, texture, virtuoso style, fast arpeggios, spiccato, ricochet, or caprice-like writing is not enough.
- Do not output a rejected false label.
- If the proposed title is not exact enough, set title null, matchesProposed false, and exactEnough false.
- Include concrete musical clues a violinist can verify by listening.

JSON schema:
{{
  "title": "verified exact piece title or null",
  "matchesProposed": false,
  "exactEnough": false,
  "confidenceScore": 0.0,
  "musicalClues": ["clue"],
  "topCandidates": [
    {{"title": "candidate", "score": 0.0, "reason": "short reason"}}
  ],
  "notes": "short factual note"
}}
""".strip()


def chat_audio_payload(model: str, prompt: str, encoded_audio: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "input_audio", "input_audio": {"data": encoded_audio, "format": "wav"}},
                ],
            }
        ],
    }
    if model.startswith("gpt-audio"):
        payload["modalities"] = ["text"]
    return payload


def call_audio_json_model(wav_path: Path, sample: dict[str, Any], *, prompt: str, model: str, blocker: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"status": "blocked", "blocker": "missing_openai_api_key", "sampleId": sample.get("id")}

    encoded = base64.b64encode(wav_path.read_bytes()).decode("ascii")
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=chat_audio_payload(model, prompt, encoded),
        timeout=180,
    )
    if response.status_code >= 400:
        return {
            "status": "blocked",
            "blocker": blocker,
            "sampleId": sample.get("id"),
            "detail": response.text[:500],
        }
    content = response.json()["choices"][0]["message"].get("content") or "{}"
    try:
        raw = decode_json(content)
    except json.JSONDecodeError:
        return {
            "status": "blocked",
            "blocker": f"{blocker}_parse",
            "sampleId": sample.get("id"),
            "detail": content[:500],
        }
    return raw


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def compact_title(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    normalized = normalized.replace("prelude", "preludio")
    return re.sub(r"\s+", " ", normalized).strip()


def title_tokens(value: str) -> set[str]:
    return {token for token in compact_title(value).split() if token and token not in WEAK_TITLE_WORDS}


def configured_rejected_pieces() -> list[str]:
    raw = os.getenv("CURTIS_REJECTED_PIECES", "")
    configured = [item.strip() for item in raw.split("|") if item.strip()]
    return list(dict.fromkeys([*DEFAULT_REJECTED_PIECES, *configured]))


def rejections_apply_to_sample(sample: dict[str, Any]) -> bool:
    if os.getenv("CURTIS_GLOBAL_REJECTED_PIECES", "").strip().lower() in {"1", "true", "yes"}:
        return True
    title = compact_title(str(sample.get("title") or ""))
    window = str(sample.get("window") or "")
    return "5 1 26" in title or "5-1" in title or "5/1" in title or "wDfVpTU4I_I" in window


def rejected_pieces_for_sample(sample: dict[str, Any]) -> list[str]:
    if not rejections_apply_to_sample(sample):
        return []
    return configured_rejected_pieces()


def rejected_piece_text(sample: dict[str, Any]) -> str:
    rejected = rejected_pieces_for_sample(sample)
    return ", ".join(rejected) if rejected else "none"


def title_is_rejected(title: str, sample: dict[str, Any]) -> bool:
    compact = compact_title(title)
    if not compact:
        return False
    for rejected in rejected_pieces_for_sample(sample):
        rejected_compact = compact_title(rejected)
        if compact == rejected_compact or compact in rejected_compact or rejected_compact in compact:
            return True
    return False


def same_piece_title(left: str, right: str) -> bool:
    left_compact = compact_title(left)
    right_compact = compact_title(right)
    if not left_compact or not right_compact:
        return False
    if left_compact == right_compact:
        return True
    if len(left_compact) >= 12 and left_compact in right_compact:
        return True
    if len(right_compact) >= 12 and right_compact in left_compact:
        return True
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    common = left_tokens & right_tokens
    if re.search(r"\bbwv\s*1006\b", left_compact) and re.search(r"\bbwv\s*1006\b", right_compact):
        return True
    left_numbers = set(re.findall(r"\d+", left_compact))
    right_numbers = set(re.findall(r"\d+", right_compact))
    if left_numbers & right_numbers and len(common) >= 2:
        return True
    required = max(3, min(len(left_tokens), len(right_tokens), 5))
    return len(common) >= required


def sanitized_candidates(raw: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = raw.get("topCandidates") if isinstance(raw.get("topCandidates"), list) else []
    clean: list[dict[str, Any]] = []
    for candidate in candidates[:5]:
        if not isinstance(candidate, dict):
            continue
        clean.append(
            {
                "title": str(candidate.get("title") or "").strip()[:140],
                "score": max(0.0, min(1.0, number(candidate.get("score")))),
                "reason": str(candidate.get("reason") or "").strip()[:180],
            }
        )
    return clean


def musical_clues(raw: dict[str, Any]) -> list[str]:
    return [str(item).strip()[:180] for item in raw.get("musicalClues", []) if str(item).strip()][:5]


def normalize_primary_identification(raw: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    raw_title = str(raw.get("title") or "").strip()[:140]
    score = max(0.0, min(1.0, number(raw.get("confidenceScore"))))
    raw_confidence = str(raw.get("confidence") or "unknown").strip().lower()
    rejected = title_is_rejected(raw_title, sample)
    clear = raw_confidence == "clear" and score >= CLEAR_SCORE and piece_title_is_identified(raw_title) and not rejected
    clues = musical_clues(raw)
    candidates = sanitized_candidates(raw)
    status = "piece_candidate_clear" if clear else "piece_rejected_guess" if rejected else "piece_unidentified"
    return {
        "status": status,
        "sampleId": sample.get("id"),
        "url": sample.get("url"),
        "title": raw_title if clear else "Piece being identified",
        "proposedTitle": raw_title,
        "confidence": "clear" if clear else "unknown",
        "confidenceScore": score,
        "completionPercent": int(round(max(0.0, min(100.0, number(raw.get("completionPercent")))))) if clear else 0,
        "immediateTip": str(
            raw.get("immediateTip")
            or "Record one clean 60-second excerpt with the full violin, bow arm, left hand, and music stand visible."
        ).strip()[:180],
        "evidence": "; ".join(clues)[:220] or str(raw.get("notes") or "Exact piece not identified from current excerpt.").strip()[:220],
        "musicalClues": clues,
        "topCandidates": candidates,
        "notes": str(raw.get("notes") or "").strip()[:300],
        "reviewVersion": PIECE_ID_VERSION,
        "createdAt": utc_now(),
    }


def normalize_verification(raw: dict[str, Any], sample: dict[str, Any], proposed_title: str) -> dict[str, Any]:
    raw_title = str(raw.get("title") or "").strip()[:140]
    score = max(0.0, min(1.0, number(raw.get("confidenceScore"))))
    matches = boolish(raw.get("matchesProposed"))
    exact = boolish(raw.get("exactEnough"))
    rejected = title_is_rejected(raw_title, sample)
    verified = (
        matches
        and exact
        and score >= CLEAR_SCORE
        and piece_title_is_identified(raw_title)
        and same_piece_title(raw_title, proposed_title)
        and not rejected
    )
    clues = musical_clues(raw)
    return {
        "status": "verified" if verified else "not_verified",
        "title": raw_title,
        "matchesProposed": matches,
        "exactEnough": exact,
        "confidenceScore": score,
        "musicalClues": clues,
        "topCandidates": sanitized_candidates(raw),
        "evidence": "; ".join(clues)[:220] or str(raw.get("notes") or "Exact piece not corroborated.").strip()[:220],
        "notes": str(raw.get("notes") or "").strip()[:300],
        "model": PIECE_VERIFY_MODEL,
    }


def corroborated_result(primary: dict[str, Any], verification: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    proposed_title = str(primary.get("proposedTitle") or "")
    if verification.get("status") != "verified":
        return {
            **primary,
            "status": "piece_candidate_unverified",
            "title": "Piece being identified",
            "confidence": "unknown",
            "confidenceScore": min(number(primary.get("confidenceScore")), number(verification.get("confidenceScore"))),
            "completionPercent": 0,
            "evidence": "Exact piece not corroborated by second audio model.",
            "verificationTitle": verification.get("title") or "",
            "verification": verification,
        }
    title = str(verification.get("title") or proposed_title).strip()[:140]
    score = min(number(primary.get("confidenceScore")), number(verification.get("confidenceScore")))
    evidence_parts = [str(primary.get("evidence") or "").strip(), str(verification.get("evidence") or "").strip()]
    return {
        **primary,
        "status": "piece_identified",
        "title": title,
        "confidence": "clear",
        "confidenceScore": max(0.0, min(1.0, score)),
        "completionPercent": int(primary.get("completionPercent") or 0),
        "evidence": "; ".join(part for part in evidence_parts if part)[:220],
        "verificationTitle": verification.get("title") or "",
        "verification": verification,
        "createdAt": utc_now(),
    }


def identify_wav_segment(wav_path: Path, sample: dict[str, Any], *, segment_start: int) -> dict[str, Any]:
    raw_primary = call_audio_json_model(
        wav_path,
        sample,
        prompt=piece_id_prompt(sample),
        model=OPENAI_AUDIO_MODEL,
        blocker="openai_piece_id_failed",
    )
    if raw_primary.get("status") == "blocked":
        return {**raw_primary, "segmentStartSeconds": segment_start}
    primary = normalize_primary_identification(raw_primary, sample)
    primary["segmentStartSeconds"] = segment_start
    if primary.get("status") != "piece_candidate_clear":
        return primary
    proposed_title = str(primary.get("proposedTitle") or "")
    raw_verification = call_audio_json_model(
        wav_path,
        sample,
        prompt=verification_prompt(sample, proposed_title),
        model=PIECE_VERIFY_MODEL,
        blocker="openai_piece_verify_failed",
    )
    if raw_verification.get("status") == "blocked":
        return {
            **primary,
            "status": "piece_candidate_unverified",
            "title": "Piece being identified",
            "confidence": "unknown",
            "completionPercent": 0,
            "blocker": raw_verification.get("blocker"),
            "detail": raw_verification.get("detail"),
        }
    verification = normalize_verification(raw_verification, sample, proposed_title)
    return corroborated_result(primary, verification, sample)


def best_non_identifying_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"status": "piece_unidentified", "title": "Piece being identified", "confidence": "unknown"}
    priority = {
        "piece_candidate_unverified": 4,
        "piece_rejected_guess": 3,
        "piece_unidentified": 2,
        "blocked": 1,
    }
    result = sorted(
        results,
        key=lambda item: (
            priority.get(str(item.get("status")), 0),
            number(item.get("confidenceScore")),
        ),
        reverse=True,
    )[0]
    return {**result, "segmentsTried": len(results)}


def identify_sample(sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(sample.get("path") or ""))
    if not path.exists():
        return {"status": "blocked", "blocker": "media_sample_missing", "sampleId": sample.get("id")}
    segment_starts = candidate_segment_starts(path)
    segment_results: list[dict[str, Any]] = []
    for segment_start in segment_starts:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            wav_path = Path(temp.name)
        try:
            ok, output = extract_piece_id_wav(path, wav_path, start_seconds=segment_start)
            if not ok:
                segment_results.append(
                    {
                        "status": "blocked",
                        "blocker": "piece_id_audio_extract_failed",
                        "sampleId": sample.get("id"),
                        "segmentStartSeconds": segment_start,
                        "detail": output[-500:],
                    }
                )
                continue
            result = identify_wav_segment(wav_path, sample, segment_start=segment_start)
            segment_results.append(result)
            if result.get("status") == "piece_identified":
                result["segmentsTried"] = len(segment_results)
                return result
        finally:
            wav_path.unlink(missing_ok=True)

    result = best_non_identifying_result(segment_results)
    if result.get("status") == "blocked" and any(item.get("status") != "blocked" for item in segment_results):
        result["status"] = "piece_unidentified"
        result["title"] = "Piece being identified"
        result["confidence"] = "unknown"
    return result


def piece_review_from_identification(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "confidence": result.get("confidence"),
        "completionPercent": result.get("completionPercent"),
        "immediateTip": result.get("immediateTip"),
        "evidence": result.get("evidence"),
        "sectionId": result.get("sampleId"),
        "sampleId": result.get("sampleId"),
        "createdAt": result.get("createdAt") or utc_now(),
        "evidenceQuality": "usable" if result.get("status") == "piece_identified" else "weak",
    }


def identify_pieces_from_samples(limit: int = 4) -> dict[str, Any]:
    state = load_state()
    review = state.setdefault("review", {})
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    previous = [
        item
        for item in review.get("pieceIdentifications", [])
        if isinstance(item, dict)
    ]
    processed_ids = {
        item.get("sampleId")
        for item in previous
        if item.get("sampleId") and item.get("reviewVersion") == PIECE_ID_VERSION
    }
    selected = [sample for sample in samples if sample.get("id") not in processed_ids][:limit]
    results = [identify_sample(sample) for sample in selected]
    usable_piece_reviews = [
        piece_review_from_identification(result)
        for result in results
        if result.get("status") == "piece_identified"
    ]
    review["pieceIdentifications"] = [*results, *previous][:80]
    if usable_piece_reviews:
        review["pieces"] = aggregate_piece_reviews(review.get("pieces", []), usable_piece_reviews)
        review["currentWork"] = f"Piece identified: {usable_piece_reviews[0]['title']}"

    blockers = [result.get("blocker") for result in results if result.get("status") == "blocked" and result.get("blocker")]
    run = {
        "startedAt": utc_now(),
        "status": "piece_identified" if usable_piece_reviews else "blocked" if blockers else "piece_unidentified",
        "sampleCount": len(selected),
        "identifiedCount": len(usable_piece_reviews),
        "blockers": list(dict.fromkeys(blockers)),
        "results": results,
    }
    state["lastPieceIdRun"] = run
    save_state(state)
    return run
