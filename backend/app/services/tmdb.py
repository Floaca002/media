"""TMDB (The Movie Database) client — metadata, search, trending, trailers."""
from __future__ import annotations

from typing import Any

import httpx
from cachetools import TTLCache

from app.config import Settings

_TTL_SECONDS = 60 * 30  # posters/trending don't change fast; cut TMDB traffic


class TMDBClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url="https://api.themoviedb.org/3",
            headers={
                "Authorization": f"Bearer {settings.tmdb_api_read_token}",
                "accept": "application/json",
            },
            timeout=10.0,
        )
        self._cache: TTLCache = TTLCache(maxsize=512, ttl=_TTL_SECONDS)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        cache_key = (path, tuple(sorted((params or {}).items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        response = await self._client.get(path, params=params or {})
        response.raise_for_status()
        data = response.json()
        self._cache[cache_key] = data
        return data

    async def trending(self, media_type: str = "all", window: str = "week") -> dict[str, Any]:
        return await self._get(f"/trending/{media_type}/{window}")

    async def popular(self, media_type: str, page: int = 1) -> dict[str, Any]:
        return await self._get(f"/{media_type}/popular", {"page": page})

    async def search_multi(self, query: str, page: int = 1) -> dict[str, Any]:
        return await self._get("/search/multi", {"query": query, "page": page, "include_adult": "false"})

    async def details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        return await self._get(
            f"/{media_type}/{tmdb_id}",
            {"append_to_response": "credits,videos,similar"},
        )

    def poster_url(self, path: str | None, size: str = "w500") -> str | None:
        if not path:
            return None
        return f"{self._settings.tmdb_image_base}/{size}{path}"

    def backdrop_url(self, path: str | None, size: str = "original") -> str | None:
        if not path:
            return None
        return f"{self._settings.tmdb_image_base}/{size}{path}"

    @staticmethod
    def trailer_key(details: dict[str, Any]) -> str | None:
        """Pick the best YouTube trailer key from a details() 'videos' block."""
        videos = details.get("videos", {}).get("results", [])
        for v in videos:
            if v.get("site") == "YouTube" and v.get("type") == "Trailer" and v.get("official"):
                return v.get("key")
        for v in videos:
            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                return v.get("key")
        return None
