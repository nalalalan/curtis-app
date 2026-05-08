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

from .analyzer import active_ranges, extract_wav as extract_full_wav, parse_window_start, rms_windows
from .coach import aggregate_piece_reviews, decode_json, piece_title_is_identified
from .corrections import (
    FIVE_ONE_REJECTED_TITLES,
    correction_for_item,
    item_stale_after_source_correction,
    scrubbed_piece_item,
    source_requires_confirmed_acceptance,
    title_rejected_for_item,
)
from .settings import OPENAI_AUDIO_MODEL, OPENAI_PIECE_VERIFY_MODEL
from .state import load_state, save_state, utc_now


PIECE_ID_VERSION = "audio_piece_id_v8"
PIECE_ID_SECONDS = int(os.getenv("CURTIS_PIECE_ID_SECONDS", "45"))
PIECE_ID_SEGMENTS = int(os.getenv("CURTIS_PIECE_ID_SEGMENTS", "3"))
CLEAR_SCORE = float(os.getenv("CURTIS_PIECE_ID_CLEAR_SCORE", "0.85"))
LONG_SESSION_PRACTICE_FLOOR_SECONDS = int(os.getenv("CURTIS_LONG_SESSION_PRACTICE_FLOOR_SECONDS", str(2 * 60 * 60)))
LONG_SESSION_LATE_SAMPLE_COUNT = int(os.getenv("CURTIS_LONG_SESSION_LATE_SAMPLE_COUNT", "3"))
LONG_SESSION_SPAN_SECONDS = int(os.getenv("CURTIS_LONG_SESSION_SPAN_SECONDS", str(90 * 60)))
PIECE_VERIFY_MODEL = OPENAI_PIECE_VERIFY_MODEL
# Alan corrections are source-specific. These do not ban future videos from
# identifying this repertoire when he actually practices it.
DEFAULT_REJECTED_PIECES = []
FIVE_ONE_SEEDED_CANDIDATES = [
    "Beethoven Symphony No. 9, Scherzo, Violin I part",
    "Beethoven Symphony No. 7, fourth movement, Violin I part",
    "Beethoven Leonore Overture No. 3, Violin I part",
    "Schumann Symphony No. 2, Scherzo, Violin I part",
    "Schubert Symphony No. 9, fourth movement, Violin I part",
    "Rossini William Tell Overture, finale, Violin I part",
    "Rossini Semiramide Overture, Violin I part",
    "Rossini La Gazza Ladra Overture, Violin I part",
    "Weber Der Freischutz Overture, Violin I part",
    "Weber Oberon Overture, Violin I part",
    "Berlioz Roman Carnival Overture, Violin I part",
    "Berlioz Symphonie fantastique, fifth movement, Violin I part",
    "Wagner Tannhauser Overture, Violin I part",
    "Wagner Die Meistersinger von Nurnberg Overture, Violin I part",
    "Wagner Rienzi Overture, Violin I part",
    "Verdi La Forza del Destino Overture, Violin I part",
    "Verdi Nabucco Overture, Violin I part",
    "Smetana The Moldau, Violin I part",
    "Rimsky-Korsakov Scheherazade, Violin I part",
    "Rimsky-Korsakov Capriccio Espagnol, Violin I part",
    "Borodin Polovtsian Dances, Violin I part",
    "Bizet L'Arlesienne Suite No. 2, Farandole, Violin I part",
    "Mahler Symphony No. 1, fourth movement, Violin I part",
    "Mahler Symphony No. 5, Scherzo, Violin I part",
    "Mahler Symphony No. 9, first movement, Violin I part",
    "Prokofiev Romeo and Juliet, Violin I part",
    "Prokofiev Lieutenant Kije Suite, Violin I part",
    "Dvorak Symphony No. 9, Scherzo, Violin I part",
    "Dvorak Slavonic Dances, Violin I part",
    "Shostakovich Symphony No. 10, Scherzo, Violin I part",
    "Shostakovich Festive Overture, Violin I part",
    "Nielsen Maskarade Overture, Violin I part",
    "Elgar Cockaigne Overture, Violin I part",
    "Stravinsky Firebird Suite, Violin I part",
    "Stravinsky Petrushka, Violin I part",
    "Stravinsky The Rite of Spring, Violin I part",
    "Bartok Concerto for Orchestra, Violin I part",
    "Kodaly Dances of Galanta, Violin I part",
    "Khachaturian Sabre Dance, Violin I part",
    "Holst The Planets, Mercury, Violin I part",
]
FIVE_ONE_REJECTED_PIECES = FIVE_ONE_REJECTED_TITLES
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
    source_hint = source_hint_text(sample)
    return f"""
Return JSON only. Identify the exact classical violin repertoire from this audio excerpt.

Context:
- Public YouTube practice capture: {sample.get("title") or "untitled"}
- Window: {sample.get("window") or "unknown"}
- Rejected false labels for this sample: {rejected}
- Source hint from Alan: {source_hint}

Rules:
- This is a piece-identification task, not a coaching task.
- If the source hint says orchestral work, identify the orchestral work and first-violin part, not a solo violin piece.
- For an orchestral-work source, do not return concerto, caprice, showpiece, sonata, partita, or other solo repertoire unless the audio clearly contradicts the hint.
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
    source_hint = source_hint_text(sample)
    return f"""
