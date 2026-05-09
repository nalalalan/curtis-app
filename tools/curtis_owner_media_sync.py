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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.analyzer import VIOLIN_PRESENCE_VERSION, classify_violin_presence, sample_is_violin_positive


ROOT = REPO_ROOT
RUNTIME = ROOT / ".runtime"
TOKEN_PATH = RUNTIME / "curtis-upload-token.txt"
MEDIA_DIR = RUNTIME / "owner-media"
API_BASE = os.getenv("CURTIS_API_BASE", "https://curtis.aolabs.io").rstrip("/")
PUBLIC_YOUTUBE_SOURCE = os.getenv("CURTIS_YOUTUBE_SOURCE", "https://www.youtube.com/@nalalan")
SAMPLE_SECONDS = int(os.getenv("CURTIS_OWNER_SAMPLE_SECONDS", "90"))
SAMPLE_START_SECONDS = int(os.getenv("CURTIS_OWNER_SAMPLE_START_SECONDS", str(10 * 60)))
WINDOWS_PER_VIDEO = int(os.getenv("CURTIS_OWNER_WINDOWS_PER_VIDEO", "8"))
BATCH_SIZE = int(os.getenv("CURTIS_OWNER_BATCH_SIZE", "4"))
EXPAND_OFFSETS = tuple(
    int(value.strip())
    for value in os.getenv("CURTIS_OWNER_EXPAND_OFFSETS", "90,180,360,720").split(",")
    if value.strip()
)
WINDOW_RE = re.compile(r"\*(\d+)-(\d+)")
CACHED_BROWSER_RE = re.compile(r"(?P<video_id>.+)-(?P<start>\d+)(?:-[^-]+)?-browser$")
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
    window_count = max(1, WINDOWS_PER_VIDEO)
    anchors = [SAMPLE_START_SECONDS]
    anchors.extend(int(duration * fraction) for fraction in (0.25, 0.5, 0.625, 0.75))
    anchors.append(latest)
    if window_count >= 6:
        anchors.extend([5 * 60, 15 * 60, int(duration * 0.125)])
    starts = [min(max(0, anchor), latest) for anchor in anchors]
    return list(dict.fromkeys(starts))[:window_count]


def sample_id(item: dict[str, Any], start: int) -> str:
    return f"{item['id']}-{start}"


def sample_video_id(sample: dict[str, Any]) -> str:
    raw_id = str(sample.get("id") or "")
    start = parse_window_start(str(sample.get("window") or ""))
    if start is not None and raw_id.endswith(f"-{start}"):
        return raw_id[: -(len(str(start)) + 1)]
    return raw_id


def live_samples(ops: dict[str, Any]) -> list[dict[str, Any]]:
    media = ops.get("media", {}) if isinstance(ops.get("media"), dict) else {}
    samples = media.get("sampleIndex") or media.get("samples") or []
    return [sample for sample in samples if isinstance(sample, dict)]


def live_sample_keys(ops: dict[str, Any]) -> tuple[set[str], set[tuple[str, int]]]:
    samples = live_samples(ops)
    sampled_ids = {
        str(sample.get("id"))
        for sample in samples
        if isinstance(sample, dict) and sample.get("id")
    }
    sampled_windows: set[tuple[str, int]] = set()
    for sample in samples:
        if not isinstance(sample, dict) or not sample.get("id"):
            continue
        start = parse_window_start(str(sample.get("window") or ""))
        if start is not None:
            video_id = sample_video_id(sample)
            sampled_ids.add(f"{video_id}-{start}")
            sampled_windows.add((str(sample.get("url") or ""), start))
    return sampled_ids, sampled_windows


def positive_sample_starts(ops: dict[str, Any]) -> dict[str, list[int]]:
    starts_by_video: dict[str, list[int]] = {}
    for sample in live_samples(ops):
        if not sample_is_violin_positive(sample):
            continue
        start = parse_window_start(str(sample.get("window") or ""))
        if start is None:
            continue
        video_id = sample_video_id(sample)
        starts_by_video.setdefault(video_id, []).append(start)
    return {
        video_id: sorted(set(starts))
        for video_id, starts in starts_by_video.items()
        if starts
    }


def expanded_starts(item: dict[str, Any], anchors: list[int]) -> list[int]:
    duration = item.get("durationSeconds")
    if not isinstance(duration, int) or duration <= SAMPLE_SECONDS + 60:
        latest = 0
    else:
        latest = max(0, duration - SAMPLE_SECONDS - 30)
    starts: list[int] = []
    for anchor in anchors:
        for offset in EXPAND_OFFSETS:
            for raw_start in (anchor - offset, anchor + offset):
                start = min(max(0, raw_start), latest)
                if start == anchor:
                    continue
                if all(abs(start - existing) >= SAMPLE_SECONDS for existing in starts):
                    starts.append(start)
    return starts


