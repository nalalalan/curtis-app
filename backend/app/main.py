from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .active_practice_scan import active_scan_state_summary, run_active_practice_scan
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
from .daily_records import (
    detected_note_series,
    is_current_transcription,
    item_has_violin_positive_sample,
    item_matches_keys,
    sample_is_violin_positive,
    score_reference_status,
    score_sequence_matches_for_series,
    video_match_keys,
    violin_positive_sample_ids,
)
from .evidence_ledger import record_evidence_correction, record_truth_item
from .gold_review import record_gold_review_item
from .media import probe_youtube_media, record_uploaded_sample
from .piece_id import identify_pieces_from_samples
from .scanner import base_ops, run_scan, transcription_items
from .score_assets import ensure_score_page
from .settings import MEDIA_DIR, ROOT_DIR, RUNTIME_DIR, SCAN_INTERVAL_SECONDS, SERVICE_NAME, allowed_origins, token_matches
from .state import load_state, save_state
from .staff4_audit import (
    ensure_staff4_phrase_audit_packet,
    latest_staff4_phrase_audit_packet,
    resolve_packet_artifact_path,
)
from .transcription import transcribe_media_samples

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")


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


class EvidenceCorrection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = "match"
    status: str = "rejected"
    source_video_id: str = Field(default="", alias="sourceVideoId")
    video_id: str = Field(default="", alias="videoId")
    source_url: str = Field(default="", alias="sourceUrl")
    source_title: str = Field(default="", alias="sourceTitle")
    practice_day: str = Field(default="", alias="practiceDay")
    sample_id: str = Field(default="", alias="sampleId")
    start_seconds: float = Field(default=0.0, alias="startSeconds")
    end_seconds: float = Field(default=0.0, alias="endSeconds")
    observed_note: str = Field(default="", alias="observedNote")
    transcribed_note: str = Field(default="", alias="transcribedNote")
    displayed_score_note: str = Field(default="", alias="displayedScoreNote")
    score_note: str = Field(default="", alias="scoreNote")
    corrected_score_note: str = Field(default="", alias="correctedScoreNote")
    accepted_score_note: str = Field(default="", alias="acceptedScoreNote")
    piece_title: str = Field(default="", alias="pieceTitle")
    score_source: str = Field(default="", alias="scoreSource")
    score_location: str = Field(default="", alias="scoreLocation")
    reason: str = ""
    note: str = ""
    benchmark: bool = False

    def to_state(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "status": self.status,
            "sourceVideoId": self.source_video_id or self.video_id,
            "sourceUrl": self.source_url,
            "sourceTitle": self.source_title,
            "practiceDay": self.practice_day,
            "sampleId": self.sample_id,
            "startSeconds": self.start_seconds,
            "endSeconds": self.end_seconds,
            "observedNote": self.observed_note,
            "transcribedNote": self.transcribed_note,
            "displayedScoreNote": self.displayed_score_note,
            "scoreNote": self.score_note,
            "correctedScoreNote": self.corrected_score_note,
            "acceptedScoreNote": self.accepted_score_note,
            "pieceTitle": self.piece_title,
            "scoreSource": self.score_source,
            "scoreLocation": self.score_location,
            "reason": self.reason,
            "note": self.note,
            "benchmark": self.benchmark,
        }


class TruthWorkbenchItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = "audio_score_match"
    status: str = "pending_review"
    source_video_id: str = Field(default="", alias="sourceVideoId")
    video_id: str = Field(default="", alias="videoId")
    source_url: str = Field(default="", alias="sourceUrl")
    source_title: str = Field(default="", alias="sourceTitle")
    practice_day: str = Field(default="", alias="practiceDay")
    sample_id: str = Field(default="", alias="sampleId")
    start_seconds: float = Field(default=0.0, alias="startSeconds")
    end_seconds: float = Field(default=0.0, alias="endSeconds")
    piece_title: str = Field(default="", alias="pieceTitle")
    score_source: str = Field(default="", alias="scoreSource")
    score_asset_id: str = Field(default="", alias="scoreAssetId")
    score_location: str = Field(default="", alias="scoreLocation")
    score_image_url: str = Field(default="", alias="scoreImageUrl")
    source_review_image_url: str = Field(default="", alias="sourceReviewImageUrl")
    source_image_url: str = Field(default="", alias="sourceImageUrl")
    original_score_snippet: bool = Field(default=False, alias="originalScoreSnippet")
    source_image_required_for_original_score: bool = Field(default=False, alias="sourceImageRequiredForOriginalScore")
    source_notation_abc: str = Field(default="", alias="sourceNotationAbc")
    copy_notation_abc: str = Field(default="", alias="copyNotationAbc")
    source_notation_events: list[dict[str, Any]] = Field(default_factory=list, alias="sourceNotationEvents")
    copy_notation_events: list[dict[str, Any]] = Field(default_factory=list, alias="copyNotationEvents")
    notation_copy_aspects: list[str] = Field(default_factory=list, alias="notationCopyAspects")
    source_piece_training_only: bool = Field(default=False, alias="sourcePieceTrainingOnly")
    notation_copy_only: bool = Field(default=False, alias="notationCopyOnly")
    detected_notes: list[str] | str = Field(default_factory=list, alias="detectedNotes")
    transcribed_notes: list[str] | str = Field(default_factory=list, alias="transcribedNotes")
    accepted_notes: list[str] | str = Field(default_factory=list, alias="acceptedNotes")
    corrected_notes: list[str] | str = Field(default_factory=list, alias="correctedNotes")
    score_notes: list[str] | str = Field(default_factory=list, alias="scoreNotes")
    source_score_notes: list[str] | str = Field(default_factory=list, alias="sourceScoreNotes")
    expected_note_letters: list[str] | str = Field(default_factory=list, alias="expectedNoteLetters")
    user_note_letters: list[str] | str = Field(default_factory=list, alias="userNoteLetters")
    note_letter_answer: str = Field(default="", alias="noteLetterAnswer")
    note_letter_correct: bool = Field(default=False, alias="noteLetterCorrect")
    note_reading_answer_mode: str = Field(default="", alias="noteReadingAnswerMode")
    reason: str = ""
    note: str = ""

    def to_state(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "status": self.status,
            "sourceVideoId": self.source_video_id or self.video_id,
            "sourceUrl": self.source_url,
            "sourceTitle": self.source_title,
            "practiceDay": self.practice_day,
            "sampleId": self.sample_id,
            "startSeconds": self.start_seconds,
            "endSeconds": self.end_seconds,
            "pieceTitle": self.piece_title,
            "scoreSource": self.score_source,
            "scoreAssetId": self.score_asset_id,
            "scoreLocation": self.score_location,
            "scoreImageUrl": self.score_image_url,
            "sourceReviewImageUrl": self.source_review_image_url,
            "sourceImageUrl": self.source_image_url,
            "originalScoreSnippet": self.original_score_snippet,
            "sourceImageRequiredForOriginalScore": self.source_image_required_for_original_score,
            "sourceNotationAbc": self.source_notation_abc,
            "copyNotationAbc": self.copy_notation_abc,
            "sourceNotationEvents": self.source_notation_events,
            "copyNotationEvents": self.copy_notation_events,
            "notationCopyAspects": self.notation_copy_aspects,
            "sourcePieceTrainingOnly": self.source_piece_training_only,
            "notationCopyOnly": self.notation_copy_only,
            "detectedNotes": self.detected_notes,
            "transcribedNotes": self.transcribed_notes,
            "acceptedNotes": self.accepted_notes,
            "correctedNotes": self.corrected_notes,
            "scoreNotes": self.score_notes,
            "sourceScoreNotes": self.source_score_notes,
            "expectedNoteLetters": self.expected_note_letters,
            "userNoteLetters": self.user_note_letters,
            "noteLetterAnswer": self.note_letter_answer,
            "noteLetterCorrect": self.note_letter_correct,
            "noteReadingAnswerMode": self.note_reading_answer_mode,
            "reason": self.reason,
            "note": self.note,
        }


class GoldReviewItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    review_item_id: str = Field(default="", alias="reviewItemId")
    type: str = "audio_phrase"
    status: str = "pending_review"
    source_video_id: str = Field(default="", alias="sourceVideoId")
    video_id: str = Field(default="", alias="videoId")
    source_url: str = Field(default="", alias="sourceUrl")
    source_title: str = Field(default="", alias="sourceTitle")
    practice_day: str = Field(default="", alias="practiceDay")
    sample_id: str = Field(default="", alias="sampleId")
    start_seconds: float = Field(default=0.0, alias="startSeconds")
    end_seconds: float = Field(default=0.0, alias="endSeconds")
    piece_title: str = Field(default="", alias="pieceTitle")
    score_source: str = Field(default="", alias="scoreSource")
    score_asset_id: str = Field(default="", alias="scoreAssetId")
    score_location: str = Field(default="", alias="scoreLocation")
    score_image_url: str = Field(default="", alias="scoreImageUrl")
    source_review_image_url: str = Field(default="", alias="sourceReviewImageUrl")
    source_image_url: str = Field(default="", alias="sourceImageUrl")
    original_score_snippet: bool = Field(default=False, alias="originalScoreSnippet")
    source_image_required_for_original_score: bool = Field(default=False, alias="sourceImageRequiredForOriginalScore")
    source_notation_abc: str = Field(default="", alias="sourceNotationAbc")
    copy_notation_abc: str = Field(default="", alias="copyNotationAbc")
    source_notation_events: list[dict[str, Any]] = Field(default_factory=list, alias="sourceNotationEvents")
    copy_notation_events: list[dict[str, Any]] = Field(default_factory=list, alias="copyNotationEvents")
    notation_copy_aspects: list[str] = Field(default_factory=list, alias="notationCopyAspects")
    source_piece_training_only: bool = Field(default=False, alias="sourcePieceTrainingOnly")
    notation_copy_only: bool = Field(default=False, alias="notationCopyOnly")
    detected_notes: list[str] | str = Field(default_factory=list, alias="detectedNotes")
    accepted_notes: list[str] | str = Field(default_factory=list, alias="acceptedNotes")
    corrected_notes: list[str] | str = Field(default_factory=list, alias="correctedNotes")
    score_notes: list[str] | str = Field(default_factory=list, alias="scoreNotes")
    source_score_notes: list[str] | str = Field(default_factory=list, alias="sourceScoreNotes")
    expected_note_letters: list[str] | str = Field(default_factory=list, alias="expectedNoteLetters")
    user_note_letters: list[str] | str = Field(default_factory=list, alias="userNoteLetters")
    note_letter_answer: str = Field(default="", alias="noteLetterAnswer")
    note_letter_correct: bool = Field(default=False, alias="noteLetterCorrect")
    note_reading_answer_mode: str = Field(default="", alias="noteReadingAnswerMode")
    reason: str = ""
    note: str = ""

    def to_state(self) -> dict[str, Any]:
        return {
            "reviewItemId": self.review_item_id,
            "type": self.type,
            "status": self.status,
            "sourceVideoId": self.source_video_id or self.video_id,
            "sourceUrl": self.source_url,
            "sourceTitle": self.source_title,
            "practiceDay": self.practice_day,
            "sampleId": self.sample_id,
            "startSeconds": self.start_seconds,
            "endSeconds": self.end_seconds,
            "pieceTitle": self.piece_title,
            "scoreSource": self.score_source,
            "scoreAssetId": self.score_asset_id,
            "scoreLocation": self.score_location,
            "scoreImageUrl": self.score_image_url,
            "sourceReviewImageUrl": self.source_review_image_url,
            "sourceImageUrl": self.source_image_url,
            "originalScoreSnippet": self.original_score_snippet,
            "sourceImageRequiredForOriginalScore": self.source_image_required_for_original_score,
            "sourceNotationAbc": self.source_notation_abc,
            "copyNotationAbc": self.copy_notation_abc,
            "sourceNotationEvents": self.source_notation_events,
            "copyNotationEvents": self.copy_notation_events,
            "notationCopyAspects": self.notation_copy_aspects,
            "sourcePieceTrainingOnly": self.source_piece_training_only,
            "notationCopyOnly": self.notation_copy_only,
            "detectedNotes": self.detected_notes,
            "acceptedNotes": self.accepted_notes,
            "correctedNotes": self.corrected_notes,
            "scoreNotes": self.score_notes,
            "sourceScoreNotes": self.source_score_notes,
            "expectedNoteLetters": self.expected_note_letters,
            "userNoteLetters": self.user_note_letters,
            "noteLetterAnswer": self.note_letter_answer,
            "noteLetterCorrect": self.note_letter_correct,
            "noteReadingAnswerMode": self.note_reading_answer_mode,
            "reason": self.reason,
            "note": self.note,
        }