Return JSON only. Verify whether this exact audio excerpt clearly matches the proposed repertoire title.

Context:
- Public YouTube practice capture: {sample.get("title") or "untitled"}
- Window: {sample.get("window") or "unknown"}
- Proposed title from a separate model: {proposed_title}
- Rejected false labels for this sample: {rejected}
- Source hint from Alan: {source_hint}

Rules:
- This is a verification task. Do not agree with the proposed title unless the audible material clearly supports the exact work.
- If the source hint says orchestral work, reject solo-repertoire proposals and verify only an orchestral work / violin I part.
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


def practice_window_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(samples, key=lambda sample: sample_window_start(sample))
    if prefer_late_practice_windows(ordered):
        late = [
            sample
            for sample in ordered
            if sample_window_start(sample) >= LONG_SESSION_PRACTICE_FLOOR_SECONDS
        ]
        if late:
            return late
    return ordered


def source_window_allowed(result: dict[str, Any], samples_by_url: dict[str, list[dict[str, Any]]]) -> bool:
    url = str(result.get("sourceUrl") or result.get("url") or "")
    if not url:
        return True
    group = samples_by_url.get(url, [])
    if not group or not prefer_late_practice_windows(group):
        return True
    return int(number(result.get("sourceStartSeconds"), 0)) >= LONG_SESSION_PRACTICE_FLOOR_SECONDS


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
    if os.getenv("CURTIS_GLOBAL_REJECTED_PIECES", "0").strip().lower() not in {"0", "false", "no"}:
        return True
    title = compact_title(str(sample.get("title") or ""))
    window = str(sample.get("window") or "")
    return "5 1 26" in title or "5-1" in title or "5/1" in title or "wDfVpTU4I_I" in window


def sample_matches_five_one(sample: dict[str, Any]) -> bool:
    title = compact_title(str(sample.get("title") or ""))
    window = str(sample.get("window") or "")
    return "5 1 26" in title or "5-1" in title or "5/1" in title or "wDfVpTU4I_I" in window


def rejected_pieces_for_sample(sample: dict[str, Any]) -> list[str]:
    if not rejections_apply_to_sample(sample):
        rejected = []
    else:
        rejected = configured_rejected_pieces()
    correction = correction_for_item(load_state(), sample)
    rejected = [*rejected, *[str(item) for item in correction.get("rejectedTitles", []) if str(item).strip()]]
    if sample_matches_five_one(sample):
        rejected = [*rejected, *FIVE_ONE_REJECTED_PIECES]
    return list(dict.fromkeys(rejected))


def rejected_piece_text(sample: dict[str, Any]) -> str:
    rejected = rejected_pieces_for_sample(sample)
    return ", ".join(rejected) if rejected else "none"


