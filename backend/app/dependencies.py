from fastapi import Request

from app.services.jellyfin import JellyfinClient
from app.services.qbittorrent import QBittorrentClient
from app.services.tmdb import TMDBClient


def get_qbittorrent(request: Request) -> QBittorrentClient:
    return request.app.state.qbittorrent


def get_jellyfin(request: Request) -> JellyfinClient:
    return request.app.state.jellyfin


def get_tmdb(request: Request) -> TMDBClient:
    return request.app.state.tmdb
