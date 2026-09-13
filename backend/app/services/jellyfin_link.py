"""
Backfills MediaRequest.jellyfin_item_id for requests that are AVAILABLE
but don't have one yet — the organizer and the Radarr/Sonarr sync pass
both mark a request AVAILABLE the moment the file lands, but the actual
Jellyfin library scan (and Radarr/Sonarr's own import, in the automatic
flow) can take a little longer to finish, so the matching item may not
exist in Jellyfin's database on that exact tick yet. Runs as its own
periodic pass and just keeps retrying until a match shows up.
"""
from __future__ import annotations

import logging

from sqlmodel import select

from app.db import MediaRequest, RequestStatus, get_session
from app.services.jellyfin import JellyfinClient

logger = logging.getLogger("vault.jellyfin_link")


async def run_jellyfin_link_pass(jellyfin: JellyfinClient) -> int:
    linked = 0
    with get_session() as session:
        pending = session.exec(
            select(MediaRequest).where(
                MediaRequest.status == RequestStatus.AVAILABLE,
                MediaRequest.jellyfin_item_id.is_(None),
            )
        ).all()

        for request in pending:
            item_id = await jellyfin.find_item_by_tmdb_id(request.media_type, request.tmdb_id)
            if item_id is not None:
                request.jellyfin_item_id = item_id
                session.add(request)
                session.commit()
                linked += 1
                logger.info("Request %s linked to Jellyfin item %s", request.id, item_id)

    return linked