def source_hint_text(sample: dict[str, Any]) -> str:
    correction = correction_for_item(load_state(), sample)
    hint = str(correction.get("sourceHint") or "").strip()
    if hint:
        return hint
    if sample_matches_five_one(sample):
        return "Violin I part of an orchestral work; not solo violin repertoire."
    return "none"


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
        "sampleTitle": sample.get("title"),
        "sampleWindow": sample.get("window"),
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
        "completionPercent": 0,
        "readinessStatus": "not_scored_from_piece_id",
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
    base_start = parse_window_start(str(sample.get("window") or ""))
    primary["sourceTitle"] = sample.get("title")
    primary["sourceUrl"] = sample.get("url")
    primary["sourceWindow"] = sample.get("window")
    primary["sourceStartSeconds"] = base_start + segment_start
    primary["sourceEndSeconds"] = base_start + segment_start + PIECE_ID_SECONDS
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


def candidate_title_from_result(result: dict[str, Any]) -> list[str]:
    titles = [str(result.get("title") or ""), str(result.get("proposedTitle") or "")]
    for candidate in result.get("topCandidates", []):
        if isinstance(candidate, dict):
            titles.append(str(candidate.get("title") or ""))
    return [
        title.strip()
        for title in titles
        if piece_title_is_identified(title) and not title_is_rejected(title, result)
    ]


def ranked_candidate_titles(results: list[dict[str, Any]], *, limit: int = 8) -> list[str]:
    counts: dict[str, tuple[str, int]] = {}
    for result in results:
        for title in candidate_title_from_result(result):
            key = compact_title(title)
            if not key:
                continue
            display, count = counts.get(key, (title, 0))
            counts[key] = (display, count + 1)
    ranked = sorted(counts.values(), key=lambda item: (item[1], len(item[0])), reverse=True)
    return [title for title, _count in ranked[:limit]]


def seeded_candidate_titles(sample: dict[str, Any], candidates: list[str]) -> list[str]:
    if not sample_matches_five_one(sample):
        return candidates
    return list(dict.fromkeys([*FIVE_ONE_SEEDED_CANDIDATES, *candidates]))


def consensus_prompt(sample: dict[str, Any], candidates: list[str]) -> str:
    rejected = rejected_piece_text(sample)
    source_hint = source_hint_text(sample)
    candidates = seeded_candidate_titles(sample, candidates)
    candidate_text = "\n".join(f"- {title}" for title in candidates) if candidates else "- none"
    return f"""
Return JSON only. Identify the common/main classical violin repertoire across this montage of multiple windows from the same long practice video.

Context:
- Public YouTube practice capture: {sample.get("title") or "untitled"}
- Source windows: {sample.get("window") or "multiple"}
- Rejected false labels for this video: {rejected}
- Source hint from Alan: {source_hint}
- Candidate titles already proposed by window-level passes:
{candidate_text}

Rules:
- This is a same-video consensus task. Prefer the title that explains repeated material across windows, not a one-off stylistic guess.
- If the source hint says orchestral work, identify the orchestral work and first-violin part, not solo violin repertoire.
- For an orchestral-work source, do not return concerto, caprice, showpiece, sonata, partita, or other solo repertoire unless the audio clearly contradicts the hint.
- Compare the candidate titles against the audio and choose unknown if none are exact enough.
- Do not infer a piece from generic technique: fast notes, arpeggios, ricochet, spiccato, scales, caprice-like writing, or virtuoso style.
- Do not return a rejected false label.
- If the work is clearer than the movement, put the broader work in workLevelTitle and set exactMovementConfidence below 0.75.
- No readiness or completion percent.

JSON schema:
{{
  "mainPiece": "exact piece title or null",
  "workLevelTitle": "broader work title or null",
  "confidence": "clear|possible|unknown",
  "confidenceScore": 0.0,
  "exactMovementConfidence": 0.0,
  "audibleClues": ["clue"],
  "candidateScores": [
    {{"title": "candidate", "score": 0.0, "reason": "short reason"}}
  ],
  "notes": "short factual note"
}}
""".strip()


