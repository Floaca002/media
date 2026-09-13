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
        Jellyfin 12 removed the legacy X-Emby-Authorization/X-Emby-Token/
        X-MediaBrowser-Token headers and the api_key query param entirely —
        confirmed against a live 12.0.0 server, which rejected all of them
        uniformly as unrecognized. Everything now goes through a single
        standard Authorization header carrying both client identification
        and, once available, the token (API key or user access token):
            Authorization: MediaBrowser Client="...", Device="...",
                           DeviceId="...", Version="...", Token="..."
        """
        s = self._settings
        parts = [
            f'Client="{s.jellyfin_client_name}"',
            f'Device="{s.jellyfin_device_name}"',
            f'DeviceId="{s.jellyfin_device_id}"',
            f'Version="{s.jellyfin_version}"',
        ]
        if token:
            parts.append(f'Token="{token}"')
        return {"Authorization": "MediaBrowser " + ", ".join(parts)}

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

        if response.status_code in (400, 401):
            # Jellyfin returns 400 (not just 401) for bad credentials on this
            # endpoint depending on version/config, so treat both as auth failure.
            raise JellyfinAuthError("Invalid Jellyfin username or password")
        response.raise_for_status()
        return response.json()

    async def request_password_reset_pin(self, username: str) -> dict[str, Any]:
        """
        POST /Users/ForgotPassword — asks Jellyfin to write a one-time PIN to
        a file on its own filesystem (under its config volume). Jellyfin has
        no email step in a plain self-hosted setup: reading that file is
        itself the proof that the requester has server/filesystem access,
        which is what makes this safe to expose without further auth. The
        response tells us where it wrote the file so we can tell the user
        exactly what to `docker exec` for.
        """
        response = await self._client.post(
            "/Users/ForgotPassword",
            headers=self._auth_header(),
            json={"EnteredUsername": username},
        )
        response.raise_for_status()
        return response.json()

    async def set_password(self, user_id: str, user_token: str, new_password: str) -> None:
        """POST /Users/{id}/Password as the user themselves (requires their current password)."""
        await self._request(
            "POST",
            f"/Users/{user_id}/Password",
            token=user_token,
            json={"CurrentPw": "", "NewPw": new_password},
        )

    async def find_user_by_name(self, username: str) -> dict[str, Any] | None:
        """Admin-scoped user lookup, used to resolve a user id for admin-level actions."""
        response = await self._request("GET", "/Users", token=self._settings.jellyfin_api_key)
        for user in response.json():
            if user.get("Name", "").lower() == username.lower():
                return user
        return None

    async def set_password_as_admin(self, user_id: str, new_password: str) -> None:
        """
        POST /Users/{id}/Password using the server admin API key. Fields are
        CurrentPw/NewPw (confirmed against Jellyfin's own web client via its
        network traffic) — CurrentPw is left blank since we're not the
        target user; Jellyfin's server-side permission check lets an admin
        token change any user's password without knowing the old one. The
        `ResetPassword` flag does NOT belong here: it looked plausible from
        older Jellyfin API docs, but sending it triggers a different,
        broken-for-this-purpose code path server-side (confirmed by
        reproducing "Admin user passwords must not be empty" with it set,
        which went away the moment it was removed).
        """
        await self._request(
            "POST",
            f"/Users/{user_id}/Password",
            token=self._settings.jellyfin_api_key,
            json={"CurrentPw": "", "NewPw": new_password},
        )

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

    async def get_seasons(self, user_id: str, user_token: str, series_id: str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET", f"/Shows/{series_id}/Seasons", token=user_token, params={"userId": user_id}
        )
        return response.json().get("Items", [])

    async def get_episodes(
        self, user_id: str, user_token: str, series_id: str, season_id: str
    ) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            f"/Shows/{series_id}/Episodes",
            token=user_token,
            params={"userId": user_id, "seasonId": season_id},
        )
        return response.json().get("Items", [])

    async def find_item_by_tmdb_id(self, media_type: str, tmdb_id: int) -> str | None:
        """
        Admin-scoped lookup used once a Request flips to AVAILABLE, to
        record which Jellyfin item it actually became — otherwise
        MediaRequest.jellyfin_item_id is never set at all, and "Watch Now"
        on a Discover detail page has nothing to link to.

        Filters client-side rather than trusting a server-side
        provider-id-equals query param, since this session has repeatedly
        found Jellyfin API details not to be what older docs/assumptions
        suggested — a personal library is small enough that fetching
        everything of this type and matching locally is cheap and reliable.
        """
        item_type = "Movie" if media_type == "movie" else "Series"
        response = await self._request(
            "GET",
            "/Items",
            token=self._settings.jellyfin_api_key,
            params={"Recursive": "true", "IncludeItemTypes": item_type, "Fields": "ProviderIds"},
        )
        for item in response.json().get("Items", []):
            provider_ids = item.get("ProviderIds") or {}
            if str(provider_ids.get("Tmdb")) == str(tmdb_id):
                return item["Id"]
        return None

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

    def build_hls_url(self, item_id: str, *, media_source_id: str, play_session_id: str) -> str:
        """
        Build the adaptive HLS master playlist URL for a video item — as a
        path through Vault's OWN /api/stream proxy (app/routers/stream.py),
        not a direct Jellyfin URL. Jellyfin has no published port in this
        deployment; the browser can never reach it directly by design, so
        every browser-facing media URL has to be re-authenticated and
        streamed through this backend instead. (An earlier version of this
        embedded the user's token as an `api_key` query param for the
        browser to hit Jellyfin directly — that never could have worked
        here, and separately, Jellyfin 12 also dropped support for that
        query param entirely.)
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
                "DeviceId": self._settings.jellyfin_device_id,
            }
        )
        return f"/api/stream/{item_id}/master.m3u8?{query}"

    async def get_item_image(self, item_id: str, tag: str | None = None) -> httpx.Response:
        """
        Fetches a poster/backdrop image using the admin API key, for the
        unauthenticated image-proxy endpoint to stream back to the browser
        — an <img> tag can't attach a Vault JWT the way a fetch() call can,
        so that endpoint can't require the normal auth dependency, and
        needs its own credential to reach Jellyfin instead.
        """
        params = {"tag": tag} if tag else {}
        return await self._request(
            "GET", f"/Items/{item_id}/Images/Primary", token=self._settings.jellyfin_api_key, params=params
        )

    async def stream_passthrough(self, path: str, *, token: str, params: dict[str, Any]) -> httpx.Response:
        """Authenticated raw GET used by the HLS proxy for manifests and media segments alike."""
        return await self._request("GET", path, token=token, params=params)

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