def with_sample_window(item: dict[str, Any], start: int) -> dict[str, Any]:
    return {
        **item,
        "sampleStartSeconds": start,
        "sampleId": sample_id(item, start),
        "sampleWindow": f"*{start}-{start + SAMPLE_SECONDS}",
    }


def cached_sample_info(path: Path) -> tuple[str, int] | None:
    match = CACHED_BROWSER_RE.match(path.stem)
    if not match:
        return None
    return match.group("video_id"), int(match.group("start"))


def presence_cache_path() -> Path:
    return MEDIA_DIR / ".violin-presence-cache.json"


def fresh_presence_cache() -> dict[str, Any]:
    return {"version": VIOLIN_PRESENCE_VERSION, "items": {}}


def load_presence_cache() -> dict[str, Any]:
    path = presence_cache_path()
    if not path.exists():
        return fresh_presence_cache()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fresh_presence_cache()
    if not isinstance(data, dict) or data.get("version") != VIOLIN_PRESENCE_VERSION:
        return fresh_presence_cache()
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data


def save_presence_cache(cache: dict[str, Any]) -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    path = presence_cache_path()
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def file_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "sizeBytes": int(stat.st_size),
        "mtimeNs": int(stat.st_mtime_ns),
        "violinSamplerVersion": VIOLIN_PRESENCE_VERSION,
    }


