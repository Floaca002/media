from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    jellyfin_user_id: str


class RequestPasswordResetBody(BaseModel):
    username: str


class RequestPasswordResetResponse(BaseModel):
    pin_file: str | None = None


class ResetPasswordBody(BaseModel):
    username: str
    pin: str
    pin_file: str
    new_password: str


class CreateRequestBody(BaseModel):
    tmdb_id: int
    media_type: str  # "movie" | "tv"
    title: str
    # Omit to go through Radarr/Sonarr's automatic search + grab (the
    # default "Download" button flow); provide a magnet to add it to
    # qBittorrent directly instead, bypassing indexer search entirely.
    magnet: str | None = None
    season: int | None = None
    episode: int | None = None


class RequestOut(BaseModel):
    id: int
    tmdb_id: int
    media_type: str
    title: str
    status: str
    torrent_hash: str | None
    jellyfin_item_id: str | None


class DownloadOut(BaseModel):
    hash: str
    name: str
    category: str | None
    progress: float
    download_speed_bps: int
    upload_speed_bps: int
    eta_seconds: int | None
    state: str
    size_bytes: int
    request_id: int | None = None


class PlaybackInfoOut(BaseModel):
    hls_url: str
    play_session_id: str
    media_source_id: str
    start_position_ticks: int = 0


class WatchProgressBody(BaseModel):
    item_id: str
    play_session_id: str
    media_source_id: str
    position_ticks: int
    is_paused: bool = False
    event: str = "progress"  # start | progress | stop