def consensus_title(raw: dict[str, Any]) -> str:
    exact = str(raw.get("mainPiece") or raw.get("piece") or raw.get("displayTitle") or "").strip()
    work_level = str(raw.get("workLevelTitle") or "").strip()
    exact_movement = number(raw.get("exactMovementConfidence"), 0.0)
    title = exact if exact_movement >= 0.75 else work_level or exact
    return title.strip()


def build_consensus_montage(samples: list[dict[str, Any]], target: Path) -> tuple[list[dict[str, Any]], str]:
    excerpts: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="curtis-consensus-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        concat_lines: list[str] = []
        sample_limit = max(8, int(os.getenv("CURTIS_PIECE_CONSENSUS_SAMPLE_LIMIT", "12")))
        for index, sample in enumerate(samples[:sample_limit]):
            source = Path(str(sample.get("path") or ""))
            if not source.exists():
                continue
            starts = candidate_segment_starts(source)
            segment_start = starts[0] if starts else 0
            segment_path = temp_dir / f"segment-{index:02d}.wav"
            code, output = run_process(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(max(0, segment_start)),
                    "-i",
                    str(source),
                    "-t",
                    "12",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "wav",
                    str(segment_path),
                ],
                timeout=120,
            )
            if code != 0 or not segment_path.exists() or segment_path.stat().st_size <= 44:
                continue
            base_start = parse_window_start(str(sample.get("window") or ""))
            excerpts.append(
                {
                    "sampleId": sample.get("id"),
                    "title": sample.get("title"),
                    "url": sample.get("url"),
                    "window": sample.get("window"),
                    "startSeconds": base_start + segment_start,
                    "endSeconds": base_start + segment_start + 12,
                }
            )
            concat_lines.append(f"file '{segment_path.resolve().as_posix()}'")
        if len(concat_lines) < 2:
            return excerpts, "not_enough_consensus_segments"
        concat_path = temp_dir / "concat.txt"
        concat_path.write_text("\n".join(concat_lines), encoding="ascii")
        code, output = run_process(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(target),
            ],
            timeout=180,
        )
        if code != 0 or not target.exists() or target.stat().st_size <= 44:
            return excerpts, output[-500:]
    return excerpts, ""


def consensus_matches(primary: dict[str, Any], verifier: dict[str, Any], sample: dict[str, Any]) -> bool:
    primary_title = consensus_title(primary)
    verifier_title = consensus_title(verifier)
    if title_is_rejected(primary_title, sample) or title_is_rejected(verifier_title, sample):
        return False
    primary_score = number(primary.get("confidenceScore"), 0.0)
    verifier_score = number(verifier.get("confidenceScore"), 0.0)
    primary_confidence = str(primary.get("confidence") or "unknown").lower()
    verifier_confidence = str(verifier.get("confidence") or "unknown").lower()
    return (
        primary_confidence in {"clear", "possible"}
        and verifier_confidence in {"clear", "possible"}
        and min(primary_score, verifier_score) >= 0.7
        and piece_title_is_identified(primary_title)
        and same_piece_title(primary_title, verifier_title)
    )