def cached_local_violin_presence(path: Path, cache: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    signature = file_signature(path)
    items = cache.setdefault("items", {})
    if not isinstance(items, dict):
        cache["items"] = items = {}
    key = str(signature["path"])
    entry = items.get(key)
    if isinstance(entry, dict) and entry.get("signature") == signature and isinstance(entry.get("presence"), dict):
        return entry["presence"], False
    presence = local_violin_presence(path)
    items[key] = {"signature": signature, "presence": presence}
    return presence, True


def cached_media_candidates(ops: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = ops.get("inventory", {}).get("youtube", [])
    sampled_ids, sampled_windows = live_sample_keys(ops)
    by_id = {
        str(item.get("id")): item
        for item in inventory
        if isinstance(item, dict) and item.get("id") and item.get("url")
    }
    candidates: list[dict[str, Any]] = []
    if not MEDIA_DIR.exists():
        return candidates
    include_negative = os.getenv("CURTIS_OWNER_UPLOAD_CACHED_NEGATIVES", "").strip().lower() in {"1", "true", "yes", "on"}
    presence_cache = load_presence_cache()
    presence_cache_changed = False
    for path in sorted(MEDIA_DIR.glob("*-browser.webm")):
        info = cached_sample_info(path)
        if not info:
            continue
        video_id, start = info
        item = by_id.get(video_id)
        if not item:
            continue
        sample_id_value = sample_id(item, start)
        key = (str(item.get("url") or ""), start)
        if sample_id_value in sampled_ids or key in sampled_windows:
            continue
        presence, changed = cached_local_violin_presence(path, presence_cache)
        presence_cache_changed = presence_cache_changed or changed
        if not include_negative and not presence.get("containsViolin"):
            continue
        candidate = with_sample_window(item, start)
        candidate["cachedPath"] = str(path)
        candidate["localPresence"] = presence
        candidates.append(candidate)
    if presence_cache_changed:
        save_presence_cache(presence_cache)
    return sorted(
        candidates,
        key=lambda item: (
            bool(item.get("localPresence", {}).get("containsViolin")),
            float(item.get("localPresence", {}).get("violinSamplerScore") or 0),
            str(item.get("publishedAt") or ""),
        ),
        reverse=True,
    )


def media_candidates(ops: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = ops.get("inventory", {}).get("youtube", [])
    sampled_ids, sampled_windows = live_sample_keys(ops)
    cached = cached_media_candidates(ops)
    cached_ids = {str(item.get("sampleId")) for item in cached if item.get("sampleId")}
    positive_starts = positive_sample_starts(ops)

    expansion: list[dict[str, Any]] = []
    for item in sorted(inventory, key=inventory_sort_key, reverse=True):
        if not (
            isinstance(item, dict)
            and item.get("practiceCandidate")
            and item.get("id")
            and item.get("url")
        ):
            continue
        for start in expanded_starts(item, positive_starts.get(str(item["id"]), [])):
            candidate = with_sample_window(item, start)
            key = (str(item.get("url") or ""), start)
            if str(candidate["sampleId"]) not in sampled_ids and str(candidate["sampleId"]) not in cached_ids and key not in sampled_windows:
                expansion.append(candidate)

    by_video: list[list[dict[str, Any]]] = []
    for item in sorted(inventory, key=inventory_sort_key, reverse=True):
        if not (
            isinstance(item, dict)
            and item.get("practiceCandidate")
            and item.get("id")
            and item.get("url")
        ):
            continue
        windows = []
        for start in sample_starts(item):
            candidate = with_sample_window(item, start)
            key = (str(item.get("url") or ""), start)
            if str(candidate["sampleId"]) not in sampled_ids and str(candidate["sampleId"]) not in cached_ids and key not in sampled_windows:
                windows.append(candidate)
        if windows:
            by_video.append(windows)

    candidates: list[dict[str, Any]] = []
    max_windows = max((len(windows) for windows in by_video), default=0)
    for index in range(max_windows):
        for windows in by_video:
            if index < len(windows):
                candidates.append(windows[index])
    return [*cached, *expansion, *candidates]


def inventory_sort_key(item: dict[str, Any]) -> tuple[int, str, int]:
    duration = item.get("durationSeconds")
    duration_value = duration if isinstance(duration, int) else 0
    title = str(item.get("title") or "").lower()
    dated = 1 if re.search(r"\b\d{1,2}-\d{1,2}-\d{2,4}\b", title) else 0
    return (dated, str(item.get("publishedAt") or ""), duration_value)


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
    cached = item.get("cachedPath")
    if cached:
        cached_path = Path(str(cached))
        if cached_path.exists() and cached_path.stat().st_size:
            return cached_path
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


def local_violin_presence(path: Path) -> dict[str, Any]:
    try:
        return classify_violin_presence(path)
    except Exception as exc:
        return {
            "containsViolin": False,
            "violinPresence": "unverified",
            "practiceEvidenceStatus": "needs_violin_verification",
            "violinSamplerVersion": VIOLIN_PRESENCE_VERSION,
            "violinSamplerScore": 0,
            "violinSamplerBlocker": "local_violin_presence_scan_failed",
            "violinSamplerDetail": str(exc)[:180],
        }


def upload_sample(client: httpx.Client, token: str, item: dict[str, Any], path: Path, presence: dict[str, Any]) -> dict[str, Any]:
    with path.open("rb") as handle:
        response = client.post(
            f"{API_BASE}/api/curtis/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "video_id": str(item.get("sampleId") or item["id"]),
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "window": str(item.get("sampleWindow") or sample_window(item)),
                "containsViolin": "true" if presence.get("containsViolin") else "false",
                "violinPresence": str(presence.get("violinPresence") or ""),
                "practiceEvidenceStatus": str(presence.get("practiceEvidenceStatus") or ""),
                "violinSamplerScore": str(presence.get("violinSamplerScore") or ""),
                "violinSamplerVersion": str(presence.get("violinSamplerVersion") or ""),
                "violinSamplerFeatures": json.dumps(presence.get("violinSamplerFeatures") or {}, ensure_ascii=False),
            },
            files={"file": (path.name, handle, "application/octet-stream")},
            timeout=180,
        )
    response.raise_for_status()
    return response.json()


def refresh_inventory(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        f"{API_BASE}/api/curtis/scan/run",
        json={
            "youtube": PUBLIC_YOUTUBE_SOURCE,
            "instagram": "",
            "scanScope": "Autonomous public channel refresh",
            "scanCadence": "Every owner sync",
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    token = load_token()
    if not token:
        print(json.dumps({"status": "blocked", "blocker": "missing_upload_token"}))
        return 2

    with httpx.Client(timeout=60) as client:
        try:
            ops = refresh_inventory(client)
        except Exception:
            ops = client.get(f"{API_BASE}/api/curtis/ops-check").json()
        candidates = media_candidates(ops)
        if not candidates:
            print(json.dumps({"status": "blocked", "blocker": "no_unsynced_practice_candidates"}))
            return 1
        uploaded: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        classified: list[dict[str, Any]] = []
        updated: dict[str, Any] = ops
        for item in candidates[: max(1, BATCH_SIZE)]:
            try:
                sample_path = download_sample(item)
                presence = item.get("localPresence") if isinstance(item.get("localPresence"), dict) else local_violin_presence(sample_path)
                updated = upload_sample(client, token, item, sample_path, presence)
                classified.append(
                    {
                        "id": item.get("sampleId") or item.get("id"),
                        "score": presence.get("violinSamplerScore"),
                        "violinPresence": presence.get("violinPresence"),
                        "containsViolin": presence.get("containsViolin"),
                    }
                )
                uploaded.append(
                    {
                        "id": item.get("sampleId") or item.get("id"),
                        "video": item.get("title"),
                        "window": item.get("sampleWindow") or sample_window(item),
                        "violinPresence": presence.get("violinPresence"),
                        "score": presence.get("violinSamplerScore"),
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
        "classified": classified,
        "blocked": blockers[:3],
        "mediaAccess": updated.get("review", {}).get("mediaAccess"),
        "samples": len(updated.get("media", {}).get("samples", [])),
    }))
    return 0 if uploaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
