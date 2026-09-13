"""
Periodic status check for requests created via the automatic Radarr/Sonarr
flow (services/arr.py). Those never get a torrent_hash of ours to track —
Radarr/Sonarr own the whole download-and-import lifecycle themselves — so
this is the only thing that ever flips such a request out of SEARCHING.
"""
from __future__ import annotations

import logging

from sqlmodel import select

from app.db import MediaRequest, RequestStatus, get_session
from app.services.arr import ArrUnavailableError
from app.services.jellyfin import JellyfinClient
from app.services.radarr import RadarrClient
from app.services.sonarr import SonarrClient

logger = logging.getLogger("vault.arr_sync")


def _has_content(media_type: str, entity: dict) -> bool:
    if media_type == "movie":
        return bool(entity.get("hasFile"))
    stats = entity.get("statistics") or {}
    return stats.get("episodeFileCount", 0) > 0


async def run_arr_sync_pass(radarr: RadarrClient, sonarr: SonarrClient, jellyfin: JellyfinClient) -> int:
    updated = 0
    with get_session() as session:
        pending = session.exec(
            select(MediaRequest).where(
                MediaRequest.arr_id.is_not(None),
                MediaRequest.status.in_([RequestStatus.SEARCHING, RequestStatus.DOWNLOADING]),
            )
        ).all()

        for request in pending:
            client = radarr if request.media_type == "movie" else sonarr
            if not client.configured:
                continue
            try:
                entity = await client.get_entity(request.arr_id)
            except ArrUnavailableError:
                logger.warning("Could not reach %s for request %s", request.media_type, request.id)
                continue

            if _has_content(request.media_type, entity):
                request.status = RequestStatus.AVAILABLE
                session.add(request)
                session.commit()
                updated += 1
                logger.info("Request %s (%s) now available via Radarr/Sonarr", request.id, request.title)

        if updated:
            await jellyfin.refresh_library()

    return updated