def identify_video_consensus(samples: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable_samples = practice_window_samples([sample for sample in samples if Path(str(sample.get("path") or "")).exists()])
    if len(usable_samples) < 2:
        return None
    first = usable_samples[0]
    candidates = ranked_candidate_titles(results)
    fake_sample = {
        "id": f"{first.get('id')}-consensus",
        "title": first.get("title"),
        "url": first.get("url"),
        "window": ", ".join(str(sample.get("window") or "") for sample in usable_samples[:8] if sample.get("window")),
    }
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        montage_path = Path(temp.name)
    try:
        if not candidates:
            probe_limit = max(0, int(os.getenv("CURTIS_PIECE_CONSENSUS_PROBE_LIMIT", "2")))
            probe_results = [identify_sample(sample) for sample in usable_samples[:probe_limit]]
            candidates = ranked_candidate_titles(probe_results)
        excerpts, error = build_consensus_montage(usable_samples, montage_path)
        if error:
            return {
                "status": "blocked",
                "blocker": "piece_consensus_audio_extract_failed",
                "sampleId": fake_sample["id"],
                "detail": error,
            }
        primary_raw = call_audio_json_model(
            montage_path,
            fake_sample,
            prompt=consensus_prompt(fake_sample, candidates),
            model=OPENAI_AUDIO_MODEL,
            blocker="openai_piece_consensus_failed",
        )
        if primary_raw.get("status") == "blocked":
            return primary_raw
        verifier_raw = call_audio_json_model(
            montage_path,
            fake_sample,
            prompt=consensus_prompt(fake_sample, candidates),
            model=PIECE_VERIFY_MODEL,
            blocker="openai_piece_consensus_verify_failed",
        )
        if verifier_raw.get("status") == "blocked":
            return verifier_raw
    finally:
        montage_path.unlink(missing_ok=True)

    verified = consensus_matches(primary_raw, verifier_raw, fake_sample)
    title = consensus_title(primary_raw)
    source = excerpts[0] if excerpts else {}
    confidence_score = min(number(primary_raw.get("confidenceScore")), number(verifier_raw.get("confidenceScore")))
    return {
        "status": "piece_identified" if verified else "piece_candidate_unverified",
        "sampleId": fake_sample["id"],
        "url": first.get("url"),
        "sampleTitle": first.get("title"),
        "sampleWindow": fake_sample.get("window"),
        "title": title if verified else "Piece being identified",
        "proposedTitle": title,
        "confidence": "clear" if verified else "unknown",
        "confidenceScore": max(0.0, min(1.0, confidence_score)),
        "completionPercent": 0,
        "readinessStatus": "not_scored_from_piece_id",
        "immediateTip": "Use one short repeated cell, then record one clean source take for verification.",
        "evidence": "; ".join(str(item).strip() for item in primary_raw.get("audibleClues", []) if str(item).strip())[:220]
        or str(primary_raw.get("notes") or "Same-video consensus completed.").strip()[:220],
        "musicalClues": [str(item).strip()[:180] for item in primary_raw.get("audibleClues", []) if str(item).strip()][:5],
        "topCandidates": sanitized_candidates({"topCandidates": primary_raw.get("candidateScores", [])}),
        "notes": str(primary_raw.get("notes") or "").strip()[:300],
        "reviewVersion": PIECE_ID_VERSION,
        "createdAt": utc_now(),
        "sourceTitle": source.get("title") or first.get("title"),
        "sourceUrl": source.get("url") or first.get("url"),
        "sourceWindow": source.get("window") or first.get("window"),
        "sourceStartSeconds": source.get("startSeconds"),
        "sourceEndSeconds": source.get("endSeconds"),
        "consensus": {
            "sampleCount": len(usable_samples),
            "excerpts": excerpts[:8],
            "candidates": candidates,
            "primary": primary_raw,
            "verifier": verifier_raw,
        },
    }


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
        "completionPercent": 0,
        "immediateTip": result.get("immediateTip"),
        "evidence": result.get("evidence"),
        "sectionId": result.get("sampleId"),
        "sampleId": result.get("sampleId"),
        "sourceTitle": result.get("sourceTitle") or result.get("sampleTitle"),
        "sourceUrl": result.get("sourceUrl") or result.get("url"),
        "sourceWindow": result.get("sourceWindow") or result.get("sampleWindow"),
        "sourceStartSeconds": result.get("sourceStartSeconds"),
        "sourceEndSeconds": result.get("sourceEndSeconds"),
        "createdAt": result.get("createdAt") or utc_now(),
        "reviewVersion": PIECE_ID_VERSION,
        "evidenceQuality": "verified_piece_id" if result.get("status") == "piece_identified" else "weak",
    }


