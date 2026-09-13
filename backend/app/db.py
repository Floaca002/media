from __future__ import annotations

import datetime as dt
from enum import Enum

from sqlalchemy import inspect, text
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
    # Radarr/Sonarr's own internal movie/series id, for requests made
    # through the automatic-search flow (services/arr.py) rather than a
    # manually-pasted magnet — used to poll for completion, since these
    # never get a torrent_hash of ours to track (Radarr/Sonarr manage the
    # download and library import entirely on their own).
    arr_id: int | None = Field(default=None)
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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """
    No migration framework for a single-user app — create_all only creates
    missing *tables*, never alters existing ones, so a model change like
    adding MediaRequest.arr_id would otherwise crash every query against
    an already-existing vault.db with "no such column". Add whatever the
    model declares that the on-disk table doesn't have yet.
    """
    inspector = inspect(_engine)
    table_name = MediaRequest.__tablename__
    if table_name not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    with _engine.begin() as conn:
        for column in MediaRequest.__table__.columns:
            if column.name not in existing:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.type}"))


def get_session() -> Session:
    return Session(_engine)