app = FastAPI(title="Curtis Media Review", version="0.2.0")
PAPER_DIR = ROOT_DIR / "paper"
PAPER_PDF = PAPER_DIR / "curtis-aolabs-paper.pdf"
PAPER_TEX = PAPER_DIR / "curtis-aolabs-paper.tex"
PAPER_BIB = PAPER_DIR / "references.bib"
CLIP_CACHE_DIR = RUNTIME_DIR / "clips"
TRANSCRIPTION_PDF_CACHE_DIR = RUNTIME_DIR / "transcription-pdfs"
ASSETS_DIR = ROOT_DIR / "assets"
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
            await asyncio.to_thread(run_active_practice_scan)
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
    line_height = 15
    top = 760
    bottom = 60
    max_chars = 112
    wrapped: list[str] = []
    for line in lines:
        text = str(line or "")
        if not text:
            wrapped.append("")
            continue
        while len(text) > max_chars:
            split_at = text.rfind(" ", 0, max_chars)
            if split_at < 40:
                split_at = max_chars
            wrapped.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip()
        wrapped.append(text)
    lines_per_page = max(1, int((top - bottom) / line_height))
    pages = [wrapped[index : index + lines_per_page] for index in range(0, len(wrapped), lines_per_page)] or [[]]
    page_objects: list[bytes] = []
    kids: list[str] = []
    font_object_number = 3
    for page_index, page_lines in enumerate(pages):
        page_number = 4 + (page_index * 2)
        content_number = page_number + 1
        kids.append(f"{page_number} 0 R")
        commands = ["BT", "/F1 11 Tf", f"60 {top} Td"]
        for index, line in enumerate(page_lines):
            if index:
                commands.append(f"0 -{line_height} Td")
            commands.append(f"({_pdf_text(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        page_objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                    f"/Contents {content_number} 0 R >>"
                ).encode("ascii"),
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
            ]
        )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        *page_objects,
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


