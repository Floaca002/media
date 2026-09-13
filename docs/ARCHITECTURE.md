# Architecture & Data Flow

## 1. Goal

A single custom web app ("Vault") that is the *only* UI a user ever opens.
Jellyfin, qBittorrent (and optionally Sonarr/Radarr) run headless — their
own web UIs are never exposed to the user. Our backend is the sole client
of their APIs and re-exposes a small, purpose-built REST API to our frontend.

```
┌───────────────────────────────────────────────────────────────────────┐
│                              Browser (User)                           │
│   Next.js App Router SPA — Discover / Downloads / Library / Watch     │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │ HTTPS (JSON + HLS)
┌───────────────────────────────▼───────────────────────────────────────┐
│                     Vault Backend (FastAPI, Python)                   │
│  ┌───────────────┐ ┌────────────────┐ ┌───────────────────────────┐   │
│  │ discovery.py   │ │ downloads.py   │ │ library.py / watch.py     │   │
│  │ (TMDB proxy +  │ │ (qBittorrent   │ │ (Jellyfin proxy + HLS     │   │
│  │  request logic)│ │  orchestration)│ │  URL signing + progress)  │   │
│  └───────┬────────┘ └───────┬────────┘ └────────────┬──────────────┘  │
│          │                  │                        │                │
│  ┌───────▼────────┐ ┌───────▼────────┐ ┌─────────────▼─────────────┐  │
│  │ TMDBClient     │ │ QBittorrentClient│ │ JellyfinClient           │  │
│  │ (httpx, cached)│ │ (cookie session) │ │ (API key + user token)   │  │
│  └───────┬────────┘ └───────┬────────┘ └─────────────┬─────────────┘  │
│          │                  │                        │                │
│  ┌───────▼──────────────────▼────────────────────────▼─────────────┐  │
│  │  Postgres/SQLite: requests, users, watch-progress cache          │  │
│  │  Redis (optional): TMDB response cache, job queue for organizer  │  │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │ Organizer worker (APScheduler / Celery beat)                   │   │
│  │  polls qBittorrent for 100% + "seeding" torrents → hardlinks/  │   │
│  │  moves files into Jellyfin library tree → triggers Jellyfin    │   │
│  │  library scan → marks internal Request as AVAILABLE            │   │
│  └───────────────────────────────────────────────────────────────┘   │
└───────────┬───────────────────────┬───────────────────────┬──────────┘
            │ REST (Web API)        │ REST (Web API)         │ REST API
            ▼                       ▼                        ▼
   ┌─────────────────┐    ┌──────────────────┐     ┌─────────────────────┐
   │  TMDB (SaaS)     │    │  qBittorrent      │     │  Jellyfin            │
   │  metadata only   │    │  (headless,       │     │  (headless, transcode│
   │                  │    │   WebUI off/       │     │   + library, HLS)    │
   │                  │    │   firewalled)      │     │                      │
   └─────────────────┘    └──────────────────┘     └─────────────────────┘
                                    │                          ▲
                                    │ downloaded files          │ file system
                                    ▼                          │
                           /data/downloads/complete ──organizer──▶ /data/media/{movies,tv}
```

## 2. Why a backend orchestration layer (not calling qBittorrent/Jellyfin
   directly from the browser)

- **Single origin of trust.** qBittorrent's WebUI auth and Jellyfin's API
  key are secrets; they must never reach the browser. The backend holds
  them and issues its own session (JWT/cookie) to the frontend.
- **CORS/mixed content.** qBittorrent and Jellyfin usually live on the LAN
  (`10.0.0.x:8080`, `:8096`) without valid public TLS. The backend is the
  only thing that needs LAN + service access; the frontend only ever talks
  to one HTTPS origin (the backend), which can sit behind a reverse proxy
  with a real certificate.
- **Aggregation.** "Download this movie" is really: TMDB lookup → search
  indexer/Jarr for a release → add magnet to qBittorrent → create an
  internal `Request` row → (later) organizer moves the file → Jellyfin
  scan. No single upstream API does this; it only exists in our layer.
- **HLS URL signing/short-lived tokens.** We don't want to hand the
  browser a permanent Jellyfin API key embedded in a video `src`. The
  backend mints a short-lived Jellyfin *user* access token / play session
  and returns a stream URL scoped to that session.

## 3. Components

