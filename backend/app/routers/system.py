from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.dependencies import get_jellyfin, get_qbittorrent, get_radarr, get_sonarr, get_tmdb
from app.services.arr import ArrClient
from app.services.jellyfin import JellyfinClient
from app.services.qbittorrent import QBittorrentClient
from app.services.tmdb import TMDBClient

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health(
    qbt: QBittorrentClient = Depends(get_qbittorrent),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
    tmdb: TMDBClient = Depends(get_tmdb),
    radarr: ArrClient = Depends(get_radarr),
    sonarr: ArrClient = Depends(get_sonarr),
) -> dict:
    async def check(coro) -> str:
        try:
            await coro
            return "up"
        except Exception:  # noqa: BLE001 - health check must never raise
            return "down"

    async def check_arr(client: ArrClient) -> str:
        if not client.configured:
            return "not_configured"
        return await check(client.ping())

    qbt_status, jellyfin_status, tmdb_status, radarr_status, sonarr_status = await asyncio.gather(
        check(qbt.list_torrents()),
        check(jellyfin.ping()),
        check(tmdb.trending()),
        check_arr(radarr),
        check_arr(sonarr),
    )
    return {
        "qbittorrent": qbt_status,
        "jellyfin": jellyfin_status,
        "tmdb": tmdb_status,
        "radarr": radarr_status,
        "sonarr": sonarr_status,
    }
