from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .analyzer import parse_window_start
from .settings import MODEL_REVIEW_SAMPLE_SECONDS, OPENAI_AUDIO_MODEL
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


def normalize_review(raw: dict[str, Any], section: dict[str, Any]) -> dict[str, Any]:
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
                "dimension": dimension,
                "judgment": judgment,
                "evidence": evidence,
                "practiceConstraint": str(item.get("practiceConstraint") or "").strip()[:180],
                "createdAt": utc_now(),
            }
        )

    plan = raw.get("progressPlan") if isinstance(raw.get("progressPlan"), dict) else {}
    session_plan = raw.get("sessionPlan") if isinstance(raw.get("sessionPlan"), list) else []
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
        "evidenceQuality": evidence_quality,
        "sectionSummary": str(raw.get("sectionSummary") or "Model review completed.").strip()[:260],
        "findings": findings[:5],
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
- No admission prediction, no odds, no reassurance, no motivation, no diagnosis language.
- Do not name repertoire unless it is clearly audible.
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
        return normalize_review(decode_json(content), section)
    except Exception:
        return {"status": "blocked", "blocker": "openai_audio_review_parse_failed", "detail": content[:500]}


def review_media_sections(limit: int = 2) -> dict[str, Any]:
    state = load_state()
    review = state.setdefault("review", {})
    samples = [sample for sample in state.get("mediaSamples", []) if isinstance(sample, dict)]
    sections = [section for section in review.get("notableSections", []) if isinstance(section, dict)]
    findings = [finding for finding in review.get("skillFindings", []) if isinstance(finding, dict)]
    reviewed_sections = {finding.get("sectionId") for finding in findings if finding.get("sectionId")}
    selected = [
        section
        for section in sections
        if section.get("status") == "candidate_playing_section" and section.get("id") not in reviewed_sections
    ][:limit]

    results: list[dict[str, Any]] = []
    new_findings: list[dict[str, Any]] = []
    progress_plan: dict[str, Any] | None = None

    for section in selected:
        sample = sample_for_section(section, samples)
        if not sample:
            results.append({"status": "blocked", "blocker": "media_sample_missing", "sectionId": section.get("id")})
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            wav_path = Path(temp.name)
        try:
            ok, output = extract_review_wav(sample, section, wav_path)
            if not ok:
                results.append({"status": "blocked", "blocker": "audio_extract_failed", "sectionId": section.get("id"), "detail": output[-500:]})
                continue
            result = call_audio_model(wav_path, section)
        finally:
            wav_path.unlink(missing_ok=True)
        results.append(result)
        if result.get("status") == "model_reviewed":
            new_findings.extend(result.get("findings", []))
            progress_plan = result.get("progressPlan") or progress_plan

    if new_findings:
        by_id = {finding.get("id"): finding for finding in findings if finding.get("id")}
        for finding in new_findings:
            by_id[finding["id"]] = finding
        review["skillFindings"] = list(by_id.values())[:80]
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
