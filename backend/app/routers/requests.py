from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.config import Settings, get_settings
from app.db import MediaRequest, RequestStatus, User, get_session
from app.dependencies import get_qbittorrent, get_radarr, get_sonarr, get_tmdb
from app.schemas import CreateRequestBody, RequestOut
from app.security import get_current_user
from app.services.arr import ArrUnavailableError
from app.services.qbittorrent import QBittorrentClient, QBittorrentUnavailableError
from app.services.radarr import RadarrClient
from app.services.sonarr import SonarrClient
from app.services.tmdb import TMDBClient

router = APIRouter(prefix="/requests", tags=["requests"])

_BTIH_RE = re.compile(r"urn:btih:([a-zA-Z0-9]+)")


def _extract_info_hash(magnet_uri: str) -> str | None:
    match = _BTIH_RE.search(magnet_uri)
    return match.group(1).lower() if match else None


async def _create_via_magnet(
    body: CreateRequestBody, user: User, qbt: QBittorrentClient, settings: Settings
) -> MediaRequest:
    category = (
        settings.qbittorrent_category_movies if body.media_type == "movie" else settings.qbittorrent_category_tv
    )
    try:
        await qbt.add_magnet(body.magnet, category=category)
    except QBittorrentUnavailableError as exc:
        raise HTTPException(status_code=502, detail="qBittorrent unavailable") from exc

    # qBittorrent's /torrents/add doesn't echo back the hash it assigned,
    # but a v1 (BTIH) magnet link's info-hash *is* the torrent hash
    # qBittorrent will use, so we derive it directly rather than
    # re-querying /torrents/info to confirm it — that re-query was racy in
    # practice (qBittorrent hadn't registered the torrent yet immediately
    # after /torrents/add returned), which left the request stuck in
    # SEARCHING with no torrent_hash at all, forever.
    torrent_hash = _extract_info_hash(body.magnet)

    return MediaRequest(
        tmdb_id=body.tmdb_id,
        media_type=body.media_type,
        title=body.title,
        season=body.season,
        episode=body.episode,
        status=RequestStatus.DOWNLOADING if torrent_hash else RequestStatus.SEARCHING,
        torrent_hash=torrent_hash,
        requested_by_user_id=user.id,
    )


async def _create_via_arr(
    body: CreateRequestBody, user: User, radarr: RadarrClient, sonarr: SonarrClient, tmdb: TMDBClient
) -> MediaRequest:
    """
    The default "Download" flow: no magnet needed at all. Radarr/Sonarr
    search every configured indexer themselves, grab the best release per
    their quality profile, hand it to qBittorrent, and later import the
    finished file into the Jellyfin-scanned library on their own — this
    function's only job is telling one of them to start.
    """
    if body.media_type == "movie":
        if not radarr.configured:
            raise HTTPException(
                status_code=503,
                detail="Radarr isn't configured yet (set RADARR_API_KEY) — paste a magnet link instead, "
                "or finish the Radarr setup first.",
            )
        try:
            added = await radarr.add_and_search(body.tmdb_id)
        except ArrUnavailableError as exc:
            raise HTTPException(status_code=502, detail=f"Radarr unavailable: {exc}") from exc
        return MediaRequest(
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
            title=body.title,
            status=RequestStatus.SEARCHING,
            arr_id=added["id"],
            requested_by_user_id=user.id,
        )

    if not sonarr.configured:
        raise HTTPException(
            status_code=503,
            detail="Sonarr isn't configured yet (set SONARR_API_KEY) — paste a magnet link instead, "
            "or finish the Sonarr setup first.",
        )
    tvdb_id = await tmdb.get_tv_tvdb_id(body.tmdb_id)
    if tvdb_id is None:
        raise HTTPException(status_code=404, detail="TMDB has no TVDB mapping for this show")
    try:
        added = await sonarr.add_and_search(tvdb_id)
    except ArrUnavailableError as exc:
        raise HTTPException(status_code=502, detail=f"Sonarr unavailable: {exc}") from exc
    return MediaRequest(
        tmdb_id=body.tmdb_id,
        media_type=body.media_type,
        title=body.title,
        status=RequestStatus.SEARCHING,
        arr_id=added["id"],
        requested_by_user_id=user.id,
    )


@router.post("", response_model=RequestOut)
async def create_request(
    body: CreateRequestBody,
    user: User = Depends(get_current_user),
    qbt: QBittorrentClient = Depends(get_qbittorrent),
    radarr: RadarrClient = Depends(get_radarr),
    sonarr: SonarrClient = Depends(get_sonarr),
    tmdb: TMDBClient = Depends(get_tmdb),
    settings: Settings = Depends(get_settings),
) -> RequestOut:
    with get_session() as session:
        existing = session.exec(
            select(MediaRequest).where(
                MediaRequest.tmdb_id == body.tmdb_id,
                MediaRequest.media_type == body.media_type,
                MediaRequest.status != RequestStatus.FAILED,
            )
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="This title has already been requested")

        request = (
            await _create_via_magnet(body, user, qbt, settings)
            if body.magnet
            else await _create_via_arr(body, user, radarr, sonarr, tmdb)
        )
        session.add(request)
        session.commit()
        session.refresh(request)
        return RequestOut(
            id=request.id,
            tmdb_id=request.tmdb_id,
            media_type=request.media_type,
            title=request.title,
            status=request.status,
            torrent_hash=request.torrent_hash,
            jellyfin_item_id=request.jellyfin_item_id,
        )


@router.get("", response_model=list[RequestOut])
async def list_requests(
    status_filter: str | None = None, _: User = Depends(get_current_user)
) -> list[RequestOut]:
    with get_session() as session:
        query = select(MediaRequest)
        if status_filter:
            query = query.where(MediaRequest.status == status_filter)
        rows = session.exec(query.order_by(MediaRequest.created_at.desc())).all()
        return [
            RequestOut(
                id=r.id,
                tmdb_id=r.tmdb_id,
                media_type=r.media_type,
                title=r.title,
                status=r.status,
                torrent_hash=r.torrent_hash,
                jellyfin_item_id=r.jellyfin_item_id,
            )
            for r in rows
        ]


@router.delete("/{request_id}")
async def delete_request(
    request_id: int,
    qbt: QBittorrentClient = Depends(get_qbittorrent),
    _: User = Depends(get_current_user),
) -> dict:
    with get_session() as session:
        request = session.get(MediaRequest, request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found")
        if request.torrent_hash:
            await qbt.delete(request.torrent_hash, delete_files=True)
        session.delete(request)
        session.commit()
    return {"ok": True}
