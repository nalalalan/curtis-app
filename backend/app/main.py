from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .analyzer import analyze_media_samples
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
from .settings import ROOT_DIR, SCAN_INTERVAL_SECONDS, SERVICE_NAME, allowed_origins, token_matches
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
            analyze_media_samples()
            transcribe_media_samples()
            identify_pieces_from_samples()
            if os.getenv("CURTIS_MODEL_REVIEW_AUTORUN", "1").strip().lower() not in {"0", "false", "no"}:
                review_media_sections()
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
    analyze_media_samples()
    transcribe_media_samples()
    return base_ops(load_state())


@app.post("/api/curtis/analyze/run")
async def analyze_run() -> dict[str, Any]:
    analyze_media_samples()
    transcribe_media_samples()
    identify_pieces_from_samples()
    review_media_sections()
    return base_ops(load_state())


@app.post("/api/curtis/transcribe/run")
async def transcribe_run() -> dict[str, Any]:
    transcribe_media_samples()
    return base_ops(load_state())


@app.post("/api/curtis/coach/run")
async def coach_run() -> dict[str, Any]:
    review_media_sections()
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
    record_uploaded_sample(temp_path, video_id=video_id, title=title, url=url, window=window)
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
