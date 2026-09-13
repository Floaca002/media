"""
qBittorrent Web API client.

Handles cookie-based session auth (with automatic re-login on expiry),
adding magnet links, polling torrent status, and pause/resume/delete.

Docs: https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("vault.qbittorrent")


class QBittorrentAuthError(Exception):
    """Raised when login to qBittorrent fails (bad credentials)."""


class QBittorrentUnavailableError(Exception):
    """Raised when qBittorrent cannot be reached at all."""


class QBittorrentClient:
    """
    Thin async wrapper around qBittorrent's Web API.

    qBittorrent uses a session cookie (SID) obtained from /api/v2/auth/login.
    Since v4.1 it also enforces a Referer/Origin check, so both headers are
    set to the qBittorrent base URL on every request. The client re-logs-in
    transparently whenever a request comes back 403 (session expired).
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.qbittorrent_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Referer": self._base_url,
                "Origin": self._base_url,
            },
            timeout=15.0,
        )
        self._login_lock = asyncio.Lock()
        self._authenticated = False

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------------------------------------------------------------- auth
    async def _login(self) -> None:
        """
        POST /api/v2/auth/login with form-encoded credentials.
        On success qBittorrent sets a session cookie on the underlying
        httpx.AsyncClient cookie jar automatically — historically named
        "SID", but observed as "QBT_SID_<port>" on a newer release, so we
        don't match on an exact cookie name. The response shape on success
        has similarly varied (200 with body "Ok." historically; 204 with an
        empty body observed here) so the reliable success signal is simply
        whether *any* cookie got set, since qBittorrent sets none on a
        failed login.
        """
        async with self._login_lock:
            if self._authenticated:
                return
            try:
                response = await self._client.post(
                    "/api/v2/auth/login",
                    data={
                        "username": self._settings.qbittorrent_username,
                        "password": self._settings.qbittorrent_password,
                    },
                )
            except httpx.RequestError as exc:
                raise QBittorrentUnavailableError(str(exc)) from exc

            if not self._client.cookies:
                raise QBittorrentAuthError(
                    f"qBittorrent login failed (status={response.status_code}, "
                    f"body={response.text!r})"
                )
            self._authenticated = True
            logger.info("qBittorrent: authenticated session established")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """
        Issue a request, ensuring we're logged in first. If qBittorrent
        responds 403 (session cookie missing/expired), force a re-login
        once and retry.
        """
        if not self._authenticated:
            await self._login()

        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise QBittorrentUnavailableError(str(exc)) from exc

        if response.status_code == 403:
            logger.warning("qBittorrent: session expired, re-authenticating")
            self._authenticated = False
            await self._login()
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.RequestError as exc:
                raise QBittorrentUnavailableError(str(exc)) from exc

        response.raise_for_status()
        return response

    # ------------------------------------------------------------ commands
    async def add_magnet(self, magnet_uri: str, category: str, *, paused: bool = False) -> None:
        """
        POST /api/v2/torrents/add — multipart form, 'urls' holds magnet link(s).

        Explicitly sets `savepath` to the shared downloads volume's mount
        point inside this container. Without it, qBittorrent falls back to
        its own internal default save location (observed as "/downloads",
        an ephemeral root-owned path baked into the image — nothing to do
        with our actual `media-downloads` volume, mounted here at
        DOWNLOADS_SAVE_PATH), causing every download to fail with a
        permission error and, even if it somehow succeeded, leaving files
        somewhere the organizer's vault-backend container has no access to
        at all.

        A 409 from qBittorrent means a torrent with this info-hash already
        exists (e.g. a previous attempt's entry that was never cleaned up
        on qBittorrent's side) — that's not a real failure for an
        add-if-missing operation like this one, so it's treated as success
        rather than surfaced as a crash.
        """
        try:
            await self._request(
                "POST",
                "/api/v2/torrents/add",
                data={
                    "urls": magnet_uri,
                    "category": category,
                    "savepath": self._settings.downloads_save_path,
                    "paused": "true" if paused else "false",
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                logger.info("qBittorrent: torrent already exists, treating add_magnet as a no-op")
                return
            raise

    async def ensure_category_save_path(self, category: str, save_path: str) -> None:
        """
        Pins a category's save path inside qBittorrent itself, so *any*
        client adding a torrent under this category — our own backend,
        Radarr, or Sonarr — saves into the shared volume regardless of
        whether that specific caller bothered to pass its own `savepath`.
        Passing one on our own /torrents/add calls (see add_magnet) doesn't
        help at all for torrents Radarr/Sonarr add directly, which is
        exactly the gap that caused a second round of the same permission
        error this call fixes for good.
        """
        try:
            await self._request(
                "POST", "/api/v2/torrents/createCategory", data={"category": category, "savePath": save_path}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:  # category already exists
                await self._request(
                    "POST", "/api/v2/torrents/editCategory", data={"category": category, "savePath": save_path}
                )
            else:
                raise

    async def set_default_save_path(self, save_path: str) -> None:
        """
        POST /api/v2/app/setPreferences — sets qBittorrent's own global
        default save location. A category's save path (ensure_category_save_
        path) only actually applies to torrents added under Automatic
        Torrent Management, and Radarr's own /torrents/add calls don't
        request that — reproduced live: even after pinning the "radarr"
        category's path, new torrents Radarr added still fell back to
        qBittorrent's global default ("/downloads", the same broken
        ephemeral path from the start of this saga) and failed the same
        way. Setting the global default directly closes that gap for any
        caller that doesn't specify AutoTMM or an explicit savepath.
        """
        await self._request(
            "POST", "/api/v2/app/setPreferences", data={"json": json.dumps({"save_path": save_path})}
        )

    async def list_torrents(self, category: str | None = None) -> list[dict[str, Any]]:
        """GET /api/v2/torrents/info — optionally filtered by category."""
        params: dict[str, Any] = {}
        if category:
            params["category"] = category
        response = await self._request("GET", "/api/v2/torrents/info", params=params)
        return response.json()

    async def torrent_properties(self, torrent_hash: str) -> dict[str, Any]:
        response = await self._request(
            "GET", "/api/v2/torrents/properties", params={"hash": torrent_hash}
        )
        return response.json()

    async def pause(self, torrent_hash: str) -> None:
        await self._request("POST", "/api/v2/torrents/pause", data={"hashes": torrent_hash})

    async def resume(self, torrent_hash: str) -> None:
        await self._request("POST", "/api/v2/torrents/resume", data={"hashes": torrent_hash})

    async def delete(self, torrent_hash: str, *, delete_files: bool = False) -> None:
        await self._request(
            "POST",
            "/api/v2/torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
        )

    async def set_file_priority(self, torrent_hash: str, file_ids: list[int], priority: int) -> None:
        """priority: 0=don't download, 1=normal, 6=high, 7=maximal."""
        await self._request(
            "POST",
            "/api/v2/torrents/filePrio",
            data={
                "hash": torrent_hash,
                "id": "|".join(str(i) for i in file_ids),
                "priority": priority,
            },
        )


def summarize_torrent(raw: dict[str, Any]) -> dict[str, Any]:
    """Map qBittorrent's raw torrent-info dict to the shape our API returns."""
    eta_seconds = raw.get("eta", 0)
    return {
        "hash": raw.get("hash"),
        "name": raw.get("name"),
        "category": raw.get("category"),
        "progress": round(raw.get("progress", 0.0) * 100, 1),  # percent
        "download_speed_bps": raw.get("dlspeed", 0),
        "upload_speed_bps": raw.get("upspeed", 0),
        "eta_seconds": None if eta_seconds >= 8640000 else eta_seconds,  # qBt uses 8640000 as "infinite"
        "state": raw.get("state"),
        "size_bytes": raw.get("size", 0),
        "save_path": raw.get("save_path"),
        "content_path": raw.get("content_path"),
    }
