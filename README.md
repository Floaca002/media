# Vault — self-hosted media command center

A single custom web app for searching, requesting, downloading, and
streaming movies/TV shows — backed by TMDB, qBittorrent, and Jellyfin, all
running headless behind one FastAPI orchestration layer and one Next.js UI.
You never open qBittorrent's or Jellyfin's own web interfaces.

See:
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture & data flow
- [`docs/API_SPEC.md`](docs/API_SPEC.md) — backend API endpoint spec
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — phased build plan

## Quickstart (docker-compose)

1. `cp backend/.env.example backend/.env` and fill in:
   - a TMDB v4 read access token
   - qBittorrent WebUI credentials (set once via a temporary port-forward)
   - a Jellyfin admin API key (Dashboard → API Keys)
2. `docker compose up -d --build`
3. Open `http://localhost:3000`, sign in with your Jellyfin account.

## Local development (without Docker)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit values
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Repository layout

```
backend/    FastAPI orchestration API (TMDB, qBittorrent, Jellyfin clients + auto-organizer)
frontend/   Next.js App Router UI (Discover, Downloads, Library/Watch)
docs/       Architecture, API spec, implementation plan
docker-compose.yml
```
