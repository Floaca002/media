from __future__ import annotations

from typing import Any

from app.services.arr import ArrClient


class SonarrClient(ArrClient):
    entity = "series"

    async def lookup_by_tvdb_id(self, tvdb_id: int) -> dict[str, Any]:
        """GET /api/v3/series/lookup?term=tvdb:{id} — Sonarr keys shows by TVDB id, not TMDB."""
        response = await self._request("GET", "/api/v3/series/lookup", params={"term": f"tvdb:{tvdb_id}"})
        results = response.json()
        if not results:
            raise ValueError(f"Sonarr found no series for tvdbId={tvdb_id}")
        return results[0]

    async def add_and_search(self, tvdb_id: int) -> dict[str, Any]:
        """
        Adds the series (looked up fresh by TVDB id) with monitored=True
        and an immediate search for every episode — the TV-show equivalent
        of RadarrClient.add_and_search.
        """
        lookup = await self.lookup_by_tvdb_id(tvdb_id)
        quality_profile_id = await self.get_quality_profile_id()
        root_folder = await self.get_root_folder_path()

        response = await self._request(
            "POST",
            "/api/v3/series",
            json={
                "tvdbId": lookup["tvdbId"],
                "title": lookup["title"],
                "titleSlug": lookup.get("titleSlug"),
                "images": lookup.get("images", []),
                "qualityProfileId": quality_profile_id,
                "rootFolderPath": root_folder,
                "seasonFolder": True,
                "monitored": True,
                "addOptions": {"searchForMissingEpisodes": True, "monitor": "all"},
            },
        )
        return response.json()
