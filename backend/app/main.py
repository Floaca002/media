from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.routers import auth, discovery, downloads, library, requests, system, watch
from app.services.jellyfin import JellyfinClient
from app.services.organizer import run_organizer_pass
from app.services.qbittorrent import QBittorrentClient
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

    scheduler = AsyncIOScheduler()

    async def organizer_tick() -> None:
        try:
            moved = await run_organizer_pass(settings, app.state.qbittorrent, app.state.jellyfin)
            if moved:
                logger.info("Organizer: moved %d request(s) to AVAILABLE", moved)
        except Exception:  # noqa: BLE001 - never let a bad tick kill the scheduler
            logger.exception("Organizer tick failed")

    scheduler.add_job(organizer_tick, "interval", seconds=30, id="organizer")
    scheduler.start()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await app.state.qbittorrent.aclose()
        await app.state.jellyfin.aclose()
        await app.state.tmdb.aclose()


app = FastAPI(title="Vault API", version="1.0.0", lifespan=lifespan)

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
app.include_router(system.router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Without this, an unhandled exception is caught by Starlette's outermost
    ServerErrorMiddleware, which sits *outside* CORSMiddleware and returns a
    plain response with no Access-Control-Allow-Origin header. The browser
    then reports the failure to the frontend as an opaque network error
    ("Failed to fetch") instead of surfacing the actual 500 response, making
    real bugs indistinguishable from the backend being unreachable. Handling
    it here keeps us inside the normal middleware stack so CORS headers are
    still attached.
    """
    logger.exception("Unhandled error in %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
async def root_health() -> dict:
    return {"status": "ok"}
