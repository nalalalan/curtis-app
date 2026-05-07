from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from .auth import youtube_oauth_config
from .settings import (
    INSTAGRAM_GRAPH_VERSION,
    INSTAGRAM_MAX_RESULTS,
    YOUTUBE_MAX_RESULTS,
    env_present,
)


YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True)
class InventoryResult:
    items: list[dict[str, Any]]
    blockers: list[str]
    source_type: str


def credential_state() -> dict[str, bool]:
    youtube_oauth = youtube_oauth_config()
    return {
        "openai": env_present("OPENAI_API_KEY"),
        "youtubeApiKey": env_present("YOUTUBE_API_KEY") or env_present("GOOGLE_API_KEY"),
        "youtubeOAuth": bool(
            youtube_oauth["client_id"]
            and youtube_oauth["client_secret"]
            and youtube_oauth["refresh_token"]
        ),
        "youtubeOAuthConfigured": bool(youtube_oauth["client_id"] and youtube_oauth["client_secret"]),
        "instagramGraph": env_present("INSTAGRAM_ACCESS_TOKEN") and env_present("INSTAGRAM_USER_ID"),
    }


def youtube_api_key() -> str:
    return os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def parse_youtube_source(source: str) -> dict[str, str]:
    value = source.strip()
    if not value:
        return {"type": "unset", "value": ""}

    if YOUTUBE_CHANNEL_ID_RE.match(value):
        return {"type": "channel", "value": value}
    if YOUTUBE_VIDEO_ID_RE.match(value):
        return {"type": "video", "value": value}
    if value.startswith("@"):
        return {"type": "handle", "value": value}
    if value.startswith(("PL", "UU", "OLAK5uy_")):
        return {"type": "playlist", "value": value}
    if value.lower() in {"mine", "my channel", "authenticated"}:
        return {"type": "mine", "value": "mine"}

    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc.lower().removeprefix("www.")
    path = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if "youtu.be" in host and path and YOUTUBE_VIDEO_ID_RE.match(path[0]):
        return {"type": "video", "value": path[0]}
    if "youtube.com" in host:
        if "v" in query and query["v"] and YOUTUBE_VIDEO_ID_RE.match(query["v"][0]):
            return {"type": "video", "value": query["v"][0]}
        if "list" in query and query["list"]:
            return {"type": "playlist", "value": query["list"][0]}
        if path and path[0] in {"shorts", "embed", "live"} and len(path) > 1:
            return {"type": "video", "value": path[1]}
        if path and path[0] == "channel" and len(path) > 1:
            return {"type": "channel", "value": path[1]}
        if path and path[0].startswith("@"):
            return {"type": "handle", "value": path[0]}

    return {"type": "unresolved", "value": value}


