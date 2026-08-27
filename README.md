# Shipment Label Printing Portal

Internal portal for **Green Shadow Enterprises** to generate US domestic
shipment labels through the ePost Global (EPG) carrier API — one at a time
or in bulk from an Excel upload.

See `tasks/2026-08-11/shipment-label-portal.md` in the parent workspace for
the full requirements, decisions, and design record. A copy of the frozen
plan is also kept in `PLAN.md` in this repo.

## Stack

- `backend/` — FastAPI (Python), SQLAlchemy async + asyncpg, Postgres.
  Talks to the EPG API, converts labels to PDF, runs the bulk job queue.
- `web/` — Next.js 15 + TypeScript + Tailwind, a pure UI over the backend's
  REST API (no direct DB or EPG access from the web tier).
- `migrations/` — numbered plain SQL migrations, applied automatically on
  backend startup.

## Local development

Requires a local Postgres and Python 3.11+/Node 20+.

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+asyncpg://<user>@localhost:5432/shipmentlabel
export EPG_API_KEY_SANDBOX=<your sandbox key>
export ADMIN_PASSWORD=changeme
export SESSION_SECRET=<a long random string>
export LABEL_STORAGE_ROOT=/tmp/shipmentlabel_storage
uvicorn app.main:app --reload

# Backend tests
python -m pytest -q

# Frontend
cd web
npm install
BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

Open http://localhost:3000 and log in with `ADMIN_PASSWORD`.

## Deployment

Docker Compose, three services (`postgres`, `backend`, `web`) — see
`docker-compose.yml`. Copy `.env.example` to `.env` and fill in real values
first (`.env` is gitignored). `deploy.sh` builds and pushes versioned images
for `backend` and `web`.

```bash
cp .env.example .env   # fill in real values
docker compose up --build
```

The label storage directory is a named Docker volume (`label_storage`)
mounted into the backend container at `/data`. The portal's "save directory"
setting is a relative subpath under that root (e.g. `labels`), not an
absolute host path — see D11 in the plan for why.

## EPG integration notes

- Weight must be submitted in **ounces**, dimensions in **inches** —
  confirmed empirically against the EPG sandbox (the vendor docs never
  state a unit). The app always converts before calling EPG.
- The EPG API requires a populated `customs` object even for pure domestic
  shipments, despite the docs presenting it as an international/VAT-only
  concern. The backend sends a fixed, internal customs block automatically;
  there's no customs field anywhere in the UI or the Excel template.
- `tools/epg_probe.py` is the throwaway script used to discover the above —
  kept for future re-checks against a new EPG account or environment.
