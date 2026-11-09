# Jobscope: Data Science & IT Job Market

A compact English-language desktop dashboard for collecting, cleaning and
exploring 5,000+ Data Science and IT vacancies.

## Structure

- `backend/`: Flask API, SQLAlchemy models and vacancy collection pipelines.
- `frontend/`: HTML, CSS, JavaScript, local D3 libraries and Nginx configuration.
- `docker-compose.yml`: local PostgreSQL, backend and frontend services.

SQLAlchemy creates the application tables at backend startup; no separate SQL
bootstrap or PostgreSQL extensions are required.

## Quick Start

Docker with Compose is required. On first setup, create the local configuration:

```powershell
Copy-Item .env.example .env
```

Do not overwrite an existing `.env`. Set a unique `POSTGRES_PASSWORD` and a long,
random `ETL_API_TOKEN` in it. An empty token disables collection over HTTP but
does not prevent browsing existing vacancies. Never commit `.env` or put the
token in frontend files.

Start the services from the repository root:

```powershell
docker compose --env-file .env up -d --build
```

- Dashboard: `http://localhost:8080`
- API health: `http://localhost:5000/api/v1/health`

Click **Update dataset** and enter the token from `.env` to collect up to 5,000
cleaned vacancies per run. Collection can take several minutes. The browser
does not persist the token. Repeated runs update existing records rather than
duplicating source IDs; the total stored dataset can exceed the per-run target.

View logs or stop services:

```powershell
docker compose logs -f backend
docker compose down
```

PostgreSQL data is stored in the `pgdata` Docker volume. Rebuilding containers or
running `docker compose down` preserves it; `docker compose down -v` deletes it.
Changing `.env` credentials does not change users in an existing database volume.

## Dashboard

The Overview tab shows vacancy, company, title and location counts, demand by
role, skills, leading employers, a city word cloud and salary statistics. The
Vacancies tab supports search and pagination, with seven rows on shorter windows
and eight on taller windows. Role, skill, employer and city selections open matching
vacancies. Global filters select the role family and source.

The interface is English; original vacancy titles, cities and employer names are
preserved. This is a desktop dashboard without a mobile-specific layout.

The browser calls `/api/v1` on the same origin; Nginx forwards requests to Flask.
D3 and fonts are served locally, so browsing stored data does not require internet
access. Collecting new vacancies does. Third-party asset licenses are included in
`frontend/public/THIRD_PARTY_LICENSES.txt`.

## Collection And Cleaning

Sources are HeadHunter (API with an HTML fallback) and Arbeitnow. Availability,
rate limits and the number of relevant results can prevent a run from reaching
its target. The response reports source counts, inserted and updated rows, and
notes about incomplete collection.

The ETL pipeline normalizes text, labels Data Science and IT role families,
extracts skills, converts supported salary currencies using a dated rate snapshot and
deduplicates source IDs before PostgreSQL upserts. Role labels and chart categories
are defined in `backend/app/etl/roles.py`; they do not exclude vacancies by title
or skills and do not establish whether a vacancy is still open.

Availability is separate from role classification. HH API records explicitly
marked `archived` are skipped during collection. Collection does not automatically
recheck all stored vacancies. A separate availability audit checks existing source
pages; only confirmed closed records are removed after a backup. Blocked requests,
timeouts and ambiguous responses remain unverified, not closed. Audit reports and
backups are local, ignored data artifacts under `backend/data/`, not app services.

Salary statistics only cover vacancies with disclosed, convertible amounts.
The fixed rates are from the [Bank of Russia XML snapshot for 2026-11-07](https://www.cbr.ru/scripts/XML_daily.asp?date_req=07/11/2026).
The conversion is `amount * (RUB per currency unit) / (RUB per USD)`, accounting
for quoted nominals (100 KZT and 10 UAH). The snapshot date and salary coverage
are shown in the dashboard. These are not live or publication-date rates, and
differing pay periods still limit comparability. HH's legacy BYR label is
normalized to BYN at the source; other unsupported currency codes are not converted.

`TARGET_CLEANED_ROWS`, `MAX_SOURCE_PAGES` and `REQUEST_TIMEOUT_SECONDS` configure
collection. The dashboard requests 5,000 rows; direct API calls can request an
integer `target_rows` from 1 to 10,000. Only one collection run can write at a time.

## PostgreSQL And pgAdmin

For pgAdmin running on the host, register a connection with:

- Host: `127.0.0.1`
- Port: `5433`, or `POSTGRES_HOST_PORT` from `.env`
- Database: `POSTGRES_DB` from `.env`, default `jobsdb`
- User: `POSTGRES_USER` from `.env`, default `jobs`
- Password: `POSTGRES_PASSWORD` from `.env`

Docker services use `storage:5432` internally. A separate PostgreSQL installation
on host port `5432` is not the Docker database. Core tables (`jobs`, `skills`,
`job_skills`) are created by SQLAlchemy when the backend starts.

## API

The default prefix is `/api/v1`:

- `GET /health`
- `GET /jobs`
- `GET /metrics/overview`
- `GET /metrics/roles`
- `GET /metrics/skills`
- `GET /metrics/employers`
- `GET /metrics/locations`
- `GET /metrics/salary-bands`
- `POST /etl/run`

Metrics accept `role_family` and `source`. Jobs additionally accept `page`,
`page_size`, `search`, `skill`, `company`, `location`, `country` and `category`.
Collection requires `Authorization: Bearer <ETL_API_TOKEN>`
and a JSON object such as `{"target_rows": 5000}`.

## Local Backend Without Docker

Start PostgreSQL and configure `.env` for its host and port. For the Docker
database accessed from the host, use `POSTGRES_HOST=127.0.0.1` and
`POSTGRES_PORT=5433`. Then run with Python 3.12 or newer:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The development entry point runs without debug mode. Docker runs Gunicorn.
Published Compose ports bind to `127.0.0.1`; this configuration is for local use,
not a public deployment. Keep ETL authorization, input validation and security
headers enabled when adapting it for hosting.
