# Hit Counter

Hit Counter is a distributed two-repo application with a real-time unique daily hit counter and a lightweight chat identity flow.

The system is intentionally split into independent repositories:
- `server` owns API, WebSocket broadcast, and Redis-backed state.
- `web` owns UI, routing, and client interactions.

## Components (Repositories)

| Component | Repo | Responsibility | Tech |
|---|---|---|---|
| Server | [`wsc-server`](https://github.com/programmeralek/wsc-server) | FastAPI API + WebSocket endpoint, Redis persistence for unique daily hits and chat names | Python 3.12 / FastAPI / Redis |
| Web | [`wsc-web`](https://github.com/programmeralek/wsc-web) | React UI for counter and chat flow, client-side routing, real-time updates | React / Vite / PrimeReact / Nginx |

## Architecture Overview

### 1. Browser -> Web
- React SPA served by Vite (dev) or Nginx (container)
- Routes handled client-side (`/`, `/chat`)

### 2. Web -> Server
- REST for hit registration and chat name operations
- WebSocket for live counter updates

### 3. Server -> Redis
- Stores daily unique IP sets and daily counts
- Stores per-IP chat name with TTL retention

## Runtime Behavior

- Daily uniqueness is bucketed by `BUCKET_TZ` (default `America/New_York`).
- Count retention is controlled by `RETENTION_DAYS` (default `7`).
- New unique hits broadcast updated count to all active WebSocket clients.

## API Surface (Server)

- `GET /health`
- `GET /count`
- `POST /hit`
- `GET /chat/name`
- `POST /chat/name`
- `WS /ws`

## Local Setup Guide

### Prerequisites
- Docker + Docker Compose
- Optional for non-containerized dev:
- Python 3.12+
- Node.js 18+

### Option A: Run Full Stack with Docker Compose

```bash
docker compose up --build
```

Default local endpoints:
- Web: `http://localhost:3000`
- Server API: `http://localhost:8080`
- Redis: `localhost:6379`

### Option B: Run Repos Independently

Server (`./server`):
```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

Web (`./web`):
```bash
cd web
npm install
npm run dev
```

## Configuration (Server)

- `REDIS_URL` (default `redis://redis:6379/0`)
- `BUCKET_TZ` (default `America/New_York`)
- `RETENTION_DAYS` (default `7`)
- `ALLOW_DEV_IP_OVERRIDE` (default `false`)
- `DEV_CORS` (default `false`)

## Deployment

Cloud deployment notes are documented in:
- `docs/cloud-deployment.md`

## Repository Layout

```text
hit-counter/
  server/               # backend repo (wsc-server)
  web/                  # frontend repo (wsc-web)
  docs/
    cloud-deployment.md
  docker-compose.yml
```
