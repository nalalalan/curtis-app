from __future__ import annotations

import os
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from .state import load_state, save_state, utc_now


YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def youtube_oauth_config() -> dict[str, str]:
    state = load_state()
    auth = state.get("auth", {}).get("youtube", {})
    return {
        "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        "refresh_token": (os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip() or auth.get("refreshToken", "")),
    }


def youtube_auth_status() -> dict[str, Any]:
    state = load_state()
    auth = state.get("auth", {}).get("youtube", {})
    config = youtube_oauth_config()
    return {
        "configured": bool(config["client_id"] and config["client_secret"]),
        "connected": bool(config["client_id"] and config["client_secret"] and config["refresh_token"]),
        "channelTitle": auth.get("channelTitle", ""),
        "connectedAt": auth.get("connectedAt", ""),
        "scope": auth.get("scope", ""),
    }


def build_youtube_authorization_url(redirect_uri: str) -> str:
    state = load_state()
    oauth_state = secrets.token_urlsafe(32)
    state.setdefault("auth", {}).setdefault("youtube", {})["oauthState"] = oauth_state
    save_state(state)
    query = urlencode(
        {
            "client_id": youtube_oauth_config()["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": YOUTUBE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": oauth_state,
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_youtube_code(code: str, redirect_uri: str) -> dict[str, Any]:
    config = youtube_oauth_config()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def fetch_youtube_channel_title(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        payload = response.json()
    items = payload.get("items", [])
    if not items:
        return ""
    return items[0].get("snippet", {}).get("title", "")


def save_youtube_tokens(payload: dict[str, Any], channel_title: str = "") -> None:
    state = load_state()
    youtube = state.setdefault("auth", {}).setdefault("youtube", {})
    refresh_token = payload.get("refresh_token")
    if isinstance(refresh_token, str) and refresh_token:
        youtube["refreshToken"] = refresh_token
    youtube["connected"] = bool(youtube.get("refreshToken"))
    youtube["connectedAt"] = utc_now()
    youtube["scope"] = payload.get("scope", YOUTUBE_SCOPE)
    if channel_title:
        youtube["channelTitle"] = channel_title
    state.setdefault("sources", {})["youtube"] = "mine"
    state.setdefault("sources", {})["scanScope"] = "Authenticated full archive"
    state.setdefault("sources", {})["scanCadence"] = "Daily"
    youtube.pop("oauthState", None)
    save_state(state)


def validate_youtube_oauth_state(returned_state: str) -> bool:
    state = load_state()
    expected = state.get("auth", {}).get("youtube", {}).get("oauthState")
    return bool(expected and returned_state and secrets.compare_digest(str(expected), returned_state))
