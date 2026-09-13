# Implementation Plan

## Phase 0 — Infrastructure (day 1)
1. Stand up headless services with docker-compose: `qbittorrent`
   (linuxserver/qbittorrent image), `jellyfin` (jellyfin/jellyfin), both on
   an internal-only docker network (`vault-internal`), **no published ports
   to the host** except what the backend's docker network needs.
2. In qBittorrent WebUI (one-time, via port-forward/SSH tunnel — never
   again after this): set a strong WebUI username/password, enable "Bypass
   authentication for clients on localhost" = **off**, note category
   auto-management paths.
3. In Jellyfin (one-time setup wizard): create the libraries `Movies` →
   `/data/media/movies`, `TV Shows` → `/data/media/tv`; create an admin API
   key (Dashboard → API Keys) for the backend's server-level calls.
4. Get a TMDB v4 Read Access Token (free, instant).
5. Populate `backend/.env` from `.env.example` with all of the above.

## Phase 1 — Backend skeleton (days 1–2)
Libraries: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic-settings`,
`sqlmodel`, `python-jose[cryptography]` (JWT), `passlib[bcrypt]`,
`apscheduler`, `websockets`.

1. `app/config.py` — `pydantic-settings` reading env for all three
   upstream services + JWT secret + media paths.
2. `app/services/{qbittorrent,jellyfin,tmdb}.py` — thin async clients (see
   code in this repo under `backend/app/services/`). Each owns its own
   auth/session lifecycle and retries.
3. `app/main.py` — FastAPI app, CORS locked to the frontend origin, wires
   routers, creates a shared `httpx.AsyncClient` per service in `lifespan`.
4. Health check router hitting all three services in parallel
   (`asyncio.gather`) — this is your fastest smoke test that config is right.

## Phase 2 — Discovery tab (day 2–3)
1. `routers/discovery.py` proxying TMDB search/trending/details.
2. Add a `Request` SQLModel + `availability()` helper so detail pages know
   whether to render "Watch Now" vs "Download".
3. Cache TMDB responses (in-memory `cachetools.TTLCache` for v1, Redis
   later) — TMDB rate limits and posters rarely change.
4. Frontend: `app/page.tsx` (trending hero + rails), `app/media/[type]/[id]/page.tsx`
   detail page with poster/backdrop, synopsis, cast rail, trailer modal
   (YouTube iframe), and the primary CTA button.

## Phase 3 — Downloads tab (day 3–4)
1. `services/qbittorrent.py`: login, `torrents_add(magnet, category)`,
   `torrents_info(category)`, `pause/resume/delete`.
2. `routers/requests.py` + `routers/downloads.py`.
3. For "search a magnet automatically" you need an indexer. Recommended:
   run **Prowlarr** headless too and call its `/api/v1/search` — out of
   scope for the code samples here, but `services/qbittorrent.py` accepts
   any magnet URI so v1 can ship with a "paste magnet link" field while
   Prowlarr integration is added in v1.1.
4. Frontend: `app/downloads/page.tsx` polling `/api/downloads` every 2–3s
   (swap to the WebSocket endpoint once stable) rendering progress bars,
   speed/ETA, pause/resume/delete buttons.

## Phase 4 — Auto-organizer (day 4–5)
1. `services/organizer.py` run by APScheduler every 30s:
   - Ask qBittorrent for torrents in category `vault-movies`/`vault-tv`
     with `progress == 1` and not yet marked organized (track
     `organized_hashes` in DB).
   - Move/hardlink content_path into
     `/data/media/movies/<Title> (<Year>)/<Title> (<Year>).ext` or
     `/data/media/tv/<Series>/Season 0X/<Series> - sXXeYY.ext` — use
     `guessit` (pip) to parse release names into title/year/season/episode
     reliably instead of hand-rolled regex.
   - Call Jellyfin `POST /Library/Refresh` (or the more targeted
     `POST /Items/{parentId}/Refresh`).
   - Update the matching `Request.status = AVAILABLE` and store the
     resolved `jellyfin_item_id` once a subsequent library scan surfaces it
     (match by matching TMDB id via Jellyfin's own TMDB provider field on
     the item, which Jellyfin populates automatically when its metadata
     plugin runs).
2. Prefer **hardlink + keep seeding** over move, so the torrent keeps
   seeding from `/data/downloads` while Jellyfin serves the hardlinked copy
   from `/data/media` (same filesystem/volume required).

## Phase 5 — Watch tab (day 5–6)
1. `services/jellyfin.py`: `authenticate_by_name`, `get_user_views`,
   `get_items`, `get_playback_info`, `build_hls_url`, `report_playback_*`.
2. `routers/library.py`, `routers/watch.py`.
3. Frontend: `components/VideoPlayer.tsx` using `hls.js` (Safari gets
   native HLS via `<video>` directly, everything else via hls.js),
   `app/watch/[id]/page.tsx` full-screen player page, progress reporting
   on `timeupdate` (throttled to ~10s) + `beforeunload`.
4. `app/library/page.tsx`: grid fed by `/api/library/items`, plus a
   "Continue Watching" rail from `/api/library/continue-watching`.

## Phase 6 — Polish & hardening (day 6+)
1. JWT auth end-to-end (currently backend maps Vault JWT → Jellyfin user
   token stored server-side, never sent to the browser in full).
2. Rate limiting on `/discover/search` (TMDB free tier: 50 req/s soft cap,
   fine for single-tenant, but debounce frontend search input regardless).
3. Structured logging + Sentry (or similar) around the three upstream
   clients — these are your most likely failure points.
4. `docker-compose.yml` finalization + Caddy reverse proxy with automatic
   TLS for the two public services (frontend, backend only).
5. Optional: replace manual magnet paste with full Prowlarr/Sonarr/Radarr
   automation — at that point `services/qbittorrent.py` can even be
   dropped in favor of Sonarr/Radarr's own download-client management,
   with our backend calling Sonarr/Radarr's `/api/v3/` instead. The router
   surface (`/api/requests`, `/api/downloads`) stays identical to the
   frontend either way — that's the point of the orchestration layer.

## Suggested repo layout (implemented in this repo)

```
backend/
  app/
    config.py
    main.py
    schemas.py
    db.py
    services/
      qbittorrent.py
      jellyfin.py
      tmdb.py
      organizer.py
    routers/
      auth.py
      discovery.py
      requests.py
      downloads.py
      library.py
      watch.py
      system.py
  requirements.txt
  Dockerfile
frontend/
  app/
    layout.tsx
    page.tsx                      # Discover
    media/[type]/[id]/page.tsx    # Detail
    downloads/page.tsx
    library/page.tsx
    watch/[id]/page.tsx
  components/
  lib/api.ts
  Dockerfile
docker-compose.yml
```
