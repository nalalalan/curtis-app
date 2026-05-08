from __future__ import annotations

from pathlib import Path

import httpx

from .analyzer import run_process
from .settings import RUNTIME_DIR


SCORE_ASSETS: dict[str, dict[str, str]] = {
    "haydn-94-finale-score": {
        "title": "Haydn Symphony No. 94, IV. Finale",
        "pdfUrl": "https://vmirror.imslp.org/files/imglnks/usimg/8/87/IMSLP360278-PMLP34746-Haydn%3B_Symphony_94_Corrected.pdf",
        "sourceUrl": "https://imslp.org/wiki/Symphony_No.94_%28Haydn%2C_Joseph%29",
    },
    "wieniawski-scherzo-tarantelle-vln": {
        "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
        "pdfUrl": "https://s9.imslp.org/files/imglnks/usimg/b/b0/IMSLP724668-PMLP17451-01._WIENIAWSKI_-_SCHERZO_TARANTELLE%2C_OP._16_%28GILSON%29_-_Solo_Part.pdf",
        "sourceUrl": "https://imslp.org/wiki/Scherzo_tarantelle%2C_Op.16_%28Wieniawski%2C_Henri%29",
    },
}


def score_asset_config(asset_id: str) -> dict[str, str] | None:
    return SCORE_ASSETS.get(str(asset_id or "").strip())


def score_page_url(asset_id: str, page: int) -> str:
    if not score_asset_config(asset_id):
        return ""
    safe_page = max(1, int(page or 1))
    return f"/api/curtis/score/page/{asset_id}/{safe_page}"


def score_asset_dir() -> Path:
    target = RUNTIME_DIR / "score-assets"
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_score_pdf(asset_id: str) -> Path:
    config = score_asset_config(asset_id)
    if not config:
        raise ValueError("unknown score asset")
    target = score_asset_dir() / f"{asset_id}.pdf"
    if target.exists() and target.stat().st_size > 1024:
        return target
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        response = client.get(config["pdfUrl"])
        response.raise_for_status()
        target.write_bytes(response.content)
    if target.stat().st_size <= 1024:
        raise RuntimeError("score pdf download was empty")
    return target


def ensure_score_page(asset_id: str, page: int) -> Path:
    config = score_asset_config(asset_id)
    if not config:
        raise ValueError("unknown score asset")
    safe_page = max(1, int(page or 1))
    target = score_asset_dir() / f"{asset_id}-p{safe_page}.jpg"
    if target.exists() and target.stat().st_size > 1024:
        return target
    pdf_path = ensure_score_pdf(asset_id)
    prefix = score_asset_dir() / f"{asset_id}-p{safe_page}"
    code, output = run_process(
        [
            "pdftoppm",
            "-singlefile",
            "-jpeg",
            "-f",
            str(safe_page),
            "-l",
            str(safe_page),
            "-r",
            "130",
            str(pdf_path),
            str(prefix),
        ],
        timeout=180,
    )
    if code != 0 or not target.exists() or target.stat().st_size <= 1024:
        raise RuntimeError(output[-500:] or "score page render failed")
    return target
