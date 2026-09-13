from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.db import User
from app.dependencies import get_jellyfin
from app.security import get_current_user
from app.services.jellyfin import JellyfinClient, JellyfinUnavailableError

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/items/{item_id}/image")
async def item_image(
    item_id: str, tag: str | None = None, jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> Response:
    """
    Deliberately unauthenticated (unlike every other endpoint here): an
    <img src> can't attach the Vault JWT the way a fetch() call can, and
    Jellyfin has no published port for the browser to hit directly, so
    this proxies the image through the one backend the browser can always
    reach. Posters aren't sensitive, and the item id alone reveals nothing
    an authenticated user couldn't already see via /library/items.
    """
    try:
        upstream = await jellyfin.get_item_image(item_id, tag)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc
    except httpx.HTTPStatusError as exc:
        # A bad/stale id or an item with no image at all comes back as a
        # plain 404 from Jellyfin — previously this fell through the crack
        # (only JellyfinUnavailableError was caught) and surfaced as an
        # opaque "Internal server error", which is exactly what a broken
        # <img src> shows regardless, but a real 404 is honest about why.
        raise HTTPException(status_code=exc.response.status_code, detail="Image not found") from exc
    return Response(content=upstream.content, media_type=upstream.headers.get("content-type", "image/jpeg"))


@router.get("/views")
async def views(user: User = Depends(get_current_user), jellyfin: JellyfinClient = Depends(get_jellyfin)) -> list:
    try:
        return await jellyfin.get_user_views(user.jellyfin_user_id, user.jellyfin_access_token)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc


@router.get("/items")
async def items(
    parent_id: str | None = None,
    type: str | None = None,  # noqa: A002 - mirrors Jellyfin's query param name
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
    user: User = Depends(get_current_user),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
) -> dict:
    try:
        return await jellyfin.get_items(
            user.jellyfin_user_id,
            user.jellyfin_access_token,
            parent_id=parent_id,
            include_item_types=type,
            search_term=search,
            start_index=(page - 1) * limit,
            limit=limit,
        )
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc


@router.get("/continue-watching")
async def continue_watching(
    user: User = Depends(get_current_user), jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> list:
    return await jellyfin.get_resume_items(user.jellyfin_user_id, user.jellyfin_access_token)


@router.get("/next-up")
async def next_up(
    user: User = Depends(get_current_user), jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> list:
    return await jellyfin.get_next_up(user.jellyfin_user_id, user.jellyfin_access_token)


@router.get("/items/{item_id}")
async def item_detail(
    item_id: str, user: User = Depends(get_current_user), jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> dict:
    try:
        return await jellyfin.get_item(user.jellyfin_user_id, user.jellyfin_access_token, item_id)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc


@router.get("/items/{series_id}/seasons")
async def seasons(
    series_id: str, user: User = Depends(get_current_user), jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> list:
    try:
        return await jellyfin.get_seasons(user.jellyfin_user_id, user.jellyfin_access_token, series_id)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc


@router.get("/items/{series_id}/episodes")
async def episodes(
    series_id: str,
    season_id: str,
    user: User = Depends(get_current_user),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
) -> list:
    try:
        return await jellyfin.get_episodes(user.jellyfin_user_id, user.jellyfin_access_token, series_id, season_id)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc
