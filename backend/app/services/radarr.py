from __future__ import annotations

from typing import Any

from app.services.arr import ArrClient


class RadarrClient(ArrClient):
    entity = "movie"

    async def lookup_by_tmdb_id(self, tmdb_id: int) -> dict[str, Any]:
        """GET /api/v3/movie/lookup/tmdb — metadata for a title Radarr hasn't added yet."""
        response = await self._request("GET", "/api/v3/movie/lookup/tmdb", params={"tmdbId": tmdb_id})
        return response.json()

    async def add_and_search(self, tmdb_id: int) -> dict[str, Any]:
        """
        Adds the movie (looked up fresh by TMDB id, since Radarr needs its
        own metadata snapshot to create the entry) with monitored=True and
        an immediate search — this is the one call that gets qBittorrent a
        release with zero further input, provided at least one indexer is
        configured in Prowlarr and synced to Radarr.

        If it's already in Radarr's database (e.g. a prior request that got
        cleared on Vault's side but never removed from Radarr — reproduced
        live), re-adding hits a 400, unlike qBittorrent's friendlier 409 for
        the equivalent case. Check first, and just trigger a fresh search on
        the existing entry instead.
        """
        existing = await self.is_already_added("tmdbId", tmdb_id)
        if existing is not None:
            await self.trigger_search(existing["id"], "MoviesSearch")
            return existing

        lookup = await self.lookup_by_tmdb_id(tmdb_id)
        quality_profile_id = await self.get_quality_profile_id()
        root_folder = await self.get_root_folder_path()

        response = await self._request(
            "POST",
            "/api/v3/movie",
            json={
                "tmdbId": lookup["tmdbId"],
                "title": lookup["title"],
                "year": lookup.get("year"),
                "titleSlug": lookup.get("titleSlug"),
                "images": lookup.get("images", []),
                "qualityProfileId": quality_profile_id,
                "rootFolderPath": root_folder,
                "monitored": True,
                "addOptions": {"searchForMovie": True},
            },
        )
        return response.json()