| Component | Tech | Responsibility |
|---|---|---|
| Frontend | Next.js 14 (App Router), Tailwind, Lucide, hls.js | All UI. Talks only to Vault backend. |
| Backend API | FastAPI (Python 3.12), httpx (async), Pydantic v2 | Orchestration, auth, aggregation, caching |
| DB | Postgres (SQLite fine for single-user) via SQLModel/SQLAlchemy | Users, Requests, watch-progress cache, settings |
| Cache/Queue | Redis (optional but recommended) | TMDB response cache, background job broker |
| Background worker | APScheduler in-process (simple) or Celery + Redis (scalable) | Poll downloads → organize → trigger Jellyfin scan |
| qBittorrent | qBittorrent-nox, WebUI **bound to localhost/internal docker network only** | Torrent engine |
| Jellyfin | Jellyfin server, **not exposed publicly**, only backend + internal network reach it | Transcoding, library, HLS |
| TMDB | External SaaS | Metadata, posters, trailers |
| Reverse proxy | Caddy/Traefik/Nginx | TLS termination for the frontend + backend only |

## 4. Data flow: "Download / Request" click

1. User clicks **Download** on a TMDB title in Discover.
2. Frontend → `POST /api/requests` `{ tmdb_id, media_type }`.
3. Backend looks up/records the `Request` (status=`SEARCHING`), calls an
   indexer/prowlarr (or accepts a pasted magnet in v1) to resolve a magnet
   link, then `QBittorrentClient.add_magnet(magnet, category="vault")`.
4. Backend stores `torrent_hash` on the `Request`, sets status=`DOWNLOADING`.
5. Frontend polls (or SSE/WebSocket) `GET /api/downloads` for progress.
6. Organizer worker notices the torrent in category `vault` at
   `progress==1.0` and `state in (uploading, stalledUP)`, moves/hardlinks
   the file into `/data/media/{movies|tv}/<Title>/...` following Jellyfin's
   naming convention, calls `Jellyfin: POST /Library/Refresh`, and sets the
   `Request` status to `AVAILABLE`.
7. Discover/Library UI now shows the title as "Watch Now" instead of
   "Download".

## 5. Data flow: "Watch" click

1. Frontend → `GET /api/library/items/{jellyfin_item_id}/playback`.
2. Backend calls Jellyfin `POST /Items/{id}/PlaybackInfo` with the user's
   Jellyfin access token to get `MediaSourceId` + supported streaming
   options, then builds the HLS master playlist URL
   (`/Videos/{id}/master.m3u8?...`) with a `PlaySessionId` the backend
   generates.
3. Backend returns `{ hls_url, play_session_id, item }` to the frontend
   (the `api_key` query param is either the backend's own short-lived
   proxy token — see §6 — or, in the simple single-user deployment, the
   user's Jellyfin token, since it never touches the browser's storage in
   plaintext beyond that session).
4. `<VideoPlayer>` (hls.js) loads the URL, plays it, and periodically
   `POST`s position back to `/api/watch/progress`, which the backend
   forwards to Jellyfin (`/Sessions/Playing/Progress`) so resume points and
   "Continue Watching" stay in sync with Jellyfin's own tracking — even
   though the user never opens Jellyfin's UI.

## 6. Recommended hardening: proxy the media bytes too

Simplest v1: return the real Jellyfin HLS URL (reachable because the
frontend's `<video>`/hls.js requests go straight from the *browser* to
Jellyfin on the LAN). This requires the browser to reach Jellyfin's host —
acceptable on a home LAN/VPN (Tailscale), but it does mean the browser
knows Jellyfin's address.

Production-hardened alternative: the **backend reverse-proxies** the HLS
segments (`/api/watch/stream/{item_id}/{segment}` → forwards to Jellyfin
with the server-held token). This keeps Jellyfin fully unreachable from
outside the docker network, at the cost of extra backend bandwidth. This
doc's code samples implement the direct-URL approach for simplicity but
factor the client so switching to a proxy is a router-only change.

## 7. Deployment topology (docker-compose)

```
internet ──TLS── [reverse proxy: Caddy] ──┬── vault-frontend:3000
                                            └── vault-backend:8000
                                                     │
                                    (internal docker network only)
                                                     │
                              ┌──────────────────────┼───────────────────┐
                              ▼                       ▼                   ▼
                        qbittorrent:8080        jellyfin:8096        redis:6379
                              │                       ▲
                     /data/downloads ───organizer───▶ /data/media
```
