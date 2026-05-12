from __future__ import annotations

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .analyzer import analyze_media_samples
from .analyzer import run_process
from .auth import (
    build_youtube_authorization_url,
    exchange_youtube_code,
    fetch_youtube_channel_title,
    save_youtube_tokens,
    validate_youtube_oauth_state,
    youtube_auth_status,
)
from .coach import review_media_sections
from .corrections import learn_acceptance, learn_rejection, scrub_rejected_source
from .media import probe_youtube_media, record_uploaded_sample
from .piece_id import identify_pieces_from_samples
from .scanner import base_ops, run_scan
from .score_assets import ensure_score_page
from .settings import MEDIA_DIR, ROOT_DIR, RUNTIME_DIR, SCAN_INTERVAL_SECONDS, SERVICE_NAME, allowed_origins, token_matches
from .state import load_state, save_state
from .transcription import transcribe_media_samples


class SourceConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    youtube: str = ""
    instagram: str = ""
    scan_scope: str = Field(default="Latest public posts", alias="scanScope")
    scan_cadence: str = Field(default="Run now", alias="scanCadence")

    def to_state(self) -> dict[str, str]:
        return {
            "youtube": self.youtube.strip(),
            "instagram": self.instagram.strip(),
            "scanScope": self.scan_scope,
            "scanCadence": self.scan_cadence,
        }


class PieceCorrection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_url: str = Field(default="", alias="sourceUrl")
    source_title: str = Field(default="", alias="sourceTitle")
    video_id: str = Field(default="", alias="videoId")
    rejected_title: str = Field(default="", alias="rejectedTitle")
    accepted_title: str = Field(default="", alias="acceptedTitle")
    note: str = ""


app = FastAPI(title="Curtis Media Review", version="0.2.0")
PAPER_DIR = ROOT_DIR / "paper"
PAPER_PDF = PAPER_DIR / "curtis-aolabs-paper.pdf"
PAPER_TEX = PAPER_DIR / "curtis-aolabs-paper.tex"
PAPER_BIB = PAPER_DIR / "references.bib"
CLIP_CACHE_DIR = RUNTIME_DIR / "clips"
TRANSCRIPTION_PDF_CACHE_DIR = RUNTIME_DIR / "transcription-pdfs"
STATIC_ALLOWLIST = {"index.html", "paper.html", "app.js", "styles.css", "favicon.svg", "CNAME", ".nojekyll"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=r"https://.*\.aolabs\.io",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def start_worker() -> None:
    if os.getenv("CURTIS_AUTORUN", "").strip().lower() not in {"1", "true", "yes"}:
        return
    asyncio.create_task(worker_loop())


async def worker_loop() -> None:
    while True:
        await run_scan()
        if os.getenv("CURTIS_MEDIA_AUTORUN", "1").strip().lower() not in {"0", "false", "no"}:
            await probe_youtube_media()
            await asyncio.to_thread(analyze_media_samples)
            await asyncio.to_thread(transcribe_media_samples)
            await asyncio.to_thread(identify_pieces_from_samples)
            if os.getenv("CURTIS_MODEL_REVIEW_AUTORUN", "1").strip().lower() not in {"0", "false", "no"}:
                await asyncio.to_thread(review_media_sections)
        await asyncio.sleep(max(SCAN_INTERVAL_SECONDS, 300))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


def youtube_redirect_uri() -> str:
    public_base = os.getenv("PUBLIC_BASE_URL", "https://curtis.aolabs.io").rstrip("/")
    return f"{public_base}/api/auth/youtube/callback"


def _paper_file_response(path: Path, *, media_type: str, filename: str | None = None) -> FileResponse:
    if not path.exists():
        raise HTTPException(status_code=404, detail="paper file not found")
    return FileResponse(path, media_type=media_type, filename=filename)


def _pdf_text(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _minimal_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    y = 760
    commands = ["BT", "/F1 12 Tf", "72 760 Td"]
    for index, line in enumerate(lines[:42]):
        if index:
            commands.append("0 -17 Td")
        commands.append(f"({_pdf_text(line[:110])}) Tj")
        y -= 17
        if y < 80:
            break
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(content))


def transcription_pdf_path(practice_day: str) -> Path:
    safe_day = re.sub(r"[^0-9A-Za-z_-]+", "-", practice_day)[:40] or "practice-day"
    return TRANSCRIPTION_PDF_CACHE_DIR / f"{safe_day}-transcription.pdf"


def ensure_transcription_pdf(practice_day: str) -> Path:
    records = base_ops(load_state())["review"]["dailyRecords"]
    record = next((item for item in records.get("records", []) if item.get("practiceDay") == practice_day), None)
    if not record:
        raise HTTPException(status_code=404, detail="practice day not found")
    transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
    groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
    piece_title = ", ".join(
        piece.get("title", "")
        for piece in record.get("pieces", [])
        if isinstance(piece, dict) and piece.get("title")
    ) or "piece pending"
    lines = [
        f"Curtis transcription run / {practice_day}",
        f"Piece: {piece_title}",
        f"Uploaded video: {record.get('uploadedVideoLabel') or 'pending'}",
        f"Total practice time: {record.get('activeViolinLabel') or 'pending'}",
        "Display mode: matched groups only",
        "Match rule: note sequence, rhythm ignored, minimum run 1 note",
        "",
    ]
    if groups:
        for index, group in enumerate(groups, start=1):
            clip = group.get("clip") if isinstance(group.get("clip"), dict) else {}
            source = group.get("transcription") if isinstance(group.get("transcription"), dict) else {}
            notes = source.get("notes") if isinstance(source.get("notes"), list) else []
            event_notes = [
                str(note.get("note"))
                for note in notes
                if isinstance(note, dict) and note.get("note")
            ]
            lines.extend(
                [
                    f"Group {index}: {group.get('status') or 'matched'}",
                    f"Notes: {' '.join(event_notes[:24]) or 'none rendered'}",
                    f"Matched note run: {group.get('matchedNoteRun') or group.get('minimumMatchedNoteRun') or 0}",
                    f"Audio/video sample: {clip.get('sampleId') or 'sample pending'}",
                    f"Window: {clip.get('windowLabel') or clip.get('sourceWindow') or 'window pending'}",
                    f"Score snippet: {group.get('scoreSnippetStatus') or 'pending'}",
                    "",
                ]
            )
    else:
        lines.append("No accepted matched groups yet.")
    if transcription.get("rejectedMachinePitchEventCount"):
        lines.append(f"Hidden machine pitch events: {transcription.get('rejectedMachinePitchEventCount')}")
    target = transcription_pdf_path(practice_day)
    _minimal_pdf(target, lines)
    return target


def sample_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".mp4", ".m4v"}:
        return "video/mp4"
    if suffix == ".webm":
        return "video/webm"
    if suffix in {".m4a", ".aac"}:
        return "audio/mp4"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    return "application/octet-stream"


