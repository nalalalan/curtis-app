from __future__ import annotations

import os
from typing import Any

import httpx

from .auth import youtube_auth_status
from .platforms import credential_state, fetch_instagram_inventory, fetch_youtube_inventory
from .settings import OPENAI_MODEL, OPENAI_REASONING_EFFORT, SERVICE_NAME
from .state import append_run, load_state, save_state, utc_now


def stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def effective_sources(state: dict[str, Any]) -> dict[str, Any]:
    sources = dict(state.get("sources", {}))
    sources["youtube"] = sources.get("youtube") or os.getenv("CURTIS_YOUTUBE_SOURCE", "")
    sources["instagram"] = sources.get("instagram") or os.getenv("CURTIS_INSTAGRAM_SOURCE", "")
    return sources


def derive_review(inventory: dict[str, list[dict[str, Any]]], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    sections = existing.get("notableSections") if isinstance(existing.get("notableSections"), list) else []
    reviewed_urls = {
        section.get("url")
        for section in sections
        if isinstance(section, dict) and section.get("url")
    }
    return {
        "reviewedVideoCount": len(reviewed_urls),
        "notableSections": sections,
        "currentWork": "No processed video sections.",
        "strongestSignal": "Unjudged",
        "weakestRecurringSignal": "Unjudged",
        "inventoryCount": sum(len(items) for items in inventory.values()),
    }


def base_ops(state: dict[str, Any], extra_blockers: list[str] | None = None) -> dict[str, Any]:
    credentials = credential_state()
    sources = effective_sources(state)
    blockers = list(extra_blockers or [])
    has_any_source = bool(sources.get("youtube") or sources.get("instagram"))
    if not credentials["openai"]:
        blockers.append("missing_openai_api_key")
    if not has_any_source and not sources.get("youtube"):
        blockers.append("missing_youtube_source")
    if not has_any_source and not sources.get("instagram"):
        blockers.append("missing_instagram_source")

    inventory = state.get("inventory", {"youtube": [], "instagram": []})
    review = derive_review(inventory, state.get("review"))
    status = "blocked" if blockers else "ready"
    if not blockers and review.get("inventoryCount"):
        status = "inventory_ready"

    return {
        "service": SERVICE_NAME,
        "status": status,
        "checkedAt": utc_now(),
        "model": {
            "id": OPENAI_MODEL,
            "reasoningEffort": OPENAI_REASONING_EFFORT,
        },
        "credentials": credentials,
        "auth": {
            "youtube": youtube_auth_status(),
        },
        "sources": sources,
        "inventory": inventory,
        "review": review,
        "lastScan": state.get("lastScan"),
        "blockers": stable_unique(blockers),
    }


async def run_scan(incoming_sources: dict[str, Any] | None = None) -> dict[str, Any]:
    state = load_state()
    if incoming_sources:
        state["sources"] = {
            **state.get("sources", {}),
            **{key: value for key, value in incoming_sources.items() if value is not None},
        }

    sources = effective_sources(state)
    blockers: list[str] = []
    errors: list[dict[str, str]] = []
    inventory = {"youtube": [], "instagram": []}
    has_any_source = bool(sources.get("youtube") or sources.get("instagram"))

    if sources.get("youtube"):
        try:
            youtube_result = await fetch_youtube_inventory(str(sources.get("youtube", "")))
            inventory["youtube"] = youtube_result.items
            blockers.extend(youtube_result.blockers)
        except httpx.HTTPStatusError as exc:
            blockers.append("youtube_api_error")
            errors.append({"platform": "youtube", "detail": exc.response.text[:500]})
        except Exception as exc:  # pragma: no cover - defensive service boundary
            blockers.append("youtube_scan_failed")
            errors.append({"platform": "youtube", "detail": str(exc)[:500]})

    if sources.get("instagram"):
        try:
            instagram_result = await fetch_instagram_inventory(str(sources.get("instagram", "")))
            inventory["instagram"] = instagram_result.items
            blockers.extend(instagram_result.blockers)
        except httpx.HTTPStatusError as exc:
            blockers.append("instagram_api_error")
            errors.append({"platform": "instagram", "detail": exc.response.text[:500]})
        except Exception as exc:  # pragma: no cover - defensive service boundary
            blockers.append("instagram_scan_failed")
            errors.append({"platform": "instagram", "detail": str(exc)[:500]})

    if not has_any_source:
        blockers.extend(["missing_youtube_source", "missing_instagram_source"])

    state["inventory"] = inventory
    state["review"] = derive_review(inventory, state.get("review"))

    run = {
        "startedAt": utc_now(),
        "status": "blocked" if blockers else "inventory_ready",
        "inventoryCount": sum(len(items) for items in inventory.values()),
        "blockers": stable_unique(blockers),
        "errors": errors,
    }
    append_run(state, run)
    save_state(state)
    return base_ops(state, blockers)
