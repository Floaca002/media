from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import auth, discovery, downloads, library, requests, stream, system, watch
from app.services.arr_sync import run_arr_sync_pass
from app.services.jellyfin import JellyfinClient
from app.services.organizer import run_organizer_pass
from app.services.qbittorrent import QBittorrentClient
from app.services.radarr import RadarrClient
from app.services.sonarr import SonarrClient
from app.services.tmdb import TMDBClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vault")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()

    app.state.qbittorrent = QBittorrentClient(settings)
    app.state.jellyfin = JellyfinClient(settings)
    app.state.tmdb = TMDBClient(settings)
    app.state.radarr = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    app.state.sonarr = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)

    for category in (
        settings.qbittorrent_category_movies,
        settings.qbittorrent_category_tv,
        settings.qbittorrent_category_radarr,
        settings.qbittorrent_category_sonarr,
    ):
        try:
            await app.state.qbittorrent.ensure_category_save_path(category, settings.downloads_save_path)
        except Exception:  # noqa: BLE001 - qBittorrent being briefly unreachable shouldn't block startup
            logger.exception("Could not pin save path for qBittorrent category %r", category)

    scheduler = AsyncIOScheduler()

    async def organizer_tick() -> None:
        try:
            moved = await run_organizer_pass(settings, app.state.qbittorrent, app.state.jellyfin)
            if moved:
                logger.info("Organizer: moved %d request(s) to AVAILABLE", moved)
        except Exception:  # noqa: BLE001 - never let a bad tick kill the scheduler
            logger.exception("Organizer tick failed")

    async def arr_sync_tick() -> None:
        try:
            updated = await run_arr_sync_pass(app.state.radarr, app.state.sonarr, app.state.jellyfin)
            if updated:
                logger.info("Arr sync: marked %d request(s) as AVAILABLE", updated)
        except Exception:  # noqa: BLE001 - never let a bad tick kill the scheduler
            logger.exception("Arr sync tick failed")

    scheduler.add_job(organizer_tick, "interval", seconds=30, id="organizer")
    scheduler.add_job(arr_sync_tick, "interval", seconds=30, id="arr_sync")
    scheduler.start()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await app.state.qbittorrent.aclose()
        await app.state.jellyfin.aclose()
        await app.state.tmdb.aclose()
        await app.state.radarr.aclose()
        await app.state.sonarr.aclose()


class CatchAllMiddleware(BaseHTTPMiddleware):
    """
    Starlette special-cases an exception handler registered for the literal
    `Exception` class: it gets pulled out and attached to the *outermost*
    ServerErrorMiddleware rather than staying inside the normal middleware
    stack (see Starlette's Router.build_middleware_stack). That means a
    plain `@app.exception_handler(Exception)` runs *outside* CORSMiddleware,
    so its response has no Access-Control-Allow-Origin header, and the
    browser reports the failure to client code as an opaque "Failed to
    fetch" instead of a real 500 with a body.

    Catching the exception here instead works because middleware added via
    add_middleware() participates in the normal stack. Registered before
    CORSMiddleware below, it ends up as the *inner* layer (Starlette wraps
    middleware in reverse registration order), so by the time an exception
    is caught and turned into a response, that response still passes back
    out through CORSMiddleware normally and gets its headers attached.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:  # noqa: BLE001 - last-resort catch-all, logged and reported below
            logger.exception("Unhandled error in %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app = FastAPI(title="Vault API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CatchAllMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(discovery.router, prefix="/api")
app.include_router(requests.router, prefix="/api")
app.include_router(downloads.router, prefix="/api")
app.include_router(library.router, prefix="/api")
app.include_router(watch.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(system.router, prefix="/api")


@app.get("/api/health")
async def root_health() -> dict:
    return {"status": "ok"}
