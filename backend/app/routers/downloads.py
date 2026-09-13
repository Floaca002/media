from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlmodel import select

from app.config import Settings, get_settings
from app.db import MediaRequest, get_session
from app.dependencies import get_qbittorrent
from app.schemas import DownloadOut
from app.security import get_current_user
from app.services.qbittorrent import QBittorrentClient, QBittorrentUnavailableError, summarize_torrent

router = APIRouter(prefix="/downloads", tags=["downloads"])


async def _snapshot(qbt: QBittorrentClient, settings: Settings) -> list[DownloadOut]:
    categories = [
        settings.qbittorrent_category_movies,
        settings.qbittorrent_category_tv,
        settings.qbittorrent_category_radarr,
        settings.qbittorrent_category_sonarr,
    ]
    raw: list[dict] = []
    seen_hashes: set[str] = set()
    for category in categories:
        for torrent in await qbt.list_torrents(category=category):
            if torrent["hash"] not in seen_hashes:
                seen_hashes.add(torrent["hash"])
                raw.append(torrent)

    with get_session() as session:
        hash_to_request_id = {
            r.torrent_hash: r.id
            for r in session.exec(select(MediaRequest).where(MediaRequest.torrent_hash.is_not(None))).all()
        }

    out = []
    for torrent in raw:
        summary = summarize_torrent(torrent)
        out.append(
            DownloadOut(
                **{k: v for k, v in summary.items() if k in DownloadOut.model_fields},
                request_id=hash_to_request_id.get(summary["hash"]),
            )
        )
    return out


@router.get("", response_model=list[DownloadOut])
async def list_downloads(
    qbt: QBittorrentClient = Depends(get_qbittorrent),
    settings: Settings = Depends(get_settings),
    _=Depends(get_current_user),
) -> list[DownloadOut]:
    try:
        return await _snapshot(qbt, settings)
    except QBittorrentUnavailableError as exc:
        raise HTTPException(status_code=502, detail="qBittorrent unavailable") from exc


@router.post("/{torrent_hash}/pause")
async def pause(torrent_hash: str, qbt: QBittorrentClient = Depends(get_qbittorrent), _=Depends(get_current_user)) -> dict:
    await qbt.pause(torrent_hash)
    return {"ok": True}


@router.post("/{torrent_hash}/resume")
async def resume(torrent_hash: str, qbt: QBittorrentClient = Depends(get_qbittorrent), _=Depends(get_current_user)) -> dict:
    await qbt.resume(torrent_hash)
    return {"ok": True}


@router.delete("/{torrent_hash}")
async def delete(
    torrent_hash: str,
    delete_files: bool = False,
    qbt: QBittorrentClient = Depends(get_qbittorrent),
    _=Depends(get_current_user),
) -> dict:
    await qbt.delete(torrent_hash, delete_files=delete_files)

    # Deleting a torrent here (vs. cancelling via DELETE /requests/{id})
    # left the associated Request stuck showing DOWNLOADING/SEARCHING
    # forever, since nothing else ever clears it — the movie's page then
    # permanently refuses new download attempts. Clean it up here too so
    # both delete paths leave the title back in a requestable state.
    with get_session() as session:
        request = session.exec(
            select(MediaRequest).where(MediaRequest.torrent_hash == torrent_hash)
        ).first()
        if request is not None:
            session.delete(request)
            session.commit()

    return {"ok": True}


@router.websocket("/stream")
async def downloads_stream(websocket: WebSocket) -> None:
    """
    Pushes the same payload as GET /downloads every 2s so the frontend
    doesn't need to poll. Auth: pass the Vault JWT as a 'token' query param
    since browsers can't set Authorization headers on WebSocket handshakes.
    """
    settings: Settings = get_settings()
    token = websocket.query_params.get("token")
    try:
        if not token:
            raise JWTError("missing token")
        jwt.decode(token, settings.vault_jwt_secret, algorithms=["HS256"])
    except JWTError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    qbt: QBittorrentClient = websocket.app.state.qbittorrent
    try:
        while True:
            try:
                snapshot = await _snapshot(qbt, settings)
                await websocket.send_json([d.model_dump() for d in snapshot])
            except QBittorrentUnavailableError:
                await websocket.send_json({"error": "qBittorrent unavailable"})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
