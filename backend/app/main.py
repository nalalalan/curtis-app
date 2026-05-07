from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .scanner import base_ops, run_scan
from .settings import ROOT_DIR, SCAN_INTERVAL_SECONDS, SERVICE_NAME, allowed_origins
from .state import load_state, save_state


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


app = FastAPI(title="Curtis Media Review", version="0.2.0")
STATIC_ALLOWLIST = {"index.html", "app.js", "styles.css", "favicon.svg", "CNAME", ".nojekyll"}
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
        await asyncio.sleep(max(SCAN_INTERVAL_SECONDS, 300))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


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


@app.get("/{path:path}")
async def static_app(path: str) -> FileResponse:
    target = ROOT_DIR / path
    if path in STATIC_ALLOWLIST and target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(ROOT_DIR / "index.html")
