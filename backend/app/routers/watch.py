from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.db import User
from app.dependencies import get_jellyfin
from app.schemas import PlaybackInfoOut, WatchProgressBody
from app.security import get_current_user
from app.services.jellyfin import JellyfinClient, JellyfinUnavailableError, new_play_session_id

router = APIRouter(tags=["watch"])


@router.get("/library/items/{item_id}/playback", response_model=PlaybackInfoOut)
async def get_playback_info(
    item_id: str,
    user: User = Depends(get_current_user),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
) -> PlaybackInfoOut:
    play_session_id = new_play_session_id()
    try:
        info = await jellyfin.get_playback_info(
            user.jellyfin_user_id, user.jellyfin_access_token, item_id, play_session_id
        )
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc

    media_sources = info.get("MediaSources") or []
    if not media_sources:
        raise HTTPException(status_code=404, detail="No playable media source for this item")
    media_source_id = media_sources[0]["Id"]

    hls_url = jellyfin.build_hls_url(
        item_id,
        media_source_id=media_source_id,
        play_session_id=play_session_id,
        user_token=user.jellyfin_access_token,
    )

    start_ticks = media_sources[0].get("StartPosition", 0) or 0

    return PlaybackInfoOut(
        hls_url=hls_url,
        play_session_id=play_session_id,
        media_source_id=media_source_id,
        start_position_ticks=start_ticks,
    )


@router.post("/watch/progress")
async def report_progress(
    body: WatchProgressBody,
    user: User = Depends(get_current_user),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
) -> dict:
    try:
        if body.event == "start":
            await jellyfin.report_playback_start(
                user.jellyfin_access_token, body.item_id, body.play_session_id, body.media_source_id
            )
        elif body.event == "stop":
            await jellyfin.report_playback_stopped(
                user.jellyfin_access_token, body.item_id, body.play_session_id, body.position_ticks
            )
        else:
            await jellyfin.report_playback_progress(
                user.jellyfin_access_token,
                body.item_id,
                body.play_session_id,
                body.position_ticks,
                is_paused=body.is_paused,
            )
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc
    return {"ok": True}
