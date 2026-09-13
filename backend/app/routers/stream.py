from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.db import User
from app.dependencies import get_jellyfin
from app.security import get_current_user
from app.services.jellyfin import JellyfinClient, JellyfinUnavailableError

router = APIRouter(prefix="/stream", tags=["stream"])

# Matches any non-comment, non-blank line in an HLS playlist — i.e. a URI
# reference to a variant playlist or a media segment.
_MANIFEST_URI_RE = re.compile(r"^(?!#)(\S+)$", re.MULTILINE)


def _is_manifest(content_type: str, path: str) -> bool:
    return "mpegurl" in content_type.lower() or path.endswith(".m3u8")


def _rewrite_manifest(text: str, item_id: str) -> str:
    """
    Rewrites every URI line in an HLS playlist so the player's subsequent
    requests for variant playlists and segments come back through this
    same proxy — Jellyfin's own (relative or absolute) URLs point at an
    address the browser can never reach directly in this deployment.
    """

    def replace(match: re.Match[str]) -> str:
        uri = match.group(1)
        if uri.startswith("http://") or uri.startswith("https://"):
            return uri  # not expected from Jellyfin's own playlists; leave untouched
        return f"/api/stream/{item_id}/{uri}"

    return _MANIFEST_URI_RE.sub(replace, text)


@router.get("/{item_id}/master.m3u8")
async def stream_master(
    item_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
) -> Response:
    try:
        upstream = await jellyfin.stream_passthrough(
            f"/Videos/{item_id}/master.m3u8",
            token=user.jellyfin_access_token,
            params=dict(request.query_params),
        )
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc

    return Response(
        content=_rewrite_manifest(upstream.text, item_id), media_type="application/vnd.apple.mpegurl"
    )


@router.get("/{item_id}/{sub_path:path}")
async def stream_resource(
    item_id: str,
    sub_path: str,
    request: Request,
    user: User = Depends(get_current_user),
    jellyfin: JellyfinClient = Depends(get_jellyfin),
) -> Response:
    """Proxies variant playlists and media segments referenced by the rewritten master playlist."""
    try:
        upstream = await jellyfin.stream_passthrough(
            f"/Videos/{item_id}/{sub_path}",
            token=user.jellyfin_access_token,
            params=dict(request.query_params),
        )
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    if _is_manifest(content_type, sub_path):
        return Response(content=_rewrite_manifest(upstream.text, item_id), media_type=content_type)
    return Response(content=upstream.content, media_type=content_type)
