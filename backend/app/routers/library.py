from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.db import User
from app.dependencies import get_jellyfin
from app.security import get_current_user
from app.services.jellyfin import JellyfinClient, JellyfinUnavailableError

router = APIRouter(prefix="/library", tags=["library"])


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