def resolved_runtime_media_path(raw_path: str) -> Path:
    try:
        path = Path(raw_path).resolve(strict=True)
        runtime = RUNTIME_DIR.resolve()
        media = MEDIA_DIR.resolve()
    except OSError as exc:
        raise HTTPException(status_code=404, detail="media sample not found") from exc
    in_runtime = path == runtime or runtime in path.parents
    in_media = path == media or media in path.parents
    if not (in_runtime or in_media):
        raise HTTPException(status_code=403, detail="media sample outside runtime storage")
    return path


def media_sample_from_state(sample_id: str) -> dict[str, Any]:
    target = str(sample_id or "").strip()
    samples = load_state().get("mediaSamples", [])
    for sample in samples if isinstance(samples, list) else []:
        if isinstance(sample, dict) and str(sample.get("id") or "").strip() == target:
            return sample
    raise HTTPException(status_code=404, detail="media sample not found")


def clip_cache_path(sample_id: str, start: float, end: float) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", sample_id).strip("-") or "sample"
    return CLIP_CACHE_DIR / f"{safe_id}-{int(round(start * 1000))}-{int(round(end * 1000))}.wav"


def validate_clip_window(start: float, end: float) -> tuple[float, float]:
    start = max(0.0, float(start or 0.0))
    end = max(0.0, float(end or 0.0))
    duration = end - start
    if duration <= 0.05:
        raise HTTPException(status_code=400, detail="clip end must be after start")
    if duration > 15.0:
        raise HTTPException(status_code=400, detail="clip window too long")
    return round(start, 3), round(end, 3)


@app.get("/api/curtis/ops-check")
async def ops_check() -> dict[str, Any]:
    return base_ops(load_state())


@app.get("/api/curtis/media-status")
async def media_status() -> dict[str, Any]:
    ops = base_ops(load_state())
    return {
        "status": ops["status"],
        "sources": ops["sources"],
        "inventory": ops["inventory"],
        "review": ops["review"],
        "blockers": ops["blockers"],
        "model": ops["model"],
    }


@app.get("/api/curtis/study")
async def study_packet() -> dict[str, Any]:
    return base_ops(load_state())["review"]["practiceStudy"]


@app.get("/api/curtis/daily-records")
async def daily_records() -> dict[str, Any]:
    return base_ops(load_state())["review"]["dailyRecords"]


@app.get("/api/curtis/daily-records/{practice_day}/transcription.pdf")
async def daily_record_transcription_pdf(practice_day: str) -> FileResponse:
    target = ensure_transcription_pdf(practice_day)
    return FileResponse(
        target,
        media_type="application/pdf",
        filename=f"Curtis {practice_day} transcription run.pdf",
    )


@app.get("/api/curtis/score/page/{asset_id}/{page}")
async def score_page(asset_id: str, page: int) -> FileResponse:
    try:
        target = ensure_score_page(asset_id, page)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"score page unavailable: {str(exc)[:180]}") from exc
    return FileResponse(target, media_type="image/jpeg")


@app.get("/api/curtis/media/sample/{sample_id}")
async def media_sample_file(sample_id: str) -> FileResponse:
    sample = media_sample_from_state(sample_id)
    path = resolved_runtime_media_path(str(sample.get("path") or ""))
    return FileResponse(path, media_type=sample_media_type(path))


@app.get("/api/curtis/media/sample/{sample_id}/clip")
async def media_sample_clip(sample_id: str, start: float, end: float) -> FileResponse:
    start, end = validate_clip_window(start, end)
    sample = media_sample_from_state(sample_id)
    source = resolved_runtime_media_path(str(sample.get("path") or ""))
    CLIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = clip_cache_path(sample_id, start, end)
    if not target.exists() or target.stat().st_size <= 44:
        code, output = run_process(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-f",
                "wav",
                str(target),
            ],
            timeout=60,
        )
        if code != 0 or not target.exists() or target.stat().st_size <= 44:
            raise HTTPException(status_code=503, detail=f"clip extraction failed: {output[-180:]}")
    return FileResponse(target, media_type="audio/wav")


@app.post("/api/curtis/sources")
async def update_sources(config: SourceConfig) -> dict[str, Any]:
    state = load_state()
    state["sources"] = config.to_state()
    save_state(state)
    return base_ops(state)


@app.post("/api/curtis/scan/run")
async def scan_run(config: SourceConfig | None = None) -> dict[str, Any]:
    incoming = config.to_state() if config else None
    return await run_scan(incoming)


@app.post("/api/curtis/media/probe")
async def media_probe() -> dict[str, Any]:
    await probe_youtube_media()
    await asyncio.to_thread(analyze_media_samples)
    await asyncio.to_thread(transcribe_media_samples)
    return base_ops(load_state())


@app.post("/api/curtis/analyze/run")
async def analyze_run() -> dict[str, Any]:
    await asyncio.to_thread(analyze_media_samples)
    await asyncio.to_thread(transcribe_media_samples)
    await asyncio.to_thread(identify_pieces_from_samples)
    await asyncio.to_thread(review_media_sections)
    return base_ops(load_state())


@app.post("/api/curtis/transcribe/run")
async def transcribe_run() -> dict[str, Any]:
    await asyncio.to_thread(transcribe_media_samples)
    return base_ops(load_state())


@app.post("/api/curtis/coach/run")
async def coach_run() -> dict[str, Any]:
    await asyncio.to_thread(review_media_sections)
    return base_ops(load_state())


@app.post("/api/curtis/piece-id/run")
async def piece_id_run() -> dict[str, Any]:
    identify_pieces_from_samples()
    return base_ops(load_state())


@app.post("/api/curtis/piece-corrections")
async def piece_correction(correction: PieceCorrection) -> dict[str, Any]:
    rejected_title = correction.rejected_title.strip()
    accepted_title = correction.accepted_title.strip()
    if (
        not accepted_title
        and (not rejected_title or rejected_title == "Piece being identified")
    ):
        raise HTTPException(status_code=400, detail="Rejected or accepted title required.")
    state = load_state()
    try:
        if accepted_title:
            learned = learn_acceptance(
                state,
                source_url=correction.source_url.strip(),
                source_title=correction.source_title.strip(),
                video_id=correction.video_id.strip(),
                accepted_title=accepted_title,
                note=correction.note.strip(),
            )
        else:
            learned = learn_rejection(
                state,
                source_url=correction.source_url.strip(),
                source_title=correction.source_title.strip(),
                video_id=correction.video_id.strip(),
                rejected_title=rejected_title,
                note=correction.note.strip(),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scrubbed_count = scrub_rejected_source(state, str(learned.get("sourceKey") or ""))
    state["lastPieceCorrection"] = {
        "sourceKey": learned.get("sourceKey"),
        "rejectedTitle": rejected_title,
        "acceptedTitle": accepted_title,
        "scrubbedCount": scrubbed_count,
    }
    save_state(state)
    if accepted_title:
        await asyncio.to_thread(identify_pieces_from_samples)
        state = load_state()
    ops = base_ops(state)
    ops["correction"] = {
        "sourceKey": learned.get("sourceKey"),
        "rejectedTitle": rejected_title,
        "acceptedTitle": accepted_title,
        "scrubbedCount": scrubbed_count,
    }
    return ops


@app.post("/api/curtis/media/upload")
async def media_upload(
    file: UploadFile = File(...),
    video_id: str = Form("uploaded"),
    title: str = Form(""),
    url: str = Form(""),
    window: str = Form(""),
    contains_violin: str = Form("", alias="containsViolin"),
    violin_presence: str = Form("", alias="violinPresence"),
    practice_evidence_status: str = Form("", alias="practiceEvidenceStatus"),
    violin_sampler_score: str = Form("", alias="violinSamplerScore"),
    violin_sampler_version: str = Form("", alias="violinSamplerVersion"),
    violin_sampler_features: str = Form("", alias="violinSamplerFeatures"),
    authorization: str = Header(""),
) -> dict[str, Any]:
    token = authorization.removeprefix("Bearer").strip()
    if not token_matches(token):
        raise HTTPException(status_code=401, detail="Upload token required.")

    suffix = Path(file.filename or "").suffix[:12]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        while chunk := await file.read(1024 * 1024):
            temp_file.write(chunk)
        temp_path = Path(temp_file.name)
    metadata = {
        "containsViolin": contains_violin.strip().lower() in {"1", "true", "yes"},
        "violinPresence": violin_presence,
        "practiceEvidenceStatus": practice_evidence_status,
        "violinSamplerScore": violin_sampler_score,
        "violinSamplerVersion": violin_sampler_version,
        "violinSamplerFeatures": violin_sampler_features,
    }
    record_uploaded_sample(temp_path, video_id=video_id, title=title, url=url, window=window, metadata=metadata)
    analyze_media_samples()
    transcribe_media_samples()
    identify_pieces_from_samples()
    review_media_sections()
    return base_ops(load_state())


@app.get("/api/auth/youtube/status")
async def youtube_status() -> dict[str, Any]:
    return youtube_auth_status()


@app.get("/api/auth/youtube/start")
async def youtube_oauth_start() -> RedirectResponse:
    status = youtube_auth_status()
    if not status["configured"]:
        raise HTTPException(
            status_code=503,
            detail="Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET for a Google OAuth web client.",
        )
    return RedirectResponse(build_youtube_authorization_url(youtube_redirect_uri()))


@app.get("/api/auth/youtube/callback")
async def youtube_oauth_callback(request: Request) -> RedirectResponse:
    error = request.query_params.get("error")
    if error:
        return RedirectResponse("/?youtube=error#media")
    code = request.query_params.get("code", "")
    returned_state = request.query_params.get("state", "")
    if not code or not validate_youtube_oauth_state(returned_state):
        return RedirectResponse("/?youtube=invalid#media")
    try:
        token_payload = await exchange_youtube_code(code, youtube_redirect_uri())
        channel_title = ""
        access_token = token_payload.get("access_token")
        if isinstance(access_token, str) and access_token:
            channel_title = await fetch_youtube_channel_title(access_token)
        save_youtube_tokens(token_payload, channel_title)
        await run_scan({"youtube": "mine", "scanScope": "Authenticated full archive", "scanCadence": "Daily"})
    except Exception:
        return RedirectResponse("/?youtube=failed#media")
    return RedirectResponse("/?youtube=connected#media")


@app.get("/paper")
async def paper_index() -> FileResponse:
    return FileResponse(ROOT_DIR / "paper.html")


@app.get("/paper/")
async def paper_index_slash() -> FileResponse:
    return FileResponse(ROOT_DIR / "paper.html")


@app.get("/paper.pdf")
async def paper_pdf() -> FileResponse:
    return _paper_file_response(
        PAPER_PDF,
        media_type="application/pdf",
        filename="Longitudinal media review for audition-oriented violin practice.pdf",
    )


@app.get("/paper/source.tex")
async def paper_tex() -> FileResponse:
    return _paper_file_response(PAPER_TEX, media_type="text/plain; charset=utf-8")


@app.get("/paper/references.bib")
async def paper_bib() -> FileResponse:
    return _paper_file_response(PAPER_BIB, media_type="text/plain; charset=utf-8")


@app.get("/{path:path}")
async def static_app(path: str) -> FileResponse:
    target = ROOT_DIR / path
    if path in STATIC_ALLOWLIST and target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(ROOT_DIR / "index.html")
