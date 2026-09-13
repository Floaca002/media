"""
Shared client for the "*arr" family (Radarr, Sonarr) — same API
conventions (X-Api-Key header, /api/v3/... routes) for both, differing
only in the entity name (movie vs series) and external ID scheme (TMDB
vs TVDB). Each one, once given at least one indexer (via Prowlarr) and a
download client (qBittorrent, already configured), handles searching,
grabbing, downloading, and importing into the media library completely on
its own — Vault only ever has to make one "add + search now" call.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("vault.arr")


class ArrUnavailableError(Exception):
    """Raised when Radarr/Sonarr cannot be reached, or isn't configured (no API key set)."""


class ArrClient:
    entity: str  # "movie" | "series" — subclasses set this

    def __init__(self, base_url: str, api_key: str | None):
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Api-Key": api_key} if api_key else {},
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._api_key:
            raise ArrUnavailableError(f"{self.entity} manager has no API key configured")
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise ArrUnavailableError(str(exc)) from exc
        response.raise_for_status()
        return response

    async def get_quality_profile_id(self) -> int:
        """Picks the first configured quality profile — set up during the one-time dashboard setup."""
        response = await self._request("GET", "/api/v3/qualityprofile")
        profiles = response.json()
        if not profiles:
            raise ArrUnavailableError("No quality profile configured yet")
        return profiles[0]["id"]

    async def get_root_folder_path(self) -> str:
        """Picks the first configured root folder — should point at the Jellyfin-scanned media path."""
        response = await self._request("GET", "/api/v3/rootfolder")
        folders = response.json()
        if not folders:
            raise ArrUnavailableError("No root folder configured yet")
        return folders[0]["path"]

    async def is_already_added(self, external_id_field: str, external_id: int) -> dict[str, Any] | None:
        response = await self._request("GET", f"/api/v3/{self.entity}", params={external_id_field: external_id})
        results = response.json()
        return results[0] if results else None

    async def trigger_search(self, entity_id: int, command_name: str) -> None:
        await self._request("POST", "/api/v3/command", json={"name": command_name, f"{self.entity}Ids": [entity_id]})

    async def ping(self) -> dict[str, Any]:
        response = await self._request("GET", "/api/v3/system/status")
        return response.json()

    async def get_entity(self, entity_id: int) -> dict[str, Any]:
        response = await self._request("GET", f"/api/v3/{self.entity}/{entity_id}")
        return response.json()
