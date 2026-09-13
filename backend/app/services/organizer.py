"""
Auto-organizer pipeline.

Runs on a schedule (see app/main.py APScheduler wiring). For every
completed torrent in one of Vault's managed categories, hardlinks the
finished file(s) into the Jellyfin-scanned media tree using Jellyfin's
expected naming convention, triggers a Jellyfin library scan, and flips
the matching MediaRequest to AVAILABLE.

Hardlinking (not moving) lets qBittorrent keep seeding from
DOWNLOADS_COMPLETE_PATH while Jellyfin serves the same bytes from
MEDIA_MOVIES_PATH/MEDIA_TV_PATH — both must live on the same filesystem
for os.link to succeed; falls back to a copy if they don't.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from guessit import guessit
from sqlmodel import select

from app.config import Settings
from app.db import MediaRequest, RequestStatus, get_session
from app.services.jellyfin import JellyfinClient
from app.services.qbittorrent import QBittorrentClient, summarize_torrent

logger = logging.getLogger("vault.organizer")

_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v"}
_SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*]')


def _sanitize(name: str) -> str:
    return _SAFE_NAME_RE.sub("", name).strip()


def _largest_video_file(content_path: str) -> Path | None:
    path = Path(content_path)
    if path.is_file():
        return path if path.suffix.lower() in _VIDEO_EXTENSIONS else None
    if not path.is_dir():
        return None
    candidates = [
        p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in _VIDEO_EXTENSIONS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def _link_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    try:
        os.link(src, dest)
    except OSError:
        logger.warning("Hardlink failed (%s -> %s), falling back to copy", src, dest)
        shutil.copy2(src, dest)


def _destination_for(settings: Settings, request: MediaRequest, src: Path) -> Path:
    guess = guessit(src.name)
    ext = src.suffix

    if request.media_type == "movie":
        year = guess.get("year", "")
        folder_name = _sanitize(f"{request.title} ({year})" if year else request.title)
        file_name = _sanitize(f"{request.title} ({year}){ext}" if year else f"{request.title}{ext}")
        return Path(settings.media_movies_path) / folder_name / file_name

    season = request.season or guess.get("season", 1)
    episode = request.episode or guess.get("episode", 1)
    series_folder = _sanitize(request.title)
    season_folder = f"Season {int(season):02d}"
    file_name = _sanitize(f"{request.title} - s{int(season):02d}e{int(episode):02d}{ext}")
    return Path(settings.media_tv_path) / series_folder / season_folder / file_name


async def run_organizer_pass(
    settings: Settings, qbt: QBittorrentClient, jellyfin: JellyfinClient
) -> int:
    """
    One organizer tick. Returns the number of requests moved to AVAILABLE.
    Safe to call repeatedly/concurrently-idempotent — already-linked
    destinations are skipped, and requests already AVAILABLE are excluded
    from the query.
    """
    organized = 0
    with get_session() as session:
        pending = session.exec(
            select(MediaRequest).where(
                MediaRequest.status.in_(
                    [RequestStatus.DOWNLOADING, RequestStatus.ORGANIZING]
                ),
                MediaRequest.torrent_hash.is_not(None),
            )
        ).all()

        if not pending:
            return 0

        for category in (settings.qbittorrent_category_movies, settings.qbittorrent_category_tv):
            torrents = {t["hash"]: t for t in await qbt.list_torrents(category=category)}

            for request in pending:
                torrent = torrents.get(request.torrent_hash)
                if not torrent:
                    continue

                summary = summarize_torrent(torrent)
                is_complete = summary["progress"] >= 100.0 and summary["state"] in (
                    "uploading",
                    "stalledUP",
                    "queuedUP",
                    "forcedUP",
                    "pausedUP",
                )
                if not is_complete:
                    continue

                content_path = summary["content_path"] or summary["save_path"]
                video_file = _largest_video_file(content_path)
                if video_file is None:
                    logger.warning(
                        "Request %s: torrent %s complete but no video file found under %s",
                        request.id, request.torrent_hash, content_path,
                    )
                    continue

                dest = _destination_for(settings, request, video_file)
                try:
                    _link_or_copy(video_file, dest)
                except OSError:
                    logger.exception("Failed to organize request %s", request.id)
                    request.status = RequestStatus.FAILED
                    session.add(request)
                    session.commit()
                    continue

                request.status = RequestStatus.AVAILABLE
                session.add(request)
                session.commit()
                organized += 1
                logger.info("Request %s organized -> %s", request.id, dest)

        if organized:
            await jellyfin.refresh_library()

    return organized