def day_transcriptions_from_state(state: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    raw_videos = record.get("videos", [])
    videos = [video for video in raw_videos if isinstance(video, dict)] if isinstance(raw_videos, list) else []
    keys = set().union(*(video_match_keys(video) for video in videos)) if videos else set()
    raw_samples = state.get("mediaSamples", [])
    samples = [sample for sample in raw_samples if isinstance(sample, dict)] if isinstance(raw_samples, list) else []
    day_samples = [sample for sample in samples if item_matches_keys(sample, keys)]
    day_violin_ids = violin_positive_sample_ids([sample for sample in day_samples if sample_is_violin_positive(sample)])
    all_violin_ids = violin_positive_sample_ids([sample for sample in samples if sample_is_violin_positive(sample)])
    sample_ids = day_violin_ids or all_violin_ids
    items = []
    for item in transcription_items(state):
        if not is_current_transcription(item):
            continue
        if keys and not item_matches_keys(item, keys):
            continue
        if sample_ids and not item_has_violin_positive_sample(item, sample_ids):
            continue
        items.append(item)
    return sorted(
        items,
        key=lambda item: (
            str(item.get("sourceTitle") or ""),
            str(item.get("sourceWindow") or ""),
            str(item.get("transcriptionId") or ""),
        ),
    )


def pdf_lines_for_detected_series(series: list[dict[str, Any]]) -> list[str]:
    if not series:
        return ["Detected note series: none stored yet.", ""]
    lines = [f"Detected note series: {len(series)}", ""]
    for index, run in enumerate(series, start=1):
        source = " / ".join(
            part
            for part in [
                str(run.get("sourceTitle") or "").strip(),
                str(run.get("sourceWindow") or "").strip(),
                str(run.get("sampleId") or "").strip(),
            ]
            if part
        )
        notes = str(run.get("noteSeriesLabel") or "").strip()
        collapsed = str(run.get("collapsedPitchClassSeriesLabel") or "").strip()
        if run.get("omittedNoteCount"):
            notes = f"{notes} ... +{run.get('omittedNoteCount')} notes"
        lines.extend(
            [
                f"Series {index}: {run.get('noteCount') or 0} notes / {run.get('startSeconds')}-{run.get('endSeconds')}s",
                f"Source: {source or 'source pending'}",
                f"Notes: {notes or 'none'}",
                f"Pitch classes for matching: {collapsed or run.get('pitchClassSeriesLabel') or 'none'}",
                "",
            ]
        )
    return lines


def pdf_lines_for_score_matches(matches: list[dict[str, Any]], status: str) -> list[str]:
    lines = [f"Note/reference sequence matches: {len(matches)}", f"Reference sequence status: {status}", ""]
    for index, match in enumerate(matches, start=1):
        score = match.get("score") if isinstance(match.get("score"), dict) else {}
        measure_label = (
            match.get("measureLabel")
            or score.get("measureLabel")
            or match.get("scoreSequenceLabel")
            or "pending"
        )
        lines.extend(
            [
                f"Match {index}: {match.get('pieceTitle') or 'piece'} / {match.get('matchedNoteRun') or 0} notes",
                f"Measure: {measure_label}",
                f"Detected: {match.get('detectedPitchClassSequence') or ''}",
                f"Reference: {match.get('referencePitchClassSequence') or match.get('scorePitchClassSequence') or ''}",
                f"Score alignment: {match.get('scoreSnippetStatus') or 'pending'}",
                "",
            ]
        )
    return lines


def ensure_transcription_pdf(practice_day: str) -> Path:
    state = load_state()
    records = base_ops(state)["review"]["dailyRecords"]
    record = next((item for item in records.get("records", []) if item.get("practiceDay") == practice_day), None)
    if not record:
        raise HTTPException(status_code=404, detail="practice day not found")
    transcription = record.get("transcription") if isinstance(record.get("transcription"), dict) else {}
    groups = record.get("matchGroups") if isinstance(record.get("matchGroups"), list) else []
    raw_transcriptions = day_transcriptions_from_state(state, record)
    all_series = detected_note_series(raw_transcriptions, max_series=None, max_notes_per_series=None)
    piece_title = ", ".join(
        piece.get("title", "")
        for piece in record.get("pieces", [])
        if isinstance(piece, dict) and piece.get("title")
    ) or "piece pending"
    pieces = record.get("pieces") if isinstance(record.get("pieces"), list) else []
    score_matches = score_sequence_matches_for_series(all_series, pieces, max_matches=40)
    score_status = score_reference_status(pieces)
    lines = [
        f"Curtis transcription run / {practice_day}",
        f"Piece: {piece_title}",
        f"Uploaded video: {record.get('uploadedVideoLabel') or 'pending'}",
        f"Total practice time: {record.get('activeViolinLabel') or 'pending'}",
        f"Video checked for practice time: {record.get('processedSampleLabel') or 'pending'}",
        "PDF scope: all stored detected note series for this day",
        "Match rule: source-score promotion requires exact MIDI equality plus per-note audio agreement; loose pitch-class grouping remains candidate-only",
        "",
    ]
    lines.extend(pdf_lines_for_detected_series(all_series))
    lines.extend(pdf_lines_for_score_matches(score_matches, score_status))
    if groups:
        lines.append("Displayed note-match groups")
        lines.append("")
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
                    f"Measure: {group.get('measureLabel') or (group.get('score') or {}).get('measureLabel') or group.get('scoreSequenceLabel') or 'pending'}",
                    f"Notes: {' '.join(event_notes[:24]) or 'none rendered'}",
                    f"Matched note run: {group.get('matchedNoteRun') or group.get('minimumMatchedNoteRun') or 0}",
                    f"Audio/video sample: {clip.get('sampleId') or 'sample pending'}",
                    f"Window: {clip.get('windowLabel') or clip.get('sourceWindow') or 'window pending'}",
                    f"Score alignment: {group.get('scoreSnippetStatus') or 'pending'}",
                    "",
                ]
            )
    else:
        lines.append("Displayed note-match groups: none.")
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
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".json":
        return "application/json"
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
async def transcribe_run(
    limit: int | None = Query(default=None, ge=1, le=80),
    sample_id: list[str] | None = Query(default=None, alias="sampleId"),
) -> dict[str, Any]:
    await asyncio.to_thread(transcribe_media_samples, limit, sample_id)
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


