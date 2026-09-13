from __future__ import annotations

import datetime as dt
from enum import Enum

from sqlmodel import Field, Session, SQLModel, create_engine

from app.config import get_settings


class RequestStatus(str, Enum):
    SEARCHING = "SEARCHING"
    DOWNLOADING = "DOWNLOADING"
    ORGANIZING = "ORGANIZING"
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"


class MediaRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tmdb_id: int = Field(index=True)
    media_type: str  # "movie" | "tv"
    title: str
    season: int | None = None
    episode: int | None = None
    status: RequestStatus = RequestStatus.SEARCHING
    torrent_hash: str | None = Field(default=None, index=True)
    jellyfin_item_id: str | None = Field(default=None, index=True)
    requested_by_user_id: int | None = Field(default=None, foreign_key="user.id")
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    jellyfin_user_id: str
    jellyfin_access_token: str
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


_engine = create_engine(get_settings().vault_database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(_engine)


def get_session() -> Session:
    return Session(_engine)
