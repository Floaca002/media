"""TMDB (The Movie Database) client — metadata, search, trending, trailers."""
from __future__ import annotations

from datetime import date, timedelta
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

        try:
            response = await self._client.get(path, params=params or {})
        except httpx.TransportError:
            # A single connect/read timeout to TMDB shouldn't fail an entire
            # Discover page load when a retry a moment later usually succeeds.
            response = await self._client.get(path, params=params or {})
        response.raise_for_status()
        data = response.json()
        self._cache[cache_key] = data
        return data

    async def trending(self, media_type: str = "all", window: str = "week") -> dict[str, Any]:
        return await self._get(f"/trending/{media_type}/{window}")

    async def popular(self, media_type: str, page: int = 1) -> dict[str, Any]:
        """
        TMDB's own /popular endpoint is dominated by long-running Asian daily
        dramas and variety shows — they rack up huge view/vote counts in
        TMDB's database despite not being what most people mean by "popular".
        /discover with an English-original-language filter is the standard
        workaround and matches what a Netflix-style "Popular" row expects.
        """
        return await self._get(
            f"/discover/{media_type}",
            {"sort_by": "popularity.desc", "with_original_language": "en", "page": page},
        )

    async def top_rated(self, media_type: str, page: int = 1) -> dict[str, Any]:
        return await self._get(
            f"/discover/{media_type}",
            {
                "sort_by": "vote_average.desc",
                "vote_count.gte": 200,
                "with_original_language": "en",
                "page": page,
            },
        )

    async def now_playing(self, page: int = 1) -> dict[str, Any]:
        """Movies only — TMDB has no TV equivalent of "currently in theaters"."""
        return await self._get("/movie/now_playing", {"page": page, "region": "US"})

    async def on_the_air(self, page: int = 1) -> dict[str, Any]:
        """
        TV only — shows with an episode airing in the next 7 days. TMDB's own
        /tv/on_the_air has no language filter and suffers the same skew as
        /popular, so this reproduces its "airing soon" semantics via
        /discover instead, with the same English-original-language filter.
        """
        today = date.today()
        return await self._get(
            "/discover/tv",
            {
                "sort_by": "popularity.desc",
                "with_original_language": "en",
                "air_date.gte": today.isoformat(),
                "air_date.lte": (today + timedelta(days=7)).isoformat(),
                "page": page,
            },
        )

    async def search_multi(self, query: str, page: int = 1) -> dict[str, Any]:
        return await self._get("/search/multi", {"query": query, "page": page, "include_adult": "false"})

    async def details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        return await self._get(
            f"/{media_type}/{tmdb_id}",
            {"append_to_response": "credits,videos,similar"},
        )

    async def get_tv_tvdb_id(self, tmdb_id: int) -> int | None:
        """
        Sonarr identifies shows by TVDB id, not TMDB id — TMDB exposes the
        mapping via its external_ids endpoint rather than in the regular
        details response.
        """
        data = await self._get(f"/tv/{tmdb_id}/external_ids")
        return data.get("tvdb_id")

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