async def google_oauth_token() -> str | None:
    config = youtube_oauth_config()
    if not (config["client_id"] and config["client_secret"] and config["refresh_token"]):
        return None
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "refresh_token": config["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        return token if isinstance(token, str) else None


async def youtube_get(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any],
    access_token: str | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
    request_params = dict(params)
    if not access_token:
        request_params["key"] = youtube_api_key()
    response = await client.get(
        f"https://www.googleapis.com/youtube/v3/{path}",
        params=request_params,
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


def youtube_item_from_playlist(item: dict[str, Any]) -> dict[str, Any] | None:
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    resource = snippet.get("resourceId") or {}
    video_id = content.get("videoId") or resource.get("videoId")
    if not video_id:
        return None
    return {
        "platform": "youtube",
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": snippet.get("title") or "Untitled YouTube video",
        "publishedAt": content.get("videoPublishedAt") or snippet.get("publishedAt"),
        "channelTitle": snippet.get("channelTitle"),
        "sourceType": "playlist",
        "analysisState": "metadata_ready_media_blocked",
        "blockers": ["youtube_data_api_returns_metadata_not_video_media"],
    }


def youtube_item_from_video(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    stats = item.get("statistics") or {}
    video_id = item.get("id")
    return {
        "platform": "youtube",
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": snippet.get("title") or "Untitled YouTube video",
        "publishedAt": snippet.get("publishedAt"),
        "channelTitle": snippet.get("channelTitle"),
        "duration": content.get("duration"),
        "viewCount": stats.get("viewCount"),
        "sourceType": "video",
        "analysisState": "metadata_ready_media_blocked",
        "blockers": ["youtube_data_api_returns_metadata_not_video_media"],
    }


async def fetch_youtube_inventory(source: str, limit: int = YOUTUBE_MAX_RESULTS) -> InventoryResult:
    parsed = parse_youtube_source(source)
    if parsed["type"] == "unset":
        return InventoryResult([], ["missing_youtube_source"], "unset")

    credentials = credential_state()
    if parsed["type"] == "mine" and not credentials["youtubeOAuth"]:
        return InventoryResult([], ["missing_youtube_oauth_connection"], "mine")
    if not credentials["youtubeApiKey"] and not credentials["youtubeOAuth"]:
        return InventoryResult([], ["missing_youtube_api_key_or_oauth"], parsed["type"])

    access_token = None
    if parsed["type"] == "mine" or (not credentials["youtubeApiKey"] and credentials["youtubeOAuth"]):
        access_token = await google_oauth_token()
        if not access_token:
            return InventoryResult([], ["youtube_oauth_token_refresh_failed"], parsed["type"])

    blockers: list[str] = []
    async with httpx.AsyncClient(timeout=30) as client:
        if parsed["type"] == "video":
            payload = await youtube_get(
                client,
                "videos",
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": parsed["value"],
                    "maxResults": 1,
                },
                access_token,
            )
            return InventoryResult(
                [youtube_item_from_video(item) for item in payload.get("items", [])],
                ["youtube_data_api_returns_metadata_not_video_media"],
                "video",
            )

        playlist_id = parsed["value"] if parsed["type"] == "playlist" else None
        if parsed["type"] in {"channel", "handle", "mine"}:
            params: dict[str, Any] = {"part": "contentDetails,snippet", "maxResults": 1}
            if parsed["type"] == "channel":
                params["id"] = parsed["value"]
            elif parsed["type"] == "mine":
                params["mine"] = "true"
            else:
                params["forHandle"] = parsed["value"]
            channel_payload = await youtube_get(client, "channels", params, access_token)
            items = channel_payload.get("items", [])
            if not items:
                return InventoryResult([], ["youtube_channel_not_found"], parsed["type"])
            playlist_id = (
                items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            if not playlist_id:
                return InventoryResult([], ["youtube_uploads_playlist_missing"], parsed["type"])

        if not playlist_id:
            return InventoryResult([], ["unresolved_youtube_source"], parsed["type"])

        items = []
        page_token = None
        target_count = max(limit, 1)
        while len(items) < target_count:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(target_count - len(items), 50),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = await youtube_get(client, "playlistItems", params, access_token)
            items.extend(
                mapped
                for item in payload.get("items", [])
                if (mapped := youtube_item_from_playlist(item)) is not None
            )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        blockers.append("youtube_data_api_returns_metadata_not_video_media")
        return InventoryResult(items, blockers, parsed["type"])


async def fetch_instagram_inventory(source: str, limit: int = INSTAGRAM_MAX_RESULTS) -> InventoryResult:
    if not source.strip() and not os.getenv("INSTAGRAM_USER_ID"):
        return InventoryResult([], ["missing_instagram_source"], "unset")
    if not credential_state()["instagramGraph"]:
        return InventoryResult([], ["missing_instagram_access_token_or_user_id"], "profile")

    user_id = os.getenv("INSTAGRAM_USER_ID", "")
    fields = "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"https://graph.facebook.com/{INSTAGRAM_GRAPH_VERSION}/{user_id}/media",
            params={
                "fields": fields,
                "limit": min(max(limit, 1), 50),
                "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            },
        )
        response.raise_for_status()
        payload = response.json()

    items = []
    for item in payload.get("data", []):
        media_type = item.get("media_type")
        has_media = bool(item.get("media_url") or item.get("thumbnail_url"))
        items.append(
            {
                "platform": "instagram",
                "id": item.get("id"),
                "url": item.get("permalink"),
                "title": (item.get("caption") or "Instagram media").splitlines()[0][:120],
                "publishedAt": item.get("timestamp"),
                "mediaType": media_type,
                "hasMediaUrl": has_media,
                "sourceType": "instagram_graph",
                "analysisState": "media_url_ready" if has_media else "metadata_ready_media_blocked",
                "blockers": [] if has_media else ["instagram_media_url_missing"],
            }
        )
    return InventoryResult(items, [], "instagram_graph")
