# Job Market Analytics (Data Science + IT)

Microservice-style project to scrape, clean, store, and visualize **5000+ job postings** in Data Science and IT.

## Stack

- `storage/`: PostgreSQL 16
- `backend/`: Flask + SQLAlchemy + ETL scrapers
- `frontend/`: D3.js dashboard
- `infra/`: deployment configuration (`render.yaml`)
- `scripts/`: local helper scripts

## Why an extra directory?

You asked for `frontend/backend/storage` as the main structure. I also added:

- `infra/` for deployment manifests
- `scripts/` for local workflow commands

These keep deployment and operations separate from app code.

## Features

- Multi-source scraping:
  - `hh.ru` vacancies API (Russian market)
  - `Arbeitnow` API (global/remote jobs)
- Cleaning and normalization:
  - role classification (`data_science` / `it`)
  - deduplication by source/external ID
  - skill extraction (Python, SQL, Docker, etc.)
  - salary normalization with USD conversion when possible
- PostgreSQL storage with idempotent upserts
- REST API for jobs and analytics metrics
- D3 dashboard with:
  - KPIs
  - top skills
  - salary bands
  - location bubbles
  - timeline
  - latest jobs table

## Repo Layout

```text
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   └── etl/
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── public/
│   │   ├── css/
│   │   ├── js/
│   │   └── index.html
│   └── Dockerfile
├── storage/
│   └── init/
├── infra/
│   └── render.yaml
├── scripts/
├── docker-compose.yml
└── .env.example
```

## Quick Start (Docker)

1. Copy env file:

```powershell
Copy-Item .env.example .env
```

2. Run services:

Set a unique `POSTGRES_PASSWORD` in `.env`, then generate a private ingestion token:

```powershell
py scripts/init_etl_token.py
```

```powershell
docker compose --env-file .env up --build
```

3. Open:

- Dashboard: `http://localhost:8080`
- API health: `http://localhost:5000/api/v1/health`

4. Trigger ETL for 5000 cleaned rows:

```powershell
./scripts/run_etl.ps1 -TargetRows 5000
```

or from the dashboard button `Run ETL (5000)`. Both ask for `ETL_API_TOKEN`
from your local `.env`; the dashboard does not persist it. Without a configured
token, HTTP ingestion is disabled. Never put the token in frontend config or Git.

## pgAdmin Connection (Docker Postgres)

Use these settings in pgAdmin when running via Docker Compose:

- Host: `localhost`
- Port: `5433` (host mapped port, configurable via `POSTGRES_HOST_PORT`)
- Database: `jobsdb`
- User: from `.env` `POSTGRES_USER`
- Password: from `.env` `POSTGRES_PASSWORD`

If you also run a local PostgreSQL service on `5432`, keep Docker on `5433` to avoid connecting to the wrong database.

## API Endpoints

- `GET /api/v1/health`
- `POST /api/v1/etl/run`
- `GET /api/v1/jobs?page=1&page_size=25&role_family=it&source=hh`
- `GET /api/v1/metrics/overview`
- `GET /api/v1/metrics/skills?limit=12`
- `GET /api/v1/metrics/salary-bands`
- `GET /api/v1/metrics/locations?limit=16`
- `GET /api/v1/metrics/timeline`

`POST /api/v1/etl/run` requires `Authorization: Bearer <ETL_API_TOKEN>` and
an integer `target_rows` between 1 and 10000. Only one ingestion can run at a
time across backend workers. Read-only analytics remain public.

Local Compose ports bind to `127.0.0.1`: PostgreSQL `5433`, API `5000`,
dashboard `8080`. Run `docker compose up -d --build` to apply changed bindings
to existing containers. This preserves the PostgreSQL volume.

## Local Backend (without Docker)

1. Start PostgreSQL (locally or container)
2. Create and activate venv
3. Install dependencies:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. Run Flask:

```powershell
python run.py
```

## Deploy (Render)

`infra/render.yaml` is included for blueprint deployment (backend + frontend + postgres).

1. Push this repository to GitHub.
2. In Render, create a new Blueprint and point it to the repo.
3. Use `infra/render.yaml`.
4. After deploy, update `frontend/public/js/config.js` deployed backend URL if your service names differ from the defaults.

## Notes About 5000 Rows

- The ETL target is controlled by `TARGET_CLEANED_ROWS` and `/etl/run` `target_rows`.
- Real row count depends on source API availability/rate limits and keyword coverage.
- Upserts are idempotent, so repeated runs enrich/update instead of duplicating rows.
- ETL response includes `source_rows` and `notes` so you can quickly see if one source under-delivered.
- Some environments may receive `403/400` from `hh.ru`; in that case, global ingestion from Arbeitnow still works and is visible in `source_rows`.

## Testing

```powershell
cd backend
pytest
```

Security regression tests cover ingestion authentication, input limits, CORS,
error redaction, concurrency protection, and malicious source URLs. Frontend
XSS regression tests use Node's built-in runner:

```powershell
node --test frontend/tests/security.test.cjs
py scripts/check_secrets.py
```

See `SECURITY.md` for security settings, audit scope, and remaining operational steps.