def apply_source_correction_gate(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "blocked":
        return result
    titles: list[Any] = [
        result.get("title"),
        result.get("proposedTitle"),
        result.get("candidateTitle"),
        result.get("verificationTitle"),
    ]
    verification = result.get("verification")
    if isinstance(verification, dict):
        titles.append(verification.get("title"))
    for candidate in result.get("topCandidates", []):
        if isinstance(candidate, dict):
            titles.append(candidate.get("title"))
    rejected_candidate = any(
        title_rejected_for_item(title, state, result) or title_is_rejected(str(title or ""), result)
        for title in titles
    )
    requires_acceptance = source_requires_confirmed_acceptance(state, result)
    if not rejected_candidate and not (result.get("status") == "piece_identified" and requires_acceptance):
        return result
    candidate_title = str(result.get("title") or result.get("proposedTitle") or "").strip()
    gated = scrubbed_piece_item(result)
    gated["status"] = "source_correction_unresolved" if requires_acceptance else "piece_rejected_guess"
    gated["candidateTitle"] = "" if rejected_candidate else candidate_title[:140]
    gated["candidateEvidence"] = "Repeated corrected false labels for this source. Exact piece pending."
    gated["evidence"] = "Repeated corrected false labels for this source. Exact piece pending."
    return gated


def identify_pieces_from_samples(limit: int = 4) -> dict[str, Any]:
    state = load_state()
    review = state.setdefault("review", {})
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    samples_by_url: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        url = str(sample.get("url") or "")
        if url:
            samples_by_url.setdefault(url, []).append(sample)
    prioritized_samples = [
        sample
        for group in samples_by_url.values()
        for sample in practice_window_samples(group)
    ]
    if not prioritized_samples:
        prioritized_samples = sorted(samples, key=lambda sample: sample_window_start(sample))
    previous = [
        apply_source_correction_gate(state, item)
        for item in review.get("pieceIdentifications", [])
        if isinstance(item, dict) and not item_stale_after_source_correction(state, item)
    ]
    processed_ids = {
        item.get("sampleId")
        for item in previous
        if item.get("sampleId") and item.get("reviewVersion") == PIECE_ID_VERSION
    }
    selected = [sample for sample in prioritized_samples if sample.get("id") not in processed_ids][:limit]
    results = [apply_source_correction_gate(state, identify_sample(sample)) for sample in selected]
    all_results = [*results, *previous]
    consensus_processed_urls = {
        item.get("url")
        for item in previous
        if str(item.get("sampleId") or "").endswith("-consensus") and item.get("reviewVersion") == PIECE_ID_VERSION
    }
    consensus_samples_by_url: dict[str, list[dict[str, Any]]] = {}
    for url, items in samples_by_url.items():
        if not url or url in consensus_processed_urls:
            continue
        usable_items = practice_window_samples(items)
        consensus_samples_by_url[url] = usable_items
    consensus_limit = max(0, int(os.getenv("CURTIS_PIECE_CONSENSUS_LIMIT", "2")))
    consensus_candidates = sorted(
        (items for items in consensus_samples_by_url.values() if len(items) >= 2),
        key=lambda items: (
            1 if any(sample_matches_five_one(sample) for sample in items) else 0,
            len(items),
            str(items[0].get("title") or ""),
        ),
        reverse=True,
    )[:consensus_limit]
    consensus_results = []
    for items in consensus_candidates:
        url = str(items[0].get("url") or "")
        video_results = [result for result in all_results if result.get("url") == url or result.get("sourceUrl") == url]
        result = identify_video_consensus(items, video_results)
        if result is not None:
            consensus_results.append(apply_source_correction_gate(state, result))
    results = [*consensus_results, *results]
    usable_piece_reviews = [
        piece_review_from_identification(result)
        for result in results
        if (
            result.get("status") == "piece_identified"
            and source_window_allowed(result, samples_by_url)
            and not source_requires_confirmed_acceptance(state, result)
        )
    ]
    review["pieceIdentifications"] = [*results, *previous][:80]
    review["pieces"] = [
        piece
        for piece in review.get("pieces", [])
        if not (
            isinstance(piece, dict)
            and str(piece.get("evidenceQuality") or "") == "verified_piece_id"
            and (
                str(piece.get("reviewVersion") or "") != PIECE_ID_VERSION
                or not source_window_allowed(piece, samples_by_url)
                or item_stale_after_source_correction(state, piece)
                or source_requires_confirmed_acceptance(state, piece)
            )
        )
    ]
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
