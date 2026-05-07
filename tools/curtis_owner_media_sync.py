from __future__ import annotations

import json
import os
import re
import shutil
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
WINDOWS_PER_VIDEO = int(os.getenv("CURTIS_OWNER_WINDOWS_PER_VIDEO", "4"))
BATCH_SIZE = int(os.getenv("CURTIS_OWNER_BATCH_SIZE", "3"))
WINDOW_RE = re.compile(r"\*(\d+)-(\d+)")
BUNDLED_NODE = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "node"
    / "bin"
    / "node.exe"
)
BUNDLED_NODE_MODULES = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "node"
    / "node_modules"
)


def load_token() -> str:
    token = os.getenv("CURTIS_UPLOAD_TOKEN", "").strip()
    if token:
        return token.lstrip("\ufeff")
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip().lstrip("\ufeff")
    return ""


def parse_window_start(value: str) -> int | None:
    match = WINDOW_RE.search(value or "")
    if not match:
        return None
    return int(match.group(1))


def sample_window(item: dict[str, Any]) -> str:
    start = sample_start_seconds(item)
    return f"*{start}-{start + SAMPLE_SECONDS}"


def sample_start_seconds(item: dict[str, Any]) -> int:
    duration = item.get("durationSeconds")
    start = SAMPLE_START_SECONDS
    if isinstance(duration, int) and duration > SAMPLE_SECONDS + 60:
        start = min(start, max(0, duration - SAMPLE_SECONDS - 30))
    else:
        start = 0
    return start


def sample_starts(item: dict[str, Any]) -> list[int]:
    duration = item.get("durationSeconds")
    if not isinstance(duration, int) or duration <= SAMPLE_SECONDS + 60:
        return [0]
    latest = max(0, duration - SAMPLE_SECONDS - 30)
    anchors = [
        SAMPLE_START_SECONDS,
        int(duration * 0.25),
        int(duration * 0.5),
        int(duration * 0.75),
        latest,
    ]
    starts = [min(max(0, anchor), latest) for anchor in anchors]
    return list(dict.fromkeys(starts))[: max(1, WINDOWS_PER_VIDEO)]


def sample_id(item: dict[str, Any], start: int) -> str:
    return f"{item['id']}-{start}"


def with_sample_window(item: dict[str, Any], start: int) -> dict[str, Any]:
    return {
        **item,
        "sampleStartSeconds": start,
        "sampleId": sample_id(item, start),
        "sampleWindow": f"*{start}-{start + SAMPLE_SECONDS}",
    }


def media_candidates(ops: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = ops.get("inventory", {}).get("youtube", [])
    samples = ops.get("media", {}).get("samples", [])
    sampled_ids = {
        str(sample.get("id"))
        for sample in samples
        if isinstance(sample, dict) and sample.get("id")
    }
    for sample in samples:
        if not isinstance(sample, dict) or not sample.get("id"):
            continue
        start = parse_window_start(str(sample.get("window") or ""))
        if start is not None:
            sampled_ids.add(f"{sample.get('id')}-{start}")
    candidates: list[dict[str, Any]] = []
    for item in inventory:
        if not (
            isinstance(item, dict)
            and item.get("practiceCandidate")
            and item.get("id")
            and item.get("url")
        ):
            continue
        for start in sample_starts(item):
            candidate = with_sample_window(item, start)
            if str(candidate["sampleId"]) not in sampled_ids:
                candidates.append(candidate)
    return candidates


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


def node_executable() -> str:
    configured = os.getenv("CURTIS_NODE_EXE", "").strip()
    if configured:
        return configured
    if BUNDLED_NODE.exists():
        return str(BUNDLED_NODE)
    return shutil.which("node") or "node"


def browser_capture_sample(item: dict[str, Any]) -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    video_id = str(item.get("sampleId") or item["id"])
    output_path = MEDIA_DIR / f"{video_id}-browser.webm"
    env = os.environ.copy()
    if "NODE_PATH" not in env and BUNDLED_NODE_MODULES.exists():
        env["NODE_PATH"] = str(BUNDLED_NODE_MODULES)
    completed = subprocess.run(
        [
            node_executable(),
            str(ROOT / "tools" / "capture_youtube_sample.js"),
            "--url",
            str(item["url"]),
            "--start",
            str(item.get("sampleStartSeconds", sample_start_seconds(item))),
            "--duration",
            str(SAMPLE_SECONDS),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=max(180, SAMPLE_SECONDS + 90),
    )
    if completed.returncode == 0 and output_path.exists() and output_path.stat().st_size:
        return output_path
    raise RuntimeError(completed.stdout[-1200:])


def download_sample(item: dict[str, Any]) -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    video_id = str(item.get("sampleId") or item["id"])
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
    try:
        return browser_capture_sample(item)
    except Exception as exc:
        output = f"browser_capture_failed: {exc}"

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
                "video_id": str(item.get("sampleId") or item["id"]),
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "window": str(item.get("sampleWindow") or sample_window(item)),
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
        uploaded: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        updated: dict[str, Any] = ops
        for item in candidates[: max(1, BATCH_SIZE)]:
            try:
                sample_path = download_sample(item)
                updated = upload_sample(client, token, item, sample_path)
                uploaded.append(
                    {
                        "id": item.get("sampleId") or item.get("id"),
                        "video": item.get("title"),
                        "window": item.get("sampleWindow") or sample_window(item),
                    }
                )
            except Exception as exc:
                blockers.append(
                    {
                        "video": item.get("title"),
                        "window": item.get("sampleWindow") or sample_window(item),
                        "detail": str(exc)[-500:],
                    }
                )

    print(json.dumps({
        "status": "sample_uploaded" if uploaded else "blocked",
        "uploaded": uploaded,
        "blocked": blockers[:3],
        "mediaAccess": updated.get("review", {}).get("mediaAccess"),
        "samples": len(updated.get("media", {}).get("samples", [])),
    }))
    return 0 if uploaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
