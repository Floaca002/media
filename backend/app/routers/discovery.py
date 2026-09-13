from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import select

from app.db import MediaRequest, get_session
from app.dependencies import get_tmdb
from app.security import get_current_user
from app.services.tmdb import TMDBClient

router = APIRouter(prefix="/discover", tags=["discovery"])


def _decorate_images(tmdb: TMDBClient, item: dict) -> dict:
    item = dict(item)
    item["poster_url"] = tmdb.poster_url(item.get("poster_path"))
    item["backdrop_url"] = tmdb.backdrop_url(item.get("backdrop_path"))
    return item


@router.get("/trending", dependencies=[Depends(get_current_user)])
async def trending(
    window: str = "week", media_type: str = "all", tmdb: TMDBClient = Depends(get_tmdb)
) -> dict:
    data = await tmdb.trending(media_type=media_type, window=window)
    data["results"] = [_decorate_images(tmdb, r) for r in data.get("results", [])]
    return data


@router.get("/popular", dependencies=[Depends(get_current_user)])
async def popular(
    media_type: str = "movie", page: int = 1, tmdb: TMDBClient = Depends(get_tmdb)
) -> dict:
    data = await tmdb.popular(media_type, page=page)
    data["results"] = [_decorate_images(tmdb, r) for r in data.get("results", [])]
    return data


@router.get("/search", dependencies=[Depends(get_current_user)])
async def search(q: str, page: int = 1, tmdb: TMDBClient = Depends(get_tmdb)) -> dict:
    data = await tmdb.search_multi(q, page=page)
    data["results"] = [
        _decorate_images(tmdb, r) for r in data.get("results", []) if r.get("media_type") != "person"
    ]
    return data


@router.get("/{media_type}/{tmdb_id}", dependencies=[Depends(get_current_user)])
async def details(media_type: str, tmdb_id: int, tmdb: TMDBClient = Depends(get_tmdb)) -> dict:
    data = await tmdb.details(media_type, tmdb_id)
    data["poster_url"] = tmdb.poster_url(data.get("poster_path"))
    data["backdrop_url"] = tmdb.backdrop_url(data.get("backdrop_path"))
    data["trailer_key"] = tmdb.trailer_key(data)
    data["cast"] = (data.get("credits", {}).get("cast") or [])[:12]
    data["similar"] = [_decorate_images(tmdb, r) for r in data.get("similar", {}).get("results", [])[:12]]
    return data


@router.get("/{media_type}/{tmdb_id}/availability", dependencies=[Depends(get_current_user)])
async def availability(media_type: str, tmdb_id: int) -> dict:
    with get_session() as session:
        req = session.exec(
            select(MediaRequest).where(
                MediaRequest.tmdb_id == tmdb_id, MediaRequest.media_type == media_type
            )
        ).first()
        if req is None:
            return {"status": "NOT_REQUESTED", "jellyfin_item_id": None}
        return {"status": req.status, "jellyfin_item_id": req.jellyfin_item_id, "request_id": req.id}
