# Vault Backend — API Specification

Base URL: `/api`. All responses JSON. Auth via `Authorization: Bearer <jwt>`
issued by `POST /api/auth/login` (backend's own user table, separate from
Jellyfin's user table — the backend maps 1:1 to a Jellyfin user internally).

## Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | `{username, password}` → validates against Jellyfin (`AuthenticateByName`), creates/updates local user, returns `{access_token, user}` |
| POST | `/auth/logout` | Invalidates local session |
| GET  | `/auth/me` | Current user profile |

## Discovery (TMDB-backed)

| Method | Path | Query/Body | Description |
|---|---|---|---|
| GET | `/discover/trending` | `window=day\|week`, `media_type=all\|movie\|tv` | Trending carousel |
| GET | `/discover/popular` | `media_type=movie\|tv`, `page` | Popular grid |
| GET | `/discover/search` | `q`, `page` | Multi-search (movies+TV+people, people filtered out) |
| GET | `/discover/{media_type}/{tmdb_id}` | — | Full detail: overview, genres, rating, cast (top 12), trailer (YouTube key), similar titles |
| GET | `/discover/{media_type}/{tmdb_id}/availability` | — | Cross-references our DB: `NOT_REQUESTED \| SEARCHING \| DOWNLOADING \| AVAILABLE`, plus `jellyfin_item_id` if available |

## Requests / Downloads (qBittorrent-backed)

| Method | Path | Body | Description |
|---|---|---|---|
| POST | `/requests` | `{tmdb_id, media_type, magnet?: string, season?, episode?}` | Creates a `Request`. If `magnet` omitted, backend queries configured indexer (Prowlarr/Jackett) for best release; if provided (manual/paste flow) skips search. Adds to qBittorrent under category `vault-movies`/`vault-tv`. Returns `Request`. |
| GET | `/requests` | `status=` | List all requests (for a "My Requests" view) |
| DELETE | `/requests/{id}` | — | Cancels a pending/searching request |
| GET | `/downloads` | — | Live snapshot of all torrents in Vault-managed categories: `{hash, name, progress, dlspeed, upspeed, eta, state, size, request_id}` |
| WS | `/downloads/stream` | — | WebSocket pushing the same payload as above every 2s (avoids polling) |
| POST | `/downloads/{hash}/pause` | — | Pause torrent |
| POST | `/downloads/{hash}/resume` | — | Resume torrent |
| DELETE | `/downloads/{hash}` | `delete_files=true\|false` | Remove torrent (and optionally files) |
| POST | `/downloads/{hash}/priority` | `{files: [{index, priority}]}` | Per-file priority (skip trailers/samples in a multi-file torrent) |

## Library / Watch (Jellyfin-backed)

| Method | Path | Query/Body | Description |
|---|---|---|---|
| GET | `/library/views` | — | Jellyfin libraries (Movies, TV Shows, ...) |
| GET | `/library/items` | `parent_id`, `type=Movie\|Series`, `search`, `sort_by`, `page` | Browse/search *available* library (mirrors Jellyfin `/Items`) |
| GET | `/library/items/{id}` | — | Item detail (overview, cast, runtime, episodes for series) merged with TMDB art if richer |
| GET | `/library/continue-watching` | — | Jellyfin "Resume" items for current user |
| GET | `/library/next-up` | — | Jellyfin "Next Up" (series) for current user |
| GET | `/library/items/{id}/playback` | — | Resolves `PlaybackInfo`, returns `{hls_url, play_session_id, media_source_id, subtitle_tracks, start_position_ticks}` |
| POST | `/watch/progress` | `{item_id, play_session_id, position_ticks, is_paused, event: start\|progress\|stop}` | Forwarded to Jellyfin `/Sessions/Playing[/Progress\|/Stopped]` so resume + "continue watching" stay accurate |
| POST | `/watch/mark-watched` | `{item_id}` | Manually mark watched/unwatched (toggle) |

## System / Health

| Method | Path | Description |
|---|---|---|
| GET | `/system/health` | Aggregated up/down + auth status for TMDB, qBittorrent, Jellyfin |
| GET | `/system/settings` | Non-secret config (library paths, categories) — admin only |

## Error shape

```json
{ "error": { "code": "QBITTORRENT_UNAUTHORIZED", "message": "..." } }
```

Standard HTTP codes: `401` (no/invalid Vault JWT), `502` (upstream
qBittorrent/Jellyfin/TMDB unreachable or erroring — never leak upstream
stack traces), `404`, `409` (e.g. duplicate request for a title already
downloading).
