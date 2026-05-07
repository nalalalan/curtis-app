from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
TOKEN_PATH = RUNTIME / "curtis-upload-token.txt"
MEDIA_DIR = RUNTIME / "owner-media"
API_BASE = os.getenv("CURTIS_API_BASE", "https://curtis.aolabs.io").rstrip("/")
SAMPLE_SECONDS = int(os.getenv("CURTIS_OWNER_SAMPLE_SECONDS", "90"))
SAMPLE_START_SECONDS = int(os.getenv("CURTIS_OWNER_SAMPLE_START_SECONDS", str(10 * 60)))


def load_token() -> str:
    token = os.getenv("CURTIS_UPLOAD_TOKEN", "").strip()
    if token:
        return token.lstrip("\ufeff")
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip().lstrip("\ufeff")
    return ""


def sample_window(item: dict[str, Any]) -> str:
    duration = item.get("durationSeconds")
    start = SAMPLE_START_SECONDS
    if isinstance(duration, int) and duration > SAMPLE_SECONDS + 60:
        start = min(start, max(0, duration - SAMPLE_SECONDS - 30))
    else:
        start = 0
    return f"*{start}-{start + SAMPLE_SECONDS}"


def media_candidates(ops: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = ops.get("inventory", {}).get("youtube", [])
    samples = ops.get("media", {}).get("samples", [])
    sampled_ids = {
        str(sample.get("id"))
        for sample in samples
        if isinstance(sample, dict) and sample.get("id")
    }
    return [
        item
        for item in inventory
        if isinstance(item, dict)
        and item.get("practiceCandidate")
        and item.get("id")
        and item.get("url")
        and str(item["id"]) not in sampled_ids
    ]


def run_download(args: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )
    return completed.returncode, completed.stdout


def download_sample(item: dict[str, Any]) -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    video_id = str(item["id"])
    output_template = str(MEDIA_DIR / f"{video_id}.%(ext)s")
    base_args = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--download-sections",
        sample_window(item),
        "--force-keyframes-at-cuts",
        "-f",
        "bv*[height<=360]+ba/b[height<=360]/worst",
        "-o",
        output_template,
        str(item["url"]),
    ]
    attempts = [
        base_args,
        [*base_args[:3], "--cookies-from-browser", "chrome:Default", *base_args[3:]],
        [*base_args[:3], "--cookies-from-browser", "edge:Default", *base_args[3:]],
    ]
    output = ""
    for args in attempts:
        code, output = run_download(args)
        files = sorted(MEDIA_DIR.glob(f"{video_id}.*"), key=lambda path: path.stat().st_mtime, reverse=True)
        if code == 0 and files:
            return files[0]
    raise RuntimeError(output[-1200:])


def upload_sample(client: httpx.Client, token: str, item: dict[str, Any], path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        response = client.post(
            f"{API_BASE}/api/curtis/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "video_id": str(item["id"]),
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "window": sample_window(item),
            },
            files={"file": (path.name, handle, "application/octet-stream")},
            timeout=180,
        )
    response.raise_for_status()
    return response.json()


def main() -> int:
    token = load_token()
    if not token:
        print(json.dumps({"status": "blocked", "blocker": "missing_upload_token"}))
        return 2

    with httpx.Client(timeout=60) as client:
        ops = client.get(f"{API_BASE}/api/curtis/ops-check").json()
        candidates = media_candidates(ops)
        if not candidates:
            print(json.dumps({"status": "blocked", "blocker": "no_unsynced_practice_candidates"}))
            return 1
        item = candidates[0]
        try:
            sample_path = download_sample(item)
            updated = upload_sample(client, token, item, sample_path)
        except Exception as exc:
            print(json.dumps({
                "status": "blocked",
                "blocker": "owner_media_download_or_upload_failed",
                "video": item.get("title"),
                "detail": str(exc)[-1000:],
            }))
            return 1

    print(json.dumps({
        "status": "sample_uploaded",
        "video": item.get("title"),
        "mediaAccess": updated.get("review", {}).get("mediaAccess"),
        "samples": len(updated.get("media", {}).get("samples", [])),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