@app.get("/api/curtis/active-practice-coverage")
async def active_practice_coverage() -> dict[str, Any]:
    return base_ops(load_state())["review"]["activePracticeCoverage"]


@app.get("/api/curtis/active-practice-scan")
async def active_practice_scan_status(pending_limit: int = 50) -> dict[str, Any]:
    return active_scan_state_summary(load_state(), pending_limit=pending_limit)


@app.post("/api/curtis/active-practice-scan/run")
async def active_practice_scan_run(max_samples: int = 80, max_queue: int = 250, pending_limit: int = 50) -> dict[str, Any]:
    run = await asyncio.to_thread(run_active_practice_scan, max_samples, max_queue)
    state = load_state()
    return {
        "service": SERVICE_NAME,
        "status": run.get("status") or "complete",
        "run": run,
        "activePracticeScan": active_scan_state_summary(state, pending_limit=pending_limit),
        "activePracticeCoverage": base_ops(state)["review"]["activePracticeCoverage"],
    }


@app.get("/api/curtis/evidence-progress")
async def evidence_progress() -> dict[str, Any]:
    return base_ops(load_state())["review"]["evidenceProgress"]


@app.get("/api/curtis/truth-workbench")
async def truth_workbench() -> dict[str, Any]:
    return base_ops(load_state())["review"]["truthWorkbench"]


@app.get("/api/curtis/gold-review")
async def gold_review() -> dict[str, Any]:
    return base_ops(load_state())["review"]["goldReview"]


@app.get("/api/curtis/staff4-audit")
async def staff4_audit() -> dict[str, Any]:
    state = load_state()
    return {
        "service": SERVICE_NAME,
        "status": "ready",
        "auditPacket": latest_staff4_phrase_audit_packet(state),
    }


@app.post("/api/curtis/staff4-audit/run")
async def staff4_audit_run(force: bool = True) -> dict[str, Any]:
    state = load_state()
    ops = base_ops(state)
    packet = ensure_staff4_phrase_audit_packet(
        state,
        ops["review"]["transcriptionCompletion"],
        force=force,
    )
    save_state(state)
    refreshed = base_ops(load_state())
    return {
        "service": SERVICE_NAME,
        "status": packet.get("status") or "generated",
        "auditPacket": packet,
        "review": refreshed["review"],
    }


@app.get("/api/curtis/staff4-audit/artifacts/{packet_id}/{filename}")
async def staff4_audit_artifact(packet_id: str, filename: str) -> FileResponse:
    target = resolve_packet_artifact_path(packet_id, filename)
    if not target:
        raise HTTPException(status_code=404, detail="audit artifact not found")
    return FileResponse(target, media_type=sample_media_type(target))


@app.post("/api/curtis/gold-review/items")
async def gold_review_item(item: GoldReviewItem) -> dict[str, Any]:
    state = load_state()
    try:
        result = record_gold_review_item(state, item.to_state())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_state(state)
    ops = base_ops(state)
    ops["goldReviewItem"] = result
    return ops


@app.post("/api/curtis/truth-workbench/items")
async def truth_workbench_item(item: TruthWorkbenchItem) -> dict[str, Any]:
    state = load_state()
    try:
        result = record_truth_item(state, item.to_state())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_state(state)
    ops = base_ops(state)
    ops["truthWorkbenchItem"] = result
    return ops


@app.post("/api/curtis/evidence-corrections")
async def evidence_correction(correction: EvidenceCorrection) -> dict[str, Any]:
    state = load_state()
    try:
        result = record_evidence_correction(state, correction.to_state())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_state(state)
    ops = base_ops(state)
    ops["correction"] = result
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


@app.get("/assets/{path:path}")
async def static_assets(path: str) -> FileResponse:
    target = (ASSETS_DIR / path).resolve()
    assets_root = ASSETS_DIR.resolve()
    if target != assets_root and assets_root not in target.parents:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    if target.suffix.lower() == ".woff2":
        return FileResponse(target, media_type="font/woff2")
    if target.suffix.lower() == ".woff":
        return FileResponse(target, media_type="font/woff")
    return FileResponse(target)


@app.get("/{path:path}")
async def static_app(path: str) -> FileResponse:
    target = ROOT_DIR / path
    if path in STATIC_ALLOWLIST and target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(ROOT_DIR / "index.html")
