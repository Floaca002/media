"""
Jellyfin API client.

Two auth modes are used together:
  1. A server-level admin API key (X-Emby-Token) for catalog/library reads
     that don't need to be scoped to a specific human user.
  2. Per-user authentication (AuthenticateByName) to get a user AccessToken
     + UserId, used for anything personalized: playback, resume points,
     watched status, "Continue Watching".

Docs: https://api.jellyfin.org/
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("vault.jellyfin")


class JellyfinAuthError(Exception):
    """Raised when username/password authentication against Jellyfin fails."""


class JellyfinUnavailableError(Exception):
    """Raised when Jellyfin cannot be reached at all."""


class JellyfinClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.jellyfin_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=15.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _auth_header(self, token: str | None = None) -> dict[str, str]:
        """
        Jellyfin wants a structured 'X-Emby-Authorization' header identifying
        the client on every request, plus 'X-Emby-Token' once you have a
        token (either the admin API key or a user access token).
        """
        s = self._settings
        header = (
            f'MediaBrowser Client="{s.jellyfin_client_name}", '
            f'Device="{s.jellyfin_device_name}", '
            f'DeviceId="{s.jellyfin_device_id}", '
            f'Version="{s.jellyfin_version}"'
        )
        headers = {"X-Emby-Authorization": header}
        if token:
            headers["X-Emby-Token"] = token
        return headers

    async def _request(
        self, method: str, path: str, *, token: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        headers = {**self._auth_header(token), **kwargs.pop("headers", {})}
        try:
            response = await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise JellyfinUnavailableError(str(exc)) from exc
        response.raise_for_status()
        return response

    # ---------------------------------------------------------------- auth
    async def authenticate_by_name(self, username: str, password: str) -> dict[str, Any]:
        """
        POST /Users/AuthenticateByName
        Returns the full Jellyfin auth payload: {"User": {...}, "AccessToken": "...", ...}
        """
        try:
            response = await self._client.post(
                "/Users/AuthenticateByName",
                headers=self._auth_header(),
                json={"Username": username, "Pw": password},
            )
        except httpx.RequestError as exc:
            raise JellyfinUnavailableError(str(exc)) from exc

        if response.status_code == 401:
            raise JellyfinAuthError("Invalid Jellyfin username or password")
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------ catalog
    async def get_user_views(self, user_id: str, user_token: str) -> list[dict[str, Any]]:
        """Libraries visible to a user (Movies, TV Shows, ...)."""
        response = await self._request("GET", f"/Users/{user_id}/Views", token=user_token)
        return response.json().get("Items", [])

    async def get_items(
        self,
        user_id: str,
        user_token: str,
        *,
        parent_id: str | None = None,
        include_item_types: str | None = None,
        search_term: str | None = None,
        recursive: bool = True,
        sort_by: str = "SortName",
        start_index: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "Recursive": str(recursive).lower(),
            "SortBy": sort_by,
            "StartIndex": start_index,
            "Limit": limit,
            "Fields": "Overview,Genres,PrimaryImageAspectRatio,ProviderIds,MediaSourceCount",
        }
        if parent_id:
            params["ParentId"] = parent_id
        if include_item_types:
            params["IncludeItemTypes"] = include_item_types
        if search_term:
            params["SearchTerm"] = search_term

        response = await self._request(
            "GET", f"/Users/{user_id}/Items", token=user_token, params=params
        )
        return response.json()

    async def get_item(self, user_id: str, user_token: str, item_id: str) -> dict[str, Any]:
        response = await self._request(
            "GET", f"/Users/{user_id}/Items/{item_id}", token=user_token
        )
        return response.json()

    async def get_resume_items(self, user_id: str, user_token: str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            f"/Users/{user_id}/Items/Resume",
            token=user_token,
            params={"Limit": 20, "MediaTypes": "Video"},
        )
        return response.json().get("Items", [])

    async def get_next_up(self, user_id: str, user_token: str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET", "/Shows/NextUp", token=user_token, params={"UserId": user_id, "Limit": 20}
        )
        return response.json().get("Items", [])

    async def ping(self) -> dict[str, Any]:
        """Lightweight admin-scoped health check — GET /System/Info."""
        response = await self._request("GET", "/System/Info", token=self._settings.jellyfin_api_key)
        return response.json()

    async def refresh_library(self) -> None:
        """Trigger a full library scan using the admin API key (called by the organizer)."""
        await self._request(
            "POST", "/Library/Refresh", token=self._settings.jellyfin_api_key
        )

    # --------------------------------------------------------- playback/HLS
    async def get_playback_info(
        self, user_id: str, user_token: str, item_id: str, play_session_id: str
    ) -> dict[str, Any]:
        """
        POST /Items/{id}/PlaybackInfo — negotiates what the server can
        deliver (direct play vs transcode) for this device/session.
        """
        response = await self._request(
            "POST",
            f"/Items/{item_id}/PlaybackInfo",
            token=user_token,
            params={"UserId": user_id},
            json={
                "DeviceProfile": _BROWSER_HLS_DEVICE_PROFILE,
                "PlaySessionId": play_session_id,
                "AutoOpenLiveStream": True,
            },
        )
        return response.json()

    def build_hls_url(
        self,
        item_id: str,
        *,
        media_source_id: str,
        play_session_id: str,
        user_token: str,
    ) -> str:
        """
        Build the adaptive HLS master playlist URL for a video item.

        Jellyfin serves an HLS master playlist at:
          /Videos/{itemId}/master.m3u8
        with the target codecs/session identified via query params. The
        browser's hls.js (or Safari's native HLS) then fetches variant
        playlists + .ts/.m4s segments from the same base, all of which
        Jellyfin will happily serve given a valid api_key query param —
        which is why we pass the *user's* short-lived access token rather
        than the server admin key.
        """
        query = httpx.QueryParams(
            {
                "MediaSourceId": media_source_id,
                "PlaySessionId": play_session_id,
                "VideoCodec": "h264",
                "AudioCodec": "aac,mp3",
                "MaxAudioChannels": "6",
                "TranscodingMaxAudioChannels": "6",
                "SegmentContainer": "ts",
                "MinSegments": "1",
                "BreakOnNonKeyFrames": "True",
                "api_key": user_token,
                "DeviceId": self._settings.jellyfin_device_id,
            }
        )
        return f"{self._base_url}/Videos/{item_id}/master.m3u8?{query}"

    async def report_playback_start(
        self, user_token: str, item_id: str, play_session_id: str, media_source_id: str
    ) -> None:
        await self._request(
            "POST",
            "/Sessions/Playing",
            token=user_token,
            json={
                "ItemId": item_id,
                "PlaySessionId": play_session_id,
                "MediaSourceId": media_source_id,
                "CanSeek": True,
                "PlayMethod": "Transcode",
            },
        )

    async def report_playback_progress(
        self,
        user_token: str,
        item_id: str,
        play_session_id: str,
        position_ticks: int,
        is_paused: bool = False,
    ) -> None:
        """Position ticks are 100-nanosecond units, per Jellyfin convention."""
        await self._request(
            "POST",
            "/Sessions/Playing/Progress",
            token=user_token,
            json={
                "ItemId": item_id,
                "PlaySessionId": play_session_id,
                "PositionTicks": position_ticks,
                "IsPaused": is_paused,
            },
        )

    async def report_playback_stopped(
        self, user_token: str, item_id: str, play_session_id: str, position_ticks: int
    ) -> None:
        await self._request(
            "POST",
            "/Sessions/Playing/Stopped",
            token=user_token,
            json={
                "ItemId": item_id,
                "PlaySessionId": play_session_id,
                "PositionTicks": position_ticks,
            },
        )


def new_play_session_id() -> str:
    return uuid.uuid4().hex


# A minimal device profile telling Jellyfin "I am an HTML5 browser that can
# play HLS with h264/aac via MSE (hls.js) or natively (Safari)". Jellyfin
# uses this to decide direct-play vs transcode per source.
_BROWSER_HLS_DEVICE_PROFILE: dict[str, Any] = {
    "MaxStreamingBitrate": 120000000,
    "DirectPlayProfiles": [
        {"Container": "mp4,m4v", "Type": "Video", "VideoCodec": "h264", "AudioCodec": "aac,mp3"}
    ],
    "TranscodingProfiles": [
        {
            "Container": "ts",
            "Type": "Video",
            "VideoCodec": "h264",
            "AudioCodec": "aac,mp3",
            "Protocol": "hls",
            "Context": "Streaming",
            "MaxAudioChannels": "6",
        }
    ],
    "CodecProfiles": [],
    "SubtitleProfiles": [
        {"Format": "vtt", "Method": "External"},
        {"Format": "srt", "Method": "External"},
    ],
}
